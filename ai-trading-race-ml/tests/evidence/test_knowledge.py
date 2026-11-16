"""Ontology, lexicon extraction spans, alias review, epistemic boundaries."""

from __future__ import annotations

import pytest

from research_engine.contracts.evidence import (
    AssertionStatus,
    GraphNode,
    NodeType,
    RelationType,
)
from research_engine.knowledge.ontology import (
    RELATION_SIGNATURES,
    OntologyViolation,
    assert_no_portfolio_state,
    check_assertion,
)
from research_engine.knowledge.vocabulary import load_releases

from .conftest import utc


def test_every_assertion_matches_the_ontology(home):
    assertions = home.store.list_assertions()
    assert assertions
    relations = {a.relation for a in assertions}
    for relation in (
        RelationType.PUBLISHED_BY,
        RelationType.DOCUMENTS_EVENT,
        RelationType.HAS_CHUNK,
        RelationType.MENTIONS_TOPIC,
        RelationType.REFERS_TO_SERIES,
        RelationType.RELEASE_OF,
        RelationType.PREVIOUS_EVENT,
        RelationType.SUPERSEDES,
    ):
        assert relation in relations, relation
    for assertion in assertions:
        check_assertion(assertion)
        assert (assertion.subject_type, assertion.object_type) == RELATION_SIGNATURES[
            assertion.relation
        ]


def test_lexicon_support_spans_are_exact_quotes(home):
    chunks = {
        c.chunk_id: c
        for c in home.store.chunks_for_versions(v.version_id for v in home.store.list_versions())
    }
    lexicon = [a for a in home.store.list_assertions() if a.extraction_method == "rule_lexicon_v1"]
    assert lexicon
    for assertion in lexicon:
        for span in assertion.support:
            assert span.kind == "chunk_span"
            text = chunks[span.chunk_id].text
            assert text[span.start_offset : span.end_offset] == span.quote


def test_ambiguous_patterns_go_to_review_and_are_never_traversed(home, default_index):
    review = [
        a
        for a in home.store.list_assertions()
        if a.validation_status == AssertionStatus.REVIEW_REQUIRED
    ]
    assert review  # e.g. bare "PCE" without "price"
    assert all(float(a.confidence) < 0.9 for a in review)
    graph = default_index.require_graph()
    from research_engine.knowledge.ontology import Direction

    edges = graph.edges(
        default_index.build_id,
        "series-pce-price",
        [(RelationType.REFERS_TO_SERIES, Direction.IN)],
        utc(2025, 1, 1),
    )
    assert all(e.assertion.validation_status == AssertionStatus.APPROVED for e in edges)


def test_ambiguous_alias_routes_to_review(default_index):
    resolution = default_index.resolver.resolve("What happened to PCE?", utc(2024, 1, 1))
    assert resolution.matches == ()
    assert resolution.review and "pce" in resolution.review[0]


def test_previous_event_chain_and_release_dates(home):
    previous = [
        a for a in home.store.list_assertions() if a.relation == RelationType.PREVIOUS_EVENT
    ]
    assert len(previous) == 15
    link = next(a for a in previous if a.subject_id == "event-fomc-20230322")
    assert link.object_id == "event-fomc-20230201"
    releases = load_releases()
    assert len(releases) == 24
    assert releases[0].published_at == utc(2023, 1, 12, 13, 30)  # 08:30 EST
    assert releases[5].published_at == utc(2023, 6, 13, 12, 30)  # 08:30 EDT


def test_graph_never_stores_portfolio_state(default_index):
    graph = default_index.require_graph()
    nodes = list(graph.projection(default_index.build_id).nodes.values())
    assert_no_portfolio_state(nodes)
    with pytest.raises(OntologyViolation):
        assert_no_portfolio_state(
            [
                GraphNode(
                    node_id="x",
                    node_type=NodeType.INSTRUMENT,
                    label="x",
                    available_at=utc(2024, 1, 1),
                    properties={"position_face": "1000"},
                )
            ]
        )


def test_no_causal_rule_relations_exist():
    # The ontology has no relation that could encode "X causes price move Y".
    assert not any("CAUS" in r.value or "IMPLIES" in r.value for r in RelationType)
