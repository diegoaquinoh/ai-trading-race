"""``POST /internal/v1/strategies/decisions``: bounded proposal for one strategy/cycle.

The request carries the strategy's own portfolio state inline; it is bound to
``portfolioSnapshot.contentHash`` (409 on mismatch) and the market snapshot is
bound to the engine's frozen session inputs (409 on mismatch). The result is a
signed :class:`StrategyResult` for every outcome; HOLD, abstention and stale
data are 200 results. Decisions never ingest or build indexes: evidence comes
from an already loaded READY index (503 if none). Saturation of the bounded
decision pool returns 429 with ``Retry-After``.

Risk policy: the request names ``riskPolicyId``; the policy object is resolved
from the engine's registry of known policies, or taken from an optional
``riskPolicy`` object supplied by the application whose ``policyId`` must equal
``riskPolicyId``. Strategies and models never choose the policy.

Request binding: ``StrategyResult.requestHash`` is ``content_hash`` of the JSON
request body exactly as received (parsed, then canonical JSON: sorted keys, compact,
ASCII, no floats), including the optional ``riskPolicy`` / ``executionModel``
objects. Omitted fields are not filled with defaults, so the caller verifies the
result against the exact body it sent. ``inputHashes.decisionRequest`` keeps the
hash of the parsed ``DecisionRequest`` model, as in offline replay (where no HTTP
body exists and ``requestHash`` is that model hash).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError

from research_engine.contracts.common import content_hash, sign_hash
from research_engine.contracts.decisions import (
    DecisionOutcome,
    DecisionRequest,
    RetrievalMode,
    StrategyResult,
    VersionInfo,
)
from research_engine.contracts.portfolio import (
    ExecutionModel,
    MarketSnapshotRef,
    PortfolioState,
    RiskPolicy,
    TargetWeight,
)
from research_engine.simulation.engine import engine_version

from ..common import raw_response, verified_state
from ..engine import Engine, get_engine
from ..errors import ProblemError, conflict, not_found, unavailable, unprocessable
from ..openapi_models import contract_body, contract_response
from ..strategies import ProviderUnavailable, llm_strategy_spec
from ..wire import dumps, parse_model, read_object, request_body_hash

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/v1/strategies", tags=["strategies"])

DEFAULT_POLICY = RiskPolicy()
KNOWN_POLICIES: dict[str, RiskPolicy] = {DEFAULT_POLICY.policy_id: DEFAULT_POLICY}


def resolve_policy(policy_id: str, supplied: Any) -> RiskPolicy:
    if supplied is not None:
        policy = parse_model(RiskPolicy, supplied)
        if policy.policy_id != policy_id:
            raise unprocessable(
                "risk_policy_mismatch",
                f"riskPolicy.policyId {policy.policy_id!r} differs from riskPolicyId "
                f"{policy_id!r}; the policy cannot be changed by request fields",
            )
        known = KNOWN_POLICIES.get(policy_id)
        if known is not None and known.compute_hash() != policy.compute_hash():
            raise conflict(
                "risk_policy_mismatch",
                f"riskPolicy {policy_id!r} differs from the registered immutable definition",
            )
        return policy
    try:
        return KNOWN_POLICIES[policy_id]
    except KeyError as exc:
        raise unprocessable(
            "unknown_risk_policy",
            f"risk policy {policy_id!r} is not registered; send the application's riskPolicy "
            "object with the same policyId",
        ) from exc


def sign_result(
    result: StrategyResult, key: bytes, request_hash_override: Optional[str] = None
) -> StrategyResult:
    """Hash and sign a result; ``request_hash_override`` (exact-body hash) is bound first."""
    update: dict[str, Any] = {"result_hash": None, "signature": None}
    if request_hash_override is not None:
        update["request_hash"] = request_hash_override
    bare = result.model_copy(update=update)
    digest = content_hash(bare.hash_payload())
    return bare.model_copy(update={"result_hash": digest, "signature": sign_hash(digest, key)})


def outcome_result(
    request: DecisionRequest,
    strategy: Any,
    outcome: DecisionOutcome,
    reasons: list[str],
    pricing: Any,
    input_hashes: Optional[dict[str, str]] = None,
) -> StrategyResult:
    request_hash = request.compute_hash()
    return StrategyResult(
        run_id=request.run_id,
        cycle_id=request.cycle_id,
        decision_id=request.decision_id,
        strategy_id=strategy.strategy_id,
        strategy_kind=strategy.kind,
        repetition=request.repetition,
        request_hash=request_hash,
        input_hashes=input_hashes or {"decisionRequest": request_hash},
        outcome=outcome,
        completed_at=request.decision_as_of,
        reasons=reasons,
        versions=VersionInfo(engine_version=engine_version(pricing)),
    )


def validated(raw: Any, request: DecisionRequest, strategy: Any) -> StrategyResult:
    """Same checks as the replay runner: schema, identity and proposal presence."""
    if not isinstance(raw, StrategyResult):
        raw = StrategyResult.model_validate(raw)
    else:
        raw = StrategyResult.model_validate(raw.model_dump())
    if raw.decision_id != request.decision_id or raw.strategy_id != strategy.strategy_id:
        raise ValueError("strategy result identity does not match the decision request")
    if raw.run_id != request.run_id or raw.cycle_id != request.cycle_id:
        raise ValueError("strategy result run/cycle does not match the decision request")
    if raw.outcome == DecisionOutcome.COMPLETED_PROPOSAL and raw.proposal is None:
        raise ValueError("completed_proposal without a proposal")
    return raw


class DecisionPlan:
    """Everything checked before a decision slot is taken."""

    def __init__(self, **kw: Any):
        self.__dict__.update(kw)


def plan_decision(engine: Engine, body: dict[str, Any], key: bytes) -> DecisionPlan:
    received = dict(body)  # the body exactly as received, for the request binding
    policy_raw = body.pop("riskPolicy", None)
    execution_raw = body.pop("executionModel", None)
    request = parse_model(DecisionRequest, body)
    policy = resolve_policy(request.risk_policy_id, policy_raw)
    execution = (
        parse_model(ExecutionModel, execution_raw)
        if execution_raw is not None
        else ExecutionModel()
    )
    market = engine.market
    if request.data_mode != market.data_mode:
        raise unprocessable(
            "unsupported_data_mode",
            f"dataMode {request.data_mode.value} is not served by this engine "
            f"({market.data_mode.value})",
        )
    if request.portfolio_state is None:
        raise unprocessable(
            "portfolio_state_required",
            "portfolioState must be supplied inline (hash-verified against portfolioSnapshot)",
        )
    state: PortfolioState = verified_state(
        request.portfolio_state, request.portfolio_snapshot.content_hash
    )
    if request.portfolio_snapshot.version is not None and (
        request.portfolio_snapshot.version != state.version
    ):
        raise conflict(
            "stale_portfolio_version",
            f"portfolioSnapshot.version {request.portfolio_snapshot.version} differs from the "
            f"state version {state.version}",
        )
    if state.strategy_id != request.strategy_id or state.run_id != request.run_id:
        raise unprocessable(
            "portfolio_identity_mismatch",
            "portfolioState belongs to a different strategy or run than the decision",
        )
    if state.blocked_reason:
        raise conflict("portfolio_blocked", f"portfolio blocked: {state.blocked_reason}")
    if request.decision_as_of < state.as_of:
        raise conflict("clock_moved_backward", "decisionAsOf precedes the portfolio state's as_of")
    session = request.market_session_date
    snapshot_id, snapshot_hash = market.market_snapshot_id(session)
    payload = market.market_snapshot_payload(session)
    pointer = request.market_snapshot
    if (
        pointer.id != snapshot_id
        or pointer.content_hash != snapshot_hash
        or pointer.curve_snapshot_id != payload["curveSnapshotId"]
    ):
        raise conflict(
            "market_snapshot_mismatch",
            f"market snapshot {pointer.id} does not match the frozen inputs of session "
            f"{session.isoformat()}",
            extra={"expectedMarketSnapshotId": snapshot_id, "expectedContentHash": snapshot_hash},
        )
    service = engine.strategies
    spec = llm_strategy_spec(request.strategy_id)
    provider = None
    provider_label = None
    index = None
    if spec is not None:
        _, mode, _ = spec
        if request.response_mode not in service.compatible_modes():
            raise unavailable(
                "provider_mode_unavailable",
                f"responseMode {request.response_mode} is not available with the configured "
                f"provider {service.provider_name!r}",
            )
        try:
            provider = service.provider()
        except ProviderUnavailable as exc:
            raise unavailable("model_provider_unavailable", str(exc)) from exc
        provider_label = [getattr(provider, "provider", None), getattr(provider, "model", None)]
        if mode != RetrievalMode.NONE or request.index_build_id or request.evidence_snapshot_id:
            index = engine.evidence.resolve(request.evidence_snapshot_id, request.index_build_id)
        strategy = service.create(
            request.strategy_id,
            provider=provider,
            evidence=engine.evidence_port(index) if mode != RetrievalMode.NONE else None,
            calc_store=engine.calc_store,
            signing_key=key,
        )
    else:
        try:
            strategy = service.create(request.strategy_id)
        except KeyError as exc:
            raise not_found("unknown_strategy", str(exc).strip("'\"")) from exc
        if request.index_build_id or request.evidence_snapshot_id:
            index = engine.evidence.resolve(request.evidence_snapshot_id, request.index_build_id)
    request_hash = request_body_hash(received)
    cache_key = content_hash(
        {
            "request": request_hash,
            "riskPolicy": policy.compute_hash(),
            "executionModel": execution.compute_hash(),
            "provider": provider_label,
            "indexBuild": index.build_id if index is not None else None,
        }
    )
    return DecisionPlan(
        request=request,
        policy=policy,
        execution=execution,
        state=state,
        snapshot_ref=MarketSnapshotRef(
            market_snapshot_id=snapshot_id,
            content_hash=snapshot_hash,
            curve_snapshot_id=payload["curveSnapshotId"],
            session_date=session,
            data_mode=market.data_mode,
        ),
        strategy=strategy,
        provider=provider,
        index=index,
        cache_key=cache_key,
        request_hash=request_hash,
    )


def _bootstrap_targets(engine: Engine, plan: DecisionPlan) -> tuple[TargetWeight, ...]:
    from research_engine.experiments.baselines import BootstrapError, bootstrap_allocation

    state = plan.state
    if state.positions or state.pending_settlements or state.open_orders:
        return ()
    session = plan.request.market_session_date
    try:
        allocation = bootstrap_allocation(engine.pricing.universe(session), session, plan.policy)
    except BootstrapError:
        return ()
    return allocation.targets


def _previous_session(engine: Engine, request: DecisionRequest) -> Any:
    """The run's previous decision session.

    Offline replay passes ``sessions[index - 1]`` of the run's session list (``None`` on
    the first session). The platform sends the same value as ``sessionContext`` (its
    previous frozen cycle); it is authoritative when present. Requests without it
    (older callers) fall back to the market calendar, which can only differ on a run's
    first session.
    """
    if request.session_context is not None:
        return request.session_context.previous_session_date
    session = request.market_session_date
    earlier = engine.market.sessions(session - timedelta(days=14), session - timedelta(days=1))
    return earlier[-1] if earlier else None


def _tools(engine: Engine, plan: DecisionPlan) -> dict[str, Any]:
    tools: dict[str, Any] = {"calc_store": engine.calc_store}
    if plan.index is not None:
        tools["evidence_index_build_id"] = plan.index.build_id
    return tools


def run_decision(engine: Engine, plan: DecisionPlan) -> StrategyResult:
    """Synchronous decision body (decision thread pool)."""
    from research_engine.experiments.strategy import StrategyContext

    request, strategy, market = plan.request, plan.strategy, engine.market
    session = request.market_session_date
    curve = market.curve_for_session(session)
    stale: Optional[str] = None
    if curve is None or str(curve.status).upper() != "READY":
        stale = "no_ready_curve_for_session"
    elif curve.available_at > request.decision_as_of:
        stale = "curve_not_available_by_decision_time"
    else:
        latest = market.latest_available_curve(request.decision_as_of)
        if latest is None or latest.curve_snapshot_id != curve.curve_snapshot_id:
            stale = "latest_available_curve_mismatch"
    if stale is not None:
        return outcome_result(
            request, strategy, DecisionOutcome.SKIPPED_STALE_DATA, [stale], engine.pricing
        )
    context = StrategyContext(
        request=request,
        portfolio_state=plan.state,
        market_snapshot=plan.snapshot_ref,
        universe=tuple(engine.pricing.universe(session)),
        pricing=engine.pricing,
        market=market,
        risk_policy=plan.policy,
        execution_model=plan.execution,
        bootstrap_targets=_bootstrap_targets(engine, plan),
        previous_session=_previous_session(engine, request),
        curve_observed_at=curve.observed_at,
        tools=_tools(engine, plan),
    )
    try:
        return validated(strategy.decide(context), request, strategy)
    except (ValidationError, ValueError) as exc:
        log.warning("decision %s invalid output: %s", request.decision_id, exc)
        return outcome_result(
            request,
            strategy,
            DecisionOutcome.FAILED_INVALID_OUTPUT,
            [f"invalid_output:{type(exc).__name__}"],
            engine.pricing,
            context.input_hashes,
        )
    except Exception as exc:  # isolate one competitor's failure (spec 15.3)
        log.exception("decision %s failed", request.decision_id)
        return outcome_result(
            request,
            strategy,
            DecisionOutcome.FAILED_DEPENDENCY,
            [f"strategy_error:{type(exc).__name__}"],
            engine.pricing,
            context.input_hashes,
        )


@router.post(
    "/decisions",
    summary="Bounded strategy proposal for one strategy/cycle (signed StrategyResult)",
    openapi_extra=contract_body(
        "DecisionRequest",
        "DecisionRequest with portfolioState inline (hash-verified). Optional riskPolicy / "
        "executionModel objects may accompany riskPolicyId; their ids must match.",
    ),
    responses=contract_response("StrategyResult"),
)
async def decisions(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    key = engine.require_signing()
    body = await read_object(request)
    plan = plan_decision(engine, body, key)
    cached = engine.decision_cache.get(plan.cache_key)
    if cached is not None:
        return raw_response(cached)
    if not engine.try_acquire_decision():
        retry = str(engine.settings.decision_retry_after_seconds)
        raise ProblemError(
            429,
            "decision_concurrency_limit",
            f"{engine.max_decisions} decisions are already running; retry later",
            headers={"Retry-After": retry},
        )

    def work() -> bytes:
        try:
            result = sign_result(run_decision(engine, plan), key, plan.request_hash)
            return engine.decision_cache.put(plan.cache_key, dumps(result.to_wire()))
        finally:
            engine.release_decision()

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(engine.decision_executor, work)
    deadline = (
        plan.request.budget.deadline_seconds + engine.settings.decision_deadline_margin_seconds
    )
    try:
        body_bytes = await asyncio.wait_for(asyncio.shield(future), timeout=deadline)
    except asyncio.TimeoutError:
        timed_out = outcome_result(
            plan.request,
            plan.strategy,
            DecisionOutcome.FAILED_BUDGET,
            [f"deadline_exceeded:{plan.request.budget.deadline_seconds}s"],
            engine.pricing,
        )
        body_bytes = engine.decision_cache.put(
            plan.cache_key, dumps(sign_result(timed_out, key, plan.request_hash).to_wire())
        )
    return raw_response(body_bytes)
