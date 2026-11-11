"""CurveSnapshot builder: bootstrap discount factors from Treasury par yields.

Specification ``usd-tsy-par-bootstrap-v1`` (see docs/fixed-income/numerical-methods.md):

* Reference date (valuation anchor v) = session date, D(v, v) = 1. The 1-day
  difference to Treasury's settlement convention is a declared simplification.
* Short end: tenors <= 12 months are **zero-coupon** instruments. Their par
  yield is read as a *simple* rate on ACT/365F from v to the tenor maturity
  (v + tenor, adjusted Following): ``D(T) = 1 / (1 + y * days/365)``.
* Tenors >= 2 years are **semiannual par bonds** (coupon = par yield,
  ACT/ACT-ICMA, unadjusted accrual, payments Following) priced at 100 at v.
* Interpolation: piecewise linear in ln D over ACT/365F time (QuantLib
  ``PiecewiseLogLinearDiscount``); no monotone-discount constraint, so negative
  rates are permitted.
* Extrapolation beyond the last node is rejected.
* Published nodes are platform-independent: QuantLib's bootstrap is the
  solver, then every node is refined to its exact root in 50-digit decimal
  arithmetic (closed form for the zero-coupon short end, Newton in ln D for par
  bonds against the exact earlier nodes) and rounded half-even to 14 dp. The
  QuantLib float alone is not stable to 14 dp: the iterative solver stops at a
  platform-dependent point (Apple arm64 and Linux x86-64 differed in the last
  digit on 5 of 103 sessions). Zero rates come from the same exact roots.
* Residuals for every input are re-computed from the *published* (quantized)
  nodes in the same decimal arithmetic, independently of the QuantLib helpers,
  and must pass tolerances.
"""

from __future__ import annotations

import bisect
import math
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any, Optional

import QuantLib as ql

from research_engine.contracts.common import DataMode, content_hash, short_id
from research_engine.contracts.market import (
    CalibrationInstrumentKind,
    CalibrationResidual,
    CurveInstrumentDefinition,
    CurveNode,
    CurveObservation,
    CurveSnapshot,
    CurveSpecification,
    CurveStatus,
    ParYieldPoint,
    ShortEndTreatment,
    SolverTolerances,
    TenorUnit,
)
from research_engine.instruments.calendar import (
    CALENDAR_ID,
    CALENDAR_VERSION,
    us_government_bond_calendar,
)
from research_engine.pricing.quantlib_env import (
    ENGINE_VERSION,
    evaluation_date,
    from_ql_date,
    to_ql_date,
)

from .treasury import SOURCE_ID as TREASURY_SOURCE_ID

CURVE_ID = "USD-TSY-PAR-BOOTSTRAP"
DF_PLACES = Decimal("1e-14")
RATE_PLACES = Decimal("1e-12")
TIME_PLACES = Decimal("1e-12")
PRICE_PLACES = Decimal("1e-10")
# Cash-flow amounts per 100: par coupons are 100 * y / 2 with y in whole basis points, so the
# QuantLib float amount rounds to its exact decimal value well inside this quantum.
FLOW_PLACES = Decimal("1e-10")
EXACT_PRECISION = 50  # significant digits for the decimal node solve and residuals
_NEWTON_STEP = Decimal("1e-40")
_NEWTON_MAX_ITERATIONS = 100
# The exact root must agree with QuantLib's bootstrap: a larger gap means the two disagree on
# conventions, not on rounding.
ROOT_CROSS_CHECK = Decimal("1e-10")

_ZERO_TENORS = [
    ("4W", 4, TenorUnit.WEEKS),
    ("6W", 6, TenorUnit.WEEKS),
    ("8W", 8, TenorUnit.WEEKS),
    ("1M", 1, TenorUnit.MONTHS),
    ("2M", 2, TenorUnit.MONTHS),
    ("3M", 3, TenorUnit.MONTHS),
    ("4M", 4, TenorUnit.MONTHS),
    ("6M", 6, TenorUnit.MONTHS),
    ("1Y", 1, TenorUnit.YEARS),
]
_PAR_TENORS = [
    ("2Y", 2),
    ("3Y", 3),
    ("5Y", 5),
    ("7Y", 7),
    ("10Y", 10),
    ("20Y", 20),
    ("30Y", 30),
]


