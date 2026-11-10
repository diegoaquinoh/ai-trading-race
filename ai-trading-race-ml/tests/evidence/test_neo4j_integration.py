"""Neo4j backend: build, validate, publish, traverse, rebuild-compare (integration only).

Run with: ``NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=... pytest -m integration tests/evidence``
after ``docker compose --profile graph up -d neo4j``.
"""

from __future__ import annotations

import os

import pytest

from research_engine.knowledge.neo4j_store import TEMPLATES, Neo4jGraphStore, TemplateNotAllowed

pytestmark = pytest.mark.integration


@pytest.fixture()
def neo4j_store():
    uri = os.environ.get("NEO4J_URI")
    if not uri:
        pytest.skip("NEO4J_URI not set")
    store = Neo4jGraphStore(
        uri, os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "")
    )
    yield store
    store.close()


def test_only_allowlisted_templates_run(neo4j_store):
    with pytest.raises(TemplateNotAllowed):
        neo4j_store._run("MATCH (n) DETACH DELETE n")
    assert all("$" in t or "CREATE" in t for t in TEMPLATES.values())


def test_neo4j_build_validates_publishes_and_matches_rebuild(home, default_index, neo4j_store):
    from research_engine.contracts.decisions import RetrievalMode
    from research_engine.contracts.evidence import IndexBuildStatus, RetrievalRequest
    from research_engine.knowledge.graph_store import InMemoryGraphStore
    from research_engine.retrieval.index import load_index, rebuild_graph
    from research_engine.retrieval.service import retrieve

    from .conftest import utc

    build = default_index.build
    neo4j_store.drop(build.build_id)
    projection = rebuild_graph(home.store, build, neo4j_store)
    assert neo4j_store.status(build.build_id) == IndexBuildStatus.READY
    assert neo4j_store.membership(build.build_id) == projection.membership()
    memory = InMemoryGraphStore()
    rebuild_graph(home.store, build, memory)
    assert memory.membership(build.build_id) == neo4j_store.membership(build.build_id)

    index_neo = load_index(home.store, build.build_id, graph=neo4j_store)
    index_mem = load_index(home.store, build.build_id, graph=memory)
    request = RetrievalRequest(
        question="What did the minutes of the meeting before the May 2023 meeting say about the labor market?",
        decision_as_of=utc(2023, 5, 3, 23, 30),
        mode=RetrievalMode.GRAPH_RAG,
        index_build_id=build.build_id,
        permission_scope="neo4j-integration",
    )
    run_neo, bundle_neo = retrieve(request, home.store, index_neo, use_cache=False)
    run_mem, bundle_mem = retrieve(
        request.model_copy(update={"permission_scope": "memory-integration"}),
        home.store,
        index_mem,
        use_cache=False,
    )
    assert [c.chunk_id for c in bundle_neo.chunks] == [c.chunk_id for c in bundle_mem.chunks]
    assert run_neo.graph.visited_assertion_ids == run_mem.graph.visited_assertion_ids
    neo4j_store.drop(build.build_id)
