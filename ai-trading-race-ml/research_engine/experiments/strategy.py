"""Strategy protocol shared by deterministic baselines and (later) LLM strategies.

A strategy receives a :class:`StrategyContext` - the frozen decision request,
its own frozen portfolio state, the common market snapshot reference, the
eligible universe and read-only tool handles (pricing/market ports) - and
returns a :class:`~research_engine.contracts.decisions.StrategyResult`. It
never executes: the runner submits ``completed_proposal`` outcomes through
``SUBMIT_DECISION`` transitions where sizing and policy are enforced.

Register additional strategies with :func:`register_strategy`; the replay
runner resolves strategy ids through :func:`create_strategy`, which imports
:mod:`research_engine.agents` on demand for ``llm_*`` ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from research_engine import ENGINE_VERSION
from research_engine.contracts.common import content_hash
from research_engine.contracts.decisions import (
    DecisionOutcome,
    DecisionRequest,
    Proposal,
    StrategyKind,
    StrategyResult,
    VersionInfo,
)
from research_engine.contracts.portfolio import (
    DecisionAction,
    ExecutionModel,
    MarketSnapshotRef,
    PortfolioState,
    RiskPolicy,
    TargetWeight,
)
from research_engine.simulation.ledger import Book
from research_engine.simulation.policy import DecisionSnapshot, build_decision_snapshot
from research_engine.simulation.valuation import CurveRef, MarkSource


@dataclass(frozen=True)
class StrategyContext:
    request: DecisionRequest
    portfolio_state: PortfolioState
    market_snapshot: MarketSnapshotRef
    universe: tuple  # InstrumentInfo, eligible at the decision session
    pricing: Any  # PricingPort (read-only tool handle)
    market: Any  # MarketDataPort (read-only tool handle)
    risk_policy: RiskPolicy
    execution_model: ExecutionModel
    bootstrap_targets: tuple[TargetWeight, ...] = ()
    previous_session: Optional[date] = None
    mark_source: Optional[MarkSource] = None
    curve_observed_at: Any = None
    tools: dict = field(default_factory=dict)  # optional extra typed tools (agents, retrieval)

    @property
    def session_date(self) -> date:
        return self.request.market_session_date

    @property
    def request_hash(self) -> str:
        return self.request.compute_hash()

    @property
    def input_hashes(self) -> dict[str, str]:
        return {
            "decisionRequest": self.request_hash,
            "portfolioState": self.portfolio_state.compute_hash(),
            "marketSnapshot": self.market_snapshot.content_hash,
            "riskPolicy": self.risk_policy.compute_hash(),
        }

    def initialized(self) -> bool:
        state = self.portfolio_state
        return bool(state.positions or state.pending_settlements or state.open_orders)

    @cached_property
    def snapshot(self) -> DecisionSnapshot:
        """Decision snapshot computed exactly as the policy gate computes it."""
        curve = CurveRef(
            self.market_snapshot.curve_snapshot_id,
            self.market_snapshot.session_date,
            self.curve_observed_at,
        )
        return build_decision_snapshot(
            Book.from_state(self.portfolio_state),
            self.pricing,
            curve=curve,
            decision_time=self.request.decision_as_of,
            data_mode=self.market_snapshot.data_mode,
            policy=self.risk_policy,
            mark_source=self.mark_source,
        )


@runtime_checkable
class Strategy(Protocol):
    strategy_id: str
    kind: StrategyKind
    invested: bool  # participates in the common bootstrap
    deterministic: bool  # recorded and fresh modes produce identical output
    config: dict

    def decide(self, ctx: StrategyContext) -> StrategyResult: ...


def config_hash(config: dict) -> str:
    return content_hash(config, allow_floats=True)


def make_result(
    ctx: StrategyContext,
    strategy: Strategy,
    outcome: DecisionOutcome,
    *,
    action: Optional[DecisionAction] = None,
    targets: Optional[list[TargetWeight]] = None,
    reasons: Optional[list[str]] = None,
    calculation_ids: Optional[list[str]] = None,
    versions: Optional[VersionInfo] = None,
) -> StrategyResult:
    proposal = None
    if action is not None:
        proposal = Proposal(
            action=action,
            target_weights=targets or [],
            supporting_calculation_ids=calculation_ids or [],
        )
    return StrategyResult(
        run_id=ctx.request.run_id,
        cycle_id=ctx.request.cycle_id,
        decision_id=ctx.request.decision_id,
        strategy_id=strategy.strategy_id,
        strategy_kind=strategy.kind,
        repetition=ctx.request.repetition,
        request_hash=ctx.request_hash,
        input_hashes=ctx.input_hashes,
        outcome=outcome,
        completed_at=ctx.request.decision_as_of,  # simulation time: deterministic
        reasons=reasons or [],
        proposal=proposal,
        versions=versions
        or VersionInfo(
            engine_version=ENGINE_VERSION, strategy_config_hash=config_hash(strategy.config)
        ),
    )


StrategyFactory = Callable[[dict], Strategy]
STRATEGY_REGISTRY: dict[str, StrategyFactory] = {}


def register_strategy(strategy_id: str, factory: StrategyFactory) -> None:
    """Register a strategy factory (``factory(config) -> Strategy``)."""
    STRATEGY_REGISTRY[strategy_id] = factory


def create_strategy(strategy_id: str, config: Optional[dict] = None) -> Strategy:
    if strategy_id not in STRATEGY_REGISTRY:
        # Baselines register on import.
        from . import baselines  # noqa: F401
    if strategy_id not in STRATEGY_REGISTRY and strategy_id.startswith("llm_"):
        # AI strategies register when research_engine.agents is imported; import it
        # lazily so the deterministic baselines never pull in the agent stack.
        import research_engine.agents  # noqa: F401
    try:
        factory = STRATEGY_REGISTRY[strategy_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown strategy {strategy_id!r}; registered: {sorted(STRATEGY_REGISTRY)}"
        ) from exc
    return factory(dict(config or {}))