def _default_spec() -> CurveSpecification:
    instruments = [
        CurveInstrumentDefinition(
            tenor=label,
            period_count=count,
            period_unit=unit,
            kind=CalibrationInstrumentKind.ZERO_COUPON,
            quote_convention="simple_act365f",
            day_count="ACT/365F",
        )
        for label, count, unit in _ZERO_TENORS
    ] + [
        CurveInstrumentDefinition(
            tenor=label,
            period_count=years,
            period_unit=TenorUnit.YEARS,
            kind=CalibrationInstrumentKind.PAR_BOND,
            quote_convention="semiannual_par_coupon_act_act_icma",
            day_count="ACT/ACT-ICMA",
            coupon_frequency=2,
        )
        for label, years in _PAR_TENORS
    ]
    return CurveSpecification(
        spec_id="usd-tsy-par-bootstrap",
        version="usd-tsy-par-bootstrap-v1",
        input_source_id=TREASURY_SOURCE_ID,
        calendar_id=CALENDAR_ID,
        calendar_version=CALENDAR_VERSION,
        short_end_treatment=ShortEndTreatment(
            max_zero_coupon_tenor_months=12,
            quote_convention="simple_act365f",
            description=(
                "Tenors up to 12 months are zero-coupon instruments from the reference date to "
                "reference date + tenor (Following, US-GovernmentBond); the published "
                "bond-equivalent par yield is read as a simple ACT/365F rate: "
                "D(T) = 1/(1 + y*days/365). The curve is anchored at D(v,v)=1; between v and "
                "the first node ln D is linear in time (flat continuous forward)."
            ),
        ),
        instruments=instruments,
        required_tenors=["2Y", "5Y", "10Y"],
        min_nodes=4,
        tolerances=SolverTolerances(
            bootstrap_accuracy=Decimal("1e-12"),
            max_iterations=100,
            max_abs_price_residual_per_100=Decimal("0.000001"),
            max_abs_rate_residual=Decimal("0.0000001"),
        ),
        engine="QuantLib PiecewiseLogLinearDiscount + IterativeBootstrap",
    )


DEFAULT_CURVE_SPEC = _default_spec()


def _ql_period(count: int, unit: TenorUnit) -> ql.Period:
    return ql.Period(
        count,
        {TenorUnit.WEEKS: ql.Weeks, TenorUnit.MONTHS: ql.Months, TenorUnit.YEARS: ql.Years}[unit],
    )


def zero_tenor_maturity(reference: date, count: int, unit: TenorUnit) -> date:
    cal = us_government_bond_calendar()
    return from_ql_date(cal.advance(to_ql_date(reference), _ql_period(count, unit), ql.Following))


def _is_month_end(day: date) -> bool:
    return (day + timedelta(days=1)).month != day.month


def par_bond_schedule(reference: date, years: int) -> ql.Schedule:
    """Semiannual schedule backward from reference + N years.

    The end-of-month rule applies when the reference date is a calendar month
    end, so e.g. a 29 February reference keeps regular month-end coupon dates
    instead of acquiring a short first stub.
    """
    ref = to_ql_date(reference)
    return ql.Schedule(
        ref,
        ref + ql.Period(years, ql.Years),
        ql.Period(ql.Semiannual),
        us_government_bond_calendar(),
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        _is_month_end(reference),
    )


