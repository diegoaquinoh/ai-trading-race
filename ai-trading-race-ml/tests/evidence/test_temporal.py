"""Spec 16.6 temporal scenarios for evidence, retrieval and the graph."""

from __future__ import annotations

from research_engine.contracts.common import short_id
from research_engine.contracts.decisions import RetrievalMode
from research_engine.contracts.evidence import AliasStatus, EntityAlias, RetrievalRequest
from research_engine.evidence.textnorm import alias_key
from research_engine.knowledge.graph_store import InMemoryGraphStore
from research_engine.knowledge.resolver import AliasResolver
from research_engine.retrieval.index import build_index, load_index
from research_engine.retrieval.service import retrieve
from research_engine.retrieval.snapshot import eligible_snapshot

from .conftest import utc

MINUTES_JAN_2024 = "doc-fed-fomc-minutes-20240131"
STATEMENT_JAN_2024 = "doc-fed-fomc-statement-20240131"
STATEMENT_MAR_2023 = "doc-fed-fomc-statement-20230322"


def _request(index, question, as_of, mode=RetrievalMode.HYBRID_RAG, **kw):
    return RetrievalRequest(
        question=question, decision_as_of=as_of, mode=mode, index_build_id=index.build_id, **kw
    )


def test_minutes_unavailable_on_statement_date(home, default_index):
    statement_evening = utc(2024, 1, 31, 23, 30)
    snapshot = eligible_snapshot(default_index, statement_evening, ["fed-fomc"])
    docs = {default_index.versions[v].document_id for v in snapshot.version_ids}
    assert STATEMENT_JAN_2024 in docs
    assert MINUTES_JAN_2024 not in docs
    for mode in (RetrievalMode.HYBRID_RAG, RetrievalMode.GRAPH_RAG):
        run, bundle = retrieve(
            _request(
                default_index,
                "What did the minutes of the January 2024 meeting say about inflation?",
                statement_evening,
                mode,
            ),
            home.store,
            default_index,
        )
        assert all(c.document_id != MINUTES_JAN_2024 for c in bundle.chunks)
        assert all(c.available_at <= statement_evening for c in bundle.chunks)
        if mode == RetrievalMode.GRAPH_RAG:
            # The event seed reaches the eligible statement through DOCUMENTS_EVENT.
            assert any(c.document_id == STATEMENT_JAN_2024 for c in bundle.chunks)
        assert any(
            e.reason == "not_available_at_cutoff"
            and default_index.versions[e.record_id].document_id == MINUTES_JAN_2024
            for e in run.exclusions
            if e.record_type == "document_version"
        )
    # One minute before availability (published 14:00 ET + 120 min lag) it is still excluded.
    available = next(
        v for v in default_index.versions.values() if v.document_id == MINUTES_JAN_2024
    ).available_at
    assert available == utc(2024, 2, 21, 21, 0)
    from datetime import timedelta

    before = eligible_snapshot(default_index, available - timedelta(minutes=1), ["fed-fomc"])
    at = eligible_snapshot(default_index, available, ["fed-fomc"])
    assert MINUTES_JAN_2024 not in {
        default_index.versions[v].document_id for v in before.version_ids
    }
    assert MINUTES_JAN_2024 in {default_index.versions[v].document_id for v in at.version_ids}


def test_later_correction_does_not_alter_saved_earlier_retrieval(
    home, synthetic_index, graph, clock
):
    question = "What did the March 2023 FOMC statement say about the extent of the effects of recent banking developments?"
    early = utc(2023, 3, 23, 12, 0)
    # Index built BEFORE the correction existed in the index membership.
    original_only = load_index(
        home.store,
        build_index(home.store, graph, max_available_at=utc(2023, 3, 28), clock=clock).build_id,
        graph=graph,
    )
    run_before, bundle_before = retrieve(
        _request(original_only, question, early), home.store, original_only
    )
    saved = home.store.get_bundle(bundle_before.bundle_id)
    assert saved == bundle_before
    assert all("synthetic correction" not in c.text for c in bundle_before.chunks)
    assert not any(c.synthetic for c in bundle_before.chunks)

    # Later index includes the correction: the earlier cutoff still sees the original text.
    run_early, bundle_early = retrieve(
        _request(synthetic_index, question, early), home.store, synthetic_index
    )
    assert [c.text for c in bundle_early.chunks] == [c.text for c in bundle_before.chunks]
    assert [c.chunk_id for c in bundle_early.chunks] == [c.chunk_id for c in bundle_before.chunks]
    assert run_early.snapshot_id == run_before.snapshot_id

    # After its availability the correction supersedes the original (labelled synthetic).
    late = utc(2023, 4, 5, 12, 0)
    run_late, bundle_late = retrieve(
        _request(synthetic_index, question, late), home.store, synthetic_index
    )
    march = [c for c in bundle_late.chunks if c.document_id == STATEMENT_MAR_2023]
    assert march and all(c.synthetic for c in march)
    assert any("synthetic correction" in c.text for c in march)
    assert any(e.reason.startswith("superseded_by:") for e in run_late.exclusions)
    # The saved earlier run and bundle are unchanged in the store.
    assert home.store.get_bundle(bundle_before.bundle_id) == saved
    assert home.store.get_retrieval_run(run_before.retrieval_run_id) == run_before


