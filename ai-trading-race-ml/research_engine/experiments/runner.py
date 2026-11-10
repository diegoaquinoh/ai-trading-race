"""Offline daily replay (spec 15.1, 15.4).

Cycle order for each supported session ``D`` (schedule ``schedule-ny-v1``):

1. ``PROCESS_EVENTS`` per portfolio up to D 19:00 New York (settlements,
   coupons, redemptions, fills at D's observation, expiries);
2. shared-input check: without a READY curve available by decision time every
   competitor records ``skipped_stale_data`` (matched skip);
3. freeze one common market snapshot and one own-portfolio snapshot each;
4. run strategies in deterministic (sorted strategy id) order;
5. persist every outcome (``outcomes.jsonl``) before any financial commit;
6. ``SUBMIT_DECISION`` for ``completed_proposal`` outcomes;
7. ``VALUE_PORTFOLIO`` per portfolio at D 20:00;
8. checkpoint (event position = committed transition count, portfolio
   versions/hashes, pending orders/settlements, manifest/config references).

Every financial effect is a command with a deterministic id
(``cmd:<run>:<strategy>:<session>:<step>``) committed through
:class:`OfflineStateStore`; on resume, committed commands are skipped and
persisted outcomes are reused, so an interrupted run never duplicates trades,
settlements, coupons or redemptions.

Response modes (spec 6.5 - recorded-response replay and fresh-inference reruns
are separate modes), recorded in the manifest as ``responseMode`` plus
``responseSource`` and a per-strategy ``responseSource``:

* ``recorded_replay`` + ``replay_source="stored_results"`` (default): AI
  strategies are not called; their persisted StrategyResults are re-validated
  and reused (result-level replay).
* ``recorded_replay`` + ``replay_source="recorded_responses"``: AI strategies
  run their full workflow, but every provider must be a replay-only provider
  (``provider.replay``: recorded model responses, no provider access); tools,
  retrieval, validation and policy are recomputed (provider-level replay).
* ``fresh_inference``: strategies call their configured provider; a replay-only
  provider is rejected so a replay is never labelled fresh inference.

Deterministic baselines are computed in every mode.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import Field, ValidationError, model_serializer, model_validator

from research_engine.contracts.common import (
    ContractModel,
    DecimalStr,
    InformationPolicy,
    OpaqueId,
    StrategyId,
    content_hash,
)
from research_engine.contracts.decisions import (
    DecisionOutcome,
    DecisionRequest,
    MarketSnapshotPointer,
    SnapshotRef,
    StrategyKind,
    StrategyResult,
    VersionInfo,
)
from research_engine.contracts.portfolio import (
    CommandType,
    DecisionAction,
    ExecutionModel,
    MarketSnapshotRef,
    OrderStatus,
    PortfolioState,
    RiskPolicy,
    TargetWeight,
)
from research_engine.simulation.clock import (
    CAPITAL_TIME,
    decision_at,
    make_id,
    ny_instant,
    valuation_at,
)
from research_engine.simulation.engine import (
    TransitionError,
    build_request,
    engine_version,
    propose_transition,
)
from research_engine.simulation.fills import cost_profiles
from research_engine.simulation.store import OfflineStateStore

from .baselines import BOOTSTRAP_ALLOCATION_VERSION, BootstrapError, bootstrap_allocation
from .manifest import (
    CurveManifestEntry,
    ExperimentManifest,
    StrategyManifestEntry,
    ArtifactRef,
    amend_manifest,
    dependency_lock_hashes,
    file_checksum,
    finalize_manifest,
    git_commit,
)
from .strategy import Strategy, StrategyContext, config_hash, create_strategy

CHECKPOINT_VERSION = "checkpoint-v1"
NON_DETERMINISTIC_KINDS = (StrategyKind.SINGLE_AGENT, StrategyKind.SPECIALIST_TEAM)
ReplaySource = Literal["stored_results", "recorded_responses"]
RESPONSE_SOURCES = {
    "stored_results": "stored_strategy_results",
    "recorded_responses": "recorded_provider_responses",
    "fresh_inference": "fresh_provider_calls",
}


class ResponseModeError(ValueError):
    """A strategy's provider does not match the configured response mode."""


