"""Spec 16.5 accounting rows: buy/sell/settle/coupon/mature with balanced journals."""

from datetime import date
from decimal import Decimal

from research_engine.contracts.common import money
from research_engine.contracts.portfolio import AccountCode, DecisionAction, EventType, Side
from research_engine.simulation.clock import decision_at
from research_engine.simulation.ledger import journal_is_balanced, state_balances

from .fakes import DEFAULT_INSTRUMENTS, MATURING
from .harness import Harness, book_state, lot, open_order, position, weights

N3 = "SYN-USD-NOTE-003"
N7 = "SYN-USD-NOTE-007"
JAN = lambda d: date(2024, 1, d)  # noqa: E731


def _lines(journal):
    return {(ln.account, ln.debit_usd > 0): ln for ln in journal.lines}


def _assert_ok(proposal):
    assert proposal.reconciliation.ok, proposal.reconciliation.messages
    assert all(journal_is_balanced(j) for j in proposal.journals)
    assert sum(state_balances(proposal.new_state).values(), Decimal("0")) == 0


def test_buy_fill_then_settlement_postings():
    h = Harness()
    h.capital()
    decision = h.decide(JAN(2), weights(n3="0.30", cash="0.70"), action=DecisionAction.BOOTSTRAP)
    assert decision.policy_evaluation.passed, decision.policy_evaluation.rejected_reasons
    assert decision.policy_evaluation.bootstrap_exemption_applied
    order = decision.orders_created[0]
    assert h.state.reserved_cash_usd == order.reserved_cash_usd > 0
    assert order.eligible_session_date == JAN(3)

    fill_proposal = h.process(JAN(3))
    _assert_ok(fill_proposal)
    fill = fill_proposal.fills[0]
    price = h.pricing.price(N3, "curve-2024-01-03", JAN(4))
    assert fill.reference_clean_price_per_100 == price.clean_price_per_100
    assert fill.execution_clean_price_per_100 == price.clean_price_per_100 + Decimal("0.02")
    assert fill.settlement_date == JAN(4)
    assert fill.consideration_usd == money(fill.face * fill.dirty_price_per_100 / 100)
    assert fill.spread_cost_usd == money(fill.face * Decimal("0.02") / 100)
    journal = fill_proposal.journals[0]
    assert journal.template == "buy_fill_v1"
    lines = _lines(journal)
    principal = money(fill.face * fill.execution_clean_price_per_100 / 100)
    assert lines[(AccountCode.BOND_PRINCIPAL, True)].debit_usd == principal
    assert lines[(AccountCode.ACCRUED_INTEREST_PURCHASED, True)].debit_usd == (
        fill.consideration_usd - principal
    )
    assert lines[(AccountCode.SETTLEMENT_PAYABLE, False)].credit_usd == fill.consideration_usd
    state = fill_proposal.new_state
    assert state.reserved_cash_usd == 0 and state.open_orders == []
    assert state.positions[0].economic_face == fill.face
    assert state.positions[0].settled_face == 0
    assert state.cash_usd == Decimal("1000000.00")  # no cash moves before settlement

    settle = h.process(JAN(4))
    _assert_ok(settle)
    assert [j.template for j in settle.journals] == ["buy_settlement_v1"]
    assert settle.new_state.cash_usd == Decimal("1000000.00") - fill.consideration_usd
    assert settle.new_state.positions[0].settled_face == fill.face
    assert settle.new_state.pending_settlements == []