def test_correction_boundary_uses_available_at_not_published_at(synthetic_index):
    # Synthetic correction published 18:00Z, available 20:00Z on 2023-03-29.
    for cutoff, expect_synthetic in (
        (utc(2023, 3, 29, 19, 0), False),
        (utc(2023, 3, 29, 20, 0), True),
    ):
        snapshot = eligible_snapshot(synthetic_index, cutoff, ["fed-fomc"])
        march = [
            synthetic_index.versions[v]
            for v in snapshot.version_ids
            if synthetic_index.versions[v].document_id == STATEMENT_MAR_2023
        ]
        assert len(march) == 1
        assert march[0].synthetic is expect_synthetic


def test_future_corpus_additions_do_not_change_historical_rankings_or_fanout(
    home, default_index, clock
):
    graph = InMemoryGraphStore()
    cutoff = utc(2023, 7, 27, 12, 0)
    small = load_index(
        home.store,
        build_index(home.store, graph, max_available_at=cutoff, clock=clock).build_id,
        graph=graph,
    )
    assert len(small.versions) < len(default_index.versions)
    questions = [
        "What did the minutes of the meeting before the July 2023 meeting say about the labor market?",
        "How did the Committee describe inflation and the banking system in 2023?",
        "Which CPI release was available before the July 2023 FOMC statement?",
    ]
    for question in questions:
        for mode in (RetrievalMode.HYBRID_RAG, RetrievalMode.GRAPH_RAG):
            run_small, bundle_small = retrieve(
                _request(small, question, cutoff, mode), home.store, small
            )
            run_full, bundle_full = retrieve(
                _request(default_index, question, cutoff, mode), home.store, default_index
            )
            assert run_small.snapshot_id == run_full.snapshot_id
            strip = lambda cands: [c.model_dump() for c in cands]  # noqa: E731
            assert strip(run_small.candidates) == strip(run_full.candidates)
            assert [c.chunk_id for c in bundle_small.chunks] == [
                c.chunk_id for c in bundle_full.chunks
            ]
            assert [c.provenance.model_dump() for c in bundle_small.chunks] == [
                c.provenance.model_dump() for c in bundle_full.chunks
            ]
            if mode == RetrievalMode.GRAPH_RAG:
                assert run_small.graph.seeds == run_full.graph.seeds
                assert run_small.graph.visited_assertion_ids == run_full.graph.visited_assertion_ids
                assert run_small.graph.limits_hit == run_full.graph.limits_hit
                assert bundle_small.structured_facts == bundle_full.structured_facts


def test_future_aliases_cannot_alter_past_entity_resolution(default_index):
    resolver = default_index.resolver
    before = utc(2024, 9, 1)
    after = utc(2024, 9, 19)
    # "recalibration" is a controlled alias admitted on 2024-09-18.
    assert resolver.resolve("Is a recalibration likely?", before).entity_ids() == []
    assert resolver.resolve("Is a recalibration likely?", after).entity_ids() == [
        "topic-policy-rate"
    ]
    assert resolver.resolve("SVB stress", utc(2023, 3, 1)).entity_ids() == []
    assert resolver.resolve("SVB stress", utc(2023, 3, 13)).entity_ids() == ["topic-banking-sector"]

    # A later remap (alias version 2) of an existing alias must not affect earlier cutoffs.
    remap = EntityAlias(
        alias_id=short_id("alias", {"test": "remap"}),
        entity_id="topic-financial-conditions",
        alias="banking stress",
        normalized_alias=alias_key("banking stress"),
        alias_version=2,
        available_at=utc(2024, 6, 1),
        status=AliasStatus.APPROVED,
        provenance="test remap",
    )
    entities = list(default_index.entities.values())
    aliases = [a for a in resolver._by_key.get(tuple(alias_key("banking stress").split()), [])]
    remapped = AliasResolver(aliases + [remap], entities)
    assert remapped.resolve("banking stress", utc(2023, 5, 1)).entity_ids() == [
        "topic-banking-sector"
    ]
    assert remapped.resolve("banking stress", utc(2024, 7, 1)).entity_ids() == [
        "topic-financial-conditions"
    ]


def test_policy_events_and_releases_are_not_visible_early(default_index):
    resolver = default_index.resolver
    assert resolver.resolve("March 2023 meeting", utc(2023, 3, 15)).entity_ids() == []
    assert resolver.resolve("March 2023 meeting", utc(2023, 3, 23)).entity_ids() == [
        "event-fomc-20230322"
    ]


def test_derived_assertions_inherit_latest_input_availability(home):
    by_id = {v.version_id: v for v in home.store.list_versions()}
    entities = {e.entity_id: e for e in home.store.list_entities()}
    chunks = {c.chunk_id: c for c in home.store.chunks_for_versions(by_id)}
    for assertion in home.store.list_assertions():
        times = []
        for input_id in assertion.input_ids:
            record = by_id.get(input_id) or entities.get(input_id) or chunks.get(input_id)
            assert record is not None, input_id
            times.append(record.available_at)
        assert assertion.available_at == max(times)
