"""Valuation: mark policies, staleness, incompleteness, risk aggregation (spec 8.4, 9.1)."""

from datetime import date
from decimal import Decimal

from research_engine.contracts.common import money
from research_engine.contracts.portfolio import CommandType, MarkType, PendingSettlement, Side
from research_engine.simulation.clock import valuation_at

from .fakes import FakeObservedMarks
from .harness import Harness, book_state, lot, position

JAN = lambda d: date(2024, 1, d)  # noqa: E731
N3, N5 = "SYN-USD-NOTE-003", "SYN-USD-NOTE-005"


def _holding(clean="97.0", accrued_value="0"):
    held = [lot(N3, "1000000", JAN(10), clean=clean, accrued=accrued_value)]
    return book_state(JAN(10), "50000.00", positions=[position(N3, held)])


def test_observed_mark_below_model_creates_no_artificial_nav_gain():
    probe = Harness()
    model_clean = probe.pricing.price(N3, "curve-2024-01-11", JAN(12)).clean_price_per_100
    observed_clean = (model_clean - Decimal("1.5")).quantize(Decimal("0.0001"))
    accrued = probe.pricing.accrued_per_100(N3, JAN(12))
    state = _holding(clean=str(observed_clean), accrued_value=str(money(Decimal(10000) * accrued)))

    model = Harness(state).value(JAN(11))
    observed_h = Harness(state)
    observed_h.mark_source = FakeObservedMarks(observed_h.pricing, {N3: observed_clean})
    observed = observed_h.value(JAN(11))

    assert observed.valuation.mark_policy == "observed_mid_v1"
    assert observed.valuation.marks[0].mark_type == MarkType.OBSERVED_MID
    assert model.valuation.mark_policy == "synthetic_curve_model_v1"
    gap = model.valuation.equity_usd - observed.valuation.equity_usd
    assert Decimal("14000") < gap < Decimal("16000")
    # Cost basis was struck at the observed price: no immediate unrealized gain under
    # the observed policy, while the model policy would show a ~15k "gain".
    assert abs(observed.new_state.booked_unrealized_usd) < Decimal("500")
    assert model.new_state.booked_unrealized_usd > Decimal("14000")


def test_missing_observed_mark_makes_valuation_incomplete_without_substitution():
    h = Harness(_holding())
    h.mark_source = FakeObservedMarks(h.pricing, {})
    proposal = h.value(JAN(11))
    v = proposal.valuation
    assert not v.complete and v.equity_usd is None
    assert f"missing_observed_mark:{N3}" in v.incomplete_reasons
    assert proposal.journals == []  # no mark-to-market on an incomplete valuation
    assert proposal.reconciliation.ok


def test_pending_settlement_without_discounting_support_is_incomplete():
    pending = PendingSettlement(
        settlement_id="stl:p",
        fill_id="fill:p",
        security_id=N5,
        side=Side.BUY,
        face=Decimal("100000"),
        settlement_date=JAN(12),
        cash_usd=Decimal("100000.00"),
    )
    state = book_state(
        JAN(10),
        "500000.00",
        positions=[position(N5, [lot(N5, "100000", JAN(12), trade=JAN(11))], settled="0")],
        pending=[pending],
    )
    h = Harness(state, fail_discount=True)
    v = h.value(JAN(11)).valuation
    assert not v.complete and v.equity_usd is None
    assert any(
        r.startswith("pending_settlement_discount_unavailable") for r in v.incomplete_reasons
    )
    ok = Harness(state).value(JAN(11)).valuation
    assert ok.complete
    factor = Harness(state).pricing.discount_factor("curve-2024-01-11", JAN(11), JAN(12))
    assert ok.payables_pv_usd == money(Decimal("100000.00") * factor)


def test_stale_marks_are_flagged_and_not_posted():
    h = Harness(_holding())
    proposal = h.value(JAN(16), snapshot_day=JAN(10))
    v = proposal.valuation
    assert not v.complete and v.marks[0].stale
    assert v.marks[0].mark_age_business_days == 3
    assert f"stale_mark:{N3}" in v.incomplete_reasons
    assert proposal.journals == []


def test_dv01_and_duration_aggregation():
    held = [position(N3, [lot(N3, "400000", JAN(2))]), position(N5, [lot(N5, "300000", JAN(2))])]
    h = Harness(book_state(JAN(10), "300000.00", positions=held))
    v = h.value(JAN(11)).valuation
    dv01 = sum(
        Decimal(h.pricing.value_position(s, "curve-2024-01-11", JAN(11), f).parallel_dv01_usd)
        for s, f in ((N3, Decimal("400000")), (N5, Decimal("300000")))
    )
    assert v.parallel_dv01_usd == money(dv01)
    expected = (dv01 * 10000 / v.equity_usd).quantize(Decimal("0.000001"))
    assert v.effective_duration_years == expected
    assert v.equity_usd == v.cash_usd + v.bond_value_usd


def test_no_curve_available_is_incomplete():
    from datetime import timedelta

    gap = {date(2023, 12, 1) + timedelta(days=i) for i in range(62)}
    h = Harness(_holding(), missing=gap)
    proposal = h.apply(CommandType.VALUE_PORTFOLIO, valuation_at(JAN(11)), market_snapshot=None)
    assert "no_curve_available" in proposal.valuation.incomplete_reasons
    assert proposal.valuation.marks[0].mark_type == MarkType.UNAVAILABLE
