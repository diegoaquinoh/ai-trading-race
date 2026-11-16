"""DV01, key-rate DV01, durations, scenarios and portfolio aggregation (spec 8.5, 8.6, 16.5).

Oracles are written by hand on a flat continuous curve r (D = exp(-r t)), where
a constant node shift is an exact parallel shift: PV(d) = SUM CF exp(-(r + d) t).

Tolerances and why:
* parallel DV01 vs closed form: 1e-5 USD per 1mm face (only float/quantization noise;
  the engine and oracle compute the same central difference).
* effective duration vs analytic SUM t PV / PV: 1e-6 relative; the central difference
  error is (d t)^2 / 6 ~ 1e-7 for d = 1bp and t <= 10y.
* key-rate sum vs parallel: 1e-6 relative. Tent weights form a partition of unity and
  node shocks enter ln D linearly, so the first-order terms sum exactly; what remains
  are third-order cross terms of relative size ~ (d T)^2 <= (1e-4 * 10)^2 = 1e-6.
* bump stability (0.5/1/2 bp): 2e-6 relative, the O(d^2) central-difference term for
  d = 2bp, T ~ 9y: (2e-4 * 9)^2 / 6 ~ 5e-7, with margin.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from research_engine.instruments.schedule import InstrumentModel
from research_engine.pricing.curve_model import DiscountCurveModel
from research_engine.risk.measures import ShockedCurves, curve_sensitivity
from research_engine.risk.scenarios import SCENARIO_LIBRARY_V1
from research_engine.risk.shocks import KEY_RATE_TENORS_V1, triangular_weight
from tests.numerical.helpers import FLAT_REF, flat_node_dates, flat_snapshot, make_terms
from tests.numerical.test_pricing import note_009_flows

FACE = Decimal(1_000_000)
BP = 1e-4


def t(d: date) -> float:
    return (d - FLAT_REF).days / 365.0


def pv_flat(flows, r: float, shift=lambda _t: 0.0) -> float:
    return sum(a * math.exp(-(r + shift(t(d))) * t(d)) for d, a in flows)


def test_triangular_weights_partition_of_unity():
    for x in np.linspace(0.0, 40.0, 401):
        total = sum(triangular_weight(x, KEY_RATE_TENORS_V1, k) for k in range(5))
        assert total == pytest.approx(1.0, abs=1e-15)
    assert triangular_weight(3.5, KEY_RATE_TENORS_V1, 1) == pytest.approx(0.5)
    assert triangular_weight(3.5, KEY_RATE_TENORS_V1, 2) == pytest.approx(0.5)
    assert triangular_weight(0.25, KEY_RATE_TENORS_V1, 0) == 1.0  # flat short end
    assert triangular_weight(35.0, KEY_RATE_TENORS_V1, 4) == 1.0  # flat end point


def test_parallel_dv01_and_effective_duration_closed_form(flat_pricing):
    port, curve_id, r = flat_pricing
    flows = note_009_flows()
    result = port.value_position("SYN-USD-NOTE-009", curve_id, FLAT_REF, FACE)
    expected_dv01 = 10_000 * (pv_flat(flows, r - BP) - pv_flat(flows, r + BP)) / 2
    assert abs(float(result.parallel_dv01_usd) - expected_dv01) < 1e-5
    assert result.parallel_dv01_usd > 0  # gain for a downward shift
    analytic = sum(t(d) * a * math.exp(-r * t(d)) for d, a in flows) / pv_flat(flows, r)
    assert abs(float(result.effective_duration_years) / analytic - 1) < 1e-6


def test_key_rate_oracle_single_flow_at_node():
    """A zero-coupon 5y flow sits on the 2028-03-15 node: the tent bump moves ln D there by
    exactly -d*w_k(t)*t, so KR_k = 100 e^{-rt} sinh(1bp * w_k(t) * t) (exact central diff)."""
    r = 0.04
    curve = DiscountCurveModel.from_snapshot(flat_snapshot(rate=r))
    model = InstrumentModel(make_terms("SYN-USD-NOTE-906", FLAT_REF, date(2028, 3, 15), "0"))
    tf = t(date(2028, 3, 15))
    assert date(2028, 3, 15) in flat_node_dates(FLAT_REF)
    sens = curve_sensitivity(model, curve, FLAT_REF)
    for k, key in enumerate(KEY_RATE_TENORS_V1):
        w = triangular_weight(tf, KEY_RATE_TENORS_V1, k)
        expected = 100 * math.exp(-r * tf) * math.sinh(BP * w * tf)
        assert abs(sens.key_rate_dv01[k] - expected) < 1e-12, key
    assert sens.key_rate_dv01[2] > 0.99 * sens.parallel_dv01  # almost all at the 5y key


def test_key_rate_sum_matches_parallel_for_universe(pricing, market):
    session = date(2024, 6, 3)
    curve_id = market.curve_for_session(session).curve_snapshot_id
    for info in pricing.universe(session):
        risk = pricing.position_risk(info.security_id, curve_id, session, FACE)
        total = sum(e.dv01_usd for e in risk.key_rate_dv01)
        assert abs(total - risk.parallel_dv01_usd) <= Decimal("1e-6") * risk.parallel_dv01_usd + (
            Decimal("0.00001")
        ), info.security_id
        assert abs(risk.key_rate_sum_minus_parallel_usd) <= Decimal("1e-6") * (
            risk.parallel_dv01_usd
        ) + Decimal("0.000005")


def test_bump_size_stability(pricing, market):
    session = date(2023, 9, 1)
    curve = pricing.curve_model(market.curve_for_session(session).curve_snapshot_id)
    model = InstrumentModel(pricing.terms("SYN-USD-NOTE-009"))
    dv01s = [
        curve_sensitivity(model, ShockedCurves(curve, bump=b), session).parallel_dv01
        for b in (0.5 * BP, BP, 2 * BP)
    ]
    assert max(dv01s) / min(dv01s) - 1 < 2e-6
    krs = [
        curve_sensitivity(model, ShockedCurves(curve, bump=b), session).key_rate_dv01
        for b in (0.5 * BP, 2 * BP)
    ]
    for small, large in zip(*krs):
        assert abs(small - large) <= 2e-6 * abs(small) + 1e-10


def test_parallel_scenario_full_repricing_closed_form(flat_pricing):
    port, curve_id, r = flat_pricing
    flows = note_009_flows()
    for scenario_id, bp in [("parallel_up_25", 25), ("parallel_down_100", -100)]:
        res = port.scenario("SYN-USD-NOTE-009", curve_id, FLAT_REF, scenario_id, FACE)
        expected = 10_000 * (pv_flat(flows, r + bp * BP) - pv_flat(flows, r))
        assert abs(float(res.pnl_usd) - expected) < 1e-5
        assert (res.pnl_usd < 0) == (bp > 0)
        # Approximations display their error against full repricing.
        assert res.dv01_approx_error_usd == res.dv01_approx_pnl_usd - res.pnl_usd
        assert abs(res.convexity_approx_error_usd) < abs(res.dv01_approx_error_usd)


def _steepener_shift(x: float) -> float:
    """Hand transcription of steepener_v1: -25bp at 2y, 0 at 5y, +25bp at 10y, flat outside."""
    if x <= 2:
        return -25 * BP
    if x <= 5:
        return -25 * BP + 25 * BP * (x - 2) / 3
    if x <= 10:
        return 25 * BP * (x - 5) / 5
    return 25 * BP


def test_steepener_applied_at_nodes_closed_form(flat_pricing):
    port, curve_id, r = flat_pricing
    nodes = [t(d) for d in flat_node_dates(FLAT_REF)]
    node_log_shift = [_steepener_shift(x) * x for x in nodes]

    def pv_steep(flows):
        return sum(
            a * math.exp(-r * t(d) - np.interp(t(d), nodes, node_log_shift)) for d, a in flows
        )

    flows = note_009_flows()
    res = port.scenario("SYN-USD-NOTE-009", curve_id, FLAT_REF, "steepener_v1", FACE)
    assert abs(float(res.pnl_usd) - 10_000 * (pv_steep(flows) - pv_flat(flows, r))) < 1e-5
    flat = port.scenario("SYN-USD-NOTE-009", curve_id, FLAT_REF, "flattener_v1", FACE)
    assert flat.dv01_approx_pnl_usd == -res.dv01_approx_pnl_usd  # first order is antisymmetric
    assert abs(res.dv01_approx_error_usd) < Decimal("0.02") * abs(res.pnl_usd)


def test_scenario_outside_nodes_is_flat_extension(flat_pricing):
    # NOTE-001's only remaining flow (2023-07-17) lies before the 2y scenario node, so the
    # steepener acts as a -25bp parallel shift there.
    port, curve_id, _ = flat_pricing
    steep = port.scenario("SYN-USD-NOTE-001", curve_id, FLAT_REF, "steepener_v1", FACE)
    down = port.scenario("SYN-USD-NOTE-001", curve_id, FLAT_REF, "parallel_down_25", FACE)
    assert abs(steep.pnl_usd - down.pnl_usd) <= Decimal("0.000002")


def test_scenario_library_v1_is_exact():
    assert sorted(SCENARIO_LIBRARY_V1) == sorted(
        [
            "parallel_up_25",
            "parallel_down_25",
            "parallel_up_100",
            "parallel_down_100",
            "steepener_v1",
            "flattener_v1",
        ]
    )
    steep = SCENARIO_LIBRARY_V1["steepener_v1"]
    flat = SCENARIO_LIBRARY_V1["flattener_v1"]
    assert [(n.tenor_years, n.shift_bp) for n in steep.node_shifts] == [
        (Decimal(2), Decimal(-25)),
        (Decimal(5), Decimal(0)),
        (Decimal(10), Decimal(25)),
    ]
    assert [n.shift_bp for n in flat.node_shifts] == [-n.shift_bp for n in steep.node_shifts]
    assert all(s.holdings_fixed and s.hypothetical for s in SCENARIO_LIBRARY_V1.values())
    assert SCENARIO_LIBRARY_V1["parallel_up_100"].parallel_shift_bp == Decimal(100)


def test_portfolio_aggregation_no_double_scaling(pricing, market):
    session = date(2024, 3, 1)
    curve_id = market.curve_for_session(session).curve_snapshot_id
    holdings = [
        ("SYN-USD-NOTE-009", Decimal(500_000)),
        ("SYN-USD-NOTE-009", Decimal(500_000)),  # second lot of the same security
        ("SYN-USD-NOTE-005", Decimal(1_000_000)),
    ]
    report = pricing.portfolio_risk(
        holdings,
        curve_id,
        session,
        cash_usd=Decimal(100_000),
        pending_payables_usd=Decimal(20_000),
        scenario_ids=["parallel_up_25", "steepener_v1"],
    )
    singles = [
        pricing.value_position(sid, curve_id, session, FACE)
        for sid in ("SYN-USD-NOTE-005", "SYN-USD-NOTE-009")
    ]
    assert [p.security_id for p in report.positions] == ["SYN-USD-NOTE-005", "SYN-USD-NOTE-009"]
    assert report.total_parallel_dv01_usd == sum(s.parallel_dv01_usd for s in singles)
    assert report.total_economic_value_usd == sum(s.pv_dirty_usd for s in singles)
    assert report.nav_usd == Decimal(80_000) + report.total_economic_value_usd
    weights = sum(c.weight_of_bonds for c in report.concentration)
    assert abs(weights - 1) < Decimal("1e-9")
    assert sum(b.parallel_dv01_usd for b in report.maturity_buckets) == (
        report.total_parallel_dv01_usd
    )
    kr_total = sum(e.dv01_usd for e in report.total_key_rate_dv01)
    assert abs(kr_total - report.total_parallel_dv01_usd) < Decimal("0.01")
    up = next(s for s in report.scenarios if s.scenario_id == "parallel_up_25")
    assert up.security_id is None and up.pnl_usd < 0
    assert report.relative_value.status.value == "mechanically_neutral"
    assert "yield_modified_duration_years" in report.definitions
    assert "effective_duration_years" in report.definitions
    assert all(pricing.calc_store.verify(cid) for cid in report.calculation_ids)
