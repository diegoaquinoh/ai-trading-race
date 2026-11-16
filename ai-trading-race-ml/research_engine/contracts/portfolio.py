"""Portfolio state, events, ledger, policy and transition contracts.

This module is the boundary between the canonical Python simulation engine and
the .NET transactional commit path (spec 5.3, 9, 14.5). .NET never computes
these values; it verifies hashes/signature/versions/balance and re-compares the
policy evaluation against its own copy of the risk policy, then commits.

Units: ``*_usd`` = USD cash; ``face`` = USD face amount; ``*_per_100`` = price
points per 100 face; ratios/weights are decimal fractions.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import Field, model_validator

from .common import (
    SCHEMA_VERSION,
    ContentHash,
    ContractModel,
    DataMode,
    DecimalStr,
    OpaqueId,
    PortfolioId,
    SecurityId,
    StrategyId,
    UtcDatetime,
)

ZERO = Decimal("0")


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    ACCEPTED = "ACCEPTED"  # reserved funding, awaiting eligible later observation
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"  # time-in-force elapsed without a valid observation
    CANCELLED = "CANCELLED"  # replaced by a newer target before fill
    REJECTED = "REJECTED"  # failed re-check at fill time (funding/status/data/risk)


class AccountCode(str, Enum):
    """Chart of accounts. Posting templates: docs/fixed-income/accounting.md."""

    CASH = "CASH"  # settled cash (asset)
    BOND_PRINCIPAL = "BOND_PRINCIPAL"  # clean cost basis of held face (asset)
    ACCRUED_INTEREST_PURCHASED = "ACCRUED_INTEREST_PURCHASED"  # accrued paid at purchase (asset)
    SETTLEMENT_RECEIVABLE = "SETTLEMENT_RECEIVABLE"  # sale proceeds awaiting settlement (asset)
    SETTLEMENT_PAYABLE = "SETTLEMENT_PAYABLE"  # purchase consideration awaiting settlement
    MARK_ADJUSTMENT = "MARK_ADJUSTMENT"  # valuation adjustment to economic value (asset contra)
    CAPITAL = "CAPITAL"  # external capital flows (equity)
    INTEREST_INCOME = "INTEREST_INCOME"
    REALIZED_GAIN_LOSS = "REALIZED_GAIN_LOSS"
    UNREALIZED_GAIN_LOSS = "UNREALIZED_GAIN_LOSS"
    TRANSACTION_FEES = "TRANSACTION_FEES"  # explicit commissions/fees (expense)


class CommandType(str, Enum):
    PROCESS_EVENTS = "process_events"  # due settlements, coupons, redemptions, fills, expiries
    SUBMIT_DECISION = "submit_decision"  # size validated targets into order intents
    VALUE_PORTFOLIO = "value_portfolio"  # valuation mark + unrealized posting
    CAPITAL_FLOW = "capital_flow"  # initial funding / external flows


class EventType(str, Enum):
    CAPITAL_FLOW = "capital_flow"
    SETTLEMENT_DUE = "settlement_due"
    REDEMPTION = "redemption"
    COUPON_PAYMENT = "coupon_payment"
    EXECUTION_OBSERVATION = "execution_observation"
    ORDER_EXPIRY = "order_expiry"
    VALUATION_MARK = "valuation_mark"
    ORDER_CANCELLATION = "order_cancellation"
    ORDERS_SUBMITTED = "orders_submitted"


EVENT_PRIORITY_TABLE_VERSION = "event-priority-v1"

# Lower sorts first at an identical effective timestamp (spec 9.6).
EVENT_PRIORITY: dict[EventType, int] = {
    EventType.CAPITAL_FLOW: 0,
    EventType.SETTLEMENT_DUE: 10,
    EventType.REDEMPTION: 20,
    EventType.COUPON_PAYMENT: 30,
    EventType.EXECUTION_OBSERVATION: 40,
    EventType.ORDER_EXPIRY: 45,
    EventType.VALUATION_MARK: 50,
    EventType.ORDER_CANCELLATION: 60,
    EventType.ORDERS_SUBMITTED: 70,
}


class DecisionAction(str, Enum):
    HOLD = "HOLD"
    REBALANCE = "REBALANCE"
    BOOTSTRAP = "BOOTSTRAP"


class QuoteKind(str, Enum):
    SYNTHETIC_MODEL = "synthetic_model"  # curve-model observation, not a market quote
    OBSERVED_BID = "observed_bid"
    OBSERVED_ASK = "observed_ask"
    OBSERVED_MID = "observed_mid"
    OBSERVED_EVALUATED = "observed_evaluated"
    OBSERVED_TRADE = "observed_trade"
    OBSERVED_INDICATIVE = "observed_indicative"


class MarkType(str, Enum):
    CURVE_MODEL = "curve_model"
    OBSERVED_MID = "observed_mid"
    OBSERVED_BID = "observed_bid"
    UNAVAILABLE = "unavailable"


# --------------------------------------------------------------------------- #
# Policy and execution configuration (immutable per experiment)
# --------------------------------------------------------------------------- #


class RiskPolicy(ContractModel):
    """Proposed initial controls (spec 9.3). Changing any value = new policy_id."""

    policy_id: OpaqueId = "treasury-long-only-v1"
    initial_capital_usd: DecimalStr = Decimal("1000000")
    long_only: bool = True
    leverage_allowed: bool = False
    min_cash_ratio: DecimalStr = Decimal("0.05")
    max_single_security_ratio: DecimalStr = Decimal("0.40")
    max_parallel_dv01_usd_per_million_nav: DecimalStr = Decimal("600")
    max_daily_turnover_ratio: DecimalStr = Decimal("0.20")
    max_orders_per_decision: int = 6
    min_weight_change: DecimalStr = Decimal("0.02")
    weight_sum_tolerance: DecimalStr = Decimal("0.000001")
    max_mark_age_business_days: int = 1
    bootstrap_turnover_exemption: bool = True
    projection_mode: Literal["disabled", "deterministic_projection_v1"] = "disabled"
    breach_policy: Literal["block_risk_increasing_v1"] = "block_risk_increasing_v1"


class ExecutionModel(ContractModel):
    """Fill/cost assumptions (spec 9.4). Illustrative, not measured costs."""

    execution_model_id: OpaqueId = "synthetic-half-spread-0.02-v1"
    half_spread_per_100: DecimalStr = Decimal("0.02")
    slippage_per_100: DecimalStr = Decimal("0")
    commission_usd_per_million_face: DecimalStr = Decimal("0")
    time_in_force: Literal["next_session_only"] = "next_session_only"
    fill_timing: Literal["next_session_close_daily"] = "next_session_close_daily"
    funding_rule: Literal["settled_cash_reserve_commitments_v1"] = (
        "settled_cash_reserve_commitments_v1"
    )
    batch_priority: Literal["sells_first_then_security_id_v1"] = "sells_first_then_security_id_v1"
    cash_interest_rate: DecimalStr = Decimal("0")
    face_sizing: Literal["fixed_at_submission_v1"] = "fixed_at_submission_v1"


# --------------------------------------------------------------------------- #
# State components
# --------------------------------------------------------------------------- #


class Lot(ContractModel):
    """FIFO tax lot. Remaining cost amounts shrink pro rata on partial sale."""

    lot_id: OpaqueId
    security_id: SecurityId
    face: DecimalStr
    trade_date: date
    settlement_date: date
    clean_price_per_100: DecimalStr
    principal_cost_usd: DecimalStr  # remaining clean cost
    accrued_purchased_usd: DecimalStr  # remaining accrued interest paid at purchase


class Position(ContractModel):
    security_id: SecurityId
    economic_face: DecimalStr  # trade-date exposure (includes filled, unsettled buys)
    settled_face: DecimalStr  # delivered face
    lots: list[Lot] = Field(default_factory=list)


class OrderIntent(ContractModel):
    order_id: OpaqueId
    decision_id: OpaqueId
    security_id: SecurityId
    side: Side
    face: DecimalStr
    submitted_at: UtcDatetime
    eligible_session_date: date  # next supported session strictly after submission
    expires_at: UtcDatetime
    status: OrderStatus = OrderStatus.ACCEPTED
    reserved_cash_usd: DecimalStr = ZERO  # purchase reservation incl. spread/fee buffer
    batch_priority: int = 0
    status_reason: Optional[str] = None
    bootstrap: bool = False


class Fill(ContractModel):
    fill_id: OpaqueId
    order_id: OpaqueId
    security_id: SecurityId
    side: Side
    face: DecimalStr
    executed_at: UtcDatetime
    observation_id: OpaqueId
    quote_kind: QuoteKind
    reference_clean_price_per_100: DecimalStr  # mid/model reference before costs
    execution_clean_price_per_100: DecimalStr  # after half-spread/slippage
    accrued_per_100: DecimalStr
    dirty_price_per_100: DecimalStr
    half_spread_per_100: DecimalStr
    settlement_date: date
    consideration_usd: DecimalStr  # face/100 * dirty execution price, cents
    fees_usd: DecimalStr
    spread_cost_usd: DecimalStr  # analytic: |execution - reference| * face / 100
    timing_label: str = "next_session_close_daily"


class PendingSettlement(ContractModel):
    settlement_id: OpaqueId
    fill_id: OpaqueId
    security_id: SecurityId
    side: Side
    face: DecimalStr
    settlement_date: date
    cash_usd: DecimalStr  # positive: payable for BUY, receivable for SELL


class CashFlowRecord(ContractModel):
    cash_flow_id: OpaqueId
    security_id: SecurityId
    kind: Literal["COUPON", "REDEMPTION", "CAPITAL", "CASH_INTEREST"]
    payment_date: date
    entitled_face: DecimalStr
    amount_usd: DecimalStr


class PortfolioState(ContractModel):
    """Versioned authoritative portfolio state (application-owned once committed)."""

    schema_version: str = SCHEMA_VERSION
    portfolio_id: PortfolioId
    strategy_id: StrategyId
    run_id: OpaqueId
    version: int = Field(ge=0)
    as_of: UtcDatetime
    currency: Literal["USD"] = "USD"
    cash_usd: DecimalStr  # settled cash
    reserved_cash_usd: DecimalStr = ZERO  # reserved for ACCEPTED purchase orders
    positions: list[Position] = Field(default_factory=list)
    open_orders: list[OrderIntent] = Field(default_factory=list)  # ACCEPTED only
    pending_settlements: list[PendingSettlement] = Field(default_factory=list)
    external_capital_usd: DecimalStr = ZERO
    interest_income_usd: DecimalStr = ZERO
    realized_gain_loss_usd: DecimalStr = ZERO
    transaction_fees_usd: DecimalStr = ZERO
    spread_cost_usd: DecimalStr = ZERO  # analytic, embedded in execution prices
    booked_unrealized_usd: DecimalStr = ZERO  # cumulative MARK_ADJUSTMENT balance
    cash_flows_processed_through: Optional[date] = None
    last_valuation_id: Optional[OpaqueId] = None
    risk_breaches: list[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None  # reconciliation failure blocks commits

    @model_validator(mode="after")
    def _non_negative(self) -> "PortfolioState":
        if self.cash_usd < 0:
            raise ValueError("settled cash cannot be negative (leverage disabled)")
        if self.reserved_cash_usd < 0:
            raise ValueError("reserved cash cannot be negative")
        for position in self.positions:
            if position.economic_face < 0 or position.settled_face < 0:
                raise ValueError("long-only: negative face is not permitted")
        return self


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #


class _EventBase(ContractModel):
    event_id: OpaqueId
    effective_at: UtcDatetime
    priority: int


class CapitalFlowEvent(_EventBase):
    type: Literal[EventType.CAPITAL_FLOW] = EventType.CAPITAL_FLOW
    amount_usd: DecimalStr
    reason: str = "initial_capital"


class SettlementDueEvent(_EventBase):
    type: Literal[EventType.SETTLEMENT_DUE] = EventType.SETTLEMENT_DUE
    settlement_id: OpaqueId


class RedemptionEvent(_EventBase):
    type: Literal[EventType.REDEMPTION] = EventType.REDEMPTION
    security_id: SecurityId
    payment_date: date
    redemption_per_100: DecimalStr = Decimal("100")


class CouponPaymentEvent(_EventBase):
    type: Literal[EventType.COUPON_PAYMENT] = EventType.COUPON_PAYMENT
    security_id: SecurityId
    payment_date: date
    accrual_start: date
    accrual_end: date
    coupon_per_100: DecimalStr


class ExecutionObservationEvent(_EventBase):
    """An eligible later market observation against which an order may fill."""

    type: Literal[EventType.EXECUTION_OBSERVATION] = EventType.EXECUTION_OBSERVATION
    order_id: OpaqueId
    observation_id: OpaqueId
    observed_at: UtcDatetime
    session_date: date
    quote_kind: QuoteKind
    reference_clean_price_per_100: Optional[DecimalStr] = None
    bid_clean_price_per_100: Optional[DecimalStr] = None
    ask_clean_price_per_100: Optional[DecimalStr] = None
    accrued_per_100: DecimalStr
    settlement_date: date
    instrument_active: bool = True
    data_valid: bool = True
    invalid_reason: Optional[str] = None
    # Post-trade risk recheck inputs computed by the engine at observation time.
    recheck_passed: bool = True
    recheck_reasons: list[str] = Field(default_factory=list)


class OrderExpiryEvent(_EventBase):
    type: Literal[EventType.ORDER_EXPIRY] = EventType.ORDER_EXPIRY
    order_id: OpaqueId
    reason: str = "time_in_force_elapsed"


class PositionMark(ContractModel):
    security_id: SecurityId
    economic_face: DecimalStr
    mark_type: MarkType
    clean_price_per_100: Optional[DecimalStr] = None
    accrued_per_100: Optional[DecimalStr] = None
    pv_dirty_usd: Optional[DecimalStr] = None  # valuation-date PV, face-scaled
    observed_at: Optional[UtcDatetime] = None
    mark_age_business_days: Optional[int] = None
    stale: bool = False
    calculation_id: Optional[OpaqueId] = None


class ValuationMarkEvent(_EventBase):
    type: Literal[EventType.VALUATION_MARK] = EventType.VALUATION_MARK
    valuation_id: OpaqueId
    curve_snapshot_id: Optional[OpaqueId] = None
    marks: list[PositionMark] = Field(default_factory=list)
    receivables_pv_usd: Optional[DecimalStr] = None
    payables_pv_usd: Optional[DecimalStr] = None
    complete: bool = True
    incomplete_reasons: list[str] = Field(default_factory=list)


class OrderCancellationEvent(_EventBase):
    type: Literal[EventType.ORDER_CANCELLATION] = EventType.ORDER_CANCELLATION
    order_id: OpaqueId
    replaced_by_decision_id: Optional[OpaqueId] = None


class OrdersSubmittedEvent(_EventBase):
    type: Literal[EventType.ORDERS_SUBMITTED] = EventType.ORDERS_SUBMITTED
    decision_id: OpaqueId
    orders: list[OrderIntent]


PortfolioEvent = Annotated[
    Union[
        CapitalFlowEvent,
        SettlementDueEvent,
        RedemptionEvent,
        CouponPaymentEvent,
        ExecutionObservationEvent,
        OrderExpiryEvent,
        ValuationMarkEvent,
        OrderCancellationEvent,
        OrdersSubmittedEvent,
    ],
    Field(discriminator="type"),
]


def event_sort_key(event: _EventBase) -> tuple:
    """Effective timestamp, then versioned type priority, then stable event ID."""
    return (event.effective_at, event.priority, event.event_id)


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


class JournalLine(ContractModel):
    line_id: OpaqueId
    account: AccountCode
    security_id: Optional[SecurityId] = None
    debit_usd: DecimalStr = ZERO
    credit_usd: DecimalStr = ZERO
    memo: Optional[str] = None

    @model_validator(mode="after")
    def _one_sided(self) -> "JournalLine":
        if self.debit_usd < 0 or self.credit_usd < 0:
            raise ValueError("journal amounts are non-negative; use the opposite side")
        if (self.debit_usd > 0) == (self.credit_usd > 0):
            raise ValueError("a journal line has exactly one non-zero side")
        for amount in (self.debit_usd, self.credit_usd):
            if amount != amount.quantize(Decimal("0.01")):
                raise ValueError("journal amounts are posted in cents")
        return self


class Journal(ContractModel):
    journal_id: OpaqueId
    event_id: OpaqueId
    event_type: EventType
    effective_at: UtcDatetime
    template: str  # posting template id, e.g. "buy_fill_v1"
    lines: list[JournalLine]

    @model_validator(mode="after")
    def _balanced(self) -> "Journal":
        if not self.lines:
            raise ValueError("a journal needs at least two lines")
        debits = sum((line.debit_usd for line in self.lines), ZERO)
        credits = sum((line.credit_usd for line in self.lines), ZERO)
        if debits != credits:
            raise ValueError(f"unbalanced journal {self.journal_id}: {debits} != {credits}")
        return self


# --------------------------------------------------------------------------- #
# Policy evaluation and valuation outputs
# --------------------------------------------------------------------------- #


class PolicyCheck(ContractModel):
    check_id: str  # e.g. "min_cash_ratio", "max_single_security_ratio:SYN-USD-NOTE-001"
    limit: Optional[DecimalStr] = None
    observed: Optional[DecimalStr] = None
    unit: str
    passed: bool
    reason: Optional[str] = None


class TargetWeight(ContractModel):
    security_id: SecurityId  # or CASH-USD
    weight: DecimalStr


class SizedOrder(ContractModel):
    security_id: SecurityId
    side: Side
    face: DecimalStr
    estimated_dirty_price_per_100: DecimalStr
    estimated_consideration_usd: DecimalStr


class PolicyEvaluation(ContractModel):
    policy_id: OpaqueId
    decision_id: OpaqueId
    action: DecisionAction
    passed: bool
    breach_mode: bool = False
    bootstrap_exemption_applied: bool = False
    original_targets: list[TargetWeight] = Field(default_factory=list)
    normalized_targets: list[TargetWeight] = Field(default_factory=list)
    normalization_notes: list[str] = Field(default_factory=list)
    sized_orders: list[SizedOrder] = Field(default_factory=list)
    rejected_reasons: list[str] = Field(default_factory=list)
    checks: list[PolicyCheck] = Field(default_factory=list)
    # Post-trade metrics the .NET policy gate re-compares against its own limits.
    post_trade_nav_usd: Optional[DecimalStr] = None
    post_trade_cash_ratio: Optional[DecimalStr] = None
    post_trade_max_security_ratio: Optional[DecimalStr] = None
    post_trade_parallel_dv01_usd: Optional[DecimalStr] = None
    # Same metric definitions on the state before the order set (incl. pending
    # commitments); populated whenever the post-trade metrics are. A limit breached
    # post-trade passes only if it was already breached pre-trade and the order set
    # does not worsen it (breach policy, spec 9.3): upper limits pass when
    # ``post <= limit or (pre > limit and post <= pre)``; the minimum cash ratio
    # passes when ``post >= min or (pre < min and post >= pre)``. The DV01 limit
    # scales with NAV: post-trade NAV for the post-trade limit, pre-trade NAV for the
    # pre-trade limit (``maxParallelDv01UsdPerMillionNav * NAV / 1,000,000``).
    pre_trade_nav_usd: Optional[DecimalStr] = None
    pre_trade_cash_ratio: Optional[DecimalStr] = None
    pre_trade_max_security_ratio: Optional[DecimalStr] = None
    pre_trade_parallel_dv01_usd: Optional[DecimalStr] = None
    turnover_ratio: Optional[DecimalStr] = None
    order_count: int = 0
    calculation_ids: list[OpaqueId] = Field(default_factory=list)


class ValuationSnapshot(ContractModel):
    valuation_id: OpaqueId
    portfolio_id: PortfolioId
    state_version: int
    valuation_at: UtcDatetime
    data_mode: DataMode
    curve_snapshot_id: Optional[OpaqueId] = None
    mark_policy: str = "synthetic_curve_model_v1"
    complete: bool
    incomplete_reasons: list[str] = Field(default_factory=list)
    cash_usd: DecimalStr
    bond_value_usd: Optional[DecimalStr] = None  # sum of valuation-date dirty PVs
    receivables_pv_usd: Optional[DecimalStr] = None
    payables_pv_usd: Optional[DecimalStr] = None
    equity_usd: Optional[DecimalStr] = None  # cash + bonds + receivables - payables
    marks: list[PositionMark] = Field(default_factory=list)
    parallel_dv01_usd: Optional[DecimalStr] = None
    effective_duration_years: Optional[DecimalStr] = None
    calculation_ids: list[OpaqueId] = Field(default_factory=list)


class ReconciliationReport(ContractModel):
    ok: bool
    journals_balanced: bool
    ledger_cash_usd: DecimalStr
    state_cash_usd: DecimalStr
    ledger_principal_face_check: bool
    book_equity_usd: DecimalStr  # capital + income + realized + unrealized - fees
    economic_equity_usd: Optional[DecimalStr] = None  # from latest complete valuation
    difference_usd: Optional[DecimalStr] = None
    messages: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Transition request / proposal
# --------------------------------------------------------------------------- #


class MarketSnapshotRef(ContractModel):
    market_snapshot_id: OpaqueId
    content_hash: ContentHash
    curve_snapshot_id: Optional[OpaqueId] = None
    session_date: date
    data_mode: DataMode


class TransitionRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    command_id: OpaqueId  # logical idempotency key
    command_type: CommandType
    portfolio_state: PortfolioState
    portfolio_state_hash: ContentHash  # hash of the exact state the caller holds
    advance_to: UtcDatetime  # process events with effective_at <= advance_to
    market_snapshot: Optional[MarketSnapshotRef] = None
    risk_policy: RiskPolicy = Field(default_factory=RiskPolicy)
    execution_model: ExecutionModel = Field(default_factory=ExecutionModel)
    instrument_universe_version: OpaqueId
    # SUBMIT_DECISION only:
    decision_id: Optional[OpaqueId] = None
    action: Optional[DecisionAction] = None
    target_weights: list[TargetWeight] = Field(default_factory=list)
    # CAPITAL_FLOW only:
    capital_amount_usd: Optional[DecimalStr] = None


class TransitionProposal(ContractModel):
    """Pure numerical proposal. Committed only by the application after checks.

    ``proposal_hash`` = sha256 of canonical JSON of every field except
    ``proposal_hash`` and ``signature``; ``signature`` = HMAC over that hash.
    """

    schema_version: str = SCHEMA_VERSION
    proposal_id: OpaqueId
    command_id: OpaqueId
    command_type: CommandType
    portfolio_id: PortfolioId
    strategy_id: StrategyId
    run_id: OpaqueId
    expected_version: int
    new_version: int
    no_op: bool = False
    engine_version: str
    event_priority_table: str = EVENT_PRIORITY_TABLE_VERSION
    request_hash: ContentHash
    input_hashes: dict[str, str]  # portfolioState, marketSnapshot, riskPolicy, executionModel
    events: list[PortfolioEvent] = Field(default_factory=list)
    journals: list[Journal] = Field(default_factory=list)
    new_state: PortfolioState
    new_state_hash: ContentHash
    orders_created: list[OrderIntent] = Field(default_factory=list)
    order_status_changes: list[OrderIntent] = Field(default_factory=list)
    fills: list[Fill] = Field(default_factory=list)
    settlements_created: list[PendingSettlement] = Field(default_factory=list)
    settlements_completed: list[OpaqueId] = Field(default_factory=list)
    cash_flows: list[CashFlowRecord] = Field(default_factory=list)
    policy_evaluation: Optional[PolicyEvaluation] = None
    valuation: Optional[ValuationSnapshot] = None
    reconciliation: ReconciliationReport
    proposal_hash: Optional[ContentHash] = None
    signature: Optional[str] = None

    @model_validator(mode="after")
    def _versions(self) -> "TransitionProposal":
        expected_new = self.expected_version if self.no_op else self.expected_version + 1
        if self.new_version != expected_new or self.new_state.version != self.new_version:
            raise ValueError("new_version must be expected_version + 1 (or equal for no-op)")
        return self

    def hash_payload(self) -> dict:
        wire = self.to_wire()
        wire.pop("proposalHash", None)
        wire.pop("signature", None)
        return wire
