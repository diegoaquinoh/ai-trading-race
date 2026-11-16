"""Retrieval determinism, RRF/budget, citations, caching, graph limits/failures, index builds."""

from __future__ import annotations

from decimal import Decimal

import pytest

from research_engine.contracts.decisions import Citation, RetrievalMode
from research_engine.contracts.evidence import (
    IndexBuild,
    IndexBuildStatus,
    RetrievalBudget,
    RetrievalChannel,
    RetrievalRequest,
)
from research_engine.knowledge.graph_store import GraphRetrievalUnavailable, InMemoryGraphStore
from research_engine.retrieval import resolve_chunk, validate_citation, validate_quote
from research_engine.retrieval.citations import ChunkNotFound
from research_engine.retrieval.index import IndexNotReady, build_index, load_index, rebuild_graph
from research_engine.retrieval.service import retrieve
from research_engine.evidence.store import InvalidStateTransition

from .conftest import utc

AS_OF = utc(2024, 6, 12, 23, 30)
QUESTION = "Which CPI release was available before the June 2024 FOMC statement and what did the statement say about inflation?"


def _req(index, mode=RetrievalMode.HYBRID_RAG, question=QUESTION, as_of=AS_OF, **kw):
    return RetrievalRequest(
        question=question, decision_as_of=as_of, mode=mode, index_build_id=index.build_id, **kw
    )


def test_retrieval_is_deterministic_and_persisted(home, default_index):
    run1, bundle1 = retrieve(_req(default_index), home.store, default_index, use_cache=False)
    run2, bundle2 = retrieve(_req(default_index), home.store, default_index, use_cache=False)
    assert run1 == run2 and bundle1 == bundle2
    assert home.store.get_retrieval_run(run1.retrieval_run_id) == run1
    assert home.store.get_bundle(bundle1.bundle_id) == bundle1
    # Cache hit returns the stored run, never a recomputation.
    run3, bundle3 = retrieve(_req(default_index), home.store, default_index)
    assert run3 == run1 and bundle3 == bundle1


def test_cache_key_covers_cutoff_scope_and_permission(home, default_index):
    base, _ = retrieve(_req(default_index), home.store, default_index)
    other_cutoff, _ = retrieve(
        _req(default_index, as_of=utc(2024, 6, 13)), home.store, default_index
    )
    other_scope, _ = retrieve(
        _req(default_index, permission_scope="strategy:llm_rag"), home.store, default_index
    )
    keys = {base.cache_key, other_cutoff.cache_key, other_scope.cache_key}
    assert len(keys) == 3


def test_rrf_fusion_and_budget(home, default_index):
    run, bundle = retrieve(_req(default_index), home.store, default_index)
    k = run.request.budget.rrf_k
    assert len([c for c in run.candidates if c.lexical_rank]) <= 30
    assert len([c for c in run.candidates if c.vector_rank]) <= 30
    for cand in run.candidates:
        expected = Decimal(0)
        if cand.lexical_rank:
            expected += Decimal(1) / (k + cand.lexical_rank)
        if cand.vector_rank:
            expected += Decimal(1) / (k + cand.vector_rank)
        assert abs(cand.fused_score - expected) < Decimal("1e-9")
    ranks = [c.fused_rank for c in run.candidates]
    assert ranks == sorted(ranks)
    assert bundle.chunk_count <= 12 and bundle.total_tokens <= 8000
    assert bundle.total_tokens == sum(c.token_count for c in bundle.chunks)
    per_doc = {}
    for c in bundle.chunks:
        per_doc[c.document_id] = per_doc.get(c.document_id, 0) + 1
    assert max(per_doc.values()) <= run.request.budget.max_chunks_per_document
    assert [c.chunk_id for c in bundle.chunks] == run.delivered_chunk_ids


def test_tight_budget_truncates_deterministically(home, default_index):
    budget = RetrievalBudget(max_chunks=3, max_evidence_tokens=1200)
    run, bundle = retrieve(_req(default_index, budget=budget), home.store, default_index)
    assert bundle.chunk_count <= 3 and bundle.total_tokens <= 1200
    assert bundle.truncated_by_budget
    reasons = {e.reason for e in run.exclusions if e.record_type == "chunk"}
    assert reasons & {"budget_max_chunks", "budget_max_evidence_tokens"}
    again, bundle_again = retrieve(
        _req(default_index, budget=budget), home.store, default_index, use_cache=False
    )
    assert bundle_again == bundle


