"""Response modes (spec 6.5) and lazy registration of AI strategies."""

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from research_engine.contracts.decisions import DecisionOutcome, StrategyKind
from research_engine.contracts.portfolio import DecisionAction
from research_engine.experiments.parity import default_parity_config
from research_engine.experiments.runner import (
    ReplayConfig,
    ReplayRunner,
    ResponseModeError,
    StrategySpec,
)
from research_engine.experiments.strategy import create_strategy, make_result
from tests.simulation.fakes import make_ports

KEY = b"modes-key"
START, END = date(2024, 1, 2), date(2024, 1, 5)


class _Provider:
    provider = "fake"
    model = "fake-model-v1"
    deterministic = True
    priced = False

    def __init__(self, replay=False, capturing=False):
        self.replay = replay
        self.capturing = capturing


class _Agent:
    strategy_id = "llm_market"
    kind = StrategyKind.SINGLE_AGENT
    invested = False
    deterministic = True

    def __init__(self, provider):
        self.provider = provider
        self.config = {"version": "fake-agent-v1", "provider": "fake", "modelId": "fake-model-v1"}
        self.calls = 0

    def decide(self, ctx):
        self.calls += 1
        return make_result(ctx, self, DecisionOutcome.COMPLETED_HOLD, action=DecisionAction.HOLD)


def _config(**kw):
    return ReplayConfig(
        experiment_id="modes",
        run_id=kw.pop("run_id", "modes-r0"),
        start_date=START,
        end_date=END,
        strategies=[StrategySpec(strategy_id="cash"), StrategySpec(strategy_id="llm_market")],
        **kw,
    )


def _runner(tmp_path, config, agent, name="run", **kwargs):
    pricing, market = make_ports()
    return ReplayRunner(
        config, pricing, market, tmp_path / name, KEY, strategies={"llm_market": agent}, **kwargs
    )


def test_default_replay_source_keeps_existing_config_hashes():
    config = default_parity_config()
    assert config.replay_source is None
    assert "replaySource" not in config.to_wire()
    assert config.effective_replay_source == "stored_results"
    assert config.response_source == "stored_strategy_results"
    provider_level = ReplayConfig.model_validate(
        {**config.to_wire(), "replaySource": "recorded_responses"}
    )
    assert provider_level.compute_hash() != config.compute_hash()
    assert provider_level.response_source == "recorded_provider_responses"
    with pytest.raises(ValueError):
        ReplayConfig.model_validate(
            {
                **config.to_wire(),
                "responseMode": "fresh_inference",
                "replaySource": "stored_results",
            }
        )


def test_recorded_response_replay_calls_strategies_and_is_labelled(tmp_path):
    agent = _Agent(_Provider(replay=True))
    config = _config(response_mode="recorded_replay", replay_source="recorded_responses")
    result = _runner(tmp_path, config, agent).run()
    assert agent.calls == len(result.manifest.decision_sessions)
    assert result.manifest.response_mode == "recorded_replay"
    assert result.manifest.response_source == "recorded_provider_responses"
    sources = {s.strategy_id: s.response_source for s in result.manifest.strategies}
    assert sources == {
        "cash": "deterministic_code",
        "llm_market": "recorded_responses:fake/fake-model-v1",
    }


def test_stored_results_replay_does_not_call_strategies(tmp_path):
    agent = _Agent(_Provider(replay=True))
    result = _runner(tmp_path, _config(), agent).run()
    assert agent.calls == 0
    assert result.manifest.response_source == "stored_strategy_results"
    assert {s.strategy_id: s.response_source for s in result.manifest.strategies}[
        "llm_market"
    ] == "stored_strategy_result"


def test_fresh_inference_labels_capture(tmp_path):
    agent = _Agent(_Provider(capturing=True))
    result = _runner(tmp_path, _config(response_mode="fresh_inference"), agent).run()
    assert agent.calls == len(result.manifest.decision_sessions)
    assert result.manifest.response_source == "fresh_provider_calls"
    assert {s.strategy_id: s.response_source for s in result.manifest.strategies}[
        "llm_market"
    ] == "provider_call:fake/fake-model-v1:captured"


def test_mismatched_provider_and_mode_is_refused(tmp_path):
    live = _Agent(_Provider(replay=False))
    with pytest.raises(ResponseModeError):
        _runner(
            tmp_path,
            _config(response_mode="recorded_replay", replay_source="recorded_responses"),
            live,
        )
    replaying = _Agent(_Provider(replay=True))
    with pytest.raises(ResponseModeError):
        _runner(tmp_path, _config(response_mode="fresh_inference"), replaying)


def test_create_strategy_imports_agents_lazily():
    # A fresh interpreter: research_engine.agents is not imported until an llm_* id is used.
    code = (
        "import sys\n"
        "from research_engine.experiments.strategy import create_strategy\n"
        "assert create_strategy('cash').strategy_id == 'cash'\n"
        "assert 'research_engine.agents' not in sys.modules\n"
        "strategy = create_strategy('llm_market', {})\n"
        "assert 'research_engine.agents' in sys.modules\n"
        "print(strategy.strategy_id, strategy.config['provider'])\n"
    )
    root = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.split() == ["llm_market", "reference"]
    with pytest.raises(KeyError):
        create_strategy("llm_unknown")
