"""Pending orders, reservations, expiry, cancellation, and hindsight-free fills (spec 9.4, 9.6)."""

from datetime import date, time
from decimal import Decimal

import pytest

from research_engine.contracts.portfolio import (
    CommandType,
    DecisionAction,
    EventType,
    OrderStatus,
    Side,
)
from research_engine.simulation.clock import (
    decision_at,
    ny_instant,
    observation_at,
    session_end_at,
)
from research_engine.simulation.engine import DataNotYetAvailable
from research_engine.simulation.fills import cost_profiles
from research_engine.contracts.portfolio import ExecutionModel

from .fakes import DEFAULT_INSTRUMENTS, MATURING
from .harness import Harness, book_state, lot, open_order, position, weights

JAN = lambda d: date(2024, 1, d)  # noqa: E731
N3, N4, N5, N7 = (f"SYN-USD-NOTE-00{i}" for i in (3, 4, 5, 7))


def _funded(**kwargs):
    h = Harness(**kwargs)
    h.capital()
    return h


def test_decision_never_fills_at_its_own_session_observation():
    h = _funded(wobble=0.002)
    decision = h.decide(JAN(2), weights(n3="0.15", cash="0.85"))
    order = decision.orders_created[0]
    assert order.eligible_session_date == JAN(3)
    assert order.submitted_at == decision_at(JAN(2)) < observation_at(JAN(3))
    same_day = h.process(JAN(2), at=ny_instant(JAN(2), time(23, 0)))
    assert same_day.no_op and same_day.fills == []
    proposal = h.process(JAN(3))
    fill = proposal.fills[0]
    assert fill.executed_at == observation_at(JAN(3))
    own_session = h.pricing.price(N3, "curve-2024-01-02", JAN(4)).clean_price_per_100
    eligible = h.pricing.price(N3, "curve-2024-01-03", JAN(4)).clean_price_per_100
    assert fill.reference_clean_price_per_100 == eligible != own_session


@pytest.mark.parametrize(
    "day,expected",
    [(date(2024, 1, 5), date(2024, 1, 8)), (date(2024, 1, 12), date(2024, 1, 16))],
)
def test_eligible_session_uses_the_calendar(day, expected):
    h = Harness()
    h.capital(day=day)
    decision = h.decide(day, weights(n3="0.10", cash="0.90"))
    assert decision.orders_created[0].eligible_session_date == expected
    assert decision.orders_created[0].expires_at == session_end_at(expected)


@pytest.mark.parametrize("ports", [{"missing": {JAN(3)}}, {"not_ready": {JAN(3)}}])
def test_missing_eligible_quote_expires_and_later_quote_cannot_fill(ports):
    h = _funded(**ports)
    h.decide(JAN(2), weights(n3="0.15", cash="0.85"))
    reserved = h.state.reserved_cash_usd
    assert reserved > 0
    expired = h.process(JAN(3))
    assert [e.type for e in expired.events] == [EventType.ORDER_EXPIRY]
    assert expired.events[0].effective_at == session_end_at(JAN(3))
    (change,) = expired.order_status_changes
    assert change.status == OrderStatus.EXPIRED
    assert expired.new_state.reserved_cash_usd == 0 and expired.new_state.open_orders == []
    later = h.process(JAN(4))  # JAN(4) has a valid curve, but the intent is gone
    assert later.fills == [] and later.no_op


def test_delayed_observation_is_deferred_never_expired_or_exposed_early():
    late = {JAN(3): ny_instant(JAN(4), time(10, 0))}
    h = _funded(late=late, wobble=0.002)
    h.decide(JAN(2), weights(n3="0.15", cash="0.85"))
    deferred = h.process(JAN(3))
    assert deferred.fills == [] and deferred.order_status_changes == []
    assert h.state.open_orders  # still ACCEPTED
    assert h.state.as_of < observation_at(JAN(3))
    with pytest.raises(DataNotYetAvailable):
        h.propose(h.request(CommandType.VALUE_PORTFOLIO, decision_at(JAN(3))))
    filled = h.process(JAN(4))
    fill = filled.fills[0]
    assert fill.executed_at == observation_at(JAN(3))
    assert (
        fill.reference_clean_price_per_100
        == h.pricing.price(N3, "curve-2024-01-03", JAN(4)).clean_price_per_100
    )


