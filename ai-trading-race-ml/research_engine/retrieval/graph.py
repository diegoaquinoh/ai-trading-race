"""Bounded graph-assisted candidate expansion ``graph_rag_v1`` (spec 12.4).

1. Seeds (<= 8): entities matched in the question through time-filtered
   aliases and explicit identifiers (relevance 1.0), then policy events of the
   top eligible hybrid candidates (relevance <= 0.5, from frozen fused scores).
2. Breadth-first traversal over approved relationship steps only
   (``ontology.TRAVERSAL_STEPS``), semantic depth <= 2, fanout <= 8 per node,
   <= 40 visited assertions overall, and only assertions/nodes available at the
   cutoff. Neighbours are ordered by a stable key (relation round-robin, passage
   relevance on the eligible snapshot, recency, id) - never by global degree.
3. Reached document versions are materialized into at most 2 supporting chunks
   via HAS_CHUNK without opening further traversal.
4. Co-support: chunks linked by approved MENTIONS_TOPIC / REFERS_TO_SERIES to a
   topic or series seed matched in the question are materialized first, and the
   linking assertions are recorded as support (a typed-relationship signal; the
   lookup is bounded by the seed count and opens no further traversal).
5. Graph score = seed relevance x 1/path length x status weight x
   (0.5 + 0.5 x passage relevance) x (1 + other question seeds co-supporting the
   chunk); the graph list is fused with the hybrid lists.

Any graph-store failure raises ``GraphRetrievalUnavailable``; there is no
fallback to plain RAG under the graph mode label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from research_engine.contracts.evidence import (
    AssertionStatus,
    AvailabilityCheck,
    Exclusion,
    GraphNode,
    GraphSeed,
    GraphTrace,
    NodeType,
    RelationshipAssertion,
    RelationType,
    StructuredFact,
    SupportSpan,
    score_decimal,
)
from research_engine.knowledge.graph_store import Edge, GraphRetrievalUnavailable, GraphStore
from research_engine.knowledge.ontology import RELATION_ORDER, TRAVERSAL_STEPS, Direction
from research_engine.knowledge.resolver import Resolution

from .index import EvidenceIndex
from .snapshot import EligibleSnapshot

GRAPH_EXPANSION_VERSION = "graph-expand-v1"
SEED_TYPES = {
    NodeType.POLICY_EVENT,
    NodeType.MACRO_TOPIC,
    NodeType.MACRO_SERIES,
    NodeType.MACRO_RELEASE,
    NodeType.DOCUMENT_VERSION,
}
STATUS_WEIGHT = {AssertionStatus.APPROVED: 1.0}


@dataclass
class GraphHit:
    chunk_id: str
    seed_id: str
    path: list[RelationshipAssertion]
    materialization: Optional[RelationshipAssertion]
    score: float
    co_support: list[RelationshipAssertion] = field(default_factory=list)


@dataclass
class GraphResult:
    hits: dict[str, GraphHit] = field(default_factory=dict)
    exclusions: list[Exclusion] = field(default_factory=list)
    facts: list[StructuredFact] = field(default_factory=list)
    seeds: list[GraphSeed] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    limits_hit: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)
    backend: str = ""
    build_id: Optional[str] = None

    @property
    def trace(self) -> GraphTrace:
        return GraphTrace(
            seeds=self.seeds,
            visited_assertion_ids=self.visited,
            limits_hit=self.limits_hit,
            review_queue=self.review,
            graph_backend=self.backend,
            graph_build_id=self.build_id,
        )


def _seeds(
    index: EvidenceIndex,
    graph: GraphStore,
    resolution: Resolution,
    explicit: list[str],
    snapshot: EligibleSnapshot,
    hybrid_order: list[str],
    fused: dict[str, float],
    cutoff: datetime,
    max_seeds: int,
    result: GraphResult,
) -> list[GraphSeed]:
    build_id = index.build_id
    seeds: list[GraphSeed] = []
    seen: set[str] = set()
    limit_hit = False

    def add(
        node_id: str, origin: str, relevance: float, text: Optional[str], alias_id: Optional[str]
    ) -> None:
        nonlocal limit_hit
        if node_id in seen:
            return
        node = graph.node(build_id, node_id)
        if node is None or node.node_type not in SEED_TYPES:
            result.exclusions.append(
                Exclusion(record_id=node_id, record_type="seed", reason="not_a_graph_seed")
            )
            return
        if node.available_at > cutoff:
            result.exclusions.append(
                Exclusion(
                    record_id=node_id, record_type="seed", reason="seed_not_available_at_cutoff"
                )
            )
            return
        if node.node_type == NodeType.DOCUMENT_VERSION and node_id not in snapshot.version_ids:
            result.exclusions.append(
                Exclusion(record_id=node_id, record_type="seed", reason="seed_not_in_snapshot")
            )
            return
        if len(seeds) >= max_seeds:
            limit_hit = True
            return
        seen.add(node_id)
        seeds.append(
            GraphSeed(
                seed_id=node_id,
                seed_type=node.node_type,
                origin=origin,  # type: ignore[arg-type]
                matched_text=text,
                alias_id=alias_id,
                relevance=score_decimal(relevance),
            )
        )

    for match in resolution.matches:
        add(match.entity_id, "question_alias", 1.0, match.surface, match.alias_id)
    for identifier in explicit:
        target = identifier
        if identifier not in index.versions and identifier not in index.entities:
            # document id -> its eligible version in the snapshot
            target = next(
                (v for v in snapshot.version_ids if index.versions[v].document_id == identifier),
                identifier,
            )
        add(target, "explicit_identifier", 1.0, identifier, None)
    top = max((fused[c] for c in hybrid_order), default=0.0) or 1.0
    for chunk_id in hybrid_order:
        version = index.versions[index.chunks[chunk_id].version_id]
        if version.event_id:
            add(version.event_id, "candidate_metadata", 0.5 * fused[chunk_id] / top, chunk_id, None)
    if limit_hit:
        result.limits_hit.append(f"max_seeds:{max_seeds}")
    return seeds


def _relevance_of(node: GraphNode, index: EvidenceIndex, relevance: dict[str, float]) -> float:
    if node.node_type == NodeType.CHUNK:
        return relevance.get(node.node_id, 0.0)
    if node.node_type == NodeType.DOCUMENT_VERSION:
        return max(
            (relevance.get(c, 0.0) for c in index.chunks_by_version.get(node.node_id, [])),
            default=0.0,
        )
    return 0.0


def _ordered(edges: list[Edge], index: EvidenceIndex, relevance: dict[str, float]) -> list[Edge]:
    """Stable neighbour order: round-robin over relation steps, then relevance/recency/id."""
    by_relation: dict[tuple[RelationType, Direction], list[Edge]] = {}
    for edge in edges:
        by_relation.setdefault((edge.assertion.relation, edge.direction), []).append(edge)
    for key in by_relation:
        by_relation[key].sort(
            key=lambda e: (
                -_relevance_of(e.neighbor, index, relevance),
                -e.neighbor.available_at.timestamp(),
                e.neighbor.node_id,
                e.assertion.assertion_id,
            )
        )
    groups = [
        by_relation[k]
        for k in sorted(by_relation, key=lambda k: (RELATION_ORDER[k[0]], k[1].value))
    ]
    out: list[Edge] = []
    for position in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if position < len(group):
                out.append(group[position])
    return out


def expand(
    index: EvidenceIndex,
    snapshot: EligibleSnapshot,
    resolution: Resolution,
    explicit: list[str],
    hybrid_order: list[str],
    fused: dict[str, float],
    relevance: dict[str, float],
    cutoff: datetime,
    *,
    max_seeds: int,
    max_depth: int,
    max_fanout: int,
    max_visited: int,
    chunks_per_document: int,
) -> GraphResult:
    graph = index.require_graph()
    result = GraphResult()
    result.backend = graph.backend_name
    result.build_id = index.build_id
    result.review = list(resolution.review)
    build_id = index.build_id
    eligible_chunks = set(snapshot.chunk_ids)
    eligible_versions = set(snapshot.version_ids)
    try:
        seeds = _seeds(
            index,
            graph,
            resolution,
            explicit,
            snapshot,
            hybrid_order,
            fused,
            cutoff,
            max_seeds,
            result,
        )
        result.seeds = seeds
        seed_relevance = {s.seed_id: float(s.relevance) for s in seeds}
        co_index: dict[str, list[RelationshipAssertion]] = {}
        for seed in seeds:
            if seed.origin == "candidate_metadata":
                continue
            if seed.seed_type == NodeType.MACRO_TOPIC:
                relation = RelationType.MENTIONS_TOPIC
            elif seed.seed_type == NodeType.MACRO_SERIES:
                relation = RelationType.REFERS_TO_SERIES
            else:
                continue
            for edge in graph.edges(build_id, seed.seed_id, [(relation, Direction.IN)], cutoff):
                if edge.neighbor.node_id in eligible_chunks:
                    co_index.setdefault(edge.neighbor.node_id, []).append(edge.assertion)
        reached_docs: dict[str, tuple[str, list[RelationshipAssertion]]] = {}
        visited: list[str] = []
        visited_set: set[str] = set()
        visited_nodes = {s.seed_id for s in seeds}
        frontier: list[tuple[str, str, list[RelationshipAssertion]]] = [
            (s.seed_id, s.seed_id, []) for s in seeds
        ]
        for seed in seeds:
            if seed.seed_type == NodeType.DOCUMENT_VERSION:
                reached_docs.setdefault(seed.seed_id, (seed.seed_id, []))
        stop = False
        for _depth in range(1, max_depth + 1):
            next_frontier: list[tuple[str, str, list[RelationshipAssertion]]] = []
            for seed_id, node_id, path in frontier:
                node = graph.node(build_id, node_id)
                steps = TRAVERSAL_STEPS.get(node.node_type, ()) if node else ()
                if not steps:
                    continue
                edges = []
                for edge in graph.edges(build_id, node_id, steps, cutoff):
                    neighbor = edge.neighbor
                    if (
                        neighbor.node_type == NodeType.CHUNK
                        and neighbor.node_id not in eligible_chunks
                    ):
                        continue
                    if (
                        neighbor.node_type == NodeType.DOCUMENT_VERSION
                        and neighbor.node_id not in eligible_versions
                    ):
                        continue
                    edges.append(edge)
                ordered = _ordered(edges, index, relevance)
                if len(ordered) > max_fanout:
                    result.limits_hit.append(f"fanout:{node_id}:{len(ordered)}>{max_fanout}")
                for edge in ordered[:max_fanout]:
                    if edge.assertion.assertion_id in visited_set:
                        continue  # each assertion is visited (and counted) once
                    if len(visited) >= max_visited:
                        result.limits_hit.append(f"max_visited_assertions:{max_visited}")
                        stop = True
                        break
                    assertion = edge.assertion
                    visited.append(assertion.assertion_id)
                    visited_set.add(assertion.assertion_id)
                    new_path = path + [assertion]
                    neighbor = edge.neighbor
                    if assertion.relation == RelationType.RELEASE_OF:
                        subject = index.entities.get(assertion.subject_id)
                        obj = index.entities.get(assertion.object_id)
                        result.facts.append(
                            StructuredFact(
                                assertion_id=assertion.assertion_id,
                                relation=assertion.relation,
                                subject_id=assertion.subject_id,
                                subject_label=(
                                    subject.canonical_name if subject else assertion.subject_id
                                ),
                                object_id=assertion.object_id,
                                object_label=obj.canonical_name if obj else assertion.object_id,
                                available_at=assertion.available_at,
                                support=assertion.support,
                            )
                        )
                    if neighbor.node_type == NodeType.CHUNK:
                        _record_hit(
                            result,
                            neighbor.node_id,
                            seed_id,
                            new_path,
                            None,
                            seed_relevance,
                            relevance,
                            co_index,
                        )
                    elif neighbor.node_type == NodeType.DOCUMENT_VERSION:
                        reached_docs.setdefault(neighbor.node_id, (seed_id, new_path))
                    if neighbor.node_id not in visited_nodes:
                        visited_nodes.add(neighbor.node_id)
                        next_frontier.append((seed_id, neighbor.node_id, new_path))
                if stop:
                    break
            if stop:
                break
            frontier = next_frontier
        result.visited = visited
        # Materialize supporting chunks of reached versions (no further traversal).
        for version_id, (seed_id, path) in reached_docs.items():
            edges = graph.edges(
                build_id, version_id, [(RelationType.HAS_CHUNK, Direction.OUT)], cutoff
            )
            edges = [e for e in edges if e.neighbor.node_id in eligible_chunks]
            edges.sort(
                key=lambda e: (
                    -len(co_index.get(e.neighbor.node_id, [])),
                    -relevance.get(e.neighbor.node_id, 0.0),
                    e.neighbor.node_id,
                )
            )
            for edge in edges[:chunks_per_document]:
                _record_hit(
                    result,
                    edge.neighbor.node_id,
                    seed_id,
                    path,
                    edge.assertion,
                    seed_relevance,
                    relevance,
                    co_index,
                )
    except GraphRetrievalUnavailable:
        raise
    except Exception as exc:
        raise GraphRetrievalUnavailable(f"graph traversal failed: {exc}") from exc
    return result


def _record_hit(
    result: GraphResult,
    chunk_id: str,
    seed_id: str,
    path: list[RelationshipAssertion],
    materialization: Optional[RelationshipAssertion],
    seed_relevance: dict[str, float],
    relevance: dict[str, float],
    co_index: dict[str, list[RelationshipAssertion]],
) -> None:
    path_length = max(1, len(path))
    status = min((STATUS_WEIGHT.get(a.validation_status, 0.0) for a in path), default=1.0)
    path_ids = {a.assertion_id for a in path}
    co = [
        a
        for a in co_index.get(chunk_id, [])
        if a.assertion_id not in path_ids and a.object_id != seed_id
    ]
    co_seeds = len({a.object_id for a in co})
    score = (
        seed_relevance.get(seed_id, 0.0)
        * (1.0 / path_length)
        * status
        * (0.5 + 0.5 * relevance.get(chunk_id, 0.0))
        * (1 + co_seeds)
    )
    existing = result.hits.get(chunk_id)
    if existing is None or score > existing.score:
        result.hits[chunk_id] = GraphHit(chunk_id, seed_id, list(path), materialization, score, co)


def hit_provenance(
    hit: GraphHit, index: EvidenceIndex, cutoff: datetime
) -> tuple[list[SupportSpan], list[AvailabilityCheck], list[str]]:
    assertions = (
        list(hit.path)
        + ([hit.materialization] if hit.materialization else [])
        + list(hit.co_support)
    )
    spans: list[SupportSpan] = []
    checks: list[AvailabilityCheck] = []
    for assertion in assertions:
        spans.extend(assertion.support)
        checks.append(
            AvailabilityCheck(
                record_id=assertion.assertion_id,
                record_type=f"assertion:{assertion.relation.value}",
                available_at=assertion.available_at,
                cutoff=cutoff,
                passed=assertion.available_at <= cutoff,
            )
        )
    seed = index.entities.get(hit.seed_id) or index.versions.get(hit.seed_id)
    if seed is not None:
        checks.append(
            AvailabilityCheck(
                record_id=hit.seed_id,
                record_type="seed",
                available_at=seed.available_at,
                cutoff=cutoff,
                passed=seed.available_at <= cutoff,
            )
        )
    return spans, checks, [a.assertion_id for a in assertions]