def test_overlapping_chunks_are_deduplicated(home, default_index):
    run, bundle = retrieve(_req(default_index), home.store, default_index)
    for a in bundle.chunks:
        for b in bundle.chunks:
            if a.chunk_id < b.chunk_id and a.version_id == b.version_id:
                overlap = min(a.end_offset, b.end_offset) - max(a.start_offset, b.start_offset)
                assert overlap <= 0 or overlap / min(len(a.text), len(b.text)) < 0.5


def test_mode_none_returns_explicit_empty_bundle(home, default_index):
    run, bundle = retrieve(_req(default_index, mode=RetrievalMode.NONE), home.store, default_index)
    assert bundle.empty and bundle.chunks == [] and run.candidates == []


def test_citation_quote_and_offset_resolution(home, default_index):
    run, bundle = retrieve(_req(default_index), home.store, default_index)
    chunk = bundle.chunks[0]
    stored = resolve_chunk(home.store, chunk.chunk_id)
    assert stored.text == chunk.text and stored.text_hash == chunk.text_hash
    quote = chunk.text[10:60]
    assert validate_quote(chunk.text, quote).start_offset == 10
    assert validate_quote(chunk.text, quote, 10, 60).valid
    assert not validate_quote(chunk.text, quote, 11, 61).valid
    assert not validate_quote(chunk.text, "words that are not in the passage at all").valid
    assert not validate_quote(chunk.text, None, 0, len(chunk.text) + 5).valid
    good = Citation(
        citation_id="c1",
        bundle_id=bundle.bundle_id,
        chunk_id=chunk.chunk_id,
        document_version_id=chunk.version_id,
        quote=quote,
        start_offset=10,
        end_offset=60,
    )
    assert all(r.passed for r in validate_citation(good, bundle, home.store))
    wrong_version = good.model_copy(update={"document_version_id": "dv-other"})
    assert not all(r.passed for r in validate_citation(wrong_version, bundle, home.store))
    not_delivered = good.model_copy(update={"chunk_id": "chk-not-delivered"})
    assert validate_citation(not_delivered, bundle, home.store)[0].passed is False
    with pytest.raises(ChunkNotFound):
        resolve_chunk(home.store, "chk-missing")
    # Document-level offsets: chunk offsets + chunk.start_offset index the version text.
    version_text = home.artifacts.get_text(
        home.store.get_version(chunk.version_id).normalized_artifact_uri
    )
    assert version_text[chunk.start_offset + 10 : chunk.start_offset + 60] == quote


def test_graph_mode_limits_and_provenance(home, default_index):
    run, bundle = retrieve(
        _req(default_index, mode=RetrievalMode.GRAPH_RAG), home.store, default_index
    )
    trace = run.graph
    assert trace is not None and trace.graph_build_id == default_index.build_id
    assert len(trace.seeds) <= 8
    assert len(trace.visited_assertion_ids) <= 40
    assert len(set(trace.visited_assertion_ids)) == len(trace.visited_assertion_ids)
    graph = default_index.require_graph()
    proj = graph.projection(default_index.build_id)
    for assertion_id in trace.visited_assertion_ids:
        assertion = proj.assertions[assertion_id]
        assert assertion.validation_status.value == "approved"
        assert assertion.available_at <= AS_OF
    graph_chunks = [c for c in bundle.chunks if c.provenance.graph]
    assert graph_chunks
    for chunk in graph_chunks:
        prov = chunk.provenance.graph
        assert prov.seed_id in {s.seed_id for s in trace.seeds}
        assert prov.path_assertion_ids and prov.support_spans
        assert prov.availability_checks and all(c.passed for c in prov.availability_checks)
        assert RetrievalChannel.GRAPH.value in chunk.provenance.ranking_contribution
        assert prov.path_length <= 2
    # CPI release facts come from RELEASE_OF assertions available at the cutoff.
    facts = bundle.structured_facts
    assert facts and facts[0].subject_id == "release-cpi-20240612"
    assert all(f.available_at <= AS_OF for f in facts)


