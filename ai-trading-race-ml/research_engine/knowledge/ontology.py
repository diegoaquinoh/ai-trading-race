"""Graph ontology ``fi-graph-v1`` (spec 12.1, 12.2).

The graph stores sourced facts and discovery relationships only. It never
stores holdings, cash, orders, weights or numerical risk snapshots, and it never
stores inferred causal rules ("hawkish statement causes bond prices to fall") as
facts. ``assert_no_portfolio_state`` enforces the property-key boundary.
"""

from __future__ import annotations

from enum import Enum

from research_engine.contracts.evidence import (
    GraphNode,
    NodeType,
    RelationshipAssertion,
    RelationType,
)

GRAPH_SCHEMA_VERSION = "fi-graph-v1"


class Direction(str, Enum):
    OUT = "out"  # subject -> object
    IN = "in"  # object <- subject


# relation -> (subject type, object type)
RELATION_SIGNATURES: dict[RelationType, tuple[NodeType, NodeType]] = {
    RelationType.PUBLISHED_BY: (NodeType.DOCUMENT_VERSION, NodeType.INSTITUTION),
    RelationType.AUTHORED_BY: (NodeType.DOCUMENT_VERSION, NodeType.PERSON),
    RelationType.DOCUMENTS_EVENT: (NodeType.DOCUMENT_VERSION, NodeType.POLICY_EVENT),
    RelationType.HAS_CHUNK: (NodeType.DOCUMENT_VERSION, NodeType.CHUNK),
    RelationType.MENTIONS_TOPIC: (NodeType.CHUNK, NodeType.MACRO_TOPIC),
    RelationType.REFERS_TO_SERIES: (NodeType.CHUNK, NodeType.MACRO_SERIES),
    RelationType.RELEASE_OF: (NodeType.MACRO_RELEASE, NodeType.MACRO_SERIES),
    RelationType.REFERS_TO_INSTRUMENT: (NodeType.CHUNK, NodeType.INSTRUMENT),
    RelationType.ISSUED_BY: (NodeType.INSTRUMENT, NodeType.INSTITUTION),
    RelationType.PREVIOUS_EVENT: (NodeType.POLICY_EVENT, NodeType.POLICY_EVENT),
    RelationType.SUPERSEDES: (NodeType.DOCUMENT_VERSION, NodeType.DOCUMENT_VERSION),
}

# Approved traversal steps for graph-assisted retrieval. HAS_CHUNK is structural
# materialization and does not count towards semantic depth. PUBLISHED_BY is
# metadata only: the publisher is a hub and is never expanded.
TRAVERSAL_STEPS: dict[NodeType, tuple[tuple[RelationType, Direction], ...]] = {
    NodeType.POLICY_EVENT: (
        (RelationType.DOCUMENTS_EVENT, Direction.IN),
        (RelationType.PREVIOUS_EVENT, Direction.OUT),
        (RelationType.PREVIOUS_EVENT, Direction.IN),
    ),
    NodeType.DOCUMENT_VERSION: (
        (RelationType.DOCUMENTS_EVENT, Direction.OUT),
        (RelationType.SUPERSEDES, Direction.OUT),
        (RelationType.SUPERSEDES, Direction.IN),
    ),
    NodeType.MACRO_TOPIC: ((RelationType.MENTIONS_TOPIC, Direction.IN),),
    NodeType.MACRO_SERIES: (
        (RelationType.REFERS_TO_SERIES, Direction.IN),
        (RelationType.RELEASE_OF, Direction.IN),
    ),
    NodeType.MACRO_RELEASE: ((RelationType.RELEASE_OF, Direction.OUT),),
    NodeType.CHUNK: (),
    NodeType.INSTITUTION: (),
    NodeType.PERSON: (),
    NodeType.INSTRUMENT: (),
}

# Lower value = expanded first when ordering neighbours (stable, never degree-based).
RELATION_ORDER: dict[RelationType, int] = {
    RelationType.DOCUMENTS_EVENT: 0,
    RelationType.PREVIOUS_EVENT: 1,
    RelationType.SUPERSEDES: 2,
    RelationType.MENTIONS_TOPIC: 3,
    RelationType.REFERS_TO_SERIES: 4,
    RelationType.RELEASE_OF: 5,
    RelationType.HAS_CHUNK: 6,
    RelationType.PUBLISHED_BY: 7,
    RelationType.AUTHORED_BY: 8,
    RelationType.REFERS_TO_INSTRUMENT: 9,
    RelationType.ISSUED_BY: 10,
}

FORBIDDEN_PROPERTY_FRAGMENTS = (
    "holding",
    "position",
    "cash",
    "order",
    "weight",
    "dv01",
    "duration",
    "pnl",
    "nav",
    "portfolio",
    "exposure",
)


class OntologyViolation(ValueError):
    pass


def check_assertion(assertion: RelationshipAssertion) -> None:
    expected = RELATION_SIGNATURES[assertion.relation]
    if (assertion.subject_type, assertion.object_type) != expected:
        raise OntologyViolation(
            f"{assertion.relation.value} requires {expected[0].value}->{expected[1].value}, "
            f"got {assertion.subject_type.value}->{assertion.object_type.value}"
        )
    if not assertion.support:
        raise OntologyViolation(f"assertion {assertion.assertion_id} has no support")


def assert_no_portfolio_state(nodes: list[GraphNode]) -> None:
    """Spec 12.2: portfolio/risk state stays in canonical application stores."""
    for node in nodes:
        for key in node.properties:
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_PROPERTY_FRAGMENTS):
                raise OntologyViolation(f"node {node.node_id} carries forbidden property {key!r}")