def par_bond_flows(reference: date, years: int, coupon: float) -> list[tuple[date, float]]:
    """(payment date, amount per 100) of the par calibration bond.

    Amounts come from the same QuantLib schedule/day counter the helper uses;
    the residual check then discounts them with the published nodes only.
    """
    schedule = par_bond_schedule(reference, years)
    bond = ql.FixedRateBond(
        0,
        100.0,
        schedule,
        [coupon],
        ql.ActualActual(ql.ActualActual.ISMA, schedule),
        ql.Following,
        100.0,
        to_ql_date(reference),
    )
    flows: dict[date, float] = {}
    for cf in bond.cashflows():
        pay = from_ql_date(cf.date())
        flows[pay] = flows.get(pay, 0.0) + float(cf.amount())
    return sorted(flows.items())


class CurveBuildError(RuntimeError):
    pass


def exact_context():
    """Decimal context for node solving and residuals; same digits on every platform."""
    return localcontext(prec=EXACT_PRECISION, rounding=ROUND_HALF_EVEN)


def exact_par_bond_flows(
    reference: date, years: int, coupon: Decimal
) -> list[tuple[date, Decimal]]:
    """``par_bond_flows`` with amounts as exact decimals (dates still from QuantLib)."""
    return [
        (pay, Decimal(repr(amount)).quantize(FLOW_PLACES))
        for pay, amount in par_bond_flows(reference, years, float(coupon))
    ]


class ExactDiscountCurve:
    """Log-linear ln D in ACT/365F time over decimal nodes, evaluated in decimal arithmetic.

    Same interpolation as ``PiecewiseLogLinearDiscount`` / ``DiscountCurveModel``; the weight
    between two nodes is a ratio of day counts, so only ``ln`` and ``exp`` round, and decimal
    ``ln``/``exp`` are correctly rounded. Call inside :func:`exact_context`.
    """

    def __init__(self, reference: date, node_dates: list[date], discount_factors: list[Decimal]):
        if not node_dates or node_dates[0] != reference:
            raise CurveBuildError("exact curve nodes must start at the reference date")
        self._days = [(d - reference).days for d in node_dates]
        self._reference = reference
        self._dfs = list(discount_factors)
        self._lns = [df.ln() for df in self._dfs]

    def discount(self, day: date) -> Decimal:
        offset = (day - self._reference).days
        if offset < 0 or offset > self._days[-1]:
            raise CurveBuildError(f"exact curve extrapolation to {day.isoformat()}")
        index = bisect.bisect_left(self._days, offset)
        if self._days[index] == offset:
            return self._dfs[index]
        lo, hi = index - 1, index
        weight = Decimal(offset - self._days[lo]) / Decimal(self._days[hi] - self._days[lo])
        return (self._lns[lo] + weight * (self._lns[hi] - self._lns[lo])).exp()


def _solve_par_node(
    reference: date,
    node_dates: list[date],
    exact: list[Decimal],
    definition: CurveInstrumentDefinition,
    point: ParYieldPoint,
    start: Decimal,
) -> Decimal:
    """Discount factor at ``node_dates[-1]`` that prices the par bond at exactly 100.

    Flows up to the previous node use the exact earlier nodes; later flows interpolate
    log-linearly towards the unknown node. Newton in ``y = ln D`` (price is increasing and
    convex in y), started from QuantLib's root.
    """
    previous, node = node_dates[-2], node_dates[-1]
    known_curve = ExactDiscountCurve(reference, node_dates[:-1], exact)
    ln_previous = exact[-1].ln()
    span = Decimal((node - previous).days)
    known = Decimal(0)
    dependent: list[tuple[Decimal, Decimal]] = []
    for pay, amount in exact_par_bond_flows(reference, definition.period_count, point.par_yield):
        if pay <= previous:
            known += amount * known_curve.discount(pay)
        elif pay <= node:
            dependent.append((amount, Decimal((pay - previous).days) / span))
        else:
            raise CurveBuildError(f"par_flow_beyond_node:{definition.tenor}")
    y = start.ln()
    for _ in range(_NEWTON_MAX_ITERATIONS):
        values = [(a, w, (ln_previous + w * (y - ln_previous)).exp()) for a, w in dependent]
        price = known + sum(a * v for a, _, v in values)
        slope = sum(a * w * v for a, w, v in values)
        step = (price - 100) / slope
        y -= step
        if abs(step) < _NEWTON_STEP:
            return y.exp()
    raise CurveBuildError(f"exact_root_no_convergence:{definition.tenor}")


