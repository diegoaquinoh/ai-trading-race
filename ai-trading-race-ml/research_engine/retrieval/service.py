"""Public retrieval entry point: ``retrieve(request, store, index)`` (spec 12.3, 12.4, 13.3).

Pipeline (``hybrid_rag_v1``): eligible snapshot -> deterministic query ->
30 BM25 + 30 exact-cosine candidates -> reciprocal rank fusion (k = 60) ->
overlap dedupe + per-document diversity -> budget (<= 12 chunks, <= 8,000
``ws-regex-v1`` tokens) -> persisted ``RetrievalRun`` + ``EvidenceBundle``.

``graph_rag_v1`` uses the same hybrid candidates plus the bounded graph list
(``retrieval.graph``) as a third RRF input and the same final budget.

``none`` returns an explicit empty bundle. Every run is persisted; the cache key
covers cutoff, snapshot, index build, embedding model, query/request and
permission scope, and the run id is derived from it, so a repeated identical
request returns the stored run (never a recomputed one).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Optional

from research_engine import ENGINE_VERSION
from research_engine.contracts.common import HASH_PREFIX, content_hash, short_id
from research_engine.contracts.decisions import RetrievalMode
from research_engine.contracts.evidence import (
    AvailabilityCheck,
    ChunkProvenance,
    DeliveredChunk,
    EvidenceBundle,
    Exclusion,
    GraphProvenance,
    RetrievalCandidate,
    RetrievalChannel,
    RetrievalRequest,
    RetrievalRun,
    bundle_identity_payload,
    score_decimal,
)
from research_engine.evidence.store import ResearchStore

from .graph import GRAPH_EXPANSION_VERSION, GraphResult, expand, hit_provenance
from .index import EvidenceIndex, IndexNotReady
from .query import QUERY_CONSTRUCTION, build_query
from .snapshot import LEXICAL_VERSION, bm25_scores, eligible_snapshot, top_k, vector_scores

RETRIEVAL_VERSION = "retrieval-v1"
FUSION_VERSION = "rrf-v1"
SELECTION_VERSION = "dedupe-diversity-budget-graphquota-v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def cache_key(request: RetrievalRequest, snapshot_id: str, index: EvidenceIndex) -> str:
    return content_hash(
        {
            "cutoff": request.decision_as_of,
            "snapshot": snapshot_id,
            "index": index.build_id,
            "embedding": [index.build.embedding_provider, index.build.embedding_model],
            "versions": [
                RETRIEVAL_VERSION,
                LEXICAL_VERSION,
                FUSION_VERSION,
                SELECTION_VERSION,
                QUERY_CONSTRUCTION,
                GRAPH_EXPANSION_VERSION,
            ],
            "request": request.to_wire(),
            "permission": request.permission_scope,
        }
    )


def _rrf(
    lists: dict[RetrievalChannel, list[str]], weights: dict[RetrievalChannel, float], k: int
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    fused: dict[str, float] = {}
    parts: dict[str, dict[str, float]] = {}
    for channel, ranked in lists.items():
        for rank, chunk_id in enumerate(ranked, start=1):
            contribution = weights[channel] / (k + rank)
            fused[chunk_id] = fused.get(chunk_id, 0.0) + contribution
            parts.setdefault(chunk_id, {})[channel.value] = contribution
    return fused, parts


def _select(
    order: list[str],
    index: EvidenceIndex,
    request: RetrievalRequest,
    priority: Optional[list[str]] = None,
    reserved: int = 0,
) -> tuple[list[str], list[Exclusion], list[str]]:
    """Deterministic truncation: optional reserved priority slots, then fused order.

    Rules for every pass: exact-text dedupe, same-version overlap dedupe,
    per-document cap, chunk cap, token cap (greedy; a later smaller chunk may fit).
    """
    budget = request.budget
    delivered: list[str] = []
    exclusions: list[Exclusion] = []
    truncated: list[str] = []
    tokens = 0
    per_doc: dict[str, int] = {}
    hashes: dict[str, str] = {}
    ratio = float(budget.overlap_dedupe_ratio)
    if priority and reserved > 0:
        taken = 0
        for chunk_id in priority:
            if taken >= reserved or len(delivered) >= budget.max_chunks:
                break
            chunk = index.chunks[chunk_id]
            if (
                chunk.text_hash in hashes
                or per_doc.get(chunk.document_id, 0) >= budget.max_chunks_per_document
            ):
                continue
            if tokens + chunk.token_count > budget.max_evidence_tokens:
                continue
            if any(
                index.chunks[o].version_id == chunk.version_id
                and min(index.chunks[o].end_offset, chunk.end_offset)
                - max(index.chunks[o].start_offset, chunk.start_offset)
                > 0
                for o in delivered
            ):
                continue
            delivered.append(chunk_id)
            hashes[chunk.text_hash] = chunk_id
            tokens += chunk.token_count
            per_doc[chunk.document_id] = per_doc.get(chunk.document_id, 0) + 1
            taken += 1
    for chunk_id in order:
        if chunk_id in delivered:
            continue
        chunk = index.chunks[chunk_id]
        if chunk.text_hash in hashes:
            exclusions.append(
                Exclusion(
                    record_id=chunk_id,
                    record_type="chunk",
                    reason=f"duplicate_text_of:{hashes[chunk.text_hash]}",
                )
            )
            continue
        overlap_with = None
        for other_id in delivered:
            other = index.chunks[other_id]
            if other.version_id != chunk.version_id:
                continue
            overlap = min(other.end_offset, chunk.end_offset) - max(
                other.start_offset, chunk.start_offset
            )
            shorter = min(len(other.text), len(chunk.text)) or 1
            if overlap > 0 and overlap / shorter >= ratio:
                overlap_with = other_id
                break
        if overlap_with:
            exclusions.append(
                Exclusion(
                    record_id=chunk_id,
                    record_type="chunk",
                    reason=f"overlap_duplicate_of:{overlap_with}",
                )
            )
            continue
        if per_doc.get(chunk.document_id, 0) >= budget.max_chunks_per_document:
            exclusions.append(
                Exclusion(record_id=chunk_id, record_type="chunk", reason="document_diversity_cap")
            )
            continue
        if len(delivered) >= budget.max_chunks:
            exclusions.append(
                Exclusion(record_id=chunk_id, record_type="chunk", reason="budget_max_chunks")
            )
            truncated.append(chunk_id)
            continue
        if tokens + chunk.token_count > budget.max_evidence_tokens:
            exclusions.append(
                Exclusion(
                    record_id=chunk_id, record_type="chunk", reason="budget_max_evidence_tokens"
                )
            )
            truncated.append(chunk_id)
            continue
        delivered.append(chunk_id)
        hashes[chunk.text_hash] = chunk_id
        tokens += chunk.token_count
        per_doc[chunk.document_id] = per_doc.get(chunk.document_id, 0) + 1
    return delivered, exclusions, truncated


def retrieve(
    request: RetrievalRequest,
    store: ResearchStore,
    index: EvidenceIndex,
    *,
    clock: Callable[[], datetime] = utc_now,
    use_cache: bool = True,
) -> tuple[RetrievalRun, EvidenceBundle]:
    """Retrieve an eligible evidence bundle; persists the run and the bundle.

    Raises ``IndexNotReady`` for a non-READY/mismatched build and
    ``GraphRetrievalUnavailable`` when graph mode cannot use its graph.
    """
    started = time.perf_counter()
    if request.index_build_id != index.build_id:
        raise IndexNotReady(
            f"request names build {request.index_build_id}, loaded {index.build_id}"
        )
    stored = store.get_index_build(index.build_id)
    if stored is None or stored.status.value != "READY":
        raise IndexNotReady(f"index build {index.build_id} is not READY")
    cutoff = request.decision_as_of
    snapshot = eligible_snapshot(index, cutoff, list(request.source_scope))
    key = cache_key(request, snapshot.snapshot_id, index)
    run_id = "rr-" + key[len(HASH_PREFIX) : len(HASH_PREFIX) + 24]
    if use_cache:
        cached = store.get_retrieval_run(run_id)
        if cached is not None:
            bundle = store.get_bundle(cached.bundle_id)
            if bundle is not None:
                return cached, bundle

    budget = request.budget
    resolution = index.resolver.resolve(request.question, cutoff)
    query = build_query(request, index, resolution)
    candidates: list[RetrievalCandidate] = []
    exclusions: list[Exclusion] = list(snapshot.exclusions)
    delivered_ids: list[str] = []
    truncated: list[str] = []
    graph_result: Optional[GraphResult] = None
    fused: dict[str, float] = {}
    parts: dict[str, dict[str, float]] = {}
    lex_rank: dict[str, int] = {}
    vec_rank: dict[str, int] = {}
    graph_rank: dict[str, int] = {}
    lex: dict[str, float] = {}
    vec: dict[str, float] = {}
    graph_scores: dict[str, float] = {}

    if request.mode != RetrievalMode.NONE:
        lex = bm25_scores(index, snapshot, query.terms)
        vec = vector_scores(index, snapshot, query.text)
        lex_top = top_k(lex, budget.lexical_candidates)
        vec_top = top_k(vec, budget.vector_candidates)
        lex_rank = {c: i for i, c in enumerate(lex_top, start=1)}
        vec_rank = {c: i for i, c in enumerate(vec_top, start=1)}
        lists = {RetrievalChannel.LEXICAL: lex_top, RetrievalChannel.VECTOR: vec_top}
        weights = {
            RetrievalChannel.LEXICAL: 1.0,
            RetrievalChannel.VECTOR: 1.0,
            RetrievalChannel.GRAPH: float(budget.graph_rrf_weight),
        }
        hybrid_fused, _ = _rrf(lists, weights, budget.rrf_k)
        if request.mode == RetrievalMode.GRAPH_RAG:
            max_lex = max(lex.values(), default=0.0) or 1.0
            max_vec = max(vec.values(), default=0.0) or 1.0
            relevance = {
                c: 0.5 * lex.get(c, 0.0) / max_lex + 0.5 * max(vec.get(c, 0.0), 0.0) / max_vec
                for c in snapshot.chunk_ids
            }
            hybrid_order = sorted(hybrid_fused, key=lambda c: (-hybrid_fused[c], c))
            graph_result = expand(
                index,
                snapshot,
                resolution,
                list(request.explicit_identifiers),
                hybrid_order,
                hybrid_fused,
                relevance,
                cutoff,
                max_seeds=budget.graph_max_seeds,
                max_depth=budget.graph_max_depth,
                max_fanout=budget.graph_max_fanout,
                max_visited=budget.graph_max_visited_assertions,
                chunks_per_document=budget.graph_chunks_per_document,
            )
            graph_scores = {c: h.score for c, h in graph_result.hits.items()}
            graph_list = sorted(graph_scores, key=lambda c: (-graph_scores[c], c))
            graph_rank = {c: i for i, c in enumerate(graph_list, start=1)}
            lists[RetrievalChannel.GRAPH] = graph_list
            exclusions.extend(graph_result.exclusions)
        fused, parts = _rrf(lists, weights, budget.rrf_k)
        order = sorted(fused, key=lambda c: (-fused[c], c))
        graph_priority = lists.get(RetrievalChannel.GRAPH)
        delivered_ids, select_exclusions, truncated = _select(
            order,
            index,
            request,
            priority=graph_priority,
            reserved=budget.graph_reserved_slots if graph_priority else 0,
        )
        rank_of = {c: i for i, c in enumerate(order)}
        delivered_ids.sort(key=lambda c: rank_of[c])
        exclusions.extend(select_exclusions)
        delivered_set = set(delivered_ids)
        for final_rank, chunk_id in enumerate(order, start=1):
            chunk = index.chunks[chunk_id]
            channels = [
                ch
                for ch, ranks in (
                    (RetrievalChannel.LEXICAL, lex_rank),
                    (RetrievalChannel.VECTOR, vec_rank),
                    (RetrievalChannel.GRAPH, graph_rank),
                )
                if chunk_id in ranks
            ]
            candidates.append(
                RetrievalCandidate(
                    chunk_id=chunk_id,
                    version_id=chunk.version_id,
                    document_id=chunk.document_id,
                    channels=channels,
                    lexical_rank=lex_rank.get(chunk_id),
                    lexical_score=score_decimal(lex[chunk_id]) if chunk_id in lex_rank else None,
                    vector_rank=vec_rank.get(chunk_id),
                    vector_score=score_decimal(vec[chunk_id]) if chunk_id in vec_rank else None,
                    graph_rank=graph_rank.get(chunk_id),
                    graph_score=(
                        score_decimal(graph_scores[chunk_id]) if chunk_id in graph_rank else None
                    ),
                    fused_score=score_decimal(fused[chunk_id]),
                    fused_rank=final_rank,
                    delivered=chunk_id in delivered_set,
                )
            )

    final_rank_of = {c.chunk_id: c.fused_rank for c in candidates}
    hybrid_ids = set(lex_rank) | set(vec_rank)
    delivered: list[DeliveredChunk] = []
    for chunk_id in delivered_ids:
        chunk = index.chunks[chunk_id]
        version = index.versions[chunk.version_id]
        graph_prov = None
        checks = [
            AvailabilityCheck(
                record_id=version.version_id,
                record_type="document_version",
                available_at=version.available_at,
                cutoff=cutoff,
                passed=version.available_at <= cutoff,
            )
        ]
        if graph_result is not None and chunk_id in graph_result.hits:
            hit = graph_result.hits[chunk_id]
            spans, graph_checks, assertion_ids = hit_provenance(hit, index, cutoff)
            graph_prov = GraphProvenance(
                seed_id=hit.seed_id,
                path_assertion_ids=assertion_ids,
                path_length=max(1, len(hit.path)),
                support_spans=spans,
                availability_checks=graph_checks,
                graph_score=score_decimal(hit.score),
                added_by_graph=chunk_id not in hybrid_ids,
            )
        delivered.append(
            DeliveredChunk(
                chunk_id=chunk_id,
                version_id=version.version_id,
                document_id=version.document_id,
                source_id=version.source_id,
                document_type=version.document_type,
                title=version.title,
                source_url=version.source_url,
                published_at=version.published_at,
                available_at=version.available_at,
                availability_policy=version.availability_policy,
                heading_path=chunk.heading_path,
                ordinal=chunk.ordinal,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                text=chunk.text,
                text_hash=chunk.text_hash,
                token_count=chunk.token_count,
                fidelity_flags=version.fidelity_flags,
                synthetic=version.synthetic,
                provenance=ChunkProvenance(
                    channels=[
                        ch
                        for ch, ranks in (
                            (RetrievalChannel.LEXICAL, lex_rank),
                            (RetrievalChannel.VECTOR, vec_rank),
                            (RetrievalChannel.GRAPH, graph_rank),
                        )
                        if chunk_id in ranks
                    ],
                    lexical_rank=lex_rank.get(chunk_id),
                    vector_rank=vec_rank.get(chunk_id),
                    graph_rank=graph_rank.get(chunk_id),
                    ranking_contribution={
                        k: score_decimal(v) for k, v in sorted(parts.get(chunk_id, {}).items())
                    },
                    fused_score=score_decimal(fused.get(chunk_id, 0.0)),
                    final_rank=final_rank_of[chunk_id],
                    graph=graph_prov,
                    availability_checks=checks,
                ),
            )
        )
    for item in delivered:  # structural guarantee: nothing after the cutoff is delivered
        if item.available_at > cutoff:
            raise AssertionError(f"temporal violation: {item.chunk_id}")

    bundle = EvidenceBundle(
        bundle_id="pending",
        retrieval_run_id=run_id,
        decision_as_of=cutoff,
        mode=request.mode,
        index_build_id=index.build_id,
        snapshot_id=snapshot.snapshot_id,
        chunks=delivered,
        structured_facts=graph_result.facts if graph_result else [],
        total_tokens=sum(c.token_count for c in delivered),
        chunk_count=len(delivered),
        truncated_by_budget=truncated,
        empty=not delivered,
    )
    bundle = bundle.model_copy(
        update={"bundle_id": short_id("eb", bundle_identity_payload(bundle), 24)}
    )
    bundle = EvidenceBundle.model_validate(bundle.model_dump())
    run = RetrievalRun(
        retrieval_run_id=run_id,
        request=request,
        request_hash=request.compute_hash(),
        cache_key=key,
        query=query,
        cutoff=cutoff,
        filters={
            "mode": request.mode.value,
            "source_scope": ",".join(request.source_scope),
            "permission_scope": request.permission_scope,
            "availability": "available_at<=decision_as_of",
            "supersession": "latest eligible version per document",
        },
        snapshot_id=snapshot.snapshot_id,
        snapshot_version_ids=list(snapshot.version_ids),
        snapshot_chunk_count=len(snapshot.chunk_ids),
        index_build_id=index.build_id,
        embedding_model=index.build.embedding_model,
        candidates=candidates,
        exclusions=exclusions,
        delivered_chunk_ids=delivered_ids,
        bundle_id=bundle.bundle_id,
        graph=graph_result.trace if graph_result else None,
        engine_version=ENGINE_VERSION,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    store.put_retrieval(run, bundle, clock(), duration_ms)
    return run, bundle


def retrieval_latency_ms(store: ResearchStore, run_id: str) -> Optional[int]:
    import sqlalchemy as sa

    tbl = store.tbl("retrieval_runs")
    with store.engine.connect() as conn:
        value = conn.execute(
            sa.select(tbl.c.duration_ms).where(tbl.c.retrieval_run_id == run_id)
        ).scalar()
    return int(value) if value is not None else None
