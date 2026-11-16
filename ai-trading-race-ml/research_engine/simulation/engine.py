"""Pure transition engine: ``propose_transition`` (spec 5.3, 9, 14.5).

Given a versioned :class:`PortfolioState`, a command and the numerical ports,
compute the next state, balanced journals, events, orders, fills, settlements,
cash flows, policy evaluation, valuation and a reconciliation report. The
result is hashed and HMAC-signed; nothing is persisted here.

Processing order inside one transition:

1. Derive every due event with ``state.as_of < effective_at <= horizon``:
   settlements, entitled coupons and redemptions of held (or ordered)
   securities, execution observations for ACCEPTED orders whose eligible
   session observation is available, and expiries of orders whose session
   ended without a valid observation. Fills create settlements that are
   inserted dynamically when they fall inside the horizon.
2. Apply them in ``event_sort_key`` order (effective time, versioned type
   priority ``event-priority-v1``, stable event id).
3. Apply the command at ``advance_to``: capital flow, decision submission
   (cancellations of unfilled intents then ``orders_submitted``), or the
   valuation mark. ``process_events`` applies only step 1-2.

The clock never moves backward: ``advance_to < state.as_of`` is rejected. If an
order's eligible-session observation time has passed but its data is not yet
available at ``advance_to``, ``process_events`` stops just before that
observation (the new ``as_of`` is clamped) and other commands raise
:class:`DataNotYetAvailable`; a later observation is never exposed early.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from research_engine import ENGINE_VERSION
from research_engine.contracts.common import (
    check_schema_version,
    content_hash,
    sign_hash,
    short_id,
)
from research_engine.contracts.portfolio import (
    EVENT_PRIORITY,
    CapitalFlowEvent,
    CommandType,
    CouponPaymentEvent,
    DecisionAction,
    EventType,
    Journal,
    OrderCancellationEvent,
    OrderExpiryEvent,
    OrderIntent,
    OrdersSubmittedEvent,
    OrderStatus,
    PolicyEvaluation,
    PortfolioState,
    RedemptionEvent,
    SettlementDueEvent,
    Side,
    TransitionProposal,
    TransitionRequest,
    ValuationMarkEvent,
    ValuationSnapshot,
    event_sort_key,
)

from .clock import (
    cash_event_at,
    compact_instant,
    make_id,
    ny_date,
    observation_at,
)
from .fills import (
    batch_order_key,
    build_observation_event,
    compute_fill,
    expiry_event_id,
    observation_event_id,
    synthetic_quote,
)
from .ledger import (
    ZERO,
    Book,
    LedgerInvariantError,
    post_buy_fill,
    post_capital_flow,
    post_cash_interest,
    post_coupon,
    post_mark_to_market,
    post_redemption,
    post_sell_fill,
    post_settlement,
    reconcile,
)
from .policy import (
    RiskMetrics,
    breaches,
    build_decision_snapshot,
    evaluate_decision,
    valuation_metrics,
)
from .valuation import CurveRef, MarkSource, value_book

SIMULATION_VERSION = "simulation-v1"
CASH_INTEREST_DAY_COUNT = Decimal("360")


class TransitionError(ValueError):
    """Request rejected before any computation (HTTP 400/409 semantics)."""

    code = "invalid_request"


class InvalidTransitionRequest(TransitionError):
    code = "invalid_request"


class StateHashMismatch(TransitionError):
    code = "state_hash_mismatch"


class ClockMovedBackward(TransitionError):
    code = "clock_moved_backward"


class PortfolioBlocked(TransitionError):
    code = "portfolio_blocked"


class DataNotYetAvailable(TransitionError):
    code = "data_not_yet_available"


def engine_version(pricing) -> str:
    return f"{ENGINE_VERSION}+{SIMULATION_VERSION}+pricing:{pricing.engine_version}"


@dataclass
class _Work:
    request: TransitionRequest
    pricing: Any
    market: Any
    mark_source: Optional[MarkSource]
    book: Book
    horizon: datetime
    queue: list = field(default_factory=list)
    queued_ids: set = field(default_factory=set)
    events: list = field(default_factory=list)
    journals: list[Journal] = field(default_factory=list)
    fills: list = field(default_factory=list)
    settlements_created: list = field(default_factory=list)
    settlements_completed: list[str] = field(default_factory=list)
    cash_flows: list = field(default_factory=list)
    status_changes: list[OrderIntent] = field(default_factory=list)
    orders_created: list[OrderIntent] = field(default_factory=list)
    day_adjust: dict = field(default_factory=dict)
    cash_flow_securities: set = field(default_factory=set)
    policy_evaluation: Optional[PolicyEvaluation] = None
    valuation: Optional[ValuationSnapshot] = None

    @property
    def data_mode(self):
        return self.market.data_mode

    def push(
        self,
        effective_at: datetime,
        priority: int,
        event_id: str,
        kind: str,
        payload,
        order_key: Optional[tuple] = None,
    ):
        """Queue an event; ``order_key`` (execution batches) replaces id-text ordering."""
        if event_id in self.queued_ids:
            return
        self.queued_ids.add(event_id)
        tiebreak = order_key if order_key is not None else (event_id,)
        heapq.heappush(self.queue, (effective_at, priority, tiebreak, event_id, kind, payload))

    def journal(self, journal: Optional[Journal]) -> None:
        if journal is not None:
            self.journals.append(journal)

    def change_status(self, order: OrderIntent, status: OrderStatus, reason: Optional[str]):
        updated = order.model_copy(update={"status": status, "status_reason": reason})
        self.book.open_orders.pop(order.order_id, None)
        self.book.reserved -= order.reserved_cash_usd
        self.status_changes.append(updated)
        return updated


# --------------------------------------------------------------------------- #
# Event derivation
# --------------------------------------------------------------------------- #


def _ready(curve) -> bool:
    return curve is not None and str(curve.status).upper() == "READY"


def _clamp_horizon(work: _Work, processing_time: datetime) -> Optional[datetime]:
    """Earliest observation instant whose data is not yet available, if any."""
    blocked: Optional[datetime] = None
    for order in work.book.open_orders.values():
        curve = work.market.curve_for_session(order.eligible_session_date)
        if not _ready(curve):
            continue
        observed = curve.observed_at
        if observed <= work.horizon and curve.available_at > processing_time:
            blocked = observed if blocked is None else min(blocked, observed)
    return blocked


def _schedule_cash_flow_events(work: _Work, security_id: str, after: datetime) -> None:
    if security_id in work.cash_flow_securities:
        return
    work.cash_flow_securities.add(security_id)
    pid = work.book.portfolio_id
    for cf in work.pricing.cash_flows(security_id):
        at = cash_event_at(cf.payment_date)
        if not (after < at <= work.horizon):
            continue
        if cf.principal_per_100 > 0:
            event = RedemptionEvent(
                event_id=make_id("evt", "redeem", pid, security_id, cf.payment_date.isoformat()),
                effective_at=at,
                priority=EVENT_PRIORITY[EventType.REDEMPTION],
                security_id=security_id,
                payment_date=cf.payment_date,
                redemption_per_100=cf.principal_per_100,
            )
            work.push(at, event.priority, event.event_id, "event", event)
        if cf.coupon_per_100 > 0:
            event = CouponPaymentEvent(
                event_id=make_id("evt", "coupon", pid, security_id, cf.payment_date.isoformat()),
                effective_at=at,
                priority=EVENT_PRIORITY[EventType.COUPON_PAYMENT],
                security_id=security_id,
                payment_date=cf.payment_date,
                accrual_start=cf.accrual_start,
                accrual_end=cf.accrual_end,
                coupon_per_100=cf.coupon_per_100,
            )
            work.push(at, event.priority, event.event_id, "event", event)


def _schedule_settlement(work: _Work, settlement) -> None:
    at = cash_event_at(settlement.settlement_date)
    if at <= work.horizon:
        event = SettlementDueEvent(
            event_id=make_id("evt", "settle", settlement.settlement_id),
            effective_at=at,
            priority=EVENT_PRIORITY[EventType.SETTLEMENT_DUE],
            settlement_id=settlement.settlement_id,
        )
        work.push(at, event.priority, event.event_id, "event", event)


def _derive_due_events(work: _Work, processing_time: datetime) -> None:
    book = work.book
    for settlement in sorted(book.pending.values(), key=lambda s: s.settlement_id):
        _schedule_settlement(work, settlement)
    candidates = set(book.held_securities()) | {o.security_id for o in book.open_orders.values()}
    for sid in sorted(candidates):
        _schedule_cash_flow_events(work, sid, book.as_of)
    for order in sorted(book.open_orders.values(), key=lambda o: o.order_id):
        session = order.eligible_session_date
        curve = work.market.curve_for_session(session)
        valid = (
            _ready(curve)
            and curve.observed_at > order.submitted_at
            and ny_date(curve.observed_at) == session
            and curve.observed_at <= order.expires_at
        )
        if valid:
            if curve.observed_at <= work.horizon and curve.available_at <= processing_time:
                work.push(
                    curve.observed_at,
                    EVENT_PRIORITY[EventType.EXECUTION_OBSERVATION],
                    observation_event_id(order),
                    "observation",
                    (order.order_id, curve),
                    order_key=batch_order_key(order),
                )
        elif order.expires_at <= work.horizon:
            reason = "no_eligible_observation_in_session"
            event = OrderExpiryEvent(
                event_id=expiry_event_id(order),
                effective_at=order.expires_at,
                priority=EVENT_PRIORITY[EventType.ORDER_EXPIRY],
                order_id=order.order_id,
                reason=reason,
            )
            work.push(
                event.effective_at,
                event.priority,
                event.event_id,
                "event",
                event,
                order_key=batch_order_key(order),
            )


# --------------------------------------------------------------------------- #
# Event application
# --------------------------------------------------------------------------- #


def _entitled_face(work: _Work, security_id: str, payment_date: date) -> Decimal:
    """Face settled strictly before the payment date (settled now +/- same-day moves)."""
    position = work.book.positions.get(security_id)
    settled = position.settled_face if position else ZERO
    return settled + work.day_adjust.get((security_id, payment_date), ZERO)


def _adjust(work: _Work, security_id: str, day: date, amount: Decimal) -> None:
    key = (security_id, day)
    work.day_adjust[key] = work.day_adjust.get(key, ZERO) + amount


def _apply_settlement(work: _Work, event: SettlementDueEvent) -> None:
    settlement = work.book.pending.get(event.settlement_id)
    if settlement is None:
        raise LedgerInvariantError(f"unknown settlement {event.settlement_id}")
    work.journal(post_settlement(work.book, event, settlement))
    # Undo same-day delivery when measuring entitlement on that date.
    delta = -settlement.face if settlement.side == Side.BUY else settlement.face
    _adjust(work, settlement.security_id, settlement.settlement_date, delta)
    work.settlements_completed.append(settlement.settlement_id)
    work.events.append(event)


def _apply_redemption(work: _Work, event: RedemptionEvent) -> None:
    face = _entitled_face(work, event.security_id, event.payment_date)
    journal, record = post_redemption(work.book, event, face)
    if record is None:
        return
    _adjust(work, event.security_id, event.payment_date, face)
    work.journal(journal)
    work.cash_flows.append(record)
    work.events.append(event)


def _apply_coupon(work: _Work, event: CouponPaymentEvent) -> None:
    face = _entitled_face(work, event.security_id, event.payment_date)
    journal, record = post_coupon(work.book, event, face)
    if record is None:
        return
    work.journal(journal)
    work.cash_flows.append(record)
    work.events.append(event)


def _fill_risk_recheck(work: _Work, order: OrderIntent, curve, fill) -> list[str]:
    """Post-fill limits for purchases on the eligible observation's curve."""
    request = work.request
    policy = request.risk_policy
    curve_ref = CurveRef(curve.curve_snapshot_id, curve.session_date, curve.observed_at)
    valuation, detail = value_book(
        work.book,
        work.pricing,
        valuation_id=make_id("fillcheck", order.order_id),
        valuation_at=curve.observed_at,
        curve=curve_ref,
        data_mode=work.data_mode,
        policy=policy,
        state_version=work.book.version,
        mark_source=work.mark_source,
    )
    if valuation.equity_usd is None:
        return ["missing_risk_output_at_fill"]
    try:
        new_face = work.book.economic_face(order.security_id) + order.face
        result = work.pricing.value_position(
            order.security_id, curve.curve_snapshot_id, curve.session_date, new_face
        )
    except Exception:
        return ["missing_risk_output_at_fill"]
    costs = fill.spread_cost_usd + fill.fees_usd
    nav = valuation.equity_usd - costs
    pv = dict(detail.pv)
    pv[order.security_id] = Decimal(result.pv_dirty_usd)
    dv01 = detail.total_dv01 - detail.dv01.get(order.security_id, ZERO)
    dv01 += Decimal(result.parallel_dv01_usd)
    cash = (
        work.book.cash
        + work.book.receivables()
        - work.book.payables()
        - fill.consideration_usd
        - fill.fees_usd
    )
    metrics = RiskMetrics(nav=nav, cash=cash, pv=pv, dv01=dv01)
    reasons = []
    for breach in breaches(metrics, policy):
        if breach == "min_cash_ratio" or breach == "parallel_dv01":
            reasons.append(f"risk_limit_at_fill:{breach}")
        elif breach == f"max_single_security_ratio:{order.security_id}":
            reasons.append(f"risk_limit_at_fill:{breach}")
    return reasons