def exact_discount_factors(
    reference: date,
    used: list[tuple[CurveInstrumentDefinition, ParYieldPoint]],
    nodes_raw: list[tuple[date, float]],
) -> list[Decimal]:
    """Exact (unrounded) discount factors at QuantLib's node dates, reference node first."""
    by_date = {zero_or_par_maturity(reference, d): (d, p) for d, p in used}
    node_dates = [d for d, _ in nodes_raw]
    if node_dates[0] != reference or sorted(by_date) != node_dates[1:]:
        raise CurveBuildError("bootstrap nodes do not match the calibration instruments")
    exact = [Decimal(1)]
    with exact_context():
        for index in range(1, len(node_dates)):
            node = node_dates[index]
            definition, point = by_date[node]
            start = Decimal(repr(nodes_raw[index][1]))
            if definition.kind is CalibrationInstrumentKind.ZERO_COUPON:
                tau = Decimal((node - reference).days) / Decimal(365)
                root = 1 / (1 + point.par_yield * tau)
            else:
                root = _solve_par_node(
                    reference, node_dates[: index + 1], exact, definition, point, start
                )
            if abs(root - start) > ROOT_CROSS_CHECK:
                raise CurveBuildError(f"exact_root_mismatch:{definition.tenor}")
            exact.append(root)
    return exact


def _select_points(
    observation: CurveObservation, spec: CurveSpecification
) -> tuple[list[tuple[CurveInstrumentDefinition, ParYieldPoint]], list[str], list[str]]:
    by_tenor = {i.tenor: i for i in spec.instruments}
    flagged = {
        f.split(":", 1)[1] for f in observation.quality_flags if f.startswith("rate_out_of_range:")
    }
    used: list[tuple[CurveInstrumentDefinition, ParYieldPoint]] = []
    excluded: list[str] = []
    reasons: list[str] = []
    for point in observation.points:
        definition = by_tenor.get(point.tenor)
        if definition is None:
            excluded.append(point.tenor)
            reasons.append(f"unsupported_tenor:{point.tenor}")
            continue
        if point.tenor in flagged:
            excluded.append(point.tenor)
            reasons.append(f"rate_out_of_range:{point.tenor}")
            continue
        used.append((definition, point))
    return used, excluded, reasons


