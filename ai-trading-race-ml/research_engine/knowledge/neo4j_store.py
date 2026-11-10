"""Neo4j graph-store backend (optional ``graph`` profile; spec 5.4, 12, 18.4).

* Python is the sole writer. Only the parameterized Cypher templates in
  ``TEMPLATES`` can run (``_run`` rejects anything else); labels and the
  relationship type are fixed, all values are parameters. No generated Cypher.
* Every node/relationship carries ``build_id``; a ``FiBuild`` node holds the
  status. Reads require ``status = 'READY'``, which is set only by ``publish``
  after ``validate`` compares membership and content with the canonical
  projection. A partially written build is never visible as READY.
* Typed ontology relations are stored as ``FI_ASSERTION`` relationships with a
  ``relation`` property (relationship types cannot be parameterized safely).
* Pinned image: ``neo4j:5.26-community`` (docker-compose profile ``graph``),
  Python driver 5.x.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from research_engine.contracts.common import canonical_json
from research_engine.contracts.evidence import (
    GraphNode,
    IndexBuildStatus,
    RelationshipAssertion,
    RelationType,
)

from .graph_store import Edge, GraphProjection, GraphRetrievalUnavailable
from .ontology import Direction, check_assertion

TEMPLATES: dict[str, str] = {
    "constraint_build": (
        "CREATE CONSTRAINT fi_build_id IF NOT EXISTS FOR (b:FiBuild) REQUIRE b.build_id IS UNIQUE"
    ),
    "index_node": (
        "CREATE INDEX fi_node_build IF NOT EXISTS FOR (n:FiNode) ON (n.build_id, n.node_id)"
    ),
    "begin_build": (
        "MERGE (b:FiBuild {build_id: $build_id}) "
        "ON CREATE SET b.status = 'BUILDING', b.schema_version = $schema_version "
        "RETURN b.status AS status"
    ),
    "write_nodes": (
        "MATCH (b:FiBuild {build_id: $build_id, status: 'BUILDING'}) "
        "UNWIND $rows AS r "
        "CREATE (n:FiNode {build_id: $build_id, node_id: r.node_id, node_type: r.node_type, "
        "available_epoch: r.available_epoch, payload: r.payload})"
    ),
    "write_assertions": (
        "MATCH (b:FiBuild {build_id: $build_id, status: 'BUILDING'}) "
        "UNWIND $rows AS r "
        "MATCH (s:FiNode {build_id: $build_id, node_id: r.subject_id}) "
        "MATCH (o:FiNode {build_id: $build_id, node_id: r.object_id}) "
        "CREATE (s)-[:FI_ASSERTION {build_id: $build_id, assertion_id: r.assertion_id, "
        "relation: r.relation, status: r.status, available_epoch: r.available_epoch, "
        "payload: r.payload}]->(o)"
    ),
    "read_nodes": (
        "MATCH (n:FiNode {build_id: $build_id}) RETURN n.node_id AS id, n.payload AS payload"
    ),
    "read_assertions": (
        "MATCH (:FiNode {build_id: $build_id})-[r:FI_ASSERTION {build_id: $build_id}]->() "
        "RETURN r.assertion_id AS id, r.payload AS payload"
    ),
    "publish": (
        "MATCH (b:FiBuild {build_id: $build_id, status: 'BUILDING'}) "
        "SET b.status = 'READY' RETURN b.status AS status"
    ),
    "fail": (
        "MATCH (b:FiBuild {build_id: $build_id, status: 'BUILDING'}) "
        "SET b.status = 'FAILED', b.error = $error"
    ),
    "status": "MATCH (b:FiBuild {build_id: $build_id}) RETURN b.status AS status",
    "node": (
        "MATCH (b:FiBuild {build_id: $build_id, status: 'READY'}) "
        "MATCH (n:FiNode {build_id: $build_id, node_id: $node_id}) RETURN n.payload AS payload"
    ),
    "edges_out": (
        "MATCH (b:FiBuild {build_id: $build_id, status: 'READY'}) "
        "MATCH (s:FiNode {build_id: $build_id, node_id: $node_id})"
        "-[r:FI_ASSERTION {build_id: $build_id}]->(o:FiNode {build_id: $build_id}) "
        "WHERE r.relation = $relation AND r.status = 'approved' "
        "AND r.available_epoch <= $cutoff AND o.available_epoch <= $cutoff "
        "RETURN r.payload AS assertion, o.payload AS node "
        "ORDER BY o.node_id, r.assertion_id LIMIT $limit"
    ),
    "edges_in": (
        "MATCH (b:FiBuild {build_id: $build_id, status: 'READY'}) "
        "MATCH (o:FiNode {build_id: $build_id, node_id: $node_id})"
        "<-[r:FI_ASSERTION {build_id: $build_id}]-(s:FiNode {build_id: $build_id}) "
        "WHERE r.relation = $relation AND r.status = 'approved' "
        "AND r.available_epoch <= $cutoff AND s.available_epoch <= $cutoff "
        "RETURN r.payload AS assertion, s.payload AS node "
        "ORDER BY s.node_id, r.assertion_id LIMIT $limit"
    ),
    "drop_nodes": "MATCH (n:FiNode {build_id: $build_id}) DETACH DELETE n",
    "drop_build": "MATCH (b:FiBuild {build_id: $build_id}) DELETE b",
}

EDGE_READ_LIMIT = 2000  # hard cap per expansion; retrieval applies fanout afterwards
BATCH = 500


class TemplateNotAllowed(ValueError):
    pass


def _epoch(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp())


class Neo4jGraphStore:
    backend_name = "neo4j-5-v1"

    def __init__(self, uri: str, user: str, password: str, database: Optional[str] = None):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - dependency present in the venv
            raise GraphRetrievalUnavailable("neo4j driver not installed") from exc
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database
        self._run("constraint_build")
        self._run("index_node")

    def close(self) -> None:
        self._driver.close()

    def _run(self, template: str, **params: Any) -> list[dict[str, Any]]:
        if template not in TEMPLATES:
            raise TemplateNotAllowed(template)
        try:
            with self._driver.session(database=self._database) as session:
                result = session.run(TEMPLATES[template], **params)
                return [record.data() for record in result]
        except TemplateNotAllowed:
            raise
        except Exception as exc:  # driver/service errors are explicit graph failures
            raise GraphRetrievalUnavailable(f"neo4j {template} failed: {exc}") from exc

    def begin_build(self, build_id: str, schema_version: str) -> None:
        rows = self._run("begin_build", build_id=build_id, schema_version=schema_version)
        if rows and rows[0]["status"] != IndexBuildStatus.BUILDING.value:
            raise RuntimeError(f"graph build {build_id} already {rows[0]['status']}")

    def write(self, build_id: str, projection: GraphProjection) -> None:
        nodes = [
            {
                "node_id": n.node_id,
                "node_type": n.node_type.value,
                "available_epoch": _epoch(n.available_at),
                "payload": canonical_json(n.to_wire()),
            }
            for n in sorted(projection.nodes.values(), key=lambda n: n.node_id)
        ]
        for start in range(0, len(nodes), BATCH):
            self._run("write_nodes", build_id=build_id, rows=nodes[start : start + BATCH])
        rows = []
        for a in sorted(projection.assertions.values(), key=lambda a: a.assertion_id):
            check_assertion(a)
            rows.append(
                {
                    "assertion_id": a.assertion_id,
                    "subject_id": a.subject_id,
                    "object_id": a.object_id,
                    "relation": a.relation.value,
                    "status": a.validation_status.value,
                    "available_epoch": _epoch(a.available_at),
                    "payload": canonical_json(a.to_wire()),
                }
            )
        for start in range(0, len(rows), BATCH):
            self._run("write_assertions", build_id=build_id, rows=rows[start : start + BATCH])

    def _read(self, build_id: str) -> GraphProjection:
        proj = GraphProjection()
        for row in self._run("read_nodes", build_id=build_id):
            proj.nodes[row["id"]] = GraphNode.model_validate(json.loads(row["payload"]))
        for row in self._run("read_assertions", build_id=build_id):
            proj.assertions[row["id"]] = RelationshipAssertion.model_validate(
                json.loads(row["payload"])
            )
        return proj

    def validate(self, build_id: str, expected: GraphProjection) -> list[str]:
        stored = self._read(build_id)
        problems: list[str] = []
        if stored.membership() != expected.membership():
            problems.append("membership differs from canonical projection")
        elif stored.content_hash() != expected.content_hash():
            problems.append("graph content hash differs from canonical projection")
        return problems

    def publish(self, build_id: str) -> None:
        if not self._run("publish", build_id=build_id):
            raise RuntimeError(f"graph build {build_id} is not BUILDING")

    def fail(self, build_id: str, error: str) -> None:
        self._run("fail", build_id=build_id, error=error)

    def status(self, build_id: str) -> Optional[IndexBuildStatus]:
        rows = self._run("status", build_id=build_id)
        return IndexBuildStatus(rows[0]["status"]) if rows else None

    def membership(self, build_id: str) -> tuple[frozenset[str], frozenset[str]]:
        return self._read(build_id).membership()

    def node(self, build_id: str, node_id: str) -> Optional[GraphNode]:
        if self.status(build_id) != IndexBuildStatus.READY:
            raise GraphRetrievalUnavailable(f"graph build {build_id} is not READY")
        rows = self._run("node", build_id=build_id, node_id=node_id)
        return GraphNode.model_validate(json.loads(rows[0]["payload"])) if rows else None

    def edges(
        self,
        build_id: str,
        node_id: str,
        steps: Iterable[tuple[RelationType, Direction]],
        cutoff: datetime,
    ) -> list[Edge]:
        if self.status(build_id) != IndexBuildStatus.READY:
            raise GraphRetrievalUnavailable(f"graph build {build_id} is not READY")
        out: list[Edge] = []
        for relation, direction in steps:
            template = "edges_out" if direction == Direction.OUT else "edges_in"
            for row in self._run(
                template,
                build_id=build_id,
                node_id=node_id,
                relation=relation.value,
                cutoff=_epoch(cutoff),
                limit=EDGE_READ_LIMIT,
            ):
                assertion = RelationshipAssertion.model_validate(json.loads(row["assertion"]))
                neighbor = GraphNode.model_validate(json.loads(row["node"]))
                # Second-precision epochs in Cypher; re-check exact instants in Python.
                if assertion.available_at > cutoff or neighbor.available_at > cutoff:
                    continue
                out.append(Edge(assertion, neighbor, direction))
        out.sort(
            key=lambda e: (e.assertion.relation.value, e.neighbor.node_id, e.assertion.assertion_id)
        )
        return out

    def drop(self, build_id: str) -> None:
        self._run("drop_nodes", build_id=build_id)
        self._run("drop_build", build_id=build_id)