def test_sell_fifo_realized_gain_and_accrued_split():
    lots = [
        lot(N3, "100000", date(2023, 12, 1), clean="99", accrued="500.00"),
        lot(N3, "100000", date(2023, 12, 15), clean="98", accrued="700.00"),
    ]
    state = book_state(
        JAN(2),
        "500000.00",
        positions=[position(N3, lots)],
        orders=[open_order(N3, Side.SELL, "150000", JAN(2), JAN(3))],
    )
    h = Harness(state)
    proposal = h.process(JAN(3))
    _assert_ok(proposal)
    fill = proposal.fills[0]
    assert fill.execution_clean_price_per_100 == fill.reference_clean_price_per_100 - Decimal(
        "0.02"
    )
    clean = money(fill.face * fill.execution_clean_price_per_100 / 100)
    accrued_received = fill.consideration_usd - clean
    journal = proposal.journals[0]
    assert journal.template == "sell_fill_v1"
    by_account = {}
    for line in journal.lines:
        by_account[line.account] = by_account.get(line.account, Decimal("0")) + (
            line.debit_usd - line.credit_usd
        )
    assert by_account[AccountCode.BOND_PRINCIPAL] == Decimal("-148000.00")  # 99,000 + 49,000
    assert by_account[AccountCode.ACCRUED_INTEREST_PURCHASED] == Decimal("-850.00")
    assert by_account[AccountCode.REALIZED_GAIN_LOSS] == -(clean - Decimal("148000.00"))
    assert by_account[AccountCode.INTEREST_INCOME] == -(accrued_received - Decimal("850.00"))
    assert by_account[AccountCode.SETTLEMENT_RECEIVABLE] == fill.consideration_usd
    remaining = proposal.new_state.positions[0]
    assert remaining.economic_face == Decimal("50000") and remaining.settled_face == Decimal(
        "200000"
    )
    assert [ln.face for ln in remaining.lots] == [Decimal("50000")]
    assert remaining.lots[0].principal_cost_usd == Decimal("49000.00")
    assert remaining.lots[0].accrued_purchased_usd == Decimal("350.00")

    settle = h.process(JAN(4))
    _assert_ok(settle)
    assert [j.template for j in settle.journals] == ["sell_settlement_v1"]
    assert settle.new_state.cash_usd == Decimal("500000.00") + fill.consideration_usd
    assert settle.new_state.positions[0].settled_face == Decimal("50000")


def _coupon_state(orders=()):
    held = [lot(N3, "100000", JAN(10), clean="99.5", accrued="1750.00")]
    return book_state(JAN(29), "500000.00", positions=[position(N3, held)], orders=list(orders))


def _coupon_flows(proposal):
    return [cf for cf in proposal.cash_flows if cf.kind == "COUPON"]


def test_coupon_with_purchased_accrued_recovery():
    h = Harness(_coupon_state())
    proposal = h.process(JAN(31))
    _assert_ok(proposal)
    (flow,) = _coupon_flows(proposal)
    assert flow.entitled_face == Decimal("100000") and flow.amount_usd == Decimal("2000.00")
    journal = proposal.journals[0]
    assert journal.template == "coupon_payment_v1"
    lines = {ln.account: ln for ln in journal.lines}
    assert lines[AccountCode.CASH].debit_usd == Decimal("2000.00")
    assert lines[AccountCode.ACCRUED_INTEREST_PURCHASED].credit_usd == Decimal("1750.00")
    assert lines[AccountCode.INTEREST_INCOME].credit_usd == Decimal("250.00")
    assert proposal.new_state.positions[0].lots[0].accrued_purchased_usd == 0


def test_buy_settling_on_payment_date_is_not_entitled():
    order = open_order(N3, Side.BUY, "50000", JAN(29), JAN(30), reserved="60000.00")
    h = Harness(_coupon_state([order]))
    proposal = h.process(JAN(31))
    _assert_ok(proposal)
    assert proposal.fills[0].settlement_date == JAN(31)
    (flow,) = _coupon_flows(proposal)
    assert flow.entitled_face == Decimal("100000")  # the new 50k is not entitled
    pos = proposal.new_state.positions[0]
    assert pos.economic_face == pos.settled_face == Decimal("150000")
    new_lot = [ln for ln in pos.lots if ln.settlement_date == JAN(31)][0]
    assert new_lot.accrued_purchased_usd == 0  # accrued restarts on the payment date
    types = [e.type for e in proposal.events]
    assert types == [
        EventType.EXECUTION_OBSERVATION,
        EventType.SETTLEMENT_DUE,
        EventType.COUPON_PAYMENT,
    ]


def test_sale_settling_on_payment_date_keeps_seller_entitled():
    order = open_order(N3, Side.SELL, "40000", JAN(29), JAN(30))
    h = Harness(_coupon_state([order]))
    proposal = h.process(JAN(31))
    _assert_ok(proposal)
    (flow,) = _coupon_flows(proposal)
    assert flow.entitled_face == Decimal("100000") and flow.amount_usd == Decimal("2000.00")
    state = proposal.new_state
    assert state.positions[0].economic_face == state.positions[0].settled_face == Decimal("60000")
    # 700 purchased accrued relieved on the sale, the remaining 1,050 recovered by the coupon.
    assert state.interest_income_usd == Decimal("250.00")