def build_curve_snapshot(
    observation: CurveObservation,
    spec: CurveSpecification = DEFAULT_CURVE_SPEC,
    *,
    required_horizon: Optional[date] = None,
    data_mode: DataMode = DataMode.SYNTHETIC_CURVE,
) -> CurveSnapshot:
    """Build a READY or FAILED snapshot; never raises for bad market inputs."""
    reference = observation.session_date
    obs_hash = content_hash(observation)
    snapshot_id = short_id(
        "curve",
        {
            "observation": obs_hash,
            "spec": content_hash(spec),
            "engine": ENGINE_VERSION,
            "requiredHorizon": required_horizon.isoformat() if required_horizon else None,
            "dataMode": data_mode.value,
        },
    )
    base: dict[str, Any] = dict(
        curve_snapshot_id=snapshot_id,
        curve_id=CURVE_ID,
        version=spec.version,
        data_mode=data_mode,
        session_date=reference,
        reference_date=reference,
        valuation_at=observation.observed_at,
        available_at=observation.available_at,
        input_observation_ids=[observation.observation_id],
        input_observation_hashes=[obs_hash],
        specification=spec,
        engine_version=ENGINE_VERSION,
    )

    def failed(reasons: list[str], **extra) -> CurveSnapshot:
        snap = CurveSnapshot(status=CurveStatus.FAILED, failure_reasons=reasons, **base, **extra)
        return snap.model_copy(update={"content_hash": content_hash(snap.hash_payload())})

    used, excluded, exclusion_reasons = _select_points(observation, spec)
    used.sort(key=lambda item: zero_or_par_maturity(reference, item[0]))
    used_tenors = [d.tenor for d, _ in used]
    reasons: list[str] = []
    for tenor in spec.required_tenors:
        if tenor not in used_tenors:
            why = "missing" if tenor in observation.missing_tenors else "absent"
            reasons.append(f"required_tenor_{why}:{tenor}")
    if not any(d.kind is CalibrationInstrumentKind.ZERO_COUPON for d, _ in used):
        reasons.append("short_end_missing:no_zero_coupon_tenor")
    if len(used) < spec.min_nodes:
        reasons.append(f"too_few_nodes:{len(used)}<{spec.min_nodes}")
    for tenor in excluded:
        if tenor in spec.required_tenors:
            reasons.append(f"required_tenor_excluded:{tenor}")
    if reasons:
        return failed(
            reasons + exclusion_reasons,
            used_tenors=used_tenors,
            excluded_tenors=excluded,
        )

    try:
        nodes_raw = _bootstrap(reference, used, spec)
    except RuntimeError as exc:  # QuantLib raises RuntimeError on bootstrap failure
        message = str(exc).splitlines()[0][:200]
        return failed([f"calibration_failed:{message}"], used_tenors=used_tenors)

    for node_date, df in nodes_raw:
        if not (df > 0.0 and math.isfinite(df)):
            return failed([f"non_positive_discount_factor:{node_date.isoformat()}"])
    try:
        exact = exact_discount_factors(reference, used, nodes_raw)
    except CurveBuildError as exc:
        return failed([f"calibration_failed:{exc}"], used_tenors=used_tenors)

    nodes: list[CurveNode] = []
    tenor_by_date = {zero_or_par_maturity(reference, d): d.tenor for d, _ in used}
    with exact_context():
        for (node_date, _), root in zip(nodes_raw, exact):
            days = (node_date - reference).days
            zero = Decimal(0) if days == 0 else -root.ln() * 365 / days
            nodes.append(
                CurveNode(
                    node_date=node_date,
                    time_years=(Decimal(days) / Decimal(365)).quantize(TIME_PLACES),
                    discount_factor=root.quantize(DF_PLACES),
                    zero_rate=zero.quantize(RATE_PLACES),
                    source_tenor=tenor_by_date.get(node_date),
                )
            )

    residuals = compute_residuals(reference, nodes, used, spec)
    max_price = max(
        (abs(r.price_residual_per_100) for r in residuals if r.price_residual_per_100 is not None),
        default=Decimal(0),
    )
    max_rate = max((abs(r.rate_residual) for r in residuals), default=Decimal(0))
    horizon = nodes[-1].node_date
    reasons = [f"residual_out_of_tolerance:{r.tenor}" for r in residuals if not r.within_tolerance]
    if required_horizon is not None and required_horizon > horizon:
        reasons.append(
            f"insufficient_horizon:required {required_horizon.isoformat()} > "
            f"validated {horizon.isoformat()}"
        )
    extra: dict[str, Any] = dict(
        used_tenors=used_tenors,
        excluded_tenors=excluded,
        residuals=residuals,
        max_abs_price_residual_per_100=max_price,
        max_abs_rate_residual=max_rate,
        nodes=nodes,
        validated_horizon_date=horizon,
    )
    if reasons:
        return failed(reasons, **extra)
    snap = CurveSnapshot(status=CurveStatus.READY, **base, **extra)
    return snap.model_copy(update={"content_hash": content_hash(snap.hash_payload())})


def zero_or_par_maturity(reference: date, definition: CurveInstrumentDefinition) -> date:
    if definition.kind is CalibrationInstrumentKind.ZERO_COUPON:
        return zero_tenor_maturity(reference, definition.period_count, definition.period_unit)
    flows = par_bond_flows(reference, definition.period_count, 0.0)
    return flows[-1][0]


