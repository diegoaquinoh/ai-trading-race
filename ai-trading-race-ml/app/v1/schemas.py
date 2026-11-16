"""Request models of internal endpoints without a research-engine contract.

Field names match the .NET DTOs in
``AiTradingRace.Application/FixedIncome/Contracts/ResearchEngineContracts.cs``
exactly (camelCase on the wire; .NET omits null fields). Unknown fields are
rejected, so a request cannot smuggle a risk policy, provider or model choice.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import Field

from research_engine.contracts.common import (
    SCHEMA_VERSION,
    ContractModel,
    DecimalStr,
    OpaqueId,
    PortfolioId,
    SecurityId,
    SourceId,
    StrategyId,
    UtcDatetime,
)
from research_engine.contracts.decisions import RetrievalMode
from research_engine.contracts.portfolio import RiskPolicy


class PriceRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    curve_snapshot_id: OpaqueId
    valuation_date: date
    settlement_date: Optional[date] = None
    security_ids: list[SecurityId] = Field(min_length=1, max_length=100)
    face_usd: Optional[DecimalStr] = None


class RiskRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    portfolio_state: dict
    portfolio_state_hash: str
    curve_snapshot_id: OpaqueId
    valuation_date: date
    scenario_ids: list[str] = Field(default_factory=list, max_length=32)


class EvidenceRetrieveRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    query: str = Field(min_length=1, max_length=2000)
    as_of: UtcDatetime
    evidence_snapshot_id: OpaqueId
    index_build_id: Optional[OpaqueId] = None
    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID_RAG
    max_chunks: int = Field(default=12, ge=1, le=12)
    experiment_id: Optional[OpaqueId] = None
    strategy_id: Optional[StrategyId] = None


class ResearchNoteRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    question: str = Field(min_length=1, max_length=2000)
    as_of: Optional[UtcDatetime] = None
    evidence_snapshot_id: Optional[OpaqueId] = None
    index_build_id: Optional[OpaqueId] = None
    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID_RAG
    response_mode: str = Field(
        default="recorded_replay", pattern=r"^(recorded_replay|fresh_inference)$"
    )
    requested_by: Optional[str] = Field(default=None, max_length=200)


class IngestionRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    source_ids: list[SourceId] = Field(min_length=1, max_length=20)
    reason: Optional[str] = Field(default=None, max_length=1000)
    requested_by: Optional[str] = Field(default=None, max_length=200)


class IndexBuildRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    evidence_snapshot_id: Optional[OpaqueId] = None
    base_index_build_id: Optional[OpaqueId] = None
    validate_only: bool = False
    reason: Optional[str] = Field(default=None, max_length=1000)
    requested_by: Optional[str] = Field(default=None, max_length=200)


class BootstrapAllocationRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    session_date: date
    universe_version: OpaqueId
    risk_policy: RiskPolicy


# --------------------------------------------------------------------------- #
# POST /internal/v1/analytics/performance (evaluation metrics, spec 16.3)
#
# The platform sends the values it already stores per portfolio; every metric is
# computed by research_engine.experiments.metrics.series_metrics (the offline
# report uses the same function), never by the caller.
# --------------------------------------------------------------------------- #


class PerformanceMark(ContractModel):
    """One mark of a stored valuation (``ValuationSnapshot.marks``)."""

    economic_face: DecimalStr
    accrued_per_100: Optional[DecimalStr] = None


class PerformanceLedger(ContractModel):
    """Cumulative accounting balances of the state committed with the valuation."""

    external_capital_usd: DecimalStr
    interest_income_usd: DecimalStr
    realized_gain_loss_usd: DecimalStr
    booked_unrealized_usd: DecimalStr
    transaction_fees_usd: DecimalStr
    spread_cost_usd: DecimalStr
    # Remaining purchased-accrued balance of each held lot, as stored.
    lot_accrued_purchased_usd: list[DecimalStr] = Field(default_factory=list, max_length=5000)


class PerformanceValuation(ContractModel):
    """A stored end-of-day valuation (chronological order is required)."""

    valuation_id: OpaqueId
    valuation_at: UtcDatetime
    state_version: int = Field(ge=0)
    complete: bool
    cash_usd: DecimalStr
    equity_usd: Optional[DecimalStr] = None
    bond_value_usd: Optional[DecimalStr] = None
    parallel_dv01_usd: Optional[DecimalStr] = None
    effective_duration_years: Optional[DecimalStr] = None
    marks: list[PerformanceMark] = Field(default_factory=list, max_length=500)
    ledger: PerformanceLedger


class PerformanceFill(ContractModel):
    fill_id: OpaqueId
    executed_at: UtcDatetime
    consideration_usd: DecimalStr
    fees_usd: DecimalStr = Field(default=Decimal("0"))
    spread_cost_usd: DecimalStr = Field(default=Decimal("0"))


class PerformanceCashFlow(ContractModel):
    cash_flow_id: OpaqueId
    kind: Literal["COUPON", "REDEMPTION", "CAPITAL", "CASH_INTEREST"]
    payment_date: date
    amount_usd: DecimalStr


class PerformancePortfolio(ContractModel):
    portfolio_id: PortfolioId
    strategy_id: Optional[StrategyId] = None
    repetition: int = Field(default=0, ge=0)
    valuations: list[PerformanceValuation] = Field(default_factory=list, max_length=5000)
    fills: list[PerformanceFill] = Field(default_factory=list, max_length=20000)
    cash_flows: list[PerformanceCashFlow] = Field(default_factory=list, max_length=20000)
    orders_created: int = Field(default=0, ge=0)
    # Terminal order status counts (EXPIRED / REJECTED / CANCELLED / FILLED).
    order_status_counts: dict[str, int] = Field(default_factory=dict)
    policy_evaluations: int = Field(default=0, ge=0)
    policy_rejections: int = Field(default=0, ge=0)
    decision_outcomes: dict[str, int] = Field(default_factory=dict)


class RiskFreeObservation(ContractModel):
    session_date: date
    daily_return: DecimalStr


class RiskFreeSeries(ContractModel):
    """Declared excess-return basis; Sharpe is unavailable without one."""

    series_id: OpaqueId
    observations: list[RiskFreeObservation] = Field(default_factory=list, max_length=20000)


class PerformancePair(ContractModel):
    portfolio_id: PortfolioId
    versus_portfolio_id: PortfolioId


class BootstrapPolicyRequest(ContractModel):
    block_length: int = Field(default=5, ge=1, le=60)
    resamples: int = Field(default=1000, ge=100, le=10000)
    seed: int = 0


class PerformanceRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    run_id: Optional[OpaqueId] = None
    portfolios: list[PerformancePortfolio] = Field(min_length=1, max_length=64)
    pairs: list[PerformancePair] = Field(default_factory=list, max_length=64)
    risk_free: Optional[RiskFreeSeries] = None
    min_sharpe_observations: int = Field(default=60, ge=2, le=10000)
    annualize_min_observations: int = Field(default=252, ge=1, le=10000)
    bootstrap: BootstrapPolicyRequest = Field(default_factory=BootstrapPolicyRequest)
    include_daily_returns: bool = False


# --------------------------------------------------------------------------- #
# POST /internal/v1/instruments/payment-calendar
# --------------------------------------------------------------------------- #


class PaymentCalendarRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    request_id: OpaqueId
    portfolio_state: dict
    portfolio_state_hash: str
    # Exclusive lower bound; defaults to the state's cash-flow processing date (or as-of date).
    after: Optional[date] = None
    horizon_days: int = Field(default=366, ge=1, le=3660)
