"""Graph projection and graph-store backends (spec 5.4, 11.3, 12, 15.4).

* ``GraphProjection`` is computed deterministically from canonical research
  records; the graph is a derived, rebuildable index.
* Builds are labelled by build id. A build is invisible to retrieval until it
  is validated and published (READY). Reads against a non-READY or missing build
  raise ``GraphRetrievalUnavailable``; callers must not fall back to plain RAG.
* ``InMemoryGraphStore`` is the deterministic default backend.
  ``research_engine.knowledge.neo4j_store.Neo4jGraphStore`` implements the same
  protocol with parameterized allowlisted Cypher templates.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, Protocol

from research_engine.contracts.common import content_hash
from research_engine.contracts.evidence import (
    AssertionStatus,
    Chunk,
    DocumentVersion,
    Entity,
    GraphNode,
    IndexBuildStatus,
    NodeType,
    RelationshipAssertion,
    RelationType,
)

from .ontology import Direction, assert_no_portfolio_state, check_assertion


class GraphRetrievalUnavailable(RuntimeError):
    """The graph needed for graph-assisted retrieval is missing, not READY or failing."""


@dataclass(frozen=True)
class Edge:
    assertion: RelationshipAssertion
    neighbor: GraphNode
    direction: Direction


@dataclass
class GraphProjection:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    assertions: dict[str, RelationshipAssertion] = field(default_factory=dict)

    def membership(self) -> tuple[frozenset[str], frozenset[str]]:
        return frozenset(self.nodes), frozenset(self.assertions)

    def content_hash(self) -> str:
        return content_hash(
            {
                "nodes": [self.nodes[k].to_wire() for k in sorted(self.nodes)],
                "assertions": [self.assertions[k].to_wire() for k in sorted(self.assertions)],
            }
        )

    def assertion_set_hash(self) -> str:
        return content_hash(sorted(self.assertions))


def project(
    versions: Iterable[DocumentVersion],
    chunks: Iterable[Chunk],
    entities: Iterable[Entity],
    assertions: Iterable[RelationshipAssertion],
) -> GraphProjection:
    """Build the graph projection for an exact set of member versions.

    An assertion is projected only when both endpoints and every input record
    are part of the projection (no dangling or out-of-build support).
    """
    proj = GraphProjection()
    for entity in entities:
        proj.nodes[entity.entity_id] = GraphNode(
            node_id=entity.entity_id,
            node_type=entity.entity_type,
            label=entity.canonical_name,
            available_at=entity.available_at,
            properties=dict(entity.properties),
        )
    for version in versions:
        proj.nodes[version.version_id] = GraphNode(
            node_id=version.version_id,
            node_type=NodeType.DOCUMENT_VERSION,
            label=version.title,
            available_at=version.available_at,
            properties={
                "document_id": version.document_id,
                "document_type": version.document_type.value,
                "source_id": version.source_id,
                "synthetic": "true" if version.synthetic else "false",
            },
        )
    for chunk in chunks:
        if chunk.version_id not in proj.nodes:
            continue
        proj.nodes[chunk.chunk_id] = GraphNode(
            node_id=chunk.chunk_id,
            node_type=NodeType.CHUNK,
            label=f"{chunk.document_id}#{chunk.ordinal}",
            available_at=chunk.available_at,
            properties={"version_id": chunk.version_id, "ordinal": str(chunk.ordinal)},
        )
    for assertion in assertions:
        if assertion.validation_status == AssertionStatus.REJECTED:
            continue
        if assertion.subject_id not in proj.nodes or assertion.object_id not in proj.nodes:
            continue
        if any(i not in proj.nodes for i in assertion.input_ids):
            continue
        proj.assertions[assertion.assertion_id] = assertion
    assert_no_portfolio_state(list(proj.nodes.values()))
    return proj


class GraphStore(Protocol):
    backend_name: str

    def begin_build(self, build_id: str, schema_version: str) -> None: ...

    def write(self, build_id: str, projection: GraphProjection) -> None: ...

    def validate(self, build_id: str, expected: GraphProjection) -> list[str]: ...

    def publish(self, build_id: str) -> None: ...

    def fail(self, build_id: str, error: str) -> None: ...

    def status(self, build_id: str) -> Optional[IndexBuildStatus]: ...

    def membership(self, build_id: str) -> tuple[frozenset[str], frozenset[str]]: ...

    def node(self, build_id: str, node_id: str) -> Optional[GraphNode]: ...

    def edges(
        self,
        build_id: str,
        node_id: str,
        steps: Iterable[tuple[RelationType, Direction]],
        cutoff: datetime,
    ) -> list[Edge]: ...

    def drop(self, build_id: str) -> None: ...


@dataclass
class _Build:
    status: IndexBuildStatus
    schema_version: str
    projection: GraphProjection = field(default_factory=GraphProjection)
    out_edges: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    in_edges: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    error: Optional[str] = None


class InMemoryGraphStore:
    """Deterministic default backend. Neighbour ordering is stable and degree-free."""

    backend_name = "in-memory-graph-v1"

    def __init__(self) -> None:
        self._builds: dict[str, _Build] = {}

    def begin_build(self, build_id: str, schema_version: str) -> None:
        existing = self._builds.get(build_id)
        if existing is not None and existing.status == IndexBuildStatus.READY:
            raise RuntimeError(f"graph build {build_id} is already READY and immutable")
        self._builds[build_id] = _Build(IndexBuildStatus.BUILDING, schema_version)

    def write(self, build_id: str, projection: GraphProjection) -> None:
        build = self._builds[build_id]
        if build.status != IndexBuildStatus.BUILDING:
            raise RuntimeError("writes are only allowed while BUILDING")
        for node in projection.nodes.values():
            build.projection.nodes[node.node_id] = node
        for assertion in projection.assertions.values():
            check_assertion(assertion)
            build.projection.assertions[assertion.assertion_id] = assertion
            build.out_edges[assertion.subject_id].append(assertion.assertion_id)
            build.in_edges[assertion.object_id].append(assertion.assertion_id)

    def validate(self, build_id: str, expected: GraphProjection) -> list[str]:
        build = self._builds.get(build_id)
        if build is None:
            return ["graph build missing"]
        problems: list[str] = []
        nodes, assertions = build.projection.membership()
        exp_nodes, exp_assertions = expected.membership()
        if nodes != exp_nodes:
            problems.append(
                f"node membership differs (+{len(nodes - exp_nodes)} -{len(exp_nodes - nodes)})"
            )
        if assertions != exp_assertions:
            problems.append(
                "assertion membership differs "
                f"(+{len(assertions - exp_assertions)} -{len(exp_assertions - assertions)})"
            )
        if not problems and build.projection.content_hash() != expected.content_hash():
            problems.append("graph content hash differs from canonical projection")
        for assertion in build.projection.assertions.values():
            for input_id in assertion.input_ids:
                node = build.projection.nodes.get(input_id)
                if node is None or node.available_at > assertion.available_at:
                    problems.append(f"assertion {assertion.assertion_id} precedes input {input_id}")
                    break
        return problems

    def publish(self, build_id: str) -> None:
        build = self._builds[build_id]
        if build.status != IndexBuildStatus.BUILDING:
            raise RuntimeError(f"cannot publish a {build.status.value} graph build")
        build.status = IndexBuildStatus.READY

    def fail(self, build_id: str, error: str) -> None:
        build = self._builds.get(build_id)
        if build is not None and build.status == IndexBuildStatus.BUILDING:
            build.status = IndexBuildStatus.FAILED
            build.error = error

    def status(self, build_id: str) -> Optional[IndexBuildStatus]:
        build = self._builds.get(build_id)
        return build.status if build else None

    def _ready(self, build_id: str) -> _Build:
        build = self._builds.get(build_id)
        if build is None:
            raise GraphRetrievalUnavailable(f"graph build {build_id} not found")
        if build.status != IndexBuildStatus.READY:
            raise GraphRetrievalUnavailable(f"graph build {build_id} is {build.status.value}")
        return build

    def membership(self, build_id: str) -> tuple[frozenset[str], frozenset[str]]:
        build = self._builds.get(build_id)
        if build is None:
            return frozenset(), frozenset()
        return build.projection.membership()

    def projection(self, build_id: str) -> GraphProjection:
        return self._ready(build_id).projection

    def node(self, build_id: str, node_id: str) -> Optional[GraphNode]:
        return self._ready(build_id).projection.nodes.get(node_id)

    def edges(
        self,
        build_id: str,
        node_id: str,
        steps: Iterable[tuple[RelationType, Direction]],
        cutoff: datetime,
    ) -> list[Edge]:
        build = self._ready(build_id)
        proj = build.projection
        out: list[Edge] = []
        for relation, direction in steps:
            index = build.out_edges if direction == Direction.OUT else build.in_edges
            for assertion_id in index.get(node_id, ()):
                assertion = proj.assertions[assertion_id]
                if assertion.relation != relation:
                    continue
                if assertion.validation_status != AssertionStatus.APPROVED:
                    continue
                if assertion.available_at > cutoff:
                    continue
                other = assertion.object_id if direction == Direction.OUT else assertion.subject_id
                neighbor = proj.nodes[other]
                if neighbor.available_at > cutoff:
                    continue
                out.append(Edge(assertion, neighbor, direction))
        out.sort(
            key=lambda e: (e.assertion.relation.value, e.neighbor.node_id, e.assertion.assertion_id)
        )
        return out

    def drop(self, build_id: str) -> None:
        self._builds.pop(build_id, None)