def _apply_observation(work: _Work, order_id: str, curve) -> None:
    book = work.book
    order = book.open_orders.get(order_id)
    if order is None:  # cancelled/filled earlier in this batch
        return
    request = work.request
    execution = request.execution_model
    quote = synthetic_quote(
        order, curve.curve_snapshot_id, curve.session_date, work.pricing, execution, work.data_mode
    )
    reasons: list[str] = []
    if not quote.instrument_active:
        reasons.append("instrument_inactive")
    if not quote.data_valid:
        reasons.append(f"invalid_observation:{quote.invalid_reason}")
    fill = None
    observation_id = make_id("obs", curve.curve_snapshot_id, order.security_id)
    if not reasons:
        fill = compute_fill(order, quote, execution, curve.observed_at, observation_id)
        if order.side == Side.SELL:
            if order.face > book.economic_face(order.security_id):
                reasons.append("long_only_violation_at_fill")
        else:
            available = book.available_funding(exclude_reservation=order.reserved_cash_usd)
            if fill.consideration_usd + fill.fees_usd > available:
                reasons.append("insufficient_funding_at_fill")
            else:
                reasons.extend(_fill_risk_recheck(work, order, curve, fill))
    event = build_observation_event(
        order,
        curve_snapshot_id=curve.curve_snapshot_id,
        observed_at=curve.observed_at,
        quote=quote,
        recheck_passed=not reasons,
        recheck_reasons=reasons,
    )
    work.events.append(event)
    if reasons:
        work.change_status(order, OrderStatus.REJECTED, ";".join(reasons))
        return
    work.change_status(order, OrderStatus.FILLED, None)
    if order.side == Side.BUY:
        journal, settlement = post_buy_fill(book, event, fill, curve.session_date)
    else:
        journal, settlement = post_sell_fill(book, event, fill)
    work.journal(journal)
    work.fills.append(fill)
    work.settlements_created.append(settlement)
    _schedule_settlement(work, settlement)
    _schedule_cash_flow_events(work, order.security_id, curve.observed_at)