class StrategySpec(ContractModel):
    strategy_id: StrategyId
    config: dict[str, Any] = Field(default_factory=dict)


class ReplayConfig(ContractModel):
    config_version: str = "replay-config-v1"
    experiment_id: OpaqueId
    run_id: OpaqueId
    start_date: date
    end_date: date
    strategies: list[StrategySpec]
    risk_policy: RiskPolicy = Field(default_factory=RiskPolicy)
    execution_model: ExecutionModel = Field(default_factory=ExecutionModel)
    # Must equal the market port's universe contract version (validated by the runner).
    instrument_universe_version: OpaqueId = "synthetic_universe_v1.0"
    information_policy: InformationPolicy = InformationPolicy.RECONSTRUCTED_PUBLICATION_PLUS_LAG
    response_mode: Literal["recorded_replay", "fresh_inference"] = "recorded_replay"
    # Level of a recorded replay: ``stored_results`` reuses persisted StrategyResults,
    # ``recorded_responses`` re-runs strategies on replay-only providers. ``None``
    # means ``stored_results`` and is omitted from the wire form, so configs written
    # before this field existed keep their hashes.
    replay_source: Optional[ReplaySource] = None
    repetition: int = 0
    seed: int = 0
    initial_capital_usd: DecimalStr = Decimal("1000000")
    splits: dict[str, Any] = Field(default_factory=dict)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    calendar_version: str = "us-gov-calendar-v1"
    convention_version: str = "conventions-v1"
    signing_key_id: str = "offline-research"

    @model_validator(mode="after")
    def _replay_source_needs_recorded_mode(self) -> "ReplayConfig":
        if self.response_mode == "fresh_inference" and self.replay_source is not None:
            raise ValueError("replay_source applies only to response_mode recorded_replay")
        return self

    @model_serializer(mode="wrap")
    def _omit_default_replay_source(self, handler):
        data = handler(self)
        if self.replay_source is None and isinstance(data, dict):
            data.pop("replaySource", None)
            data.pop("replay_source", None)
        return data

    @property
    def effective_replay_source(self) -> Optional[str]:
        if self.response_mode != "recorded_replay":
            return None
        return self.replay_source or "stored_results"

    @property
    def response_source(self) -> str:
        return RESPONSE_SOURCES[self.effective_replay_source or self.response_mode]


def strategy_response_source(strategy, config: ReplayConfig) -> str:
    """Where a strategy's outputs come from under ``config`` (manifest label)."""
    provider = getattr(strategy, "provider", None)
    if strategy.kind not in NON_DETERMINISTIC_KINDS and strategy.deterministic and provider is None:
        return "deterministic_code"
    label = (
        f"{getattr(provider, 'provider', 'unknown')}/{getattr(provider, 'model', 'unknown')}"
        if provider is not None
        else "unknown"
    )
    source = config.effective_replay_source
    if source == "stored_results":
        return "stored_strategy_result"
    if source == "recorded_responses":
        return f"recorded_responses:{label}"
    suffix = ":captured" if getattr(provider, "capturing", False) else ""
    return f"provider_call:{label}{suffix}"


def check_response_mode(strategies: dict, config: ReplayConfig) -> None:
    """Refuse provider/mode combinations that would mislabel a run (spec 6.5)."""
    for sid, strategy in sorted(strategies.items()):
        if strategy.kind not in NON_DETERMINISTIC_KINDS and strategy.deterministic:
            continue
        provider = getattr(strategy, "provider", None)
        replay = bool(getattr(provider, "replay", False))
        source = config.effective_replay_source
        if source == "recorded_responses" and not replay:
            raise ResponseModeError(
                f"{sid}: recorded-response replay needs a replay-only provider "
                "(recorded responses, no provider access)"
            )
        if config.response_mode == "fresh_inference" and replay:
            raise ResponseModeError(
                f"{sid}: a replay-only provider cannot run as fresh_inference; use "
                "response_mode=recorded_replay with replay_source=recorded_responses"
            )


class ReplayInterrupted(RuntimeError):
    """Raised by test/operator interrupt hooks to simulate a worker crash."""


