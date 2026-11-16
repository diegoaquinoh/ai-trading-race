"""The committed OpenAPI document matches the internal API (contracts/openapi)."""

from __future__ import annotations

import json

from app.main import app
from app.v1.openapi_models import DEFAULT_EXPORT, internal_openapi

EXPECTED_PATHS = {
    "/internal/v1/simulation/transitions",
    "/internal/v1/simulation/bootstrap-allocation",
    "/internal/v1/strategies/decisions",
    "/internal/v1/analytics/price",
    "/internal/v1/analytics/risk",
    "/internal/v1/analytics/performance",
    "/internal/v1/evidence/retrieve",
    "/internal/v1/evidence/bundles/{bundle_id}",
    "/internal/v1/evidence/chunks/{chunk_id}",
    "/internal/v1/evidence/graph",
    "/internal/v1/research-notes",
    "/internal/v1/admin/ingestions",
    "/internal/v1/admin/index-builds",
    "/internal/v1/admin/jobs/{job_id}",
    "/internal/v1/capabilities",
    "/internal/v1/instruments",
    "/internal/v1/instruments/{security_id}/valuation",
    "/internal/v1/instruments/payment-calendar",
    "/internal/v1/curves/{snapshot_id}",
    "/internal/v1/market/sessions",
}


def test_internal_openapi_covers_every_endpoint():
    doc = internal_openapi(app)
    assert set(doc["paths"]) == EXPECTED_PATHS
    schemas = doc["components"]["schemas"]
    assert "TransitionProposal" in schemas and "StrategyResult" in schemas
    assert "portfolioId" in schemas["PortfolioState"]["properties"]  # contract, not legacy
    assert doc["security"] == [{"ApiKey": []}]


def test_committed_openapi_is_current():
    """Regenerate with ``python -m app.v1.openapi_models`` after changing the API."""
    committed = json.loads(DEFAULT_EXPORT.read_text())
    assert committed == json.loads(json.dumps(internal_openapi(app), sort_keys=True))