def test_newer_target_cancels_and_replaces_unfilled_intents():
    h = _funded()
    first = h.decide(JAN(2), weights(n3="0.15", cash="0.85"), decision_id="dec-a")
    old_order = first.orders_created[0]
    second = h.decide(JAN(2), weights(n5="0.10", cash="0.90"), decision_id="dec-b")
    types = [e.type for e in second.events]
    assert types == [EventType.ORDER_CANCELLATION, EventType.ORDERS_SUBMITTED]
    (cancelled,) = second.order_status_changes
    assert cancelled.order_id == old_order.order_id
    assert cancelled.status == OrderStatus.CANCELLED
    assert cancelled.status_reason == "replaced_by:dec-b"
    state = h.state
    assert [o.security_id for o in state.open_orders] == [N5]
    assert state.reserved_cash_usd == second.orders_created[0].reserved_cash_usd
    filled = h.process(JAN(3))
    assert [f.security_id for f in filled.fills] == [N5]


def test_committed_payables_are_unavailable_for_new_purchases():
    pending_lot = lot(N5, "200000", JAN(4), clean="100", trade=JAN(3))
    from research_engine.contracts.portfolio import PendingSettlement

    pending = PendingSettlement(
        settlement_id="stl:x",
        fill_id="fill:x",
        security_id=N5,
        side=Side.BUY,
        face=Decimal("200000"),
        settlement_date=JAN(4),
        cash_usd=Decimal("200000.00"),
    )
    state = book_state(
        JAN(2),
        "300000.00",
        positions=[
            position(N3, [lot(N3, "700000", JAN(2))]),
            position(N5, [pending_lot], settled="0"),
        ],
        pending=[pending],
    )
    h = Harness(state)
    proposal = h.decide(JAN(3), weights(n3="0.70", n5="0.20", n4="0.10", cash="0.0"))
    evaluation = proposal.policy_evaluation
    assert not evaluation.passed
    assert any(r.startswith("funding_settled_cash") for r in evaluation.rejected_reasons)
    assert proposal.no_op and proposal.orders_created == []


def test_fill_rejected_when_funding_fails_at_fill_time():
    order = open_order(N3, Side.BUY, "100000", JAN(2), JAN(3), reserved="50000.00")
    h = Harness(book_state(JAN(2), "50000.00", orders=[order]))
    proposal = h.process(JAN(3))
    (change,) = proposal.order_status_changes
    assert change.status == OrderStatus.REJECTED
    assert "insufficient_funding_at_fill" in change.status_reason
    event = proposal.events[0]
    assert event.type == EventType.EXECUTION_OBSERVATION and not event.recheck_passed
    assert proposal.fills == [] and proposal.new_state.reserved_cash_usd == 0


def test_batch_priority_sells_first_then_security_id():
    orders = [
        open_order(N4, Side.BUY, "50000", JAN(2), JAN(3), reserved="60000.00", priority=1),
        open_order(N3, Side.SELL, "50000", JAN(2), JAN(3), priority=0),
    ]
    state = book_state(
        JAN(2), "500000.00", positions=[position(N3, [lot(N3, "200000", JAN(1))])], orders=orders
    )
    proposal = Harness(state).process(JAN(3))
    assert [f.side for f in proposal.fills] == [Side.SELL, Side.BUY]
    assert [e.order_id for e in proposal.events] == [orders[1].order_id, orders[0].order_id]