@dataclass
class ReplayResult:
    status: str
    run_dir: Path
    cycles_completed: int
    final_states: dict[str, PortfolioState]
    manifest: ExperimentManifest
    failures: list[str] = field(default_factory=list)


def portfolio_id(run_id: str, strategy_id: str) -> str:
    return make_id("pf", run_id, strategy_id)


class ReplayRunner:
    CONFIG = "config.json"
    COMMITS = "commits.jsonl"
    OUTCOMES = "outcomes.jsonl"
    CHECKPOINT = "checkpoint.json"
    MANIFEST = "manifest.json"

    def __init__(
        self,
        config: ReplayConfig,
        pricing,
        market,
        run_dir: Path,
        signing_key: bytes,
        *,
        strategies: Optional[dict[str, Strategy]] = None,
        recorded_outcomes: Optional[dict[str, StrategyResult]] = None,
        mark_source=None,
        interrupt: Optional[Callable[[str], None]] = None,
        project_root: Optional[Path] = None,
        generated_at=None,
    ) -> None:
        self.config = config
        engine_universe = getattr(getattr(market, "universe_contract", None), "version", None)
        if engine_universe is not None and engine_universe != config.instrument_universe_version:
            raise ValueError(
                f"experiment universe {config.instrument_universe_version!r} differs from the "
                f"engine universe {engine_universe!r}"
            )
        self.pricing = pricing
        self.market = market
        self.run_dir = Path(run_dir)
        self.key = signing_key
        self.mark_source = mark_source
        self.interrupt = interrupt
        self.recorded = dict(recorded_outcomes or {})
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.generated_at = generated_at
        self.strategies: dict[str, Strategy] = {}
        for spec in sorted(config.strategies, key=lambda s: s.strategy_id):
            if strategies and spec.strategy_id in strategies:
                self.strategies[spec.strategy_id] = strategies[spec.strategy_id]
            else:
                self.strategies[spec.strategy_id] = create_strategy(spec.strategy_id, spec.config)
        check_response_mode(self.strategies, config)
        self.sessions = market.sessions(config.start_date, config.end_date)
        self.store: Optional[OfflineStateStore] = None
        self.outcomes: dict[str, StrategyResult] = {}
        self.failures: list[str] = []
        self.exclusions: list[str] = []
        self.bootstrap: dict[str, Any] = {}
        self.manifest: Optional[ExperimentManifest] = None

    # ------------------------------------------------------------------ paths

    def _path(self, name: str) -> Path:
        return self.run_dir / name

    def _write_json(self, name: str, payload: Any) -> None:
        tmp = self._path(name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self._path(name))

    # ------------------------------------------------------------------ entry points

    def run(self) -> ReplayResult:
        if self._path(self.CHECKPOINT).exists() or self._path(self.COMMITS).exists():
            raise RuntimeError(f"{self.run_dir} already contains a run; use resume()")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.CONFIG, self.config.to_wire())
        self.manifest = self._initial_manifest()
        self._write_json(self.MANIFEST, self.manifest.to_wire())
        return self._execute(start_index=0)

    def resume(self) -> ReplayResult:
        stored = ReplayConfig.model_validate_json(self._path(self.CONFIG).read_text())
        if stored.compute_hash() != self.config.compute_hash():
            raise RuntimeError("resume configuration differs from the recorded run")
        self.manifest = ExperimentManifest.model_validate_json(
            self._path(self.MANIFEST).read_text()
        )
        start = 0
        if self._path(self.CHECKPOINT).exists():
            checkpoint = json.loads(self._path(self.CHECKPOINT).read_text())
            self.failures = list(checkpoint.get("failures", []))
            self.exclusions = list(checkpoint.get("exclusions", []))
            self.bootstrap = dict(checkpoint.get("bootstrap", {}))
            if checkpoint["status"] in ("completed", "failed"):
                self._open_store()
                if self.manifest.finalized:
                    return self._result(checkpoint["status"], checkpoint["cycleIndex"] + 1)
                return self._finish(checkpoint["status"], checkpoint["cycleIndex"])
            start = checkpoint["cycleIndex"] + 1
        return self._execute(start_index=start)

    # ------------------------------------------------------------------ core loop

    def _open_store(self) -> None:
        self.store = OfflineStateStore(self.key, self._path(self.COMMITS))
        self.outcomes = {}
        if self._path(self.OUTCOMES).exists():
            for line in self._path(self.OUTCOMES).read_text().splitlines():
                if line.strip():
                    record = json.loads(line)
                    self.outcomes[record["decisionId"]] = StrategyResult.model_validate(
                        record["result"]
                    )

    def _execute(self, start_index: int) -> ReplayResult:
        self._open_store()
        if not self.sessions:
            raise RuntimeError("no supported sessions in the replay window")
        self._initialize_portfolios()
        status = "completed"
        index = start_index - 1
        for index in range(start_index, len(self.sessions)):
            ok = self._cycle(index, self.sessions[index])
            self._checkpoint(index, "running" if ok else "failed")
            if not ok:
                status = "failed"
                break
        return self._finish(status, index)

    def _pid(self, strategy_id: str) -> str:
        return portfolio_id(self.config.run_id, strategy_id)

    def _initialize_portfolios(self) -> None:
        first = self.sessions[0]
        for sid in self.strategies:
            pid = self._pid(sid)
            if pid not in self.store.portfolios():
                self.store.register(
                    PortfolioState(
                        portfolio_id=pid,
                        strategy_id=sid,
                        run_id=self.config.run_id,
                        version=0,
                        as_of=ny_instant(first, time(0, 0)),
                        cash_usd=Decimal("0"),
                    )
                )
            self._command(
                sid,
                "init:capital",
                CommandType.CAPITAL_FLOW,
                ny_instant(first, CAPITAL_TIME),
                label=f"init:{sid}",
                capital_amount_usd=self.config.initial_capital_usd,
            )

    def _command(self, strategy_id: str, step: str, command_type, advance_to, *, label, **kwargs):
        command_id = make_id("cmd", self.config.run_id, strategy_id, step)
        if self.store.has_command(command_id):
            return self.store.result(command_id).proposal
        state = self.store.state(self._pid(strategy_id))
        request = build_request(
            state,
            command_id=command_id,
            command_type=command_type,
            advance_to=advance_to,
            instrument_universe_version=self.config.instrument_universe_version,
            risk_policy=self.config.risk_policy,
            execution_model=self.config.execution_model,
            **kwargs,
        )
        proposal = propose_transition(
            request, self.pricing, self.market, self.key, mark_source=self.mark_source
        )
        self.store.commit(proposal, request)
        if self.interrupt is not None:
            self.interrupt(f"{label}:{command_type.value}")
        return proposal

    def _market_snapshot(self, session: date):
        curve = self.market.curve_for_session(session)
        decided = decision_at(session)
        if curve is None or str(curve.status).upper() != "READY":
            return None, curve, "no_ready_curve_for_session"
        if curve.available_at > decided:
            return None, curve, "curve_not_available_by_decision_time"
        latest = self.market.latest_available_curve(decided)
        if latest is None or latest.curve_snapshot_id != curve.curve_snapshot_id:
            return None, curve, "latest_available_curve_mismatch"
        snapshot_id, snapshot_hash = self.market.market_snapshot_id(session)
        ref = MarketSnapshotRef(
            market_snapshot_id=snapshot_id,
            content_hash=snapshot_hash,
            curve_snapshot_id=curve.curve_snapshot_id,
            session_date=session,
            data_mode=self.market.data_mode,
        )
        return ref, curve, None

    def _cycle(self, index: int, session: date) -> bool:
        decided = decision_at(session)
        session_key = session.isoformat()
        for sid in self.strategies:
            self._command(
                sid,
                f"{session_key}:process",
                CommandType.PROCESS_EVENTS,
                decided,
                label=f"{session_key}:{sid}",
            )
        if not self._check_bootstrap():
            return False
        snapshot, curve, stale_reason = self._market_snapshot(session)
        previous = self.sessions[index - 1] if index > 0 else None
        if snapshot is not None and not self.bootstrap.get("targets"):
            try:
                allocation = bootstrap_allocation(
                    self.pricing.universe(session), session, self.config.risk_policy
                )
                self.bootstrap = {
                    "version": allocation.version,
                    "session": session_key,
                    "targets": [t.to_wire() for t in allocation.targets],
                    "buckets": allocation.buckets,
                    "checked": False,
                }
            except BootstrapError as exc:
                self.failures.append(f"initialization_failed:{exc}")
                for sid in self.strategies:
                    self._decide(sid, session, None, curve, previous, failure=str(exc))
                return False
        if snapshot is None:
            self.exclusions.append(f"{session_key}:skipped_stale_data:{stale_reason}")
        proposals: list[tuple[str, StrategyResult]] = []
        for sid in self.strategies:
            result = self._decide(sid, session, snapshot, curve, previous, stale=stale_reason)
            if (
                result.outcome == DecisionOutcome.COMPLETED_PROPOSAL
                and result.proposal is not None
                and result.proposal.action != DecisionAction.HOLD
            ):
                proposals.append((sid, result))
        for sid, result in proposals:
            try:
                proposal = self._command(
                    sid,
                    f"{session_key}:decision",
                    CommandType.SUBMIT_DECISION,
                    decided,
                    label=f"{session_key}:{sid}",
                    market_snapshot=snapshot,
                    decision_id=result.decision_id,
                    action=result.proposal.action,
                    target_weights=result.proposal.target_weights,
                )
            except TransitionError as exc:
                self.failures.append(f"{session_key}:{sid}:submit_failed:{exc}")
                continue
            evaluation = proposal.policy_evaluation
            if result.proposal.action == DecisionAction.BOOTSTRAP:
                if evaluation is None or not evaluation.passed:
                    reasons = evaluation.rejected_reasons if evaluation else ["no_evaluation"]
                    self.failures.append(
                        f"initialization_failed:{sid}:bootstrap_rejected:{';'.join(reasons)}"
                    )
                    return False
                self.bootstrap.setdefault("submitted", {})[sid] = [
                    o.order_id for o in proposal.orders_created
                ]
        for sid in self.strategies:
            try:
                self._command(
                    sid,
                    f"{session_key}:value",
                    CommandType.VALUE_PORTFOLIO,
                    valuation_at(session),
                    label=f"{session_key}:{sid}",
                    market_snapshot=snapshot,
                )
            except TransitionError as exc:
                self.failures.append(f"{session_key}:{sid}:valuation_deferred:{exc}")
        return True

    # ------------------------------------------------------------------ decisions

    def _decision_id(self, strategy_id: str, session: date) -> str:
        return make_id(
            "dec",
            self.config.run_id,
            strategy_id,
            session.isoformat(),
            f"r{self.config.repetition}",
        )

    def _persist_outcome(self, result: StrategyResult) -> None:
        self.outcomes[result.decision_id] = result
        with self._path(self.OUTCOMES).open("a", encoding="utf-8") as handle:
            record = {"decisionId": result.decision_id, "result": result.to_wire()}
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    def _decision_request(self, sid, session, snapshot, curve) -> DecisionRequest:
        state = self.store.state(self._pid(sid))
        strategy = self.strategies[sid]
        pointer_hash = snapshot.content_hash if snapshot else content_hash({"missing": session})
        curve_id = curve.curve_snapshot_id if curve is not None else "none"
        return DecisionRequest(
            experiment_id=self.config.experiment_id,
            run_id=self.config.run_id,
            cycle_id=make_id("cycle", session.isoformat()),
            decision_id=self._decision_id(sid, session),
            strategy_id=sid,
            repetition=self.config.repetition,
            decision_as_of=decision_at(session),
            market_session_date=session,
            availability_policy=self.config.information_policy.value,
            data_mode=self.market.data_mode,
            portfolio_snapshot=SnapshotRef(
                id=make_id("pfs", state.portfolio_id, f"v{state.version}"),
                content_hash=state.compute_hash(),
                version=state.version,
            ),
            market_snapshot=MarketSnapshotPointer(
                id=snapshot.market_snapshot_id if snapshot else make_id("mkt-missing", session),
                content_hash=pointer_hash,
                curve_snapshot_id=curve_id,
            ),
            instrument_universe_version=self.config.instrument_universe_version,
            strategy_config_id=make_id(sid, config_hash(strategy.config)[7:23]),
            risk_policy_id=self.config.risk_policy.policy_id,
            response_mode=self.config.response_mode,
            portfolio_state=state.to_wire(),
        )

    def _skip_result(self, request, strategy, outcome, reasons) -> StrategyResult:
        return StrategyResult(
            run_id=request.run_id,
            cycle_id=request.cycle_id,
            decision_id=request.decision_id,
            strategy_id=strategy.strategy_id,
            strategy_kind=strategy.kind,
            repetition=request.repetition,
            request_hash=request.compute_hash(),
            input_hashes={"decisionRequest": request.compute_hash()},
            outcome=outcome,
            completed_at=request.decision_as_of,
            reasons=reasons,
            versions=VersionInfo(engine_version=engine_version(self.pricing)),
        )

    def _decide(self, sid, session, snapshot, curve, previous, stale=None, failure=None):
        decision_id = self._decision_id(sid, session)
        if decision_id in self.outcomes:
            return self.outcomes[decision_id]
        strategy = self.strategies[sid]
        request = self._decision_request(sid, session, snapshot, curve)
        if failure is not None:
            result = self._skip_result(
                request,
                strategy,
                DecisionOutcome.FAILED_DEPENDENCY,
                [f"bootstrap_failed:{failure}"],
            )
        elif snapshot is None:
            result = self._skip_result(
                request, strategy, DecisionOutcome.SKIPPED_STALE_DATA, [stale or "stale_data"]
            )
        elif self.config.effective_replay_source == "stored_results" and (
            strategy.kind in NON_DETERMINISTIC_KINDS or not strategy.deterministic
        ):
            recorded = self.recorded.get(decision_id)
            if recorded is None:
                result = self._skip_result(
                    request,
                    strategy,
                    DecisionOutcome.FAILED_DEPENDENCY,
                    ["recorded_response_missing"],
                )
            else:
                result = self._validated(recorded, request, strategy)
        else:
            context = StrategyContext(
                request=request,
                portfolio_state=self.store.state(self._pid(sid)),
                market_snapshot=snapshot,
                universe=tuple(self.pricing.universe(session)),
                pricing=self.pricing,
                market=self.market,
                risk_policy=self.config.risk_policy,
                execution_model=self.config.execution_model,
                bootstrap_targets=tuple(
                    TargetWeight.model_validate(t) for t in self.bootstrap.get("targets", [])
                ),
                previous_session=previous,
                mark_source=self.mark_source,
                curve_observed_at=curve.observed_at if curve is not None else None,
            )
            try:
                raw = strategy.decide(context)
                result = self._validated(raw, request, strategy)
            except (ValidationError, ValueError) as exc:
                result = self._skip_result(
                    request,
                    strategy,
                    DecisionOutcome.FAILED_INVALID_OUTPUT,
                    [f"invalid_output:{type(exc).__name__}"],
                )
            except Exception as exc:  # isolate one competitor's failure
                result = self._skip_result(
                    request,
                    strategy,
                    DecisionOutcome.FAILED_DEPENDENCY,
                    [f"strategy_error:{type(exc).__name__}"],
                )
        self._persist_outcome(result)
        return result

    def _validated(self, raw, request, strategy) -> StrategyResult:
        if not isinstance(raw, StrategyResult):
            raw = StrategyResult.model_validate(raw)
        else:  # re-validate in case the object was built without validation
            raw = StrategyResult.model_validate(raw.model_dump())
        if raw.decision_id != request.decision_id or raw.strategy_id != strategy.strategy_id:
            raise ValueError("strategy result identity does not match the decision request")
        if raw.outcome == DecisionOutcome.COMPLETED_PROPOSAL and raw.proposal is None:
            raise ValueError("completed_proposal without a proposal")
        return raw

    # ------------------------------------------------------------------ bootstrap

    def _check_bootstrap(self) -> bool:
        submitted = self.bootstrap.get("submitted")
        if not submitted or self.bootstrap.get("checked"):
            return True
        invested = sorted(s for s, strat in self.strategies.items() if strat.invested)
        statuses: dict[str, dict[str, str]] = {}
        fills: dict[str, list] = {}
        for sid in invested:
            if sid not in submitted:
                self.failures.append(f"initialization_failed:{sid}:no_bootstrap_orders")
                return False
            state = self.store.state(self._pid(sid))
            if any(o.order_id in submitted[sid] for o in state.open_orders):
                return True  # still pending; check again next cycle
            statuses[sid] = {}
            fills[sid] = []
            for proposal in self.store.committed(self._pid(sid)):
                for change in proposal.order_status_changes:
                    if change.order_id in submitted[sid]:
                        statuses[sid][change.order_id] = change.status.value
                for fill in proposal.fills:
                    if fill.order_id in submitted[sid]:
                        fills[sid].append(
                            (fill.security_id, fill.face, fill.execution_clean_price_per_100)
                        )
        for sid in invested:
            bad = {k: v for k, v in statuses[sid].items() if v != OrderStatus.FILLED.value}
            if bad or len(statuses[sid]) != len(submitted[sid]):
                self.failures.append(f"initialization_failed:{sid}:bootstrap_not_filled:{bad}")
                return False
        reference = sorted(fills[invested[0]]) if invested else []
        for sid in invested[1:]:
            if sorted(fills[sid]) != reference:
                self.failures.append("initialization_failed:bootstrap_fills_differ")
                return False
        self.bootstrap["checked"] = True
        return True

    # ------------------------------------------------------------------ checkpoint / manifest

    def _checkpoint(self, index: int, status: str) -> None:
        portfolios = {}
        pending = {}
        for sid in self.strategies:
            state = self.store.state(self._pid(sid))
            portfolios[state.portfolio_id] = {
                "version": state.version,
                "stateHash": state.compute_hash(),
            }
            pending[state.portfolio_id] = {
                "openOrders": [o.order_id for o in state.open_orders],
                "pendingSettlements": [s.settlement_id for s in state.pending_settlements],
            }
        self._write_json(
            self.CHECKPOINT,
            {
                "checkpointVersion": CHECKPOINT_VERSION,
                "cycleIndex": index,
                "sessionDate": self.sessions[index].isoformat(),
                "eventPosition": len(self.store.committed()),
                "portfolios": portfolios,
                "pendingEvents": pending,
                "outcomeCount": len(self.outcomes),
                "configHash": self.config.compute_hash(),
                "manifestRef": self.MANIFEST,
                "bootstrap": self.bootstrap,
                "failures": self.failures,
                "exclusions": self.exclusions,
                "status": status,
            },
        )

    def _strategy_entries(self) -> list[StrategyManifestEntry]:
        entries = []
        for sid, strategy in self.strategies.items():
            entries.append(
                StrategyManifestEntry(
                    strategy_id=sid,
                    kind=strategy.kind.value,
                    invested=strategy.invested,
                    deterministic=strategy.deterministic,
                    config=strategy.config,
                    config_hash=config_hash(strategy.config),
                    provider=strategy.config.get("provider"),
                    model_id=strategy.config.get("modelId"),
                    prompt_version=strategy.config.get("promptVersion"),
                    tool_schema_version=strategy.config.get("toolSchemaVersion"),
                    retrieval_mode=strategy.config.get("retrievalMode", "none"),
                    index_build_id=strategy.config.get("indexBuildId"),
                    evidence_snapshot_id=strategy.config.get("evidenceSnapshotId"),
                    response_source=strategy_response_source(strategy, self.config),
                )
            )
        return entries

    def _initial_manifest(self) -> ExperimentManifest:
        config = self.config
        lag = {
            info.security_id: str(info.settlement_lag_business_days)
            for info in self.pricing.universe(
                self.sessions[0] if self.sessions else config.start_date
            )
        }
        repo_root = self.project_root.parent
        return ExperimentManifest(
            experiment_id=config.experiment_id,
            run_id=config.run_id,
            status="running",
            git_commit=git_commit(repo_root),
            config_hash=config.compute_hash(),
            dependency_lock_hashes=dependency_lock_hashes(self.project_root),
            engine_version=engine_version(self.pricing),
            pricing_engine_version=self.pricing.engine_version,
            data_mode=self.market.data_mode,
            universe_version=config.instrument_universe_version,
            terms_versions={
                i.security_id: i.terms_version
                for i in self.pricing.universe(
                    self.sessions[0] if self.sessions else config.start_date
                )
            },
            calendar_version=config.calendar_version,
            convention_version=config.convention_version,
            start_date=config.start_date,
            end_date=config.end_date,
            decision_sessions=list(self.sessions),
            information_policy=config.information_policy.value,
            execution_model=config.execution_model,
            cost_sensitivity_profiles=[
                p.execution_model_id for p in cost_profiles(config.execution_model)
            ],
            settlement_config={"rule": "T+lag business days", **lag},
            risk_policy=config.risk_policy,
            cash_return_assumption=(
                "zero_cash_interest_v1"
                if config.execution_model.cash_interest_rate == 0
                else f"flat_cash_rate_act360:{config.execution_model.cash_interest_rate}"
            ),
            strategies=self._strategy_entries(),
            response_mode=config.response_mode,
            response_source=config.response_source,
            splits=config.splits,
            seeds={"replay": config.seed},
            repetitions=[config.repetition],
            resource_limits=config.resource_limits,
            generated_at=self.generated_at,
        )

    def _finish(self, status: str, last_index: int) -> ReplayResult:
        if last_index >= 0:
            self._checkpoint(last_index, status)
        curves = []
        for session in self.sessions:
            curve = self.market.curve_for_session(session)
            curves.append(
                CurveManifestEntry(
                    session_date=session,
                    curve_snapshot_id=curve.curve_snapshot_id if curve else None,
                    content_hash=curve.content_hash if curve else None,
                    status=str(curve.status) if curve else "MISSING",
                )
            )
        outcome_counts: dict[str, int] = {}
        for result in self.outcomes.values():
            outcome_counts[result.outcome.value] = outcome_counts.get(result.outcome.value, 0) + 1
        artifacts = [
            ArtifactRef(path=name, checksum=file_checksum(self._path(name)), role=role)
            for name, role in ((self.COMMITS, "ledger_log"), (self.OUTCOMES, "decision_outcomes"))
            if self._path(name).exists()
        ]
        manifest = self.manifest
        if not manifest.finalized:
            manifest = finalize_manifest(
                amend_manifest(manifest),
                status=status,
                curve_manifests=curves,
                bootstrap_allocation_version=(
                    BOOTSTRAP_ALLOCATION_VERSION if self.bootstrap.get("targets") else None
                ),
                bootstrap_allocation=[
                    TargetWeight.model_validate(t) for t in self.bootstrap.get("targets", [])
                ],
                realized_usage={
                    "transitionsCommitted": len(self.store.committed()),
                    "decisions": len(self.outcomes),
                    "outcomes": outcome_counts,
                    "cyclesCompleted": last_index + 1,
                },
                failures=list(self.failures),
                exclusions=list(self.exclusions),
                artifacts=artifacts,
            )
            self._write_json(self.MANIFEST, manifest.to_wire())
        self.manifest = manifest
        return self._result(status, last_index + 1)

    def _result(self, status: str, cycles: int) -> ReplayResult:
        return ReplayResult(
            status=status,
            run_dir=self.run_dir,
            cycles_completed=cycles,
            final_states={sid: self.store.state(self._pid(sid)) for sid in self.strategies},
            manifest=self.manifest,
            failures=list(self.failures),
        )


def run_replay(config: ReplayConfig, pricing, market, run_dir: Path, signing_key: bytes, **kwargs):
    """Start a new replay in ``run_dir``."""
    return ReplayRunner(config, pricing, market, run_dir, signing_key, **kwargs).run()


def resume_replay(
    config: ReplayConfig, pricing, market, run_dir: Path, signing_key: bytes, **kwargs
):
    """Resume a replay from its last checkpoint without duplicating effects."""
    return ReplayRunner(config, pricing, market, run_dir, signing_key, **kwargs).resume()
