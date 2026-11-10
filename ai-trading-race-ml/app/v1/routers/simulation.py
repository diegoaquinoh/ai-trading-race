"""``/internal/v1/simulation/*``: pure transition proposals and the common bootstrap.

Request binding: ``TransitionProposal.requestHash`` is ``content_hash`` of the JSON
request body exactly as received (parsed, then canonical JSON: sorted keys, compact,
ASCII, no floats). Fields the caller omitted are not filled with defaults first, so
the caller can verify the proposal against the exact body it sent. Offline replay
(no HTTP body) keeps hashing the ``TransitionRequest`` model.

Error mapping (spec 14.6): request-shape problems are 400/422; stale/mismatched
inputs are 409; deterministic engine rejections - including ledger invariants such
as a withdrawal above available cash - are 422 problem+json with a stable ``code``
and the ``portfolioId``; 503 is reserved for unavailable dependencies. Only
unexpected exceptions surface as 500.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from research_engine.contracts.common import content_hash
from research_engine.contracts.portfolio import TransitionRequest
from research_engine.simulation.engine import (
    ClockMovedBackward,
    DataNotYetAvailable,
    InvalidTransitionRequest,
    PortfolioBlocked,
    StateHashMismatch,
    TransitionError,
    propose_transition,
)
from research_engine.simulation.ledger import LedgerInvariantError

from ..common import in_threadpool, json_response, raw_response, universe_matches
from ..engine import Engine, get_engine
from ..errors import ProblemError, conflict, not_found, unprocessable
from ..openapi_models import contract_body, contract_response
from ..schemas import BootstrapAllocationRequest
from ..wire import check_version, dumps, parse_model, read_object, request_body_hash

router = APIRouter(prefix="/internal/v1/simulation", tags=["simulation"])

_TRANSITION_STATUS = {
    StateHashMismatch: (409, "state_hash_mismatch"),
    ClockMovedBackward: (409, "clock_moved_backward"),
    PortfolioBlocked: (409, "portfolio_blocked"),
    DataNotYetAvailable: (409, "data_not_yet_available"),
    InvalidTransitionRequest: (422, "invalid_transition_request"),
}


def verify_market_snapshot(engine: Engine, ref) -> None:
    """The referenced market snapshot must be exactly the engine's frozen inputs."""
    if ref is None:
        return
    market = engine.market
    if ref.data_mode != market.data_mode:
        raise unprocessable(
            "unsupported_data_mode",
            f"market snapshot data mode {ref.data_mode.value} differs from the engine "
            f"({market.data_mode.value})",
        )
    snapshot_id, snapshot_hash = market.market_snapshot_id(ref.session_date)
    payload = market.market_snapshot_payload(ref.session_date)
    if ref.content_hash != snapshot_hash or ref.market_snapshot_id != snapshot_id:
        raise conflict(
            "market_snapshot_mismatch",
            f"market snapshot {ref.market_snapshot_id} does not match the frozen inputs of "
            f"session {ref.session_date.isoformat()}",
            extra={"expectedMarketSnapshotId": snapshot_id, "expectedContentHash": snapshot_hash},
        )
    if ref.curve_snapshot_id is not None and ref.curve_snapshot_id != payload["curveSnapshotId"]:
        raise conflict(
            "market_snapshot_mismatch",
            f"curve snapshot {ref.curve_snapshot_id} is not the curve of session "
            f"{ref.session_date.isoformat()}",
        )


@router.post(
    "/transitions",
    summary="Pure numerical transition proposal (no application DB mutation)",
    openapi_extra=contract_body("TransitionRequest"),
    responses=contract_response("TransitionProposal"),
)
async def transitions(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    key = engine.require_signing()
    body = await read_object(request)
    state = body.get("portfolioState")
    if isinstance(state, dict):
        check_version(state.get("schemaVersion"), "portfolioState.schemaVersion")
    transition = parse_model(TransitionRequest, body)
    # Bound to the exact body received (see module docstring), not the parsed model.
    request_hash = request_body_hash(body)
    cached = engine.transition_cache.get(request_hash)
    if cached is not None:
        return raw_response(cached)
    verify_market_snapshot(engine, transition.market_snapshot)
    portfolio_id = transition.portfolio_state.portfolio_id
    try:
        proposal = await in_threadpool(
            propose_transition,
            transition,
            engine.pricing,
            engine.market,
            key,
            request_hash_override=request_hash,
        )
    except TransitionError as exc:
        status, code = _TRANSITION_STATUS.get(type(exc), (422, exc.code))
        raise ProblemError(status, code, str(exc)) from exc
    except LedgerInvariantError as exc:
        # Deterministic for this request and state: a rejection, not an outage.
        raise unprocessable(
            exc.code,
            f"portfolio {portfolio_id}: {exc}",
            extra={"portfolioId": portfolio_id},
        ) from exc
    except KeyError as exc:
        raise unprocessable("unknown_reference", str(exc)) from exc
    except ValueError as exc:
        raise unprocessable("invalid_transition_request", str(exc)) from exc
    return raw_response(engine.transition_cache.put(request_hash, dumps(proposal.to_wire())))


@router.post(
    "/bootstrap-allocation",
    summary="Common bootstrap allocation (identical for every invested strategy)",
    openapi_extra=contract_body("BootstrapAllocationRequest"),
)
async def bootstrap(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    from research_engine.experiments.baselines import BootstrapError, bootstrap_allocation

    engine.require_signing()
    body = await read_object(request)
    req = parse_model(BootstrapAllocationRequest, body)
    if not universe_matches(engine.market, req.universe_version):
        raise not_found(
            "unknown_universe_version",
            f"universe version {req.universe_version!r} is not loaded "
            f"({engine.market.universe_contract.version})",
        )
    if not engine.pricing.is_business_day(req.session_date):
        raise unprocessable(
            "not_a_session",
            f"{req.session_date.isoformat()} is not a U.S. government-bond business day",
        )

    def compute():
        universe = engine.pricing.universe(req.session_date)
        return bootstrap_allocation(universe, req.session_date, req.risk_policy)

    try:
        allocation = await in_threadpool(compute)
    except BootstrapError as exc:
        raise unprocessable("bootstrap_allocation_unavailable", str(exc)) from exc
    contract = engine.market.universe_contract
    payload = {
        "version": allocation.version,
        "sessionDate": allocation.session_date.isoformat(),
        "universeId": contract.universe_id,
        "universeVersion": contract.version,
        "universeHash": engine.market.universe_hash,
        "riskPolicyId": req.risk_policy.policy_id,
        "riskPolicyHash": req.risk_policy.compute_hash(),
        "targets": [t.to_wire() for t in allocation.targets],
        "buckets": allocation.buckets,
        "notes": list(allocation.notes),
        "dataMode": engine.market.data_mode.value,
    }
    payload["allocationHash"] = content_hash(payload)
    return json_response(payload)
