"""Authentication, problem+json errors, signing gate and capabilities shape."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.v1.engine import resolve_signing_key

from .conftest import make_engine


def test_internal_paths_require_api_key(client):
    for path in (
        "/internal/v1/capabilities",
        "/internal/v1/market/sessions?start=2024-03-01&end=2024-03-01",
    ):
        response = client.get(path, headers={"X-API-Key": ""})
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["code"] == "missing_api_key"
        wrong = client.get(path, headers={"X-API-Key": "wrong"})
        assert wrong.status_code == 401
        assert wrong.json()["code"] == "invalid_api_key"


def test_health_stays_public(client):
    response = client.get("/health", headers={"X-API-Key": ""})
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_unknown_internal_path_is_problem_json(client):
    response = client.get("/internal/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_capabilities_shape(client):
    response = client.get("/internal/v1/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["engineVersion"].startswith("research-engine/")
    assert body["ready"] is True
    assert body["schemaVersions"] == ["1.0"]
    numerical = body["numerical"]
    assert numerical["quantlibVersion"]
    assert numerical["library"].startswith("QuantLib")
    assert numerical["conventionsVersion"] == "usd-treasury-conventions-v1"
    assert numerical["eventPriorityTable"] == "event-priority-v1"
    assert body["curveDataset"]["dataMode"] == "synthetic_curve"
    assert body["curveDataset"]["coverage"]["observedSessions"] > 400
    evidence = body["evidence"]
    assert evidence["ready"] is True
    assert evidence["readyIndexBuilds"]
    build = evidence["readyIndexBuilds"][0]
    assert build["status"] == "READY" and build["evidenceSnapshotId"].startswith("evs-")
    assert build["evidenceSnapshotId"] in evidence["evidenceSnapshotIds"]
    assert evidence["sources"][0]["sourceId"] == "fed-fomc"
    assert evidence["sources"][0]["lastIngestion"]["outcome"]
    ids = {s["strategyId"] for s in body["strategies"]}
    assert {"cash", "static_ladder", "quant_duration"} <= ids
    providers = body["providers"]
    assert providers["configured"] == "reference"
    assert body["signing"]["configured"] is True
    assert body["concurrency"]["maxConcurrentDecisions"] == 2
    text = json.dumps(body).lower()
    for secret in ("test-api-v1-signing-key", "test-secret-key", 'api_key":', "apikey"):
        assert secret not in text


def test_signing_key_required_outside_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    key, configured, error = resolve_signing_key(Settings(signing_key=""))
    assert key is None and configured is False and "ML_SERVICE_SIGNING_KEY" in error
    monkeypatch.setenv("ENVIRONMENT", "development")
    key, configured, error = resolve_signing_key(Settings(signing_key=""))
    assert key and configured is False and error is None
    key, configured, _ = resolve_signing_key(Settings(signing_key="abc"))
    assert key == b"abc" and configured is True


def test_internal_endpoints_refuse_without_signing_key(ports, client_for):
    pricing, market = ports
    unsigned = make_engine(pricing, market, signing_key=None)
    client = client_for(unsigned)
    response = client.get(
        "/internal/v1/market/sessions", params={"start": "2024-03-01", "end": "2024-03-01"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "signing_not_configured"
    capabilities = client.get("/internal/v1/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["ready"] is False
    unsigned.shutdown()


def test_lifespan_does_not_build_engine_when_overridden(engine):
    from app.v1.engine import get_engine

    app.dependency_overrides[get_engine] = lambda: engine
    try:
        with TestClient(app):
            assert app.state.research_engine is None
    finally:
        app.dependency_overrides.pop(get_engine, None)
