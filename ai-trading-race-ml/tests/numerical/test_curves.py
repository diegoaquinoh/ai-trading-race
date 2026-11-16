"""Curve calibration, residuals, rejection of invalid inputs, negative rates.

Independent checks re-derive node values with hand formulas:
* short end: D(T) = 1 / (1 + y * days/365) (declared simple ACT/365F convention);
* par bonds: SUM (c/2*100) D(t_i) + 100 D(T) = 100 with hand-listed coupon dates
  and ln D linearly interpolated *in the test* (numpy), not via QuantLib.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal, localcontext

import numpy as np
import pytest

from research_engine.contracts.market import CurveSnapshot, CurveStatus
from research_engine.market import curves
from research_engine.market.curves import (
    DEFAULT_CURVE_SPEC,
    build_curve_snapshot,
    compute_residuals,
)
from research_engine.pricing.curve_model import (
    CurveNotReadyError,
    DiscountCurveModel,
    ExtrapolationError,
)
from tests.numerical.helpers import make_observation

SESSION = date(2023, 1, 3)


def hand_discount(snapshot: CurveSnapshot, day: date) -> float:
    ref = snapshot.reference_date
    times = [(n.node_date - ref).days / 365.0 for n in snapshot.nodes]
    logs = [math.log(float(n.discount_factor)) for n in snapshot.nodes]
    return math.exp(float(np.interp((day - ref).days / 365.0, times, logs)))


@pytest.fixture(scope="module")
def snapshot_20230103(market):
    return market.curve_snapshot_for_session(SESSION)


def test_fixture_curve_ready_with_residuals(snapshot_20230103):
    snap = snapshot_20230103
    assert snap.status is CurveStatus.READY
    assert snap.reference_date == SESSION
    assert len(snap.residuals) == 13  # 1M..30Y in the 2023 file
    tol = DEFAULT_CURVE_SPEC.tolerances
    for residual in snap.residuals:
        assert residual.within_tolerance
        assert abs(residual.rate_residual) <= tol.max_abs_rate_residual
        if residual.price_residual_per_100 is not None:
            assert abs(residual.price_residual_per_100) <= tol.max_abs_price_residual_per_100
    assert snap.validated_horizon_date == snap.nodes[-1].node_date
    assert snap.specification.interpolation == "piecewise_linear_log_discount"
    assert snap.specification.extrapolation == "reject_beyond_validated_horizon"


def test_short_end_zero_coupon_oracle(snapshot_20230103):
    # 1M par yield on 2023-01-03 is 4.17%; maturity 2023-02-03 (31 days).
    node = next(n for n in snapshot_20230103.nodes if n.source_tenor == "1M")
    assert node.node_date == date(2023, 2, 3)
    assert abs(float(node.discount_factor) - 1 / (1 + 0.0417 * 31 / 365)) < 1e-13
    # 1Y: 4.72%, maturity 2024-01-03 (365 days).
    node = next(n for n in snapshot_20230103.nodes if n.source_tenor == "1Y")
    assert abs(float(node.discount_factor) - 1 / (1 + 0.0472 * 365 / 365)) < 1e-13


def test_two_year_par_bond_reprices_to_100(snapshot_20230103):
    # 2Y par yield 4.40%: coupons 2.2 on 2023-07-03, 2024-01-03, 2024-07-03 and
    # 2025-01-03 (all business days) plus principal.
    pay = [date(2023, 7, 3), date(2024, 1, 3), date(2024, 7, 3), date(2025, 1, 3)]
    price = sum(2.2 * hand_discount(snapshot_20230103, d) for d in pay)
    price += 100 * hand_discount(snapshot_20230103, pay[-1])
    assert abs(price - 100.0) < 1e-6


def test_build_is_deterministic_and_content_addressed(market):
    obs = market.observation(SESSION)
    a = build_curve_snapshot(obs, required_horizon=date(2032, 2, 17))
    b = build_curve_snapshot(obs, required_horizon=date(2032, 2, 17))
    assert a.curve_snapshot_id == b.curve_snapshot_id
    assert a.content_hash == b.content_hash
    assert CurveSnapshot.model_validate(a.to_wire()) == a


BASE = {
    "1M": "4.17",
    "3M": "4.53",
    "6M": "4.77",
    "1Y": "4.72",
    "2Y": "4.40",
    "5Y": "3.94",
    "10Y": "3.79",
    "30Y": "3.88",
}


def test_missing_required_tenor_fails():
    yields = {k: v for k, v in BASE.items() if k != "10Y"}
    snap = build_curve_snapshot(make_observation(SESSION, yields, missing=("10Y",)))
    assert snap.status is CurveStatus.FAILED
    assert "required_tenor_missing:10Y" in snap.failure_reasons
    assert snap.nodes == []
    with pytest.raises(CurveNotReadyError):
        DiscountCurveModel.from_snapshot(snap)


def test_no_short_end_fails():
    yields = {k: v for k, v in BASE.items() if k.endswith("Y") and k != "1Y"}
    snap = build_curve_snapshot(make_observation(SESSION, yields))
    assert snap.status is CurveStatus.FAILED
    assert "short_end_missing:no_zero_coupon_tenor" in snap.failure_reasons


def test_out_of_range_input_excluded_and_fails_if_required():
    obs = make_observation(SESSION, BASE)
    flagged = obs.model_copy(update={"quality_flags": ["rate_out_of_range:5Y"]})
    snap = build_curve_snapshot(flagged)
    assert snap.status is CurveStatus.FAILED
    assert "required_tenor_excluded:5Y" in snap.failure_reasons


def test_insufficient_horizon_fails():
    snap = build_curve_snapshot(
        make_observation(SESSION, {k: v for k, v in BASE.items() if k != "30Y"}),
        required_horizon=date(2040, 1, 3),
    )
    assert snap.status is CurveStatus.FAILED
    assert any(r.startswith("insufficient_horizon") for r in snap.failure_reasons)


def _spec_with(**tolerances):
    return DEFAULT_CURVE_SPEC.model_copy(
        update={"tolerances": DEFAULT_CURVE_SPEC.tolerances.model_copy(update=tolerances)}
    )


def test_solver_failure_is_not_ready():
    spec = _spec_with(bootstrap_accuracy=Decimal("0.05"), max_iterations=1)
    snap = build_curve_snapshot(make_observation(SESSION, BASE), spec)
    assert snap.status is CurveStatus.FAILED
    assert snap.failure_reasons[0].startswith("calibration_failed:")


def test_loose_bootstrap_is_rejected_by_the_exact_root_cross_check():
    # A loose QuantLib bootstrap converges, but the exact decimal root disagrees with it.
    snap = build_curve_snapshot(
        make_observation(SESSION, BASE), _spec_with(bootstrap_accuracy=Decimal("0.01"))
    )
    assert snap.status is CurveStatus.FAILED
    assert any(
        r.startswith("calibration_failed:exact_root_mismatch:") for r in snap.failure_reasons
    )


def test_residuals_out_of_tolerance_are_detected_from_published_nodes(market, snapshot_20230103):
    # The residual check re-prices inputs from the published nodes only.
    snap = snapshot_20230103
    nodes = list(snap.nodes)
    index = next(i for i, n in enumerate(nodes) if n.source_tenor == "5Y")
    nodes[index] = nodes[index].model_copy(
        update={"discount_factor": nodes[index].discount_factor + Decimal("0.0001")}
    )
    by_tenor = {i.tenor: i for i in snap.specification.instruments}
    used = [
        (by_tenor[p.tenor], p)
        for p in market.observation(SESSION).points
        if p.tenor in snap.used_tenors
    ]
    residuals = compute_residuals(snap.reference_date, nodes, used, DEFAULT_CURVE_SPEC)
    failing = {r.tenor for r in residuals if not r.within_tolerance}
    assert "5Y" in failing
    assert "1M" not in failing


def test_published_nodes_do_not_depend_on_solver_noise(market, monkeypatch):
    # QuantLib's iterative bootstrap stops at a platform-dependent point (Apple arm64 and Linux
    # x86-64 differed in the 14th digit). Published nodes are exact decimal roots, so any
    # perturbation within the solver accuracy leaves the snapshot byte-identical.
    obs = market.observation(SESSION)
    baseline = build_curve_snapshot(obs)
    original = curves._bootstrap

    def noisy(reference, used, spec, sign):
        return [
            (d, df if d == reference else df * (1 + sign * 3e-13))
            for d, df in original(reference, used, spec)
        ]

    for sign in (1, -1):
        monkeypatch.setattr(curves, "_bootstrap", lambda r, u, s, k=sign: noisy(r, u, s, k))
        assert build_curve_snapshot(obs).content_hash == baseline.content_hash


def test_short_end_nodes_are_exact_decimal_roots(snapshot_20230103):
    node = next(n for n in snapshot_20230103.nodes if n.source_tenor == "1M")
    with localcontext(prec=50):
        exact = 1 / (1 + Decimal("0.0417") * Decimal(31) / Decimal(365))
    assert node.discount_factor == exact.quantize(Decimal("1e-14"))
    residual = next(r for r in snapshot_20230103.residuals if r.tenor == "1M")
    assert residual.rate_residual == 0


def test_negative_rate_environment_builds_without_monotone_constraint():
    yields = {
        "1M": "-0.75",
        "3M": "-0.70",
        "6M": "-0.62",
        "1Y": "-0.50",
        "2Y": "-0.30",
        "5Y": "0.05",
        "10Y": "0.45",
        "30Y": "0.90",
    }
    snap = build_curve_snapshot(make_observation(date(2020, 3, 16), yields))
    assert snap.status is CurveStatus.READY, snap.failure_reasons
    dfs = [float(n.discount_factor) for n in snap.nodes]
    assert all(df > 0 for df in dfs)
    assert max(dfs) > 1.0  # negative zero rates
    assert any(b > a for a, b in zip(dfs[:-1], dfs[1:]))  # not monotone decreasing
    one_month = next(n for n in snap.nodes if n.source_tenor == "1M")
    days = (one_month.node_date - date(2020, 3, 16)).days
    assert abs(float(one_month.discount_factor) - 1 / (1 - 0.0075 * days / 365)) < 1e-13
    assert all(r.within_tolerance for r in snap.residuals)


def test_curve_model_rejects_extrapolation(snapshot_20230103):
    model = DiscountCurveModel.from_snapshot(snapshot_20230103)
    assert model.discount(SESSION) == pytest.approx(1.0, abs=1e-15)
    with pytest.raises(ExtrapolationError):
        model.discount(snapshot_20230103.validated_horizon_date.replace(year=2060))
    with pytest.raises(ExtrapolationError):
        model.discount(date(2023, 1, 2))


def test_all_fixture_sessions_calibrate(market):
    snaps = market.build_all()
    assert len(snaps) == 500
    assert all(s.status is CurveStatus.READY for s in snaps.values())
    assert max(s.max_abs_price_residual_per_100 for s in snaps.values()) <= Decimal("0.000001")
