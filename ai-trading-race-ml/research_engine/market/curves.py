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
* Residuals for every input are re-computed from the *published* (quantized)
  nodes, independently of the QuantLib helpers, and must pass tolerances.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
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
from research_engine.pricing.curve_model import DiscountCurveModel, year_fraction
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


def _to_dec(value: float, places: Decimal) -> Decimal:
    return Decimal(repr(value)).quantize(places)


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

    nodes: list[CurveNode] = []
    tenor_by_date = {zero_or_par_maturity(reference, d): d.tenor for d, _ in used}
    for node_date, df in nodes_raw:
        if not (df > 0.0 and math.isfinite(df)):
            return failed([f"non_positive_discount_factor:{node_date.isoformat()}"])
        t = year_fraction(reference, node_date)
        zero = 0.0 if t == 0 else -math.log(df) / t
        nodes.append(
            CurveNode(
                node_date=node_date,
                time_years=Decimal(node_date.toordinal() - reference.toordinal()) / Decimal(365),
                discount_factor=_to_dec(df, DF_PLACES),
                zero_rate=_to_dec(zero, RATE_PLACES),
                source_tenor=tenor_by_date.get(node_date),
            )
        )
    nodes = [n.model_copy(update={"time_years": n.time_years.quantize(TIME_PLACES)}) for n in nodes]

    model = DiscountCurveModel(
        reference,
        [n.node_date for n in nodes],
        [float(n.discount_factor) for n in nodes],
        curve_snapshot_id=snapshot_id,
    )
    residuals = compute_residuals(model, used, spec)
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
    model: DiscountCurveModel,
    used: list[tuple[CurveInstrumentDefinition, ParYieldPoint]],
    spec: CurveSpecification,
) -> list[CalibrationResidual]:
    """Re-price each input from the published nodes (independent of QL helpers)."""
    reference = model.reference_date
    price_tol = spec.tolerances.max_abs_price_residual_per_100
    rate_tol = spec.tolerances.max_abs_rate_residual
    out: list[CalibrationResidual] = []
    for definition, point in used:
        quote = float(point.par_yield)
        if definition.kind is CalibrationInstrumentKind.ZERO_COUPON:
            maturity = zero_tenor_maturity(
                reference, definition.period_count, definition.period_unit
            )
            tau = (maturity - reference).days / 365.0
            implied = (1.0 / model.discount(maturity) - 1.0) / tau
            rate_res = implied - quote
            out.append(
                CalibrationResidual(
                    tenor=definition.tenor,
                    kind=definition.kind,
                    input_quote=point.par_yield,
                    model_quote=_to_dec(implied, RATE_PLACES),
                    rate_residual=_to_dec(rate_res, RATE_PLACES),
                    within_tolerance=abs(Decimal(repr(rate_res))) <= rate_tol,
                )
            )
        else:
            flows = par_bond_flows(reference, definition.period_count, quote)
            dfs = model.discounts([d for d, _ in flows])
            price = sum(a * df for (_, a), df in zip(flows, dfs))
            annuity = sum(50.0 * df for df in dfs)  # PV of 0.5 * 100 per period
            implied = (100.0 - 100.0 * dfs[-1]) / annuity
            price_res = price - 100.0
            rate_res = implied - quote
            out.append(
                CalibrationResidual(
                    tenor=definition.tenor,
                    kind=definition.kind,
                    input_quote=point.par_yield,
                    model_quote=_to_dec(implied, RATE_PLACES),
                    rate_residual=_to_dec(rate_res, RATE_PLACES),
                    price_residual_per_100=_to_dec(price_res, PRICE_PLACES),
                    within_tolerance=abs(Decimal(repr(price_res))) <= price_tol
                    and abs(Decimal(repr(rate_res))) <= rate_tol,
                )
            )
    return out
