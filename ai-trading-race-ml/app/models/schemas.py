"""Pydantic schemas for API contracts with contract versioning and explainability."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import settings
from app.models.enums import SignalContribution, TradeSide

# API Schema version for contract evolution
SCHEMA_VERSION = "1.0"


# =============================================================================
# Request Models
# =============================================================================


class CandleData(BaseModel):
    """OHLCV candle data for a single timestamp."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class PositionData(BaseModel):
    """Current position in an asset."""

    symbol: str
    quantity: Decimal
    average_price: Decimal = Field(alias="averagePrice")

    class Config:
        populate_by_name = True


class PortfolioState(BaseModel):
    """Current state of the agent's portfolio."""

    cash: Decimal
    positions: list[PositionData]
    total_value: Decimal = Field(alias="totalValue")

    class Config:
        populate_by_name = True


class AgentContextRequest(BaseModel):
    """
    Request with contract versioning for safe API evolution.

    Attributes:
        schema_version: API schema version for compatibility checks
        request_id: Unique request identifier for tracing and idempotency
        agent_id: ID of the agent requesting a decision
        portfolio: Current portfolio state
        candles: Recent market candles for analysis
        instructions: Optional agent-specific instructions
    """

    schema_version: str = Field(default=SCHEMA_VERSION, alias="schemaVersion")
    request_id: str = Field(default_factory=lambda: str(uuid4()), alias="requestId")
    agent_id: str = Field(alias="agentId")
    portfolio: PortfolioState
    candles: list[CandleData]
    instructions: str = ""

    class Config:
        populate_by_name = True


# =============================================================================
# Response Models
# =============================================================================


class ExplanationSignal(BaseModel):
    """
    Structured signal explaining why a decision was made.

    This enables explainable ML by providing feature-level
    explanations for trading decisions.
    """

    feature: str  # e.g., "rsi_14"
    value: float  # e.g., 27.3
    rule: str  # e.g., "<30 = oversold"
    fired: bool  # True if rule triggered
    contribution: SignalContribution


class TradeOrderResponse(BaseModel):
    """A single trade order in a decision."""

    asset_symbol: str = Field(alias="assetSymbol")
    side: TradeSide
    quantity: Decimal
    limit_price: Decimal | None = Field(default=None, alias="limitPrice")

    class Config:
        populate_by_name = True


class AgentDecisionResponse(BaseModel):
    """
    Response with contract versioning and structured explainability.

    Attributes:
        schema_version: API schema version
        model_version: Version of the ML model that generated this decision
        request_id: Echo of the request ID for correlation
        agent_id: ID of the agent this decision is for
        created_at: Timestamp when the decision was generated
        orders: List of trade orders
        signals: Structured explanation signals (explainable ML)
        reasoning: Human-readable summary of the decision
    """

    schema_version: str = Field(default=SCHEMA_VERSION, alias="schemaVersion")
    model_version: str = Field(default=settings.model_version, alias="modelVersion")
    request_id: str = Field(alias="requestId")
    agent_id: str = Field(alias="agentId")
    created_at: datetime = Field(alias="createdAt")
    orders: list[TradeOrderResponse]
    signals: list[ExplanationSignal] = []
    reasoning: str = ""

    class Config:
        populate_by_name = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    model_loaded: bool = Field(alias="modelLoaded")
    model_version: str = Field(alias="modelVersion")
    schema_version: str = Field(default=SCHEMA_VERSION, alias="schemaVersion")

    class Config:
        populate_by_name = True
