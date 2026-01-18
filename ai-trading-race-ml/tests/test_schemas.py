"""Tests for Pydantic schemas."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.enums import SignalContribution, TradeSide
from app.models.schemas import (
    AgentContextRequest,
    AgentDecisionResponse,
    CandleData,
    ExplanationSignal,
    HealthResponse,
    PortfolioState,
    PositionData,
    SCHEMA_VERSION,
    TradeOrderResponse,
)


class TestSchemas:
    """Tests for Pydantic schema validation and serialization."""

    def test_candle_data_creation(self):
        """Test CandleData model creation."""
        candle = CandleData(
            symbol="BTC",
            timestamp=datetime.now(timezone.utc),
            open=Decimal("42000"),
            high=Decimal("42500"),
            low=Decimal("41500"),
            close=Decimal("42200"),
            volume=Decimal("1000"),
        )
        assert candle.symbol == "BTC"
        assert candle.close == Decimal("42200")

    def test_portfolio_state_with_positions(self):
        """Test PortfolioState with positions."""
        position = PositionData(
            symbol="BTC",
            quantity=Decimal("0.5"),
            average_price=Decimal("40000"),
        )
        portfolio = PortfolioState(
            cash=Decimal("5000"),
            positions=[position],
            total_value=Decimal("25000"),
        )
        assert portfolio.cash == Decimal("5000")
        assert len(portfolio.positions) == 1
        assert portfolio.positions[0].symbol == "BTC"

    def test_agent_context_request_defaults(self):
        """Test AgentContextRequest has proper defaults."""
        portfolio = PortfolioState(
            cash=Decimal("10000"),
            positions=[],
            total_value=Decimal("10000"),
        )
        context = AgentContextRequest(
            agent_id="test-agent",
            portfolio=portfolio,
            candles=[],
        )
        assert context.schema_version == SCHEMA_VERSION
        assert context.request_id is not None  # Auto-generated
        assert context.agent_id == "test-agent"
        assert context.instructions == ""

    def test_explanation_signal(self):
        """Test ExplanationSignal model."""
        signal = ExplanationSignal(
            feature="rsi_14",
            value=27.3,
            rule="<30 = oversold",
            fired=True,
            contribution=SignalContribution.BULLISH,
        )
        assert signal.feature == "rsi_14"
        assert signal.fired is True
        assert signal.contribution == SignalContribution.BULLISH

    def test_trade_order_response(self):
        """Test TradeOrderResponse model."""
        order = TradeOrderResponse(
            asset_symbol="ETH",
            side=TradeSide.BUY,
            quantity=Decimal("1.5"),
            limit_price=None,
        )
        assert order.asset_symbol == "ETH"
        assert order.side == TradeSide.BUY

    def test_agent_decision_response(self):
        """Test AgentDecisionResponse model."""
        response = AgentDecisionResponse(
            request_id="test-request-123",
            agent_id="test-agent",
            created_at=datetime.now(timezone.utc),
            orders=[],
            signals=[],
            reasoning="No signals",
        )
        assert response.schema_version == SCHEMA_VERSION
        assert response.orders == []
        assert response.reasoning == "No signals"

    def test_health_response(self):
        """Test HealthResponse model."""
        health = HealthResponse(
            status="healthy",
            model_loaded=True,
            model_version="1.0.0",
        )
        assert health.status == "healthy"
        assert health.schema_version == SCHEMA_VERSION
