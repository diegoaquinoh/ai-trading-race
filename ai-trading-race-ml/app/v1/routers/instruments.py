"""``/internal/v1/instruments``, ``/internal/v1/instruments/{securityId}/valuation`` and
``/internal/v1/instruments/payment-calendar`` (projected payments of a portfolio state).

Synthetic instruments are hypothetical; their prices are curve-model values
labelled ``curve_model`` and never presented as market quotes. Relative value
is ``unavailable_synthetic_same_curve`` in synthetic mode (spec 3.2, 8.4).
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from research_engine.contracts.calculations import SYNTHETIC_RELATIVE_VALUE
from research_engine.contracts.common import utc_to_str
from research_engine.risk.scenarios import SCENARIO_LIBRARY_V1
from research_engine.simulation.clock import decision_at, ny_date
from research_engine.simulation import payments

from ..common import in_threadpool, json_response, page_bounds, universe_matches, verified_state
from ..engine import Engine, get_engine
from ..errors import not_found, unprocessable
from ..openapi_models import contract_body
from ..schemas import PaymentCalendarRequest
from ..wire import parse_date, parse_model, read_object

router = APIRouter(prefix="/internal/v1/instruments", tags=["instruments"])

HUNDRED = Decimal(100)
RELATIVE_VALUE_SYNTHETIC = "unavailable_synthetic_same_curve"


def _status(terms, as_of: Optional[date]) -> str:
    if as_of is None:
        return "listed"
    if as_of < terms.dates.original_issue_date:
        return "not_yet_issued"
    from research_engine.instruments.schedule import InstrumentModel

    final = InstrumentModel(terms).final_payment_date
    return "outstanding" if as_of < final else "matured"


def instrument_page(
    engine: Engine,
    as_of: Optional[date],
    universe_version: Optional[str],
    security_id: Optional[str],
    page: int,
    page_size: int,
) -> dict:
    contract = engine.market.universe_contract
    if not universe_matches(engine.market, universe_version):
        raise not_found(
            "unknown_universe_version", f"universe version {universe_version!r} is not loaded"
        )
    start, stop = page_bounds(page, page_size)
    cutoff = datetime.combine(as_of, time(23, 59, 59), tzinfo=timezone.utc) if as_of else None
    items = []
    for terms in sorted(contract.securities, key=lambda t: t.security_id):
        if security_id and terms.security_id != security_id:
            continue
        if as_of is not None:
            if terms.terms_effective_from > as_of:
                continue
            if terms.terms_effective_to is not None and terms.terms_effective_to < as_of:
                continue
            if terms.provenance.available_at > cutoff:
                continue
            if as_of < terms.dates.original_issue_date:
                continue  # point in time: no future issues
        items.append(
            {
                "securityId": terms.security_id,
                "status": _status(terms, as_of),
                "synthetic": terms.identity.classification.value == "synthetic",
                "termsHash": terms.compute_hash(),
                "terms": terms.to_wire(),
            }
        )
    if security_id and not items:
        raise not_found("unknown_security", f"security {security_id!r} is not admitted")
    return {
        "universeId": contract.universe_id,
        "universeVersion": contract.version,
        "classification": contract.classification.value,
        "hypotheticalNotice": contract.hypothetical_notice,
        "dataMode": engine.market.data_mode.value,
        "asOf": as_of.isoformat() if as_of else None,
        "page": page,
        "pageSize": page_size,
        "total": len(items),
        "items": items[start:stop],
    }


@router.get("", summary="Admitted securities and term versions (point in time)")
async def instruments(
    asOf: Optional[str] = Query(None, description="YYYY-MM-DD"),
    universeVersion: Optional[str] = Query(None),
    securityId: Optional[str] = Query(None),
    page: int = Query(1),
    pageSize: int = Query(50),
    engine: Engine = Depends(get_engine),
) -> Response:
    engine.require_signing()
    as_of = parse_date(asOf, "asOf", required=False)
    return json_response(
        await in_threadpool(
            instrument_page, engine, as_of, universeVersion, securityId, page, pageSize
        )
    )


def valuation(engine: Engine, security_id: str, day: date) -> dict:
    pricing, market = engine.pricing, engine.market
    try:
        terms = pricing.terms(security_id)
    except KeyError as exc:
        raise not_found("unknown_security", f"security {security_id!r} is not admitted") from exc
    cutoff = decision_at(day)
    curve = market.latest_available_curve(cutoff)
    if curve is None:
        raise not_found(
            "no_curve_available",
            f"no READY curve was available by {utc_to_str(cutoff)} for {day.isoformat()}",
        )
    valuation_date = curve.session_date
    from research_engine.instruments.schedule import InstrumentModel

    model = InstrumentModel(terms)
    if not model.is_outstanding(valuation_date):
        raise not_found(
            "instrument_not_outstanding",
            f"{security_id} is not outstanding on {valuation_date.isoformat()}",
        )
    curve_id = curve.curve_snapshot_id
    synthetic = market.data_mode.value == "synthetic_curve"
    try:
        risk = pricing.position_risk(security_id, curve_id, valuation_date, HUNDRED)
        results = [
            (sid, pricing.scenario(security_id, curve_id, valuation_date, sid, HUNDRED))
            for sid in sorted(SCENARIO_LIBRARY_V1)
        ]
    except ValueError as exc:  # deterministic numerical rejection (e.g. too close to maturity)
        raise unprocessable("calculation_rejected", f"{security_id}: {exc}") from exc
    flows = [
        cf.to_wire() for cf in pricing.cash_flows(security_id) if cf.payment_date > valuation_date
    ]
    scenarios = []
    for scenario_id, result in results:
        scenarios.append(
            {
                "scenarioId": scenario_id,
                "libraryVersion": result.library_version,
                "description": SCENARIO_LIBRARY_V1[scenario_id].description,
                "basePvPer100": str(result.base_pv_usd),
                "scenarioPvPer100": str(result.scenario_pv_usd),
                "pnlPer100": str(result.pnl_usd),
                "priceType": "curve_model",
                "anchor": "valuation_date_pv",
                "hypothetical": True,
                "calculationId": result.calculation_id,
            }
        )

    def s(value) -> Optional[str]:
        return str(value) if value is not None else None

    return {
        "securityId": security_id,
        "requestedDate": day.isoformat(),
        "valuationDate": valuation_date.isoformat(),
        "curveSnapshotId": curve_id,
        "curveContentHash": curve.content_hash,
        "curveSessionDate": curve.session_date.isoformat(),
        "curveAvailableAt": utc_to_str(curve.available_at),
        "curveStale": curve.session_date != day,
        "dataMode": market.data_mode.value,
        "synthetic": terms.identity.classification.value == "synthetic",
        "terms": terms.to_wire(),
        "provenance": terms.provenance.to_wire(),
        "upcomingCashFlows": flows,
        "price": {
            "priceType": "curve_model" if synthetic else "observed",
            "marketQuote": False,
            "label": (
                "curve-model value from the synthetic Treasury par curve; not a market quote"
                if synthetic
                else "model value"
            ),
            "settlementDate": risk.settlement_date.isoformat(),
            "cleanPricePer100": s(risk.clean_price_per_100),
            "accruedPer100": s(risk.accrued_per_100),
            "dirtyPricePer100": s(risk.dirty_price_per_100),
            "economicValuePer100": s(risk.economic_value_usd),
            "economicValueAnchor": "valuation_date",
        },
        "yieldToMaturity": s(risk.ytm),
        "yieldConvention": terms.conventions.yield_convention,
        "durations": {
            "yieldModifiedDurationYears": s(risk.yield_modified_duration_years),
            "yieldConvexity": s(risk.yield_convexity),
            "effectiveDurationYears": s(risk.effective_duration_years),
            "effectiveConvexity": s(risk.effective_convexity),
        },
        "dv01": {
            "faceUsd": "100",
            "parallelDv01Usd": s(risk.parallel_dv01_usd),
            "keyRateDv01": [k.to_wire() for k in risk.key_rate_dv01],
            "keyRateSumMinusParallelUsd": s(risk.key_rate_sum_minus_parallel_usd),
        },
        "remainingMaturityYears": s(risk.remaining_maturity_years),
        "maturityBucket": risk.maturity_bucket,
        "scenarios": scenarios,
        "relativeValue": (
            {"status": RELATIVE_VALUE_SYNTHETIC, "reason": SYNTHETIC_RELATIVE_VALUE.reason}
            if synthetic
            else risk.relative_value.to_wire()
        ),
        "calculationId": risk.calculation_id,
        "engineVersion": pricing.engine_version,
    }


@router.get("/{security_id}/valuation", summary="Curve-model valuation, risk and scenarios")
async def instrument_valuation(
    security_id: str,
    date_: str = Query(..., alias="date", description="YYYY-MM-DD"),
    engine: Engine = Depends(get_engine),
) -> Response:
    engine.require_signing()
    day = parse_date(date_, "date")
    return json_response(await in_threadpool(valuation, engine, security_id, day))


def payment_calendar(engine: Engine, req: PaymentCalendarRequest) -> dict:
    from datetime import timedelta

    state = verified_state(req.portfolio_state, req.portfolio_state_hash)
    known = {s.security_id for s in engine.market.universe_contract.securities}
    held = payments.held_securities(state)
    unknown = [sid for sid in held if sid not in known]
    if unknown:
        raise not_found("unknown_security", f"unknown security ids: {', '.join(unknown)}")
    after = req.after or state.cash_flows_processed_through or ny_date(state.as_of)
    through = after + timedelta(days=req.horizon_days)
    items = payments.payment_calendar(state, engine.pricing, after=after, through=through)
    synthetic = {
        t.security_id
        for t in engine.market.universe_contract.securities
        if t.identity.classification.value == "synthetic"
    }
    for item in items:
        item["synthetic"] = item["securityId"] in synthetic
    return {
        "schemaVersion": req.schema_version,
        "requestId": req.request_id,
        "portfolioId": state.portfolio_id,
        "portfolioVersion": state.version,
        "portfolioStateHash": req.portfolio_state_hash,
        "after": after.isoformat(),
        "through": through.isoformat(),
        "cashFlowsProcessedThrough": (
            state.cash_flows_processed_through.isoformat()
            if state.cash_flows_processed_through
            else None
        ),
        "basis": payments.BASIS,
        "entitlementRule": "settled face plus pending purchases minus pending sales settling "
        "strictly before the payment date",
        "note": "projection from the current state; later trades are not anticipated and no "
        "amount is a committed cash flow",
        "dataMode": engine.market.data_mode.value,
        "items": items,
        "totals": payments.totals(items),
        "engineVersion": engine.pricing.engine_version,
    }


@router.post(
    "/payment-calendar",
    summary="Projected coupons and redemptions of a portfolio state's holdings",
    openapi_extra=contract_body(
        "PaymentCalendarRequest",
        "Inline portfolio state bound to portfolioStateHash (409 on mismatch)",
    ),
)
async def instrument_payment_calendar(
    request: Request, engine: Engine = Depends(get_engine)
) -> Response:
    engine.require_signing()
    body = await read_object(request)
    req = parse_model(PaymentCalendarRequest, body)
    return json_response(await in_threadpool(payment_calendar, engine, req))
