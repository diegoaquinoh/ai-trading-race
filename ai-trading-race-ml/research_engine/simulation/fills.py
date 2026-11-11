"""Synthetic execution model (spec 9.4).

* Time in force: next supported session only. An order fills only against
  its eligible session's observation (curve observation 15:30 New York),
  which is strictly after submission; it can never fill at the decision
  session's own observation, and a later session's quote can never execute it.
* Quote: model clean price from that session's curve at the fill's settlement
  date; buy at ask = mid + half-spread (+ slippage), sell at bid = mid -
  half-spread (- slippage). These are model observations, not market quotes.
* At fill the engine re-checks instrument status, data validity, funding
  (settled cash - other reservations - committed payables) and, for
  purchases, post-fill risk limits on the observation curve. A failure
  rejects the order with a reason; quantity is never changed.
* The spread cost is recorded analytically: ``|execution - reference| * face / 100``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from research_engine.contracts.common import DataMode, money
from research_engine.contracts.portfolio import (
    ExecutionModel,
    ExecutionObservationEvent,
    EVENT_PRIORITY,
    EventType,
    Fill,
    OrderIntent,
    QuoteKind,
    Side,
)

from .clock import make_id, ny_date
from .ledger import HUNDRED, MILLION, ZERO

COST_SENSITIVITY_HALF_SPREADS = (Decimal("0.00"), Decimal("0.02"), Decimal("0.05"))


def cost_profiles(base: ExecutionModel) -> list[ExecutionModel]:
    """Half-spread sensitivity profiles 0.00 / 0.02 / 0.05 (illustrative, spec 9.4)."""
    profiles = []
    for half_spread in COST_SENSITIVITY_HALF_SPREADS:
        label = f"synthetic-half-spread-{half_spread}-v1"
        profiles.append(
            base.model_copy(
                update={"half_spread_per_100": half_spread, "execution_model_id": label}
            )
        )
    return profiles


def batch_order_key(order: OrderIntent) -> tuple:
    """Explicit execution-batch order, independent of id text (spec 9.4, 9.6).

    Session, then batch priority (sells first, then buys, each by security id as
    assigned at submission), then security id, then order id.
    """
    return (
        order.eligible_session_date.isoformat(),
        order.batch_priority,
        order.security_id,
        order.order_id,
    )


def observation_event_id(order: OrderIntent) -> str:
    """Sorts sells-first-then-security-id within one session (batch priority).

    The session and zero-padded priority lead the id, so the id order matches
    :func:`batch_order_key` even when ``make_id`` digests a long tail.
    """
    return make_id(
        "evt",
        "obs",
        order.eligible_session_date.isoformat(),
        f"{order.batch_priority:03d}",
        order.order_id,
    )


def expiry_event_id(order: OrderIntent) -> str:
    return make_id(
        "evt",
        "expiry",
        order.eligible_session_date.isoformat(),
        f"{order.batch_priority:03d}",
        order.order_id,
    )


@dataclass
class Quote:
    reference: Optional[Decimal]
    bid: Optional[Decimal]
    ask: Optional[Decimal]
    accrued: Decimal
    settlement_date: date
    instrument_active: bool
    data_valid: bool
    invalid_reason: Optional[str]
    calculation_id: Optional[str]


def synthetic_quote(
    order: OrderIntent, curve_snapshot_id: str, session_date: date, pricing, execution, data_mode
) -> Quote:
    sid = order.security_id
    try:
        info = pricing.instrument(sid)
        settle = pricing.settlement_date(sid, session_date)
    except Exception as exc:
        return Quote(
            None, None, None, ZERO, session_date, False, False, f"terms:{type(exc).__name__}", None
        )
    active = info.issue_date <= session_date and settle < info.maturity_date
    if data_mode != DataMode.SYNTHETIC_CURVE:
        return Quote(
            None, None, None, ZERO, settle, active, False, "observed_quotes_not_supported", None
        )
    try:
        price = pricing.price(sid, curve_snapshot_id, settle)
        mid = Decimal(price.clean_price_per_100)
        accrued = Decimal(price.accrued_per_100)
        if not (mid.is_finite() and accrued.is_finite()) or mid <= 0:
            raise ValueError("non-finite or non-positive model price")
    except Exception as exc:
        return Quote(
            None, None, None, ZERO, settle, active, False, f"price:{type(exc).__name__}", None
        )
    half = execution.half_spread_per_100
    return Quote(
        mid, mid - half, mid + half, accrued, settle, active, True, None, price.calculation_id
    )


def build_observation_event(
    order: OrderIntent,
    *,
    curve_snapshot_id: str,
    observed_at,
    quote: Quote,
    recheck_passed: bool,
    recheck_reasons: list[str],
) -> ExecutionObservationEvent:
    return ExecutionObservationEvent(
        event_id=observation_event_id(order),
        effective_at=observed_at,
        priority=EVENT_PRIORITY[EventType.EXECUTION_OBSERVATION],
        order_id=order.order_id,
        observation_id=make_id("obs", curve_snapshot_id, order.security_id),
        observed_at=observed_at,
        session_date=ny_date(observed_at),
        quote_kind=QuoteKind.SYNTHETIC_MODEL,
        reference_clean_price_per_100=quote.reference,
        bid_clean_price_per_100=quote.bid,
        ask_clean_price_per_100=quote.ask,
        accrued_per_100=quote.accrued,
        settlement_date=quote.settlement_date,
        instrument_active=quote.instrument_active,
        data_valid=quote.data_valid,
        invalid_reason=quote.invalid_reason,
        recheck_passed=recheck_passed,
        recheck_reasons=recheck_reasons,
    )


def compute_fill(
    order: OrderIntent, quote: Quote, execution: ExecutionModel, observed_at, observation_id: str
) -> Fill:
    if order.side == Side.BUY:
        exec_clean = quote.ask + execution.slippage_per_100
    else:
        exec_clean = quote.bid - execution.slippage_per_100
    dirty = exec_clean + quote.accrued
    return Fill(
        fill_id=make_id("fill", order.order_id),
        order_id=order.order_id,
        security_id=order.security_id,
        side=order.side,
        face=order.face,
        executed_at=observed_at,
        observation_id=observation_id,
        quote_kind=QuoteKind.SYNTHETIC_MODEL,
        reference_clean_price_per_100=quote.reference,
        execution_clean_price_per_100=exec_clean,
        accrued_per_100=quote.accrued,
        dirty_price_per_100=dirty,
        half_spread_per_100=execution.half_spread_per_100,
        settlement_date=quote.settlement_date,
        consideration_usd=money(order.face * dirty / HUNDRED),
        fees_usd=money(order.face * execution.commission_usd_per_million_face / MILLION),
        spread_cost_usd=money(abs(exec_clean - quote.reference) * order.face / HUNDRED),
    )
