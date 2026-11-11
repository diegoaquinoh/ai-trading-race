"""Shared agent fixtures: real offline numerical ports and captured decision contexts.

Contexts come from a short real replay (bootstrap 2023-06-12, fills 2023-06-13)
with a probe strategy that records the exact :class:`StrategyContext` the
runner builds. No network, no API keys.
"""

from __future__ import annotations

import dataclasses
import tempfile
from datetime import date
from pathlib import Path

import pytest

from research_engine.contracts.decisions import DecisionOutcome, StrategyKind
from research_engine.contracts.portfolio import DecisionAction
from research_engine.experiments.runner import ReplayConfig, ReplayRunner, StrategySpec
from research_engine.experiments.strategy import make_result
from research_engine.market.store import load_default_market
from research_engine.simulation.clock import make_id

SESSION = date(2023, 6, 14)
START = date(2023, 6, 12)
KEY = b"agent-test-transition-key"
RESULT_KEY = b"agent-test-result-key"


@pytest.fixture(scope="session")
def ports():
    return load_default_market(date(2023, 3, 1), date(2023, 7, 31))


class _Probe:
    strategy_id = "llm_rag"
    kind = StrategyKind.QUANT_POLICY
    invested = True
    deterministic = True
    config = {"version": "probe-v1"}

    def __init__(self):
        self.contexts = {}

    def decide(self, ctx):
        self.contexts[ctx.session_date] = ctx
        if not ctx.initialized():
            return make_result(
                ctx,
                self,
                DecisionOutcome.COMPLETED_PROPOSAL,
                action=DecisionAction.BOOTSTRAP,
                targets=list(ctx.bootstrap_targets),
            )
        return make_result(ctx, self, DecisionOutcome.COMPLETED_HOLD, action=DecisionAction.HOLD)


@pytest.fixture(scope="session")
def contexts(ports):
    pricing, market = ports
    probe = _Probe()
    config = ReplayConfig(
        experiment_id="agents-test",
        run_id="agents-test-r0",
        start_date=START,
        end_date=SESSION,
        strategies=[StrategySpec(strategy_id="llm_rag")],
        response_mode="fresh_inference",
    )
    with tempfile.TemporaryDirectory() as tmp:
        ReplayRunner(
            config, pricing, market, Path(tmp) / "run", KEY, strategies={"llm_rag": probe}
        ).run()
    return probe.contexts


def context_for(contexts, strategy_id: str, session: date = SESSION, **budget):
    ctx = contexts[session]
    request = ctx.request.model_copy(
        update={
            "strategy_id": strategy_id,
            "decision_id": make_id(
                "dec", ctx.request.run_id, strategy_id, session.isoformat(), "r0"
            ),
        }
    )
    if budget:
        request = request.model_copy(update={"budget": request.budget.model_copy(update=budget)})
    fresh = dataclasses.replace(ctx, request=request)
    return fresh


@pytest.fixture
def ctx_for(contexts):
    def build(strategy_id: str, session: date = SESSION, **budget):
        return context_for(contexts, strategy_id, session, **budget)

    return build


@pytest.fixture(scope="session")
def real_evidence(tmp_path_factory):
    from research_engine.agents.ports import open_default_evidence_port

    return open_default_evidence_port(tmp_path_factory.mktemp("agent-evidence-home"))