def _bootstrap(
    reference: date,
    used: list[tuple[CurveInstrumentDefinition, ParYieldPoint]],
    spec: CurveSpecification,
) -> list[tuple[date, float]]:
    cal = us_government_bond_calendar()
    with evaluation_date(reference) as ql_ref:
        helpers = []
        for definition, point in used:
            rate = float(point.par_yield)
            if definition.kind is CalibrationInstrumentKind.ZERO_COUPON:
                helpers.append(
                    ql.DepositRateHelper(
                        ql.QuoteHandle(ql.SimpleQuote(rate)),
                        _ql_period(definition.period_count, definition.period_unit),
                        0,
                        cal,
                        ql.Following,
                        False,
                        ql.Actual365Fixed(),
                    )
                )
            else:
                schedule = par_bond_schedule(reference, definition.period_count)
                helpers.append(
                    ql.FixedRateBondHelper(
                        ql.QuoteHandle(ql.SimpleQuote(100.0)),
                        0,
                        100.0,
                        schedule,
                        [rate],
                        ql.ActualActual(ql.ActualActual.ISMA, schedule),
                        ql.Following,
                        100.0,
                        ql_ref,
                    )
                )
        bootstrap = ql.IterativeBootstrap(
            float(spec.tolerances.bootstrap_accuracy),
            maxEvaluations=spec.tolerances.max_iterations,
        )
        curve = ql.PiecewiseLogLinearDiscount(ql_ref, helpers, ql.Actual365Fixed(), bootstrap)
        return [(from_ql_date(d), float(df)) for d, df in curve.nodes()]


def compute_residuals(
    reference: date,
    nodes: list[CurveNode],
    used: list[tuple[CurveInstrumentDefinition, ParYieldPoint]],
    spec: CurveSpecification,
) -> list[CalibrationResidual]:
    """Re-price each input from the published nodes (independent of QL helpers).

    Decimal arithmetic throughout, so the quantized residuals are identical on every platform.
    """
    price_tol = spec.tolerances.max_abs_price_residual_per_100
    rate_tol = spec.tolerances.max_abs_rate_residual
    out: list[CalibrationResidual] = []
    with exact_context():
        curve = ExactDiscountCurve(
            reference, [n.node_date for n in nodes], [n.discount_factor for n in nodes]
        )
        for definition, point in used:
            quote = point.par_yield
            if definition.kind is CalibrationInstrumentKind.ZERO_COUPON:
                maturity = zero_tenor_maturity(
                    reference, definition.period_count, definition.period_unit
                )
                tau = Decimal((maturity - reference).days) / Decimal(365)
                implied = (1 / curve.discount(maturity) - 1) / tau
                rate_res = implied - quote
                out.append(
                    CalibrationResidual(
                        tenor=definition.tenor,
                        kind=definition.kind,
                        input_quote=point.par_yield,
                        model_quote=implied.quantize(RATE_PLACES),
                        rate_residual=rate_res.quantize(RATE_PLACES),
                        within_tolerance=abs(rate_res) <= rate_tol,
                    )
                )
            else:
                flows = exact_par_bond_flows(reference, definition.period_count, quote)
                dfs = [curve.discount(d) for d, _ in flows]
                price = sum(a * df for (_, a), df in zip(flows, dfs))
                annuity = sum(50 * df for df in dfs)  # PV of 0.5 * 100 per period
                implied = (100 - 100 * dfs[-1]) / annuity
                price_res = price - 100
                rate_res = implied - quote
                out.append(
                    CalibrationResidual(
                        tenor=definition.tenor,
                        kind=definition.kind,
                        input_quote=point.par_yield,
                        model_quote=implied.quantize(RATE_PLACES),
                        rate_residual=rate_res.quantize(RATE_PLACES),
                        price_residual_per_100=price_res.quantize(PRICE_PLACES),
                        within_tolerance=abs(price_res) <= price_tol and abs(rate_res) <= rate_tol,
                    )
                )
    return out
