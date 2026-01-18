"""Tests for FastAPI endpoints."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_200(self, client):
        """Test health endpoint returns 200."""
        response = client.get("/health")
        
        assert response.status_code == 200

    def test_health_returns_schema_version(self, client):
        """Test health response includes schema version."""
        response = client.get("/health")
        data = response.json()
        
        assert "schemaVersion" in data
        assert data["status"] == "healthy"

    def test_health_no_auth_required(self, client):
        """Test health endpoint doesn't require API key."""
        response = client.get("/health")
        
        assert response.status_code == 200


class TestPredictEndpoint:
    """Tests for /predict endpoint."""

    def get_valid_context(self) -> dict:
        """Create a valid request context."""
        return {
            "agentId": "test-agent",
            "portfolio": {
                "cash": "10000",
                "positions": [],
                "totalValue": "10000",
            },
            "candles": [
                {
                    "symbol": "BTC",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "open": "42000",
                    "high": "42500",
                    "low": "41500",
                    "close": "42200",
                    "volume": "1000",
                }
                for _ in range(25)  # Need enough for indicators
            ],
            "instructions": "",
        }

    def test_predict_returns_decision(self, client):
        """Test predict endpoint returns a decision."""
        context = self.get_valid_context()
        response = client.post("/predict", json=context)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "agentId" in data
        assert "orders" in data
        assert "signals" in data
        assert "reasoning" in data

    def test_predict_includes_schema_version(self, client):
        """Test response includes schema version."""
        context = self.get_valid_context()
        response = client.post("/predict", json=context)
        data = response.json()
        
        assert "schemaVersion" in data
        assert "modelVersion" in data
        assert "requestId" in data

    def test_predict_invalid_request(self, client):
        """Test predict with invalid request returns 422."""
        response = client.post("/predict", json={"invalid": "data"})
        
        assert response.status_code == 422

    def test_predict_empty_candles(self, client):
        """Test predict with empty candles returns response."""
        context = {
            "agentId": "test-agent",
            "portfolio": {
                "cash": "10000",
                "positions": [],
                "totalValue": "10000",
            },
            "candles": [],  # Empty candles
        }
        response = client.post("/predict", json=context)
        
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []  # No trades with no data
