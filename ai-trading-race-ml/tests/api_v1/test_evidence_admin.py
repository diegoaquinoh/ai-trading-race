"""Evidence retrieval, bundles, chunks, graph provenance, research notes and admin jobs."""

from __future__ import annotations

import json

from app.v1.engine import evidence_snapshot_id

from .helpers import post_json

AS_OF = "2024-02-01T00:00:00Z"


def snapshot_of(engine) -> str:
    index = engine.evidence.indexes[engine.evidence.active_build_id]
    return evidence_snapshot_id(index.build.member_version_ids)


def retrieve(client, engine, **overrides):
    body = {
        "schemaVersion": "1.0",
        "requestId": "ev-1",
        "query": "inflation outlook and the federal funds rate target range",
        "asOf": AS_OF,
        "evidenceSnapshotId": snapshot_of(engine),
        "retrievalMode": "hybrid_rag_v1",
        "maxChunks": 6,
    }
    body.update(overrides)
    return post_json(client, "/internal/v1/evidence/retrieve", body)


def test_retrieve_respects_cutoff(client, engine):
    response = retrieve(client, engine)
    assert response.status_code == 200, response.text
    body = response.json()
    bundle = body["bundle"]
    assert body["evidenceSnapshotId"] == snapshot_of(engine)
    assert 0 < bundle["chunkCount"] <= 6
    for chunk in bundle["chunks"]:
        assert chunk["availableAt"] <= AS_OF
    assert body["retrievalRun"]["bundleId"] == bundle["bundleId"]
    again = retrieve(client, engine)
    assert again.json()["bundle"]["bundleId"] == bundle["bundleId"]


def test_retrieve_validation(client, engine):
    assert retrieve(client, engine, requestId="ev-2", maxChunks=50).status_code == 422
    assert retrieve(client, engine, requestId="ev-3", asOf="2024-02-01").status_code == 422
    response = retrieve(client, engine, requestId="ev-4", evidenceSnapshotId="evs-unknown")
    assert response.status_code == 404
    response = retrieve(client, engine, requestId="ev-5", indexBuildId="ib-unknown")
    assert response.status_code == 404
    response = retrieve(client, engine, requestId="ev-1", query="something else entirely")
    assert response.status_code == 409


def test_bundle_chunk_and_graph(client, engine):
    body = retrieve(
        client,
        engine,
        requestId="ev-graph",
        retrievalMode="graph_rag_v1",
        maxChunks=8,
        query="FOMC statement on the target range for the federal funds rate and inflation",
    ).json()
    bundle = body["bundle"]
    bundle_id = bundle["bundleId"]

    paged = client.get(
        f"/internal/v1/evidence/bundles/{bundle_id}", params={"page": 1, "pageSize": 2}
    )
    assert paged.status_code == 200
    page = paged.json()
    assert page["totalChunks"] == bundle["chunkCount"] and len(page["chunks"]) <= 2
    assert client.get("/internal/v1/evidence/bundles/bundle-nope").status_code == 404

    chunk_id = bundle["chunks"][0]["chunkId"]
    chunk = client.get(f"/internal/v1/evidence/chunks/{chunk_id}").json()
    assert chunk["text"] == bundle["chunks"][0]["text"]
    assert chunk["endOffset"] - chunk["startOffset"] == len(chunk["text"])
    version = chunk["documentVersion"]
    for key in ("title", "sourceUrl", "publishedAt", "availableAt", "status", "fidelityFlags"):
        assert key in version
    assert client.get("/internal/v1/evidence/chunks/chk-nope").status_code == 404

    graph = client.get("/internal/v1/evidence/graph", params={"bundleId": bundle_id})
    assert graph.status_code == 200, graph.text
    doc = graph.json()
    assert doc["mode"] == "graph_rag_v1"
    assert len(doc["nodes"]) <= doc["limits"]["maxNodes"]
    node_ids = {n["nodeId"] for n in doc["nodes"]}
    for node in doc["nodes"]:
        assert node["availableAt"] <= doc["decisionAsOf"]
    for edge in doc["edges"]:
        assert edge["availableAt"] <= doc["decisionAsOf"]
        assert edge["subjectId"] in node_ids and edge["objectId"] in node_ids
        assert edge["extractionMethod"]
    text = json.dumps(doc).lower()
    for forbidden in ("cashusd", "positions", "holdings", "dv01"):
        assert forbidden not in text
    assert client.get("/internal/v1/evidence/graph", params={"bundleId": "nope"}).status_code == 404