def test_redemption_credits_principal_once_and_final_coupon():
    held = [lot(N7, "200000", date(2023, 6, 1), clean="99.5", accrued="300.00")]
    state = book_state(JAN(29), "10000.00", positions=[position(N7, held)])
    h = Harness(state, instruments=DEFAULT_INSTRUMENTS + [MATURING])
    proposal = h.process(date(2024, 2, 1))
    _assert_ok(proposal)
    kinds = {cf.kind: cf.amount_usd for cf in proposal.cash_flows}
    assert kinds == {"REDEMPTION": Decimal("200000.00"), "COUPON": Decimal("1500.00")}
    templates = [j.template for j in proposal.journals]
    assert templates == ["redemption_v1", "coupon_payment_v1"]
    new = proposal.new_state
    assert new.positions == []
    assert new.cash_usd == Decimal("211500.00")
    assert new.realized_gain_loss_usd == Decimal("1000.00")
    assert new.interest_income_usd == Decimal("1200.00")
    again = h.process(date(2024, 2, 2))
    assert again.no_op and again.cash_flows == []


def test_mark_to_market_reconciles_book_to_economic_nav():
    h = Harness()
    h.capital()
    h.decide(JAN(2), weights(n3="0.30", n5="0.30", cash="0.40"), action=DecisionAction.BOOTSTRAP)
    h.process(JAN(3))
    valuation = h.value(JAN(3))
    _assert_ok(valuation)
    assert valuation.valuation.complete
    assert valuation.reconciliation.difference_usd == 0
    assert valuation.reconciliation.book_equity_usd == valuation.valuation.equity_usd
    assert [j.template for j in valuation.journals] == ["mark_to_market_v1"]
    # Payables are discounted from settlement date to the valuation date.
    assert (
        valuation.valuation.payables_pv_usd
        < h.state.pending_settlements[0].cash_usd + h.state.pending_settlements[1].cash_usd
    )


def test_coupon_payment_creates_no_artificial_nav_jump():
    held = [lot(N3, "1000000", JAN(10), clean="99.5", accrued="17500.00")]
    h = Harness(book_state(JAN(29), "50000.00", positions=[position(N3, held)]))
    before = h.value(JAN(30))
    after_coupon = h.value(JAN(31))
    _assert_ok(after_coupon)
    assert after_coupon.new_state.cash_usd - before.new_state.cash_usd == Decimal("20000.00")
    jump = after_coupon.valuation.equity_usd - before.valuation.equity_usd
    assert abs(jump) < Decimal("500")  # one day of carry, not the 20,000 coupon


def test_events_sorted_and_clock_monotonic():
    order = open_order(N3, Side.BUY, "50000", JAN(29), JAN(30), reserved="60000.00")
    h = Harness(_coupon_state([order]))
    proposal = h.process(JAN(31))
    keys = [(e.effective_at, e.priority, e.event_id) for e in proposal.events]
    assert keys == sorted(keys)
    assert all(e.effective_at > _coupon_state().as_of for e in proposal.events)
    assert proposal.new_state.as_of == decision_at(JAN(31))


def test_withdrawal_is_limited_to_settled_cash_net_of_reservations_and_payables():
    import pytest

    from research_engine.contracts.portfolio import CommandType, PendingSettlement
    from research_engine.simulation.ledger import WithdrawalExceedsAvailableCash

    day = date(2024, 4, 10)
    pending = PendingSettlement(
        settlement_id="stl:fill:x",
        fill_id="fill:x",
        security_id=N3,
        side=Side.BUY,
        face=Decimal("500000"),
        settlement_date=date(2024, 4, 11),
        cash_usd=Decimal("500000.00"),
    )
    held = lot(N3, "500000", date(2024, 4, 11), clean="100", trade=day)
    reserved = open_order(
        "SYN-USD-NOTE-004", Side.BUY, "40000", day, date(2024, 4, 11), reserved="40000.00"
    )
    state = book_state(
        day,
        "600000",
        positions=[position(N3, [held], settled="0")],
        pending=[pending],
        orders=[reserved],
        as_of=decision_at(day),
    )
    h = Harness(state)
    # 600,000 settled - 40,000 reserved - 500,000 payable = 60,000 available.
    with pytest.raises(WithdrawalExceedsAvailableCash, match="available cash 60000"):
        h.apply(CommandType.CAPITAL_FLOW, decision_at(day), capital_amount_usd=Decimal("-60000.01"))
    assert h.state.version == state.version  # nothing committed
    ok = h.apply(CommandType.CAPITAL_FLOW, decision_at(day), capital_amount_usd=Decimal("-60000"))
    _assert_ok(ok)
    assert ok.new_state.cash_usd == Decimal("540000.00")
