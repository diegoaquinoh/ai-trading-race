"""Versioned hypothetical scenario library ``scenario_library_v1`` (spec 8.6).

Each scenario shifts the continuous ACT/365F zero rate at every curve node:

=================  =====================================================
parallel_up_25     +25 bp at all supported nodes
parallel_down_25   -25 bp at all supported nodes
parallel_up_100    +100 bp at all supported nodes
parallel_down_100  -100 bp at all supported nodes
steepener_v1       -25 bp at 2y, 0 at 5y, +25 bp at 10y, linear between
flattener_v1       +25 bp at 2y, 0 at 5y, -25 bp at 10y (reverse)
=================  =====================================================

Outside the scenario nodes the nearest node's shift is extended flat (before
2y: the 2y shift; after 10y: the 10y shift). Scenarios are instantaneous at the
valuation date, holdings fixed, valued as valuation-date PV (no settlement lag).
Full repricing is authoritative; first-order (DV01 / key-rate DV01) and
second-order (duration + convexity, parallel only) approximations are reported
with their error against full repricing. These shocks are hypothetical, not
calibrated forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from research_engine.contracts.calculations import ScenarioDefinition, ScenarioNodeShift
from research_engine.instruments.schedule import InstrumentModel
from research_engine.pricing.curve_model import DiscountCurveModel, ShiftFunction

from .measures import CurveSensitivity, pv_per_100
from .shocks import BP, parallel_shift, piecewise_linear_shift

SCENARIO_LIBRARY_VERSION = "scenario_library_v1"


def _parallel(scenario_id: str, bp: int, purpose: str) -> ScenarioDefinition:
    return ScenarioDefinition(
        scenario_id=scenario_id,
        library_version=SCENARIO_LIBRARY_VERSION,
        description=f"All supported zero-rate nodes {bp:+d} bp. {purpose}",
        kind="parallel",
        parallel_shift_bp=Decimal(bp),
    )


def _shape(scenario_id: str, shifts: tuple[int, int, int], purpose: str) -> ScenarioDefinition:
    nodes = [
        ScenarioNodeShift(tenor_years=Decimal(t), shift_bp=Decimal(s))
        for t, s in zip((2, 5, 10), shifts)
    ]
    return ScenarioDefinition(
        scenario_id=scenario_id,
        library_version=SCENARIO_LIBRARY_VERSION,
        description=(
            f"{shifts[0]:+d} bp at 2y, {shifts[1]:+d} bp at 5y, {shifts[2]:+d} bp at 10y, "
            f"linear in time between nodes, flat outside. {purpose}"
        ),
        kind="piecewise_linear_tenor",
        node_shifts=nodes,
    )


SCENARIO_LIBRARY_V1: dict[str, ScenarioDefinition] = {
    s.scenario_id: s
    for s in (
        _parallel("parallel_up_25", 25, "Moderate upward rate shock."),
        _parallel("parallel_down_25", -25, "Moderate downward rate shock."),
        _parallel("parallel_up_100", 100, "Larger stress."),
        _parallel("parallel_down_100", -100, "Larger reverse stress."),
        _shape("steepener_v1", (-25, 0, 25), "Curve-shape exposure."),
        _shape("flattener_v1", (25, 0, -25), "Opposite curve-shape exposure."),
    )
}


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    try:
        return SCENARIO_LIBRARY_V1[scenario_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown scenario {scenario_id!r}; allowed: {sorted(SCENARIO_LIBRARY_V1)}"
        ) from exc


def shift_function(definition: ScenarioDefinition) -> ShiftFunction:
    if definition.kind == "parallel":
        assert definition.parallel_shift_bp is not None
        return parallel_shift(float(definition.parallel_shift_bp) * BP)
    return piecewise_linear_shift(
        [float(n.tenor_years) for n in definition.node_shifts],
        [float(n.shift_bp) * BP for n in definition.node_shifts],
    )


@dataclass(frozen=True)
class ScenarioOutcome:
    """Per 100 face at the valuation anchor."""

    scenario_id: str
    base_pv: float
    scenario_pv: float
    pnl: float
    first_order_pnl: float
    second_order_pnl: float | None
    method: str


def evaluate_scenario(
    model: InstrumentModel,
    curve: DiscountCurveModel,
    valuation_date: date,
    definition: ScenarioDefinition,
    sensitivity: CurveSensitivity,
) -> ScenarioOutcome:
    shocked = curve.shifted(shift_function(definition), description=definition.scenario_id)
    base = sensitivity.pv
    scen = pv_per_100(model, shocked, valuation_date)
    first, second, method = approximate_pnl(definition, sensitivity)
    return ScenarioOutcome(definition.scenario_id, base, scen, scen - base, first, second, method)


def approximate_pnl(
    definition: ScenarioDefinition, sensitivity: CurveSensitivity
) -> tuple[float, float | None, str]:
    """(first-order, second-order or None, method label) per 100 face."""
    if definition.kind == "parallel":
        assert definition.parallel_shift_bp is not None
        shift_bp = float(definition.parallel_shift_bp)
        first = -sensitivity.parallel_dv01 * shift_bp
        dy = shift_bp * BP
        second = sensitivity.pv * (
            -sensitivity.effective_duration * dy + 0.5 * sensitivity.effective_convexity * dy * dy
        )
        return first, second, "parallel_dv01 (first order); effective duration+convexity"
    shape = shift_function(definition)
    first = -sum(
        dv01 * shape(key) / BP
        for key, dv01 in zip(sensitivity.key_tenors, sensitivity.key_rate_dv01)
    )
    return first, None, "key_rate_dv01 weighted by scenario shift at key tenors (first order)"