def _apply_expiry(work: _Work, event: OrderExpiryEvent) -> None:
    order = work.book.open_orders.get(event.order_id)
    if order is None:
        return
    work.change_status(order, OrderStatus.EXPIRED, event.reason)
    work.events.append(event)


def _drain(work: _Work) -> None:
    while work.queue:
        _, _, _, _, kind, payload = heapq.heappop(work.queue)
        if kind == "observation":
            _apply_observation(work, *payload)
            continue
        event = payload
        if isinstance(event, SettlementDueEvent):
            _apply_settlement(work, event)
        elif isinstance(event, RedemptionEvent):
            _apply_redemption(work, event)
        elif isinstance(event, CouponPaymentEvent):
            _apply_coupon(work, event)
        elif isinstance(event, OrderExpiryEvent):
            _apply_expiry(work, event)
        elif isinstance(event, CapitalFlowEvent):
            journal, record = post_capital_flow(work.book, event)
            work.journal(journal)
            work.cash_flows.append(record)
            work.events.append(event)
        else:  # pragma: no cover - defensive
            raise LedgerInvariantError(f"unexpected queued event {type(event).__name__}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def _curve_for_snapshot(work: _Work, at: datetime) -> tuple[Optional[CurveRef], list[str]]:
    """Resolve the frozen market snapshot's curve; never use data after ``at``."""
    request = work.request
    snapshot = request.market_snapshot
    if snapshot is None:
        curve = work.market.latest_available_curve(at)
        if not _ready(curve):
            return None, ["no_curve_available"]
        return CurveRef(curve.curve_snapshot_id, curve.session_date, curve.observed_at), []
    curve = work.market.curve_for_session(snapshot.session_date)
    if not _ready(curve):
        return None, ["market_snapshot_curve_not_ready"]
    if snapshot.curve_snapshot_id and curve.curve_snapshot_id != snapshot.curve_snapshot_id:
        return None, ["market_snapshot_curve_mismatch"]
    if curve.available_at > at:
        return None, ["market_snapshot_not_available_at_decision_time"]
    snapshot_id, snapshot_hash = work.market.market_snapshot_id(snapshot.session_date)
    if (snapshot_id, snapshot_hash) != (snapshot.market_snapshot_id, snapshot.content_hash):
        return None, ["market_snapshot_hash_mismatch"]
    return CurveRef(curve.curve_snapshot_id, curve.session_date, curve.observed_at), []


def _submit_decision(work: _Work) -> None:
    request = work.request
    book = work.book
    at = request.advance_to
    if request.decision_id is None or request.action is None:
        raise InvalidTransitionRequest("submit_decision requires decision_id and action")
    curve, curve_reasons = (None, [])
    if request.action != DecisionAction.HOLD or request.market_snapshot is not None:
        curve, curve_reasons = _curve_for_snapshot(work, at)
    snapshot = build_decision_snapshot(
        book,
        work.pricing,
        curve=curve,
        decision_time=at,
        data_mode=work.data_mode,
        policy=request.risk_policy,
        mark_source=work.mark_source,
    )
    snapshot.reasons.extend(curve_reasons)
    evaluation, orders = evaluate_decision(
        book,
        snapshot,
        decision_id=request.decision_id,
        action=request.action,
        targets=list(request.target_weights),
        policy=request.risk_policy,
        execution=request.execution_model,
        pricing=work.pricing,
        submitted_at=at,
    )
    work.policy_evaluation = evaluation
    if not evaluation.passed or request.action == DecisionAction.HOLD:
        return
    for order in sorted(book.open_orders.values(), key=lambda o: o.order_id):
        event = OrderCancellationEvent(
            event_id=make_id("evt", "cancel", order.order_id, request.decision_id),
            effective_at=at,
            priority=EVENT_PRIORITY[EventType.ORDER_CANCELLATION],
            order_id=order.order_id,
            replaced_by_decision_id=request.decision_id,
        )
        work.change_status(order, OrderStatus.CANCELLED, f"replaced_by:{request.decision_id}")
        work.events.append(event)
    if not orders:
        return
    for order in orders:
        if order.order_id in book.open_orders:
            raise InvalidTransitionRequest(f"duplicate order id {order.order_id}")
        book.open_orders[order.order_id] = order
        book.reserved += order.reserved_cash_usd
    work.orders_created.extend(orders)
    work.events.append(
        OrdersSubmittedEvent(
            event_id=make_id("evt", "submit", request.decision_id),
            effective_at=at,
            priority=EVENT_PRIORITY[EventType.ORDERS_SUBMITTED],
            decision_id=request.decision_id,
            orders=orders,
        )
    )


def _value_portfolio(work: _Work) -> None:
    request = work.request
    book = work.book
    at = request.advance_to
    valuation_id = make_id("val", book.portfolio_id, compact_instant(at))
    event_id = make_id("evt", "mark", valuation_id)
    curve, reasons = _curve_for_snapshot(work, at)
    valuation_date = ny_date(at)
    placeholder = ValuationMarkEvent(
        event_id=event_id,
        effective_at=at,
        priority=EVENT_PRIORITY[EventType.VALUATION_MARK],
        valuation_id=valuation_id,
    )
    rate = request.execution_model.cash_interest_rate
    if (
        rate != 0
        and book.cash_flows_through is not None
        and valuation_date > book.cash_flows_through
    ):
        days = Decimal((valuation_date - book.cash_flows_through).days)
        work.journal(
            post_cash_interest(book, placeholder, book.cash * rate * days / CASH_INTEREST_DAY_COUNT)
        )
    book.cash_flows_through = valuation_date
    valuation, detail = value_book(
        book,
        work.pricing,
        valuation_id=valuation_id,
        valuation_at=at,
        curve=curve,
        data_mode=work.data_mode,
        policy=request.risk_policy,
        state_version=book.version + 1,
        mark_source=work.mark_source,
        extra_reasons=tuple(reasons),
    )
    if valuation.complete and valuation.equity_usd is not None:
        work.journal(post_mark_to_market(book, placeholder, valuation.equity_usd))
    metrics = valuation_metrics(valuation, detail, book)
    if metrics is not None:
        book.risk_breaches = breaches(metrics, request.risk_policy)
    book.last_valuation_id = valuation_id
    work.valuation = valuation
    work.events.append(
        ValuationMarkEvent(
            event_id=event_id,
            effective_at=at,
            priority=EVENT_PRIORITY[EventType.VALUATION_MARK],
            valuation_id=valuation_id,
            curve_snapshot_id=valuation.curve_snapshot_id,
            marks=valuation.marks,
            receivables_pv_usd=valuation.receivables_pv_usd,
            payables_pv_usd=valuation.payables_pv_usd,
            complete=valuation.complete,
            incomplete_reasons=valuation.incomplete_reasons,
        )
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def propose_transition(
    request: TransitionRequest,
    pricing,
    market,
    signing_key: bytes,
    *,
    mark_source: Optional[MarkSource] = None,
    request_hash_override: Optional[str] = None,
) -> TransitionProposal:
    """Compute a signed, hash-identified transition proposal. Pure (no persistence).

    ``request_hash`` is ``request.compute_hash()`` (offline replay). The API passes
    ``request_hash_override`` = hash of the exact JSON body it received so the caller
    can bind the proposal to the request it sent; it is set before hashing/signing.
    """
    try:
        check_schema_version(request.schema_version)
        check_schema_version(request.portfolio_state.schema_version)
    except ValueError as exc:
        raise InvalidTransitionRequest(str(exc)) from exc
    state = request.portfolio_state
    state_hash = state.compute_hash()
    if request.portfolio_state_hash != state_hash:
        raise StateHashMismatch("portfolio_state_hash does not match the supplied state")
    if state.blocked_reason:
        raise PortfolioBlocked(f"portfolio blocked: {state.blocked_reason}")
    if request.advance_to < state.as_of:
        raise ClockMovedBackward(
            f"advance_to {request.advance_to.isoformat()} precedes state as_of"
        )
    if (
        request.market_snapshot is not None
        and request.market_snapshot.data_mode != market.data_mode
    ):
        raise InvalidTransitionRequest("market snapshot data mode differs from the market port")
    command = request.command_type
    if command == CommandType.CAPITAL_FLOW and not request.capital_amount_usd:
        raise InvalidTransitionRequest("capital_flow requires a non-zero capital_amount_usd")

    book = Book.from_state(state)
    work = _Work(
        request=request,
        pricing=pricing,
        market=market,
        mark_source=mark_source,
        book=book,
        horizon=request.advance_to,
    )
    blocked_at = _clamp_horizon(work, request.advance_to)
    new_as_of = request.advance_to
    if blocked_at is not None:
        if command != CommandType.PROCESS_EVENTS:
            raise DataNotYetAvailable(
                f"eligible observation at {blocked_at.isoformat()} is not yet available"
            )
        work.horizon = max(state.as_of, blocked_at - timedelta(microseconds=1))
        new_as_of = work.horizon

    _derive_due_events(work, request.advance_to)
    if command == CommandType.CAPITAL_FLOW:
        event = CapitalFlowEvent(
            event_id=make_id("evt", "capital", request.command_id),
            effective_at=request.advance_to,
            priority=EVENT_PRIORITY[EventType.CAPITAL_FLOW],
            amount_usd=request.capital_amount_usd,
            reason="initial_capital" if state.version == 0 else "external_flow",
        )
        work.push(event.effective_at, event.priority, event.event_id, "event", event)
    _drain(work)
    if command == CommandType.SUBMIT_DECISION:
        _submit_decision(work)
    elif command == CommandType.VALUE_PORTFOLIO:
        _value_portfolio(work)

    keys = [event_sort_key(e) for e in work.events]
    if keys != sorted(keys):  # pragma: no cover - invariant
        raise LedgerInvariantError("events were not applied in sort order")
    if any(e.effective_at < state.as_of for e in work.events):  # pragma: no cover
        raise ClockMovedBackward("an event precedes the state clock")

    no_op = not work.events
    if no_op:
        new_state = state
    else:
        new_state = book.to_state(state.version + 1, max(state.as_of, new_as_of))
    reconciliation = reconcile(
        state,
        work.journals,
        new_state,
        work.valuation,
        require_economic_match=command == CommandType.VALUE_PORTFOLIO
        and work.valuation is not None
        and work.valuation.complete,
    )
    request_hash = request_hash_override or request.compute_hash()
    market_hash = (
        request.market_snapshot.content_hash
        if request.market_snapshot is not None
        else content_hash(None)
    )
    proposal = TransitionProposal(
        proposal_id=short_id("prop", {"command": request.command_id, "request": request_hash}),
        command_id=request.command_id,
        command_type=command,
        portfolio_id=state.portfolio_id,
        strategy_id=state.strategy_id,
        run_id=state.run_id,
        expected_version=state.version,
        new_version=new_state.version,
        no_op=no_op,
        engine_version=engine_version(pricing),
        request_hash=request_hash,
        input_hashes={
            "portfolioState": state_hash,
            "marketSnapshot": market_hash,
            "riskPolicy": request.risk_policy.compute_hash(),
            "executionModel": request.execution_model.compute_hash(),
        },
        events=work.events,
        journals=work.journals,
        new_state=new_state,
        new_state_hash=new_state.compute_hash(),
        orders_created=work.orders_created,
        order_status_changes=work.status_changes,
        fills=work.fills,
        settlements_created=work.settlements_created,
        settlements_completed=work.settlements_completed,
        cash_flows=work.cash_flows,
        policy_evaluation=work.policy_evaluation,
        valuation=work.valuation,
        reconciliation=reconciliation,
    )
    return sign_proposal(proposal, signing_key)


def sign_proposal(proposal: TransitionProposal, signing_key: bytes) -> TransitionProposal:
    digest = content_hash(proposal.hash_payload())
    return proposal.model_copy(
        update={"proposal_hash": digest, "signature": sign_hash(digest, signing_key)}
    )


def build_request(
    state: PortfolioState,
    *,
    command_id: str,
    command_type: CommandType,
    advance_to: datetime,
    instrument_universe_version: str,
    market_snapshot=None,
    risk_policy=None,
    execution_model=None,
    decision_id: Optional[str] = None,
    action: Optional[DecisionAction] = None,
    target_weights=(),
    capital_amount_usd=None,
) -> TransitionRequest:
    """Convenience constructor that binds the state hash."""
    kwargs: dict[str, Any] = {}
    if risk_policy is not None:
        kwargs["risk_policy"] = risk_policy
    if execution_model is not None:
        kwargs["execution_model"] = execution_model
    return TransitionRequest(
        command_id=command_id,
        command_type=command_type,
        portfolio_state=state,
        portfolio_state_hash=state.compute_hash(),
        advance_to=advance_to,
        market_snapshot=market_snapshot,
        instrument_universe_version=instrument_universe_version,
        decision_id=decision_id,
        action=action,
        target_weights=list(target_weights),
        capital_amount_usd=capital_amount_usd,
        **kwargs,
    )


__all__ = [
    "ClockMovedBackward",
    "DataNotYetAvailable",
    "InvalidTransitionRequest",
    "PortfolioBlocked",
    "StateHashMismatch",
    "TransitionError",
    "build_request",
    "engine_version",
    "observation_at",
    "propose_transition",
    "sign_proposal",
]
