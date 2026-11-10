"""Pricing against independent closed forms on a flat continuous curve.

Oracle: with D(v, t) = exp(-r * days(v, t) / 365) (exact under log-linear
interpolation because ln D is linear in t), a note's dirty price at settlement s
is SUM_{t_i > s} CF_i * exp(-r * (t_i - t_s)); flows and accrual are written out
by hand from the contract terms. Tolerance: 0.0001 per 100 (spec 16.5).
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import pytest

from research_engine.instruments.schedule import InstrumentModel, InstrumentNotTradableError
from research_engine.pricing.bond_pricer import AnchorError
from research_engine.pricing.curve_model import ExtrapolationError
from research_engine.pricing.yields import dirty_from_yield, solve_ytm, yield_risk
from tests.numerical.helpers import FLAT_REF, make_terms

TOL = 0.0001  # per 100 face


def t(d: date) -> float:
    return (d - FLAT_REF).days / 365.0


def note_009_flows() -> list[tuple[date, float]]:
    """SYN-USD-NOTE-009: 1.90% coupon, 0.95 per period, Feb/Aug 15, matures 2032-02-15 (Sun)."""
    flows = []
    for year in range(2023, 2033):
        for month in (2, 8):
            d = date(year, month, 15)
            if FLAT_REF < d <= date(2032, 2, 15):
                flows.append((d, 0.95))
    # Payment dates adjusted Following on the government-bond calendar (Washington's
    # Birthday = third Monday of February):
    #   2025-02-15 Sat -> Mon 17 holiday -> Tue 18;  2026-02-15 Sun -> Mon 16 holiday -> Tue 17
    #   2026-08-15 Sat -> Mon 17;                    2027-02-15 Mon holiday -> Tue 16
    #   2027-08-15 Sun -> Mon 16;                    2031-02-15 Sat -> Mon 17 holiday -> Tue 18
    #   2032-02-15 Sun -> Mon 16 holiday -> Tue 17;  others fall on business days.
    adjust = {
        date(2025, 2, 15): date(2025, 2, 18),
        date(2026, 2, 15): date(2026, 2, 17),
        date(2026, 8, 15): date(2026, 8, 17),
        date(2027, 2, 15): date(2027, 2, 16),
        date(2027, 8, 15): date(2027, 8, 16),
        date(2031, 2, 15): date(2031, 2, 18),
        date(2032, 2, 15): date(2032, 2, 17),
    }
    out = [(adjust.get(d, d), a) for d, a in flows]
    out[-1] = (out[-1][0], out[-1][1] + 100.0)
    return out


def test_payment_dates_match_hand_adjustments(universe):
    model = InstrumentModel(universe.get("SYN-USD-NOTE-009"))
    remaining = [
        (p.payment_date, float(p.amount_per_100)) for p in model.entitled_periods(FLAT_REF)
    ]
    assert remaining == note_009_flows()


def test_dirty_clean_accrued_against_closed_form(flat_pricing):
    port, curve_id, r = flat_pricing
    s = date(2023, 3, 16)
    expected_dirty = sum(a * math.exp(-r * (t(d) - t(s))) for d, a in note_009_flows())
    # Accrued: period 2023-02-15 .. 2023-08-15 = 181 days, 29 elapsed at 03-16.
    expected_accrued = 0.95 * 29 / 181
    result = port.price("SYN-USD-NOTE-009", curve_id, s)
    assert abs(float(result.dirty_price_per_100) - expected_dirty) < TOL
    assert abs(float(result.accrued_per_100) - expected_accrued) < 1e-10
    assert abs(float(result.clean_price_per_100) - (expected_dirty - expected_accrued)) < TOL
    # Clean/dirty conversion is exact in the published decimals.
    assert result.dirty_price_per_100 - result.clean_price_per_100 == result.accrued_per_100
    assert result.settlement_date == s


def test_settlement_vs_valuation_anchor(flat_pricing):
    """PV(v) = dirty(s) * D(v,s) when no flow falls in (v, s]."""
    port, curve_id, r = flat_pricing
    v, s = FLAT_REF, date(2023, 3, 16)
    face = Decimal(1_000_000)
    price = port.price("SYN-USD-NOTE-009", curve_id, s)
    position = port.value_position("SYN-USD-NOTE-009", curve_id, v, face)
    expected_pv = 10_000 * sum(a * math.exp(-r * t(d)) for d, a in note_009_flows())
    assert abs(float(position.pv_dirty_usd) - expected_pv) < 1e-4
    d_vs = math.exp(-r * t(s))
    assert abs(float(price.dirty_price_per_100) * d_vs * 10_000 - expected_pv) < 1e-3
    assert abs(float(port.discount_factor(curve_id, v, s)) - d_vs) < 1e-13
    # The settlement value is not the valuation-date PV.
    assert price.dirty_price_per_100 * 10_000 != position.pv_dirty_usd


def test_flow_between_valuation_and_settlement(flat_pricing):
    """A coupon paid on settlement day belongs to the seller (entitlement), so the
    valuation-date PV exceeds the discounted settlement value by that coupon."""
    port, curve_id, r = flat_pricing
    # NOTE-007 (3.95%, Mar/Sep 15) pays 2024-09-16 (Sun 15 adjusted). Valuation on
    # Friday 2024-09-13 settles Monday 2024-09-16 = payment date.
    v = date(2024, 9, 13)
    s = port.settlement_date("SYN-USD-NOTE-007", v)
    assert s == date(2024, 9, 16)
    price = port.price("SYN-USD-NOTE-007", curve_id, s)
    pv = port.value_position("SYN-USD-NOTE-007", curve_id, v, Decimal(100))
    d_vs = math.exp(-r * (t(s) - t(v)))
    coupon_pv = 1.975 * d_vs
    assert abs(float(pv.pv_dirty_usd) - (float(price.dirty_price_per_100) * d_vs + coupon_pv)) < (
        1e-5
    )


def test_anchor_before_curve_reference_rejected(flat_pricing):
    port, curve_id, _ = flat_pricing
    with pytest.raises(AnchorError):
        port.price("SYN-USD-NOTE-009", curve_id, date(2023, 3, 14))
    with pytest.raises(InstrumentNotTradableError):
        port.price("SYN-USD-NOTE-001", curve_id, date(2023, 7, 17))  # final payment date


def test_extrapolation_beyond_horizon_rejected(universe):
    from research_engine.pricing.calc_store import CalculationStore
    from research_engine.pricing.curve_model import InMemoryCurveSource
    from research_engine.pricing.port import QuantLibPricingPort
    from tests.numerical.helpers import TEST_KEY, flat_snapshot

    short = flat_snapshot(years=5)  # horizon 2028-03-15
    port = QuantLibPricingPort(universe, InMemoryCurveSource([short]), CalculationStore(TEST_KEY))
    port.price("SYN-USD-NOTE-007", short.curve_snapshot_id, date(2023, 3, 16))  # 2028-03-15 ok
    with pytest.raises(ExtrapolationError):
        port.price("SYN-USD-NOTE-009", short.curve_snapshot_id, date(2023, 3, 16))


def test_ytm_par_bond_on_coupon_date():
    # On a coupon date with price 100, the street yield equals the coupon (closed form:
    # SUM 2/(1.02)^k + 100/(1.02)^10 = 100).
    terms = make_terms("SYN-USD-NOTE-903", date(2023, 3, 15), date(2028, 3, 15), "0.04")
    model = InstrumentModel(terms)
    assert abs(dirty_from_yield(model, date(2023, 3, 15), 0.04) - 100.0) < 1e-12
    assert abs(solve_ytm(model, date(2023, 3, 15), 100.0) - 0.04) < 1e-12


def test_ytm_round_trip_and_yield_duration_closed_form():
    terms = make_terms("SYN-USD-NOTE-904", date(2023, 3, 15), date(2028, 3, 15), "0.03")
    model = InstrumentModel(terms)
    y = 0.051234
    i = y / 2
    n = 10
    # Closed form on a coupon date: annuity + discounted principal.
    expected = 1.5 * (1 - (1 + i) ** -n) / i + 100 * (1 + i) ** -n
    assert abs(dirty_from_yield(model, date(2023, 3, 15), y) - expected) < 1e-10
    assert abs(solve_ytm(model, date(2023, 3, 15), expected) - y) < 1e-12
    # Modified duration (years) = (1/(1+i)) * SUM (k/2) * PV_k / P.
    mac_years = sum((k / 2) * cf * (1 + i) ** -k for k, cf in _cfs(1.5, n)) / expected
    risk = yield_risk(model, date(2023, 3, 15), y)
    assert abs(risk.modified_duration - mac_years / (1 + i)) < 1e-10
    convexity = sum(k * (k + 1) / 4 * cf * (1 + i) ** (-k - 2) for k, cf in _cfs(1.5, n)) / (
        expected
    )
    assert abs(risk.convexity - convexity) < 1e-9


def _cfs(coupon: float, n: int) -> list[tuple[int, float]]:
    return [(k, coupon + (100.0 if k == n else 0.0)) for k in range(1, n + 1)]


def test_ytm_mid_period_fractional_exponent():
    # Settlement 2023-05-15: 61 of 184 days into 2023-03-15..2023-09-15 -> w = 123/184.
    terms = make_terms("SYN-USD-NOTE-905", date(2023, 3, 15), date(2025, 3, 15), "0.05")
    model = InstrumentModel(terms)
    s = date(2023, 5, 15)
    y = 0.047
    w = 123 / 184
    expected = sum((2.5 + (100 if k == 3 else 0)) / (1 + y / 2) ** (w + k) for k in range(4))
    assert abs(dirty_from_yield(model, s, y) - expected) < 1e-12
    assert abs(solve_ytm(model, s, expected) - y) < 1e-12


def test_port_yield_quote_conversion(flat_pricing):
    port, curve_id, _ = flat_pricing
    s = date(2023, 3, 16)
    price = port.price("SYN-USD-NOTE-009", curve_id, s)
    ytm = port.yield_from_clean_price("SYN-USD-NOTE-009", s, price.clean_price_per_100)
    model = InstrumentModel(port.terms("SYN-USD-NOTE-009"))
    assert abs(dirty_from_yield(model, s, float(ytm)) - float(price.dirty_price_per_100)) < 1e-8


def test_value_position_scales_face_once(flat_pricing):
    port, curve_id, _ = flat_pricing
    one = port.value_position("SYN-USD-NOTE-009", curve_id, FLAT_REF, Decimal(100))
    big = port.value_position("SYN-USD-NOTE-009", curve_id, FLAT_REF, Decimal(2_500_000))
    assert abs(big.pv_dirty_usd - one.pv_dirty_usd * 25_000) < Decimal("0.05")
    assert abs(big.parallel_dv01_usd - one.parallel_dv01_usd * 25_000) < Decimal("0.05")
    assert big.effective_duration_years == one.effective_duration_years
