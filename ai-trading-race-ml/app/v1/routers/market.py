"""``/internal/v1/market/sessions`` and ``/internal/v1/curves/{snapshotId}``.

A session is usable for a decision only when its curve is READY *and* its
``availableAt`` is no later than the scheduled decision time (19:00
America/New_York); otherwise it is a flagged gap, never filled from a
neighbouring day.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from research_engine.contracts.common import utc_to_str
from research_engine.simulation.clock import decision_at, observation_at

from ..common import curve_or_404, in_threadpool, json_response
from ..engine import Engine, get_engine
from ..errors import unprocessable
from ..wire import parse_date

router = APIRouter(prefix="/internal/v1", tags=["market"])

MAX_SESSION_RANGE_DAYS = 1100


def session_rows(engine: Engine, start: date, end: date) -> list[dict]:
    market, pricing = engine.market, engine.pricing
    rows = []
    for day in market.sessions(start, end):
        status = market.session_status(day)
        snapshot = market.curve_snapshot_for_session(day)
        observation = market.observation(day)
        decided = decision_at(day)
        observed_at = (
            snapshot.valuation_at
            if snapshot
            else (observation.observed_at if observation else None)
        )
        available_at = (
            snapshot.available_at
            if snapshot
            else (observation.available_at if observation else None)
        )
        gap_reason: Optional[str] = None
        if status != "READY":
            gap_reason = status
            if snapshot is not None and snapshot.failure_reasons:
                gap_reason = f"{status}:" + ";".join(snapshot.failure_reasons)
        elif available_at is None or available_at > decided:
            gap_reason = "curve_not_available_by_decision_time"
        gap = gap_reason is not None
        snapshot_id = snapshot_hash = None
        if not gap:
            snapshot_id, snapshot_hash = market.market_snapshot_id(day)
        next_session = pricing.advance_business_days(day, 1)
        rows.append(
            {
                "sessionDate": day.isoformat(),
                "marketSnapshotId": snapshot_id,
                "marketSnapshotHash": snapshot_hash,
                "curveSnapshotId": snapshot.curve_snapshot_id if snapshot else None,
                "curveStatus": status,
                "observedAt": utc_to_str(observed_at) if observed_at else None,
                "availableAt": utc_to_str(available_at) if available_at else None,
                "decisionAsOf": utc_to_str(decided),
                "executionObservationAt": utc_to_str(observation_at(next_session)),
                "gap": gap,
                "gapReason": gap_reason,
            }
        )
    return rows


@router.get("/market/sessions", summary="Market sessions with snapshot ids and gap flags")
async def sessions(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    engine: Engine = Depends(get_engine),
) -> Response:
    engine.require_signing()
    first = parse_date(start, "start")
    last = parse_date(end, "end")
    assert first is not None and last is not None
    if last < first:
        raise unprocessable("invalid_request", "end precedes start")
    if (last - first).days > MAX_SESSION_RANGE_DAYS:
        raise unprocessable(
            "invalid_request", f"session range is limited to {MAX_SESSION_RANGE_DAYS} days"
        )
    rows = await in_threadpool(session_rows, engine, first, last)
    contract = engine.market.universe_contract
    return json_response(
        {
            "dataMode": engine.market.data_mode.value,
            "universeVersion": contract.version,
            "universeId": contract.universe_id,
            "datasetId": engine.market.dataset_id,
            "datasetStart": engine.market.start.isoformat(),
            "datasetEnd": engine.market.end.isoformat(),
            "schedule": "schedule-ny-v1",
            "sessions": rows,
        }
    )


def curve_document(engine: Engine, snapshot_id: str) -> dict:
    market = engine.market
    snapshot = curve_or_404(market, snapshot_id)
    observation = market.observation(snapshot.session_date)
    inputs = []
    if observation is not None and observation.observation_id in snapshot.input_observation_ids:
        inputs.append(observation.to_wire())
    wire = snapshot.to_wire()
    return {
        **wire,
        "inputs": inputs,
        "diagnostics": {
            "status": snapshot.status.value,
            "failureReasons": list(snapshot.failure_reasons),
            "usedTenors": list(snapshot.used_tenors),
            "excludedTenors": list(snapshot.excluded_tenors),
            "maxAbsRateResidual": wire.get("maxAbsRateResidual"),
            "residuals": wire.get("residuals", []),
            "validatedHorizonDate": wire.get("validatedHorizonDate"),
        },
        "labels": {
            "dataMode": snapshot.data_mode.value,
            "inputQuoteBasis": "indicative_bid_side_par_yield",
            "executable": False,
            "availabilityReconstructed": (
                observation.availability_reconstructed if observation is not None else None
            ),
        },
    }


@router.get("/curves/{snapshot_id}", summary="Curve inputs, specification, diagnostics and nodes")
async def curve(snapshot_id: str, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    return json_response(await in_threadpool(curve_document, engine, snapshot_id))