def test_graph_fanout_and_visit_limits_are_enforced(home, default_index):
    budget = RetrievalBudget(graph_max_fanout=2, graph_max_visited_assertions=5, graph_max_seeds=2)
    run, bundle = retrieve(
        _req(default_index, mode=RetrievalMode.GRAPH_RAG, budget=budget), home.store, default_index
    )
    assert len(run.graph.seeds) <= 2
    assert len(run.graph.visited_assertion_ids) <= 5
    assert any(
        lim.startswith(("max_seeds", "fanout", "max_visited")) for lim in run.graph.limits_hit
    )
    graph = default_index.require_graph()
    proj = graph.projection(default_index.build_id)
    per_subject: dict[str, int] = {}
    for assertion_id in run.graph.visited_assertion_ids:
        a = proj.assertions[assertion_id]
        per_subject[a.subject_id + a.object_id] = per_subject.get(a.subject_id + a.object_id, 0) + 1
    assert all(v == 1 for v in per_subject.values())


def test_graph_neighbor_order_ignores_global_degree(default_index):
    graph = default_index.require_graph()
    from research_engine.knowledge.ontology import TRAVERSAL_STEPS
    from research_engine.contracts.evidence import NodeType

    edges = graph.edges(
        default_index.build_id,
        "topic-inflation",
        TRAVERSAL_STEPS[NodeType.MACRO_TOPIC],
        utc(2023, 3, 1),
    )
    assert edges and all(e.assertion.available_at <= utc(2023, 3, 1) for e in edges)
    ids = [e.neighbor.node_id for e in edges]
    assert ids == sorted(ids)  # stable id order from the store; retrieval re-ranks by relevance


class FailingGraph(InMemoryGraphStore):
    backend_name = "failing-graph"

    def edges(self, *args, **kwargs):
        raise ConnectionError("graph backend unreachable")


def test_graph_failure_is_explicit_never_plain_rag(home, default_index):
    failing = FailingGraph()
    rebuild_graph(home.store, default_index.build, failing)
    index = load_index(home.store, default_index.build_id, graph=failing)
    with pytest.raises(GraphRetrievalUnavailable):
        retrieve(
            _req(index, mode=RetrievalMode.GRAPH_RAG, question="inflation in June 2024"),
            home.store,
            index,
        )
    # Hybrid mode does not depend on the graph and still works on the same index.
    run, bundle = retrieve(_req(index, question="inflation in June 2024"), home.store, index)
    assert bundle.chunks and run.graph is None

    missing = InMemoryGraphStore()
    index_missing = load_index(home.store, default_index.build_id, graph=missing)
    missing.drop(default_index.build_id)
    with pytest.raises(GraphRetrievalUnavailable):
        retrieve(
            _req(index_missing, mode=RetrievalMode.GRAPH_RAG, question="balance sheet runoff"),
            home.store,
            index_missing,
        )


@pytest.mark.parametrize(
    "stage", ["members", "embeddings", "graph_write", "graph_validate", "publish"]
)
def test_index_build_never_ready_before_validation(home, stage, clock):
    graph = InMemoryGraphStore()

    def fault(name):
        if name == stage:
            raise RuntimeError(f"injected failure at {name}")

    build = build_index(
        home.store, graph, clock=clock, build_salt=hash(stage) % 10_000 + 1, fault=fault
    )
    assert build.status == IndexBuildStatus.FAILED
    assert "injected failure" in (build.error or "")
    assert graph.status(build.build_id) in (None, IndexBuildStatus.FAILED)
    with pytest.raises(IndexNotReady):
        load_index(home.store, build.build_id, graph=graph)
    with pytest.raises(InvalidStateTransition):
        home.store.update_index_build(build)


def test_ready_requires_recorded_validation(default_index, home):
    data = default_index.build.model_dump()
    with pytest.raises(ValueError):
        IndexBuild.model_validate({**data, "validated_at": None})
    with pytest.raises(ValueError):
        IndexBuild.model_validate({**data, "validation_checks": []})
    with pytest.raises(InvalidStateTransition):
        home.store.put_index_build(default_index.build)  # cannot insert as READY


def test_rebuild_membership_equality_in_memory(home, default_index):
    fresh = InMemoryGraphStore()
    rebuilt = rebuild_graph(home.store, default_index.build, fresh)
    original = default_index.require_graph().membership(default_index.build_id)
    assert fresh.membership(default_index.build_id) == original == rebuilt.membership()
    assert (
        fresh.projection(default_index.build_id).content_hash()
        == default_index.require_graph().projection(default_index.build_id).content_hash()
    )
    assert len(rebuilt.assertions) == default_index.build.assertion_count
    assert len(rebuilt.nodes) == default_index.build.node_count


def test_identical_config_reuses_build(home, default_index, graph, clock):
    again = build_index(home.store, graph, include_synthetic=False, clock=clock)
    assert again.build_id == default_index.build_id
    assert again == home.store.get_index_build(default_index.build_id)
