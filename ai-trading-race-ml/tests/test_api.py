"""Tests for FastAPI endpoints."""

import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

# Set test API key before importing app (settings reads env at import time)
os.environ.setdefault("ML_SERVICE_API_KEY", "test-secret-key")

from app.main import app

TEST_API_KEY = os.environ["ML_SERVICE_API_KEY"]


@pytest.fixture
def client():
    """Create a test client with proper lifespan initialization."""
    with TestClient(app) as c:
        yield c


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
        """Create a valid request context with realistic candle data."""
        base_time = datetime.now(timezone.utc) - timedelta(days=30)
        base_price = 42000
        candles = []
        
        for i in range(30):
            # Create varying prices to generate meaningful indicators
            price_change = 1 + (0.01 * ((i % 5) - 2))  # Oscillate between -2% and +2%
            current_price = base_price * price_change
            
            candles.append({
                "symbol": "BTC",
                "timestamp": (base_time + timedelta(days=i)).isoformat(),
                "open": str(current_price),
                "high": str(current_price * 1.01),
                "low": str(current_price * 0.99),
                "close": str(current_price * (1 + 0.005 * ((i % 3) - 1))),
                "volume": str(1000 + i * 10),
            })
        
        return {
            "agentId": "test-agent",
            "portfolio": {
                "cash": "10000",
                "positions": [],
                "totalValue": "10000",
            },
            "candles": candles,
            "instructions": "",
        }

    def test_predict_returns_decision(self, client):
        """Test predict endpoint returns a decision."""
        context = self.get_valid_context()
        response = client.post("/predict", json=context, headers={"X-API-Key": TEST_API_KEY})
        
        assert response.status_code == 200
        data = response.json()
        
        assert "agentId" in data
        assert "orders" in data
        assert "signals" in data
        assert "reasoning" in data

    def test_predict_includes_schema_version(self, client):
        """Test response includes schema version."""
        context = self.get_valid_context()
        response = client.post("/predict", json=context, headers={"X-API-Key": TEST_API_KEY})
        data = response.json()
        
        assert "schemaVersion" in data
        assert "modelVersion" in data
        assert "requestId" in data

    def test_predict_invalid_request(self, client):
        """Test predict with invalid request returns 422."""
        response = client.post("/predict", json={"invalid": "data"}, headers={"X-API-Key": TEST_API_KEY})
        
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
        response = client.post("/predict", json=context, headers={"X-API-Key": TEST_API_KEY})

        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []  # No trades with no data
