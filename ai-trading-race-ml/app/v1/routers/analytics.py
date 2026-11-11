"""``/internal/v1/analytics/*``: curve-model prices, portfolio risk and evaluation metrics.

Every numerical output is a signed ``CalculationResult`` registered in the
calculation store; responses carry the calculation ids and records. Prices in
synthetic mode are curve-model values (``priceType = curve_model``), never
market quotes. ``/performance`` computes evaluation metrics (spec 16.3) from the
series the platform stores, with ``research_engine.experiments.metrics`` - the same
implementation as the offline report.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from research_engine.contracts.calculations import Completeness
from research_engine.contracts.portfolio import Side
from research_engine.risk.scenarios import SCENARIO_LIBRARY_V1

from ..common import curve_or_404, in_threadpool, json_response, require_ready_curve, verified_state
from ..engine import Engine, get_engine
from ..errors import not_found, unprocessable
from ..openapi_models import contract_body
from ..performance import compute_performance
from ..schemas import PerformanceRequest, PriceRequest, RiskRequest
from ..wire import parse_model, read_object

router = APIRouter(prefix="/internal/v1/analytics", tags=["analytics"])

HUNDRED = Decimal(100)


def price_type(engine: Engine) -> str:
    return "curve_model" if engine.market.data_mode.value == "synthetic_curve" else "observed"


def _calc(engine: Engine, calc_id):
    record = engine.calc_store.get(calc_id) if calc_id else None
    return record.to_wire() if record is not None else None


def compute_prices(engine: Engine, req: PriceRequest) -> dict:
    pricing = engine.pricing
    snapshot = curve_or_404(engine.market, req.curve_snapshot_id)
    require_ready_curve(snapshot)
    if req.valuation_date != snapshot.reference_date:
        raise unprocessable(
            "valuation_date_mismatch",
            f"valuationDate {req.valuation_date.isoformat()} must equal the curve reference "
            f"date {snapshot.reference_date.isoformat()}",
        )
    if req.settlement_date is not None and req.settlement_date < req.valuation_date:
        raise unprocessable("invalid_request", "settlementDate precedes valuationDate")
    if req.face_usd is not None and req.face_usd <= 0:
        raise unprocessable("invalid_units", "faceUsd must be a positive USD face amount")
    known = {s.security_id for s in engine.market.universe_contract.securities}
    unknown = [sid for sid in req.security_ids if sid not in known]
    if unknown:
        raise not_found("unknown_security", f"unknown security ids: {', '.join(unknown)}")
    items = []
    calc_ids: list[str] = []
    for sid in dict.fromkeys(req.security_ids):
        settle = req.settlement_date or pricing.settlement_date(sid, req.valuation_date)
        item: dict = {
            "securityId": sid,
            "settlementDate": settle.isoformat(),
            "priceType": price_type(engine),
            "quoteBasis": "clean_per_100",
            "diagnostics": [],
        }
        result = None
        if req.settlement_date is None and not pricing.is_tradable(sid, req.valuation_date):
            item["diagnostics"].append("not tradable at standard settlement")
        else:
            try:
                result = pricing.price(sid, req.curve_snapshot_id, settle)
            except (ValueError, RuntimeError) as exc:
                item["diagnostics"].append(f"price unavailable: {exc}")
        if result is None:
            item.update(
                completeness=Completeness.UNAVAILABLE.value,
                cleanPricePer100=None,
                accruedPer100=None,
                dirtyPricePer100=None,
                calculationId=None,
            )
        else:
            item.update(
                completeness=Completeness.COMPLETE.value,
                cleanPricePer100=str(result.clean_price_per_100),
                accruedPer100=str(result.accrued_per_100),
                dirtyPricePer100=str(result.dirty_price_per_100),
                calculationId=result.calculation_id,
            )
            calc_ids.append(result.calculation_id)
            if req.face_usd is not None:
                try:
                    position = pricing.value_position(
                        sid, req.curve_snapshot_id, req.valuation_date, req.face_usd
                    )
                except ValueError as exc:  # deterministic numerical rejection
                    raise unprocessable("calculation_rejected", f"{sid}: {exc}") from exc
                item["position"] = {
                    "faceUsd": str(req.face_usd),
                    "settlementConsiderationUsd": str(
                        (req.face_usd / HUNDRED * result.dirty_price_per_100).quantize(
                            Decimal("0.01")
                        )
                    ),
                    "pvDirtyUsd": str(position.pv_dirty_usd),
                    "pvAnchor": "valuation_date",
                    "parallelDv01Usd": str(position.parallel_dv01_usd),
                    "effectiveDurationYears": str(position.effective_duration_years),
                    "calculationId": position.calculation_id,
                }
                calc_ids.append(position.calculation_id)
        items.append(item)
    return {
        "schemaVersion": req.schema_version,
        "requestId": req.request_id,
        "curveSnapshotId": snapshot.curve_snapshot_id,
        "curveContentHash": snapshot.content_hash,
        "valuationDate": req.valuation_date.isoformat(),
        "dataMode": engine.market.data_mode.value,
        "priceType": price_type(engine),
        "marketQuote": False,
        "engineVersion": pricing.engine_version,
        "items": items,
        "calculationIds": calc_ids,
        "calculations": [c for c in (_calc(engine, i) for i in calc_ids) if c is not None],
    }


@router.post(
    "/price",
    summary="Price an admitted instrument batch against a frozen curve",
    openapi_extra=contract_body("PriceRequest"),
)
async def price(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    body = await read_object(request)
    req = parse_model(PriceRequest, body)
    engine.requests.bind("analytics.price", req.request_id, req.to_wire())
    return json_response(await in_threadpool(compute_prices, engine, req))


def compute_risk(engine: Engine, req: RiskRequest) -> dict:
    state = verified_state(req.portfolio_state, req.portfolio_state_hash)
    snapshot = curve_or_404(engine.market, req.curve_snapshot_id)
    require_ready_curve(snapshot)
    if req.valuation_date < snapshot.reference_date:
        raise unprocessable(
            "valuation_date_mismatch",
            f"valuationDate {req.valuation_date.isoformat()} precedes the curve reference date",
        )
    unknown_scenarios = [s for s in req.scenario_ids if s not in SCENARIO_LIBRARY_V1]
    if unknown_scenarios:
        raise unprocessable(
            "unknown_scenario",
            f"unknown scenario ids {unknown_scenarios}; allowed: {sorted(SCENARIO_LIBRARY_V1)}",
        )
    known = {s.security_id for s in engine.market.universe_contract.securities}
    holdings = [(p.security_id, p.economic_face) for p in state.positions if p.economic_face > 0]
    unknown = [sid for sid, _ in holdings if sid not in known]
    if unknown:
        raise not_found("unknown_security", f"unknown security ids: {', '.join(unknown)}")
    payables = sum(
        (s.cash_usd for s in state.pending_settlements if s.side == Side.BUY), Decimal(0)
    )
    receivables = sum(
        (s.cash_usd for s in state.pending_settlements if s.side == Side.SELL), Decimal(0)
    )
    try:
        report = engine.pricing.portfolio_risk(
            holdings,
            req.curve_snapshot_id,
            req.valuation_date,
            portfolio_snapshot_id=f"pfs:{state.portfolio_id}:v{state.version}",
            cash_usd=state.cash_usd,
            pending_payables_usd=payables,
            pending_receivables_usd=receivables,
            scenario_ids=list(req.scenario_ids) or None,
        )
    except ValueError as exc:  # deterministic numerical rejection, not an outage
        raise unprocessable(
            "calculation_rejected",
            f"portfolio {state.portfolio_id}: {exc}",
            extra={"portfolioId": state.portfolio_id},
        ) from exc
    return {
        "schemaVersion": req.schema_version,
        "requestId": req.request_id,
        "portfolioId": state.portfolio_id,
        "portfolioVersion": state.version,
        "portfolioStateHash": req.portfolio_state_hash,
        "curveSnapshotId": snapshot.curve_snapshot_id,
        "curveContentHash": snapshot.content_hash,
        "valuationDate": req.valuation_date.isoformat(),
        "priceType": price_type(engine),
        "pendingSettlementBasis": "undiscounted_contractual_cash",
        "report": report.to_wire(),
    }


@router.post(
    "/risk",
    summary="Portfolio risk and scenario outputs for exact snapshots",
    openapi_extra=contract_body("RiskRequest"),
)
async def risk(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    body = await read_object(request)
    req = parse_model(RiskRequest, body)
    engine.requests.bind("analytics.risk", req.request_id, req.to_wire())
    return json_response(await in_threadpool(compute_risk, engine, req))


@router.post(
    "/performance",
    summary="Evaluation metrics for stored portfolio series (metrics-v1)",
    openapi_extra=contract_body(
        "PerformanceRequest",
        "Stored valuations (with accounting balances), fills, cash flows, order and decision "
        "outcome counts per portfolio; metrics are computed by research_engine.experiments.metrics",
    ),
)
async def performance(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    body = await read_object(request)
    req = parse_model(PerformanceRequest, body)
    engine.requests.bind("analytics.performance", req.request_id, req.to_wire())
    version = getattr(engine.pricing, "engine_version", None)
    return json_response(await in_threadpool(compute_performance, req, version))