def test_research_note_has_no_order_authority(client, engine):
    response = post_json(
        client,
        "/internal/v1/research-notes",
        {
            "schemaVersion": "1.0",
            "requestId": "note-1",
            "question": "What did the FOMC say about inflation?",
            "asOf": AS_OF,
            "retrievalMode": "hybrid_rag_v1",
            "responseMode": "recorded_replay",
            "requestedBy": "analyst@example.test",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["orderAuthority"] is False
    note = body["researchNote"]
    assert note["status"] in ("supported", "insufficient_evidence", "contradictory_evidence")
    text = json.dumps(body)
    assert "targetWeights" not in text and "proposal" not in body
    assert body["status"] in ("completed", "insufficient_evidence", "contradictory_evidence")
    for citation in note["citations"]:
        assert citation["bundleId"] in body["bundleIds"]
    if "result" in body:
        assert body["result"]["orderAuthority"] is False
        from .helpers import verify_signed

        verify_signed(body["result"], "resultHash")


def test_admin_jobs(client, engine):
    request = {
        "schemaVersion": "1.0",
        "requestId": "ingest-1",
        "sourceIds": ["fed-fomc"],
        "reason": "test",
    }
    response = post_json(client, "/internal/v1/admin/ingestions", request)
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["state"] in ("queued", "running", "completed")
    finished = engine.jobs.wait(job["jobId"])
    assert finished.state.value == "completed", finished.error
    status = client.get(f"/internal/v1/admin/jobs/{job['jobId']}").json()
    assert status["state"] == "completed"
    assert status["result"]["sources"][0]["mode"] == "offline_fixture"
    again = post_json(client, "/internal/v1/admin/ingestions", request)
    assert again.status_code == 200 and again.json()["jobId"] == job["jobId"]
    changed = post_json(client, "/internal/v1/admin/ingestions", {**request, "reason": "other"})
    assert changed.status_code == 409
    bad = post_json(
        client,
        "/internal/v1/admin/ingestions",
        {**request, "requestId": "ingest-2", "sourceIds": ["web"]},
    )
    assert bad.status_code == 422
    assert client.get("/internal/v1/admin/jobs/job-nope").status_code == 404


def test_index_build_jobs(client, engine):
    validate = post_json(
        client,
        "/internal/v1/admin/index-builds",
        {"schemaVersion": "1.0", "requestId": "validate-1", "validateOnly": True},
    )
    assert validate.status_code == 202
    done = engine.jobs.wait(validate.json()["jobId"])
    assert done.state.value == "completed", (done.error, done.result)
    assert done.result["valid"] is True
    build = post_json(
        client,
        "/internal/v1/admin/index-builds",
        {"schemaVersion": "1.0", "requestId": "build-1", "evidenceSnapshotId": snapshot_of(engine)},
    )
    assert build.status_code == 202
    done = engine.jobs.wait(build.json()["jobId"])
    assert done.state.value == "completed", (done.error, done.result)
    assert done.result["status"] == "READY"
    assert done.result["buildId"] in engine.evidence.indexes
    missing = post_json(
        client,
        "/internal/v1/admin/index-builds",
        {"schemaVersion": "1.0", "requestId": "build-2", "evidenceSnapshotId": "evs-missing"},
    )
    failed = engine.jobs.wait(missing.json()["jobId"])
    assert failed.state.value == "failed"