def test_instrument_settling_at_maturity_is_rejected_at_fill():
    order = open_order(N7, Side.BUY, "10000", JAN(29), JAN(30), reserved="20000.00")
    h = Harness(
        book_state(JAN(29), "100000.00", orders=[order]),
        instruments=DEFAULT_INSTRUMENTS + [MATURING],
    )
    proposal = h.process(JAN(30))
    (change,) = proposal.order_status_changes
    assert change.status == OrderStatus.REJECTED and "instrument_inactive" in change.status_reason


def test_cost_sensitivity_profiles():
    profiles = cost_profiles(ExecutionModel())
    assert [p.half_spread_per_100 for p in profiles] == [
        Decimal("0.00"),
        Decimal("0.02"),
        Decimal("0.05"),
    ]
    h = Harness()
    h.capital()
    h.decide(JAN(2), weights(n3="0.10", cash="0.90"), execution_model=profiles[2])
    fill = h.apply(
        CommandType.PROCESS_EVENTS, decision_at(JAN(3)), execution_model=profiles[2]
    ).fills[0]
    assert fill.spread_cost_usd == fill.face * Decimal("0.05") / 100
    assert fill.half_spread_per_100 == Decimal("0.05")


def test_bootstrap_action_flags_orders():
    h = _funded()
    decision = h.decide(
        JAN(2), weights(n3="0.47", n5="0.47", cash="0.06"), action=DecisionAction.BOOTSTRAP
    )
    # 47% breaches the single-security cap even for the bootstrap.
    assert not decision.policy_evaluation.passed
    ok = h.decide(
        JAN(2), weights(n3="0.30", n5="0.30", cash="0.40"), action=DecisionAction.BOOTSTRAP
    )
    assert ok.policy_evaluation.passed and all(o.bootstrap for o in ok.orders_created)


def test_make_id_keeps_a_readable_order_preserving_prefix():
    from research_engine.simulation.clock import make_id

    tail = "x" * 200
    first = make_id("evt", "obs", "2024-01-03", "000", tail)
    second = make_id("evt", "obs", "2024-01-03", "001", tail)
    assert len(first) == len(second) == 160
    assert first.startswith("evt:obs:2024-01-03:000:xxx")
    assert first < second  # priority survives the digest
    assert make_id("p", tail) != make_id("p", tail + "y")  # digest covers the full text
    assert make_id("evt", "obs", "short") == "evt:obs:short"


def test_batch_priority_survives_a_160_char_run_id():
    """make_id digests long ids; fills stay sells first and events stay in sort order."""
    from research_engine.contracts.portfolio import event_sort_key
    from research_engine.simulation.clock import make_id

    run_id = "run-0-" + "x" * 154
    assert len(run_id) == 160
    decision = make_id("dec", run_id, "quant_duration", JAN(2).isoformat(), "r0")
    orders = [
        open_order(
            N4,
            Side.BUY,
            "50000",
            JAN(2),
            JAN(3),
            reserved="60000.00",
            priority=1,
            decision=decision,
        ),
        open_order(N3, Side.SELL, "50000", JAN(2), JAN(3), priority=0, decision=decision),
    ]
    assert all(len(o.order_id) == 160 for o in orders)
    state = book_state(
        JAN(2), "500000.00", positions=[position(N3, [lot(N3, "200000", JAN(1))])], orders=orders
    )
    proposal = Harness(state).process(JAN(3))
    assert [f.side for f in proposal.fills] == [Side.SELL, Side.BUY]
    observations = [e for e in proposal.events if e.type == EventType.EXECUTION_OBSERVATION]
    assert [e.order_id for e in observations] == [orders[1].order_id, orders[0].order_id]
    assert observations[0].event_id.startswith("evt:obs:2024-01-03:000:ord:dec:run-0-")
    assert all(len(e.event_id) <= 160 for e in proposal.events)
    keys = [event_sort_key(e) for e in proposal.events]
    assert keys == sorted(keys)
