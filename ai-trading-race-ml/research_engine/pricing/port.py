"""``QuantLibPricingPort``: the numerical core's implementation of ``PricingPort``.

Every price/valuation/risk/scenario output is registered as a signed
``CalculationResult`` in the shared ``CalculationStore``; the returned
``calculation_id`` can later be resolved and verified by other components.

Anchors: ``price`` is settlement-anchored (per 100, D(v,t)/D(v,s));
``value_position`` is valuation-date PV (face-scaled, D(v,t)/D(v,u)).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from research_engine.contracts.calculations import (
    SYNTHETIC_RELATIVE_VALUE,
    Anchor,
    CalculatedValue,
    CalculationResult,
    CalculationType,
    Completeness,
    ConcentrationEntry,
    EngineProvenance,
    KeyRateExposure,
    MaturityBucket,
    PositionRisk,
    RelativeValueEstimate,
    RelativeValueStatus,
    RiskReport,
    ScenarioResult,
    ValueBasis,
)
from research_engine.contracts.common import DataMode, Unit, content_hash, short_id
from research_engine.contracts.instruments import InstrumentUniverse, SecurityTerms
from research_engine.contracts.market import CurveSnapshot
from research_engine.instruments import calendar as cal
from research_engine.instruments.schedule import InstrumentModel
from research_engine.instruments.universe import instrument_info
from research_engine.risk.measures import (
    CurveSensitivity,
    ShockedCurves,
    curve_sensitivity,
    maturity_bucket,
)
from research_engine.risk.scenarios import SCENARIO_LIBRARY_V1, evaluate_scenario, get_scenario
from research_engine.risk.shocks import BP, KEY_RATE_SET_ID
from research_engine.simulation.ports import (
    InstrumentInfo,
    PositionValuationResult,
    PriceResult,
    ScheduledCashFlow,
)

from .bond_pricer import settlement_price, valuation_pv
from .calc_store import CalculationStore
from .curve_model import CurveSource, DiscountCurveModel
from .quantlib_env import CONVENTIONS_VERSION, ENGINE_VERSION, LIBRARY
from .units import df_dec, price_dec, rate_dec, usd_dec, years_dec
from .yields import YIELD_CONVENTION, solve_ytm, yield_risk

PRICE_TOLERANCE_PER_100 = "0.0001"
HUNDRED = Decimal(100)


class QuantLibPricingPort:
    engine_version: str = ENGINE_VERSION

    def __init__(
        self,
        universe: InstrumentUniverse,
        curves: CurveSource,
        calc_store: Optional[CalculationStore] = None,
        *,
        data_mode: DataMode = DataMode.SYNTHETIC_CURVE,
        curve_cache_size: int = 256,
    ):
        self._universe = universe
        self.universe_id = universe.universe_id
        self.universe_version = universe.version
        self.universe_hash = content_hash(universe)
        self._models = {s.security_id: InstrumentModel(s) for s in universe.securities}
        self._terms_hash = {sid: content_hash(m.terms) for sid, m in self._models.items()}
        self._curves = curves
        self.calc_store = calc_store if calc_store is not None else CalculationStore()
        self.data_mode = data_mode
        self._cache: OrderedDict[str, ShockedCurves] = OrderedDict()
        self._cache_size = curve_cache_size
        self._lock = threading.Lock()
        self._provenance = EngineProvenance(
            engine_version=ENGINE_VERSION, library=LIBRARY, conventions_version=CONVENTIONS_VERSION
        )

    # ------------------------------------------------------------------ #
    # Instruments and calendar
    # ------------------------------------------------------------------ #
    def _model(self, security_id: str) -> InstrumentModel:
        try:
            return self._models[security_id]
        except KeyError as exc:
            raise KeyError(f"unknown security {security_id!r} in {self.universe_id}") from exc

    def terms(self, security_id: str) -> SecurityTerms:
        return self._model(security_id).terms

    def instrument(self, security_id: str) -> InstrumentInfo:
        return instrument_info(self._model(security_id))

    def universe(self, as_of: date) -> list[InstrumentInfo]:
        return [instrument_info(m) for m in self._models.values() if m.is_outstanding(as_of)]

    def cash_flows(self, security_id: str) -> list[ScheduledCashFlow]:
        return self._model(security_id).cash_flows()

    def is_business_day(self, day: date) -> bool:
        return cal.is_business_day(day)

    def advance_business_days(self, day: date, n: int) -> date:
        return cal.advance_business_days(day, n)

    def settlement_date(self, security_id: str, trade_date: date) -> date:
        return self._model(security_id).settlement_date(trade_date)

    def is_tradable(self, security_id: str, trade_date: date) -> bool:
        return self._model(security_id).is_tradable(trade_date)

    def accrued_per_100(self, security_id: str, settlement_date: date) -> Decimal:
        return price_dec(self._model(security_id).accrued_per_100(settlement_date))

    # ------------------------------------------------------------------ #
    # Curves
    # ------------------------------------------------------------------ #
    def curve_snapshot(self, curve_snapshot_id: str) -> CurveSnapshot:
        return self._curves.get_curve_snapshot(curve_snapshot_id)

    def _curve_set(self, curve_snapshot_id: str) -> ShockedCurves:
        with self._lock:
            hit = self._cache.get(curve_snapshot_id)
            if hit is not None:
                self._cache.move_to_end(curve_snapshot_id)
                return hit
        snapshot = self.curve_snapshot(curve_snapshot_id)
        curve_set = ShockedCurves(DiscountCurveModel.from_snapshot(snapshot))
        with self._lock:
            self._cache[curve_snapshot_id] = curve_set
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return curve_set

    def curve_model(self, curve_snapshot_id: str) -> DiscountCurveModel:
        return self._curve_set(curve_snapshot_id).base

    def discount_factor(self, curve_snapshot_id: str, anchor: date, payment_date: date) -> Decimal:
        return df_dec(self.curve_model(curve_snapshot_id).anchored_discount(anchor, payment_date))

    # ------------------------------------------------------------------ #
    # Calculation registration
    # ------------------------------------------------------------------ #
    def _register(
        self,
        calc_type: CalculationType,
        version: str,
        snapshot: CurveSnapshot,
        outputs: list[CalculatedValue],
        *,
        security_id: Optional[str] = None,
        valuation_date: Optional[date] = None,
        settlement_date: Optional[date] = None,
        face: Optional[Decimal] = None,
        completeness: Completeness = Completeness.COMPLETE,
        diagnostics: Iterable[str] = (),
        extra_inputs: Optional[dict[str, str]] = None,
        tolerances: Optional[dict[str, str]] = None,
    ) -> CalculationResult:
        inputs = {"curveSnapshot": snapshot.content_hash or ""}
        if security_id is not None:
            inputs["securityTerms"] = self._terms_hash[security_id]
        if extra_inputs:
            inputs.update(extra_inputs)
        result = CalculationResult(
            calculation_type=calc_type,
            calculation_version=version,
            data_mode=self.data_mode,
            security_id=security_id,
            curve_snapshot_id=snapshot.curve_snapshot_id,
            input_hashes=inputs,
            as_of=snapshot.available_at,
            valuation_date=valuation_date,
            settlement_date=settlement_date,
            face_usd=face,
            outputs=outputs,
            completeness=completeness,
            diagnostics=list(diagnostics),
            tolerances=tolerances or {"pricePer100": PRICE_TOLERANCE_PER_100},
            engine=self._provenance,
        )
        return self.calc_store.register(result)

    # ------------------------------------------------------------------ #
    # PricingPort: price / value_position
    # ------------------------------------------------------------------ #
    def price(self, security_id: str, curve_snapshot_id: str, settlement_date: date) -> PriceResult:
        model = self._model(security_id)
        snapshot = self.curve_snapshot(curve_snapshot_id)
        curve = self.curve_model(curve_snapshot_id)
        sp = settlement_price(model, curve, settlement_date)
        pv_v = valuation_pv(model, curve, curve.reference_date)
        dirty = price_dec(sp.dirty_per_100)
        accrued = price_dec(sp.accrued_per_100)
        clean = dirty - accrued
        v, s = curve.reference_date, settlement_date
        outputs = [
            CalculatedValue(
                name="dirty_price_per_100",
                value=dirty,
                unit=Unit.PRICE_PER_100,
                basis=ValueBasis.PER_100_FACE,
                anchor=Anchor.SETTLEMENT,
                anchor_date=s,
                definition="SUM_{t_i>s} CF_i*D(v,t_i)/D(v,s)",
            ),
            CalculatedValue(
                name="accrued_per_100",
                value=accrued,
                unit=Unit.PRICE_PER_100,
                basis=ValueBasis.PER_100_FACE,
                anchor=Anchor.SETTLEMENT,
                anchor_date=s,
                definition="ACT/ACT-ICMA accrued on unadjusted coupon dates",
            ),
            CalculatedValue(
                name="clean_price_per_100",
                value=clean,
                unit=Unit.PRICE_PER_100,
                basis=ValueBasis.PER_100_FACE,
                anchor=Anchor.SETTLEMENT,
                anchor_date=s,
                definition="dirty - accrued",
            ),
            CalculatedValue(
                name="discount_factor_to_settlement",
                value=df_dec(sp.discount_to_settlement),
                unit=Unit.RATIO,
                basis=ValueBasis.UNSCALED,
                anchor=Anchor.VALUATION,
                anchor_date=v,
                definition="D(v,s)",
            ),
            CalculatedValue(
                name="valuation_pv_per_100",
                value=price_dec(pv_v.pv_per_100),
                unit=Unit.PRICE_PER_100,
                basis=ValueBasis.PER_100_FACE,
                anchor=Anchor.VALUATION,
                anchor_date=v,
                definition="SUM_{t_i>v} CF_i*D(v,t_i) (valuation-date PV, not a settlement price)",
            ),
        ]
        calc = self._register(
            CalculationType.PRICE,
            "price-settlement-anchor-v1",
            snapshot,
            outputs,
            security_id=security_id,
            valuation_date=v,
            settlement_date=s,
        )
        return PriceResult(
            security_id=security_id,
            curve_snapshot_id=curve_snapshot_id,
            settlement_date=s,
            clean_price_per_100=clean,
            accrued_per_100=accrued,
            dirty_price_per_100=dirty,
            calculation_id=_calc_id(calc),
        )

    def _display_price(
        self, model: InstrumentModel, curve: DiscountCurveModel, valuation_date: date
    ) -> tuple[date, Optional[Decimal], Optional[Decimal], Optional[Decimal], list[str]]:
        settle = model.settlement_date(valuation_date)
        if model.is_tradable(valuation_date):
            sp = settlement_price(model, curve, settle)
            dirty = price_dec(sp.dirty_per_100)
            accrued = price_dec(sp.accrued_per_100)
            return settle, dirty - accrued, accrued, dirty, []
        return (
            settle,
            None,
            None,
            None,
            [
                f"not tradable at standard settlement {settle.isoformat()} (final payment "
                f"{model.final_payment_date.isoformat()}); settlement-anchored prices unavailable"
            ],
        )

    def value_position(
        self, security_id: str, curve_snapshot_id: str, valuation_date: date, face: Decimal
    ) -> PositionValuationResult:
        face = Decimal(face)
        if face < 0:
            raise ValueError("long-only: face must be non-negative")
        model = self._model(security_id)
        snapshot = self.curve_snapshot(curve_snapshot_id)
        curves = self._curve_set(curve_snapshot_id)
        sens = curve_sensitivity(model, curves, valuation_date, include_key_rates=False)
        scale = float(face) / 100.0
        pv_usd = usd_dec(sens.pv * scale)
        dv01_usd = usd_dec(sens.parallel_dv01 * scale)
        settle, clean, accrued, dirty, diags = self._display_price(
            model, curves.base, valuation_date
        )
        if clean is None:
            # Display fallback: valuation-date anchored per-100 values.
            accrued_u = price_dec(model.accrued_per_100(valuation_date))
            pv100 = price_dec(sens.pv)
            clean, accrued = pv100 - accrued_u, accrued_u
            diags.append("display clean/accrued anchored at valuation date instead")
        assert clean is not None and accrued is not None
        outputs = [
            CalculatedValue(
                name="pv_dirty_usd",
                value=pv_usd,
                unit=Unit.USD,
                basis=ValueBasis.FACE_SCALED,
                anchor=Anchor.VALUATION,
                anchor_date=valuation_date,
                definition="face/100 * SUM_{t_i>u} CF_i*D(v,t_i)/D(v,u)",
            ),
            CalculatedValue(
                name="parallel_dv01_usd",
                value=dv01_usd,
                unit=Unit.USD_PER_BP,
                basis=ValueBasis.FACE_SCALED,
                anchor=Anchor.VALUATION,
                anchor_date=valuation_date,
                definition="(PV(zero -1bp) - PV(zero +1bp))/2; positive = gain if rates fall",
            ),
            CalculatedValue(
                name="effective_duration_years",
                value=years_dec(sens.effective_duration),
                unit=Unit.YEARS,
                basis=ValueBasis.UNSCALED,
                anchor=Anchor.VALUATION,
                anchor_date=valuation_date,
                definition="curve effective duration (PV_down - PV_up)/(2*PV*1bp)",
            ),
            CalculatedValue(
                name="clean_price_per_100",
                value=clean,
                unit=Unit.PRICE_PER_100,
                basis=ValueBasis.PER_100_FACE,
                anchor=Anchor.SETTLEMENT if dirty is not None else Anchor.VALUATION,
                anchor_date=settle if dirty is not None else valuation_date,
            ),
            CalculatedValue(
                name="accrued_per_100",
                value=accrued,
                unit=Unit.PRICE_PER_100,
                basis=ValueBasis.PER_100_FACE,
                anchor=Anchor.SETTLEMENT if dirty is not None else Anchor.VALUATION,
                anchor_date=settle if dirty is not None else valuation_date,
            ),
        ]
        calc = self._register(
            CalculationType.POSITION_VALUATION,
            "position-valuation-v1",
            snapshot,
            outputs,
            security_id=security_id,
            valuation_date=valuation_date,
            settlement_date=settle,
            face=face,
            diagnostics=diags,
        )
        return PositionValuationResult(
            security_id=security_id,
            curve_snapshot_id=curve_snapshot_id,
            valuation_date=valuation_date,
            face=face,
            pv_dirty_usd=pv_usd,
            clean_price_per_100=clean,
            accrued_per_100=accrued,
            parallel_dv01_usd=dv01_usd,
            effective_duration_years=years_dec(sens.effective_duration),
            calculation_id=_calc_id(calc),
        )

    # ------------------------------------------------------------------ #
    # Quote conversion
    # ------------------------------------------------------------------ #
    def yield_from_clean_price(
        self, security_id: str, settlement_date: date, clean_price_per_100: Decimal
    ) -> Decimal:
        model = self._model(security_id)
        dirty = float(clean_price_per_100) + float(model.accrued_per_100(settlement_date))
        return rate_dec(solve_ytm(model, settlement_date, dirty))

    # ------------------------------------------------------------------ #
    # Risk
    # ------------------------------------------------------------------ #
    def _sensitivity(
        self, model: InstrumentModel, curve_snapshot_id: str, valuation_date: date
    ) -> CurveSensitivity:
        return curve_sensitivity(model, self._curve_set(curve_snapshot_id), valuation_date)

    def position_risk(
        self,
        security_id: str,
        curve_snapshot_id: str,
        valuation_date: date,
        face: Decimal = HUNDRED,
        *,
        relative_value: RelativeValueEstimate = SYNTHETIC_RELATIVE_VALUE,
    ) -> PositionRisk:
        face = Decimal(face)
        model = self._model(security_id)
        snapshot = self.curve_snapshot(curve_snapshot_id)
        curve = self.curve_model(curve_snapshot_id)
        sens = self._sensitivity(model, curve_snapshot_id, valuation_date)
        scale = float(face) / 100.0
        settle, clean, accrued, dirty, diags = self._display_price(model, curve, valuation_date)
        ytm = mod_dur = convexity = None
        if dirty is not None:
            sp = settlement_price(model, curve, settle)
            y = solve_ytm(model, settle, sp.dirty_per_100)
            yr = yield_risk(model, settle, y)
            ytm, mod_dur, convexity = (
                rate_dec(y),
                years_dec(yr.modified_duration),
                years_dec(yr.convexity),
            )
        else:
            diags.append("yield-based measures unavailable: no tradable settlement")
        fq = face / HUNDRED
        kr = [
            KeyRateExposure(key_tenor_years=Decimal(repr(k)), dv01_usd=usd_dec(v * scale))
            for k, v in zip(sens.key_tenors, sens.key_rate_dv01)
        ]
        remaining = model.remaining_maturity_years(valuation_date)
        risk = PositionRisk(
            security_id=security_id,
            face_usd=face,
            valuation_date=valuation_date,
            settlement_date=settle,
            clean_price_per_100=clean,
            accrued_per_100=accrued,
            dirty_price_per_100=dirty,
            settlement_consideration_usd=usd_dec(fq * dirty) if dirty is not None else None,
            clean_value_usd=usd_dec(fq * clean) if clean is not None else None,
            accrued_interest_usd=usd_dec(fq * accrued) if accrued is not None else None,
            economic_value_usd=usd_dec(sens.pv * scale),
            ytm=ytm,
            yield_modified_duration_years=mod_dur,
            yield_convexity=convexity,
            effective_duration_years=years_dec(sens.effective_duration),
            effective_convexity=years_dec(sens.effective_convexity),
            parallel_dv01_usd=usd_dec(sens.parallel_dv01 * scale),
            key_rate_dv01=kr,
            key_rate_sum_minus_parallel_usd=usd_dec(
                (sens.key_rate_sum - sens.parallel_dv01) * scale
            ),
            remaining_maturity_years=years_dec(remaining),
            maturity_bucket=maturity_bucket(remaining),
            relative_value=relative_value,
        )
        outputs = [
            CalculatedValue(
                name=name,
                value=value,
                unit=unit,
                basis=basis,
                anchor=anchor,
                anchor_date=anchor_date,
            )
            for name, value, unit, basis, anchor, anchor_date in [
                (
                    "economic_value_usd",
                    risk.economic_value_usd,
                    Unit.USD,
                    ValueBasis.FACE_SCALED,
                    Anchor.VALUATION,
                    valuation_date,
                ),
                (
                    "parallel_dv01_usd",
                    risk.parallel_dv01_usd,
                    Unit.USD_PER_BP,
                    ValueBasis.FACE_SCALED,
                    Anchor.VALUATION,
                    valuation_date,
                ),
                (
                    "effective_duration_years",
                    risk.effective_duration_years,
                    Unit.YEARS,
                    ValueBasis.UNSCALED,
                    Anchor.VALUATION,
                    valuation_date,
                ),
                (
                    "ytm",
                    risk.ytm,
                    Unit.DECIMAL_RATE,
                    ValueBasis.UNSCALED,
                    Anchor.SETTLEMENT,
                    settle,
                ),
                (
                    "yield_modified_duration_years",
                    risk.yield_modified_duration_years,
                    Unit.YEARS,
                    ValueBasis.UNSCALED,
                    Anchor.SETTLEMENT,
                    settle,
                ),
                (
                    "dirty_price_per_100",
                    risk.dirty_price_per_100,
                    Unit.PRICE_PER_100,
                    ValueBasis.PER_100_FACE,
                    Anchor.SETTLEMENT,
                    settle,
                ),
            ]
        ] + [
            CalculatedValue(
                name=f"key_rate_dv01_usd:{e.key_tenor_years}y",
                value=e.dv01_usd,
                unit=Unit.USD_PER_BP,
                basis=ValueBasis.FACE_SCALED,
                anchor=Anchor.VALUATION,
                anchor_date=valuation_date,
            )
            for e in kr
        ]
        calc = self._register(
            CalculationType.RISK,
            "position-risk-v1",
            snapshot,
            outputs,
            security_id=security_id,
            valuation_date=valuation_date,
            settlement_date=settle,
            face=face,
            completeness=Completeness.COMPLETE if dirty is not None else Completeness.PARTIAL,
            diagnostics=diags
            + [
                f"key rates: {KEY_RATE_SET_ID}; yield convention {YIELD_CONVENTION}",
                f"relative value: {relative_value.status.value}",
            ],
            tolerances={
                "pricePer100": PRICE_TOLERANCE_PER_100,
                "keyRateSumVsParallelRelative": "1e-6",
            },
        )
        return risk.model_copy(update={"calculation_id": _calc_id(calc)})

    def scenario(
        self,
        security_id: str,
        curve_snapshot_id: str,
        valuation_date: date,
        scenario_id: str,
        face: Decimal = HUNDRED,
    ) -> ScenarioResult:
        return self.portfolio_scenario(
            [(security_id, Decimal(face))], curve_snapshot_id, valuation_date, scenario_id
        )

    def portfolio_scenario(
        self,
        holdings: Sequence[tuple[str, Decimal]],
        curve_snapshot_id: str,
        valuation_date: date,
        scenario_id: str,
    ) -> ScenarioResult:
        definition = get_scenario(scenario_id)
        snapshot = self.curve_snapshot(curve_snapshot_id)
        curve = self.curve_model(curve_snapshot_id)
        faces = _aggregate_faces(holdings)
        base = scen = first = 0.0
        seconds: list[Optional[float]] = []
        method = ""
        for security_id, face in faces.items():
            model = self._model(security_id)
            sens = self._sensitivity(model, curve_snapshot_id, valuation_date)
            out = evaluate_scenario(model, curve, valuation_date, definition, sens)
            scale = float(face) / 100.0
            base += out.base_pv * scale
            scen += out.scenario_pv * scale
            first += out.first_order_pnl * scale
            seconds.append(None if out.second_order_pnl is None else out.second_order_pnl * scale)
            method = out.method
        second = None if any(v is None for v in seconds) else sum(v for v in seconds if v)
        pnl = scen - base
        single = next(iter(faces)) if len(faces) == 1 else None
        result = ScenarioResult(
            scenario_id=scenario_id,
            library_version=definition.library_version,
            curve_snapshot_id=curve_snapshot_id,
            valuation_date=valuation_date,
            security_id=single,
            face_usd=faces[single] if single else None,
            base_pv_usd=usd_dec(base),
            scenario_pv_usd=usd_dec(scen),
            pnl_usd=usd_dec(pnl),
            dv01_approx_pnl_usd=usd_dec(first),
            dv01_approx_error_usd=usd_dec(first - pnl),
            convexity_approx_pnl_usd=usd_dec(second) if second is not None else None,
            convexity_approx_error_usd=usd_dec(second - pnl) if second is not None else None,
            approximation_method=method,
        )
        calc = self._register(
            CalculationType.SCENARIO,
            "scenario-full-reprice-v1",
            snapshot,
            [
                CalculatedValue(
                    name="pnl_usd",
                    value=result.pnl_usd,
                    unit=Unit.USD,
                    basis=ValueBasis.FACE_SCALED,
                    anchor=Anchor.VALUATION,
                    anchor_date=valuation_date,
                    definition="full repricing under the scenario curve (authoritative)",
                ),
                CalculatedValue(
                    name="dv01_approx_error_usd",
                    value=result.dv01_approx_error_usd,
                    unit=Unit.USD,
                    basis=ValueBasis.FACE_SCALED,
                    anchor=Anchor.VALUATION,
                    anchor_date=valuation_date,
                ),
            ],
            security_id=single,
            valuation_date=valuation_date,
            face=faces[single] if single else None,
            extra_inputs={
                "scenario": content_hash(definition),
                "holdings": content_hash([[sid, str(face)] for sid, face in sorted(faces.items())]),
            },
        )
        return result.model_copy(update={"calculation_id": _calc_id(calc)})

    def portfolio_risk(
        self,
        holdings: Sequence[tuple[str, Decimal]],
        curve_snapshot_id: str,
        valuation_date: date,
        *,
        portfolio_snapshot_id: Optional[str] = None,
        cash_usd: Optional[Decimal] = None,
        pending_payables_usd: Optional[Decimal] = None,
        pending_receivables_usd: Optional[Decimal] = None,
        turnover_usd: Optional[Decimal] = None,
        scenario_ids: Optional[Sequence[str]] = None,
    ) -> RiskReport:
        """Aggregate economic positions: face is summed per security, then each
        position is face-scaled exactly once; portfolio DV01 is the sum."""
        snapshot = self.curve_snapshot(curve_snapshot_id)
        faces = _aggregate_faces(holdings)
        positions = [
            self.position_risk(sid, curve_snapshot_id, valuation_date, face)
            for sid, face in faces.items()
        ]
        total_pv = sum((p.economic_value_usd for p in positions), Decimal(0))
        total_dv01 = sum((p.parallel_dv01_usd for p in positions), Decimal(0))
        key_totals: dict[Decimal, Decimal] = {}
        for p in positions:
            for e in p.key_rate_dv01:
                key_totals[e.key_tenor_years] = key_totals.get(e.key_tenor_years, Decimal(0)) + (
                    e.dv01_usd
                )
        nav = None
        if cash_usd is not None:
            nav = (
                cash_usd
                + total_pv
                + (pending_receivables_usd or Decimal(0))
                - (pending_payables_usd or Decimal(0))
            )
        concentration = [
            ConcentrationEntry(
                security_id=p.security_id,
                economic_value_usd=p.economic_value_usd,
                weight_of_bonds=(
                    (p.economic_value_usd / total_pv).quantize(Decimal("1e-10"))
                    if total_pv
                    else Decimal(0)
                ),
                weight_of_nav=(
                    (p.economic_value_usd / nav).quantize(Decimal("1e-10")) if nav else None
                ),
            )
            for p in sorted(positions, key=lambda p: -p.economic_value_usd)
        ]
        buckets: dict[str, list[PositionRisk]] = {}
        for p in positions:
            buckets.setdefault(p.maturity_bucket, []).append(p)
        maturity = [
            MaturityBucket(
                bucket=label,
                economic_value_usd=sum((p.economic_value_usd for p in items), Decimal(0)),
                parallel_dv01_usd=sum((p.parallel_dv01_usd for p in items), Decimal(0)),
                security_ids=[p.security_id for p in items],
            )
            for label, items in sorted(buckets.items())
        ]
        scenarios = [
            self.portfolio_scenario(list(faces.items()), curve_snapshot_id, valuation_date, sid)
            for sid in (scenario_ids if scenario_ids is not None else SCENARIO_LIBRARY_V1)
        ]
        eff_dur = years_dec(float(total_dv01) / (float(total_pv) * BP)) if total_pv > 0 else None
        report = RiskReport(
            curve_snapshot_id=curve_snapshot_id,
            portfolio_snapshot_id=portfolio_snapshot_id,
            as_of=snapshot.available_at,
            valuation_date=valuation_date,
            data_mode=self.data_mode,
            positions=positions,
            total_economic_value_usd=total_pv,
            total_parallel_dv01_usd=total_dv01,
            total_key_rate_dv01=[
                KeyRateExposure(key_tenor_years=k, dv01_usd=v) for k, v in key_totals.items()
            ],
            portfolio_effective_duration_years=eff_dur,
            concentration=concentration,
            maturity_buckets=maturity,
            cash_available_usd=cash_usd,
            pending_settlement_payables_usd=pending_payables_usd,
            pending_settlement_receivables_usd=pending_receivables_usd,
            turnover_usd=turnover_usd,
            nav_usd=nav,
            scenarios=scenarios,
            relative_value=(
                SYNTHETIC_RELATIVE_VALUE
                if self.data_mode is DataMode.SYNTHETIC_CURVE
                else RelativeValueEstimate(
                    status=RelativeValueStatus.UNAVAILABLE,
                    reason="no admitted comparison-set reference curve",
                )
            ),
            definitions=RISK_DEFINITIONS,
            calculation_ids=[p.calculation_id for p in positions if p.calculation_id]
            + [s.calculation_id for s in scenarios if s.calculation_id],
        )
        return report.model_copy(
            update={"report_id": short_id("risk", report.model_dump(mode="json", by_alias=True))}
        )


def _calc_id(calc: CalculationResult) -> str:
    assert calc.calculation_id is not None, "calculation store must assign an id"
    return calc.calculation_id


def _aggregate_faces(holdings: Sequence[tuple[str, Decimal]]) -> dict[str, Decimal]:
    faces: dict[str, Decimal] = {}
    for security_id, face in holdings:
        face = Decimal(face)
        if face < 0:
            raise ValueError("long-only: negative face")
        faces[security_id] = faces.get(security_id, Decimal(0)) + face
    return {sid: faces[sid] for sid in sorted(faces)}


RISK_DEFINITIONS = {
    "economic_value_usd": "valuation-date PV of remaining flows (payment_date > valuation date), "
    "face-scaled once",
    "settlement_consideration_usd": "face/100 * dirty price at standard settlement, before fees",
    "parallel_dv01_usd": "(PV(zero curve -1bp) - PV(zero curve +1bp))/2; positive = gain for a "
    "downward shift; approx_pnl(up x bp) = -dv01*x",
    "key_rate_dv01": f"{KEY_RATE_SET_ID}: triangular zero-rate bumps at 1/2/5/10/30y nodes, "
    "flat beyond the end keys; sums to parallel DV01",
    "effective_duration_years": "curve-based: (PV_down - PV_up)/(2*PV*1bp)",
    "yield_modified_duration_years": f"yield-based ({YIELD_CONVENTION}); not the curve measure",
    "yield_convexity": f"yield-based ({YIELD_CONVENTION})",
    "maturity_bucket": "remaining years to unadjusted maturity on ACT/365.25",
    "relative_value": "synthetic same-curve mode: mechanically neutral, not a signal",
}
