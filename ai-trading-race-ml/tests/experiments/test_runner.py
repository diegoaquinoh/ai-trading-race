"""Daily replay runner: checkpoints, recovery, matched skips, bootstrap, response modes."""

import json
from datetime import date
from decimal import Decimal

import pytest

from research_engine.contracts.decisions import (
    DecisionOutcome,
    Proposal,
    StrategyKind,
    StrategyResult,
)
from research_engine.contracts.portfolio import CommandType, DecisionAction, TargetWeight
from research_engine.experiments.manifest import (
    ManifestImmutable,
    amend_manifest,
    verify_manifest,
)
from research_engine.experiments.runner import (
    ReplayConfig,
    ReplayInterrupted,
    ReplayRunner,
    StrategySpec,
)
from research_engine.experiments.strategy import make_result
from research_engine.simulation.store import OfflineStateStore
from tests.simulation.fakes import DEFAULT_INSTRUMENTS, make_ports

KEY = b"runner-key"
START, END = date(2024, 1, 2), date(2024, 2, 9)


def _config(strategies=("cash", "quant_duration", "static_ladder"), **kw):
    return ReplayConfig(
        experiment_id="exp-t",
        run_id=kw.pop("run_id", "run-t"),
        start_date=kw.pop("start", START),
        end_date=kw.pop("end", END),
        strategies=[StrategySpec(strategy_id=s) for s in strategies],
        **kw,
    )


def _run(tmp_path, name="run", config=None, ports=None, **kwargs):
    pricing, market = ports or make_ports()
    runner = ReplayRunner(config or _config(), pricing, market, tmp_path / name, KEY, **kwargs)
    return runner, runner.run()


def _fingerprint(runner):
    store = runner.store
    proposals = store.committed()
    return {
        "states": {p: store.state(p).compute_hash() for p in store.portfolios()},
        "fills": sorted(f.fill_id for p in proposals for f in p.fills),
        "cash_flows": sorted(c.cash_flow_id for p in proposals for c in p.cash_flows),
        "settlements": sorted(s for p in proposals for s in p.settlements_completed),
    }


def test_replay_completes_with_matched_bootstrap(tmp_path):
    runner, result = _run(tmp_path)
    assert result.status == "completed" and not result.failures
    assert result.cycles_completed == len(runner.sessions)
    fills = {}
    for sid in ("quant_duration", "static_ladder"):
        pid = runner._pid(sid)
        first = [p for p in runner.store.committed(pid) if p.fills][0]
        fills[sid] = sorted(
            (f.security_id, f.face, f.execution_clean_price_per_100) for f in first.fills
        )
    assert fills["quant_duration"] == fills["static_ladder"]
    assert runner.bootstrap["checked"]
    manifest = result.manifest
    assert manifest.status == "completed" and verify_manifest(manifest)
    assert len(manifest.bootstrap_allocation) == 7
    coupons = [c for p in runner.store.committed() for c in p.cash_flows if c.kind == "COUPON"]
    assert coupons  # NOTE-003 pays on 2024-01-31, NOTE-004/005 on 2024-02-15 (outside window)
    ids = [e.event_id for p in runner.store.committed() for e in p.events]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "crash_at",
    [
        "2024-01-02:quant_duration:submit_decision",  # mid-cycle, before the ladder submits
        "2024-01-31:static_ladder:process_events",  # right after a coupon commit
        "2024-02-01:quant_duration:value_portfolio",  # after a monthly rebalance submission
    ],
)
def test_resume_after_crash_has_no_duplicate_effects(tmp_path, crash_at):
    reference, _ = _run(tmp_path, "reference")
    expected = _fingerprint(reference)

    fired = []

    def crash(label):
        if label == crash_at and not fired:
            fired.append(label)
            raise ReplayInterrupted(label)

    pricing, market = make_ports()
    crashed = ReplayRunner(_config(), pricing, market, tmp_path / "crashed", KEY, interrupt=crash)
    with pytest.raises(ReplayInterrupted):
        crashed.run()
    assert fired == [crash_at]
    resumed = ReplayRunner(_config(), pricing, market, tmp_path / "crashed", KEY)
    result = resumed.resume()
    assert result.status == "completed"
    actual = _fingerprint(resumed)
    assert actual == expected
    assert len(actual["fills"]) == len(set(actual["fills"]))
    assert len(actual["cash_flows"]) == len(set(actual["cash_flows"]))
    # The JSONL log replays to the same authoritative states.
    log = OfflineStateStore(KEY, tmp_path / "crashed" / "commits.jsonl")
    assert {p: log.state(p).compute_hash() for p in log.portfolios()} == expected["states"]
    # Resuming a completed run is a no-op.
    again = ReplayRunner(_config(), pricing, market, tmp_path / "crashed", KEY).resume()
    assert again.manifest.manifest_hash == result.manifest.manifest_hash


def test_missing_shared_curve_skips_the_matched_cycle_for_everyone(tmp_path):
    gap = date(2024, 1, 10)
    runner, result = _run(tmp_path, ports=make_ports(missing={gap}))
    assert result.status == "completed"
    on_gap = [r for r in runner.outcomes.values() if r.cycle_id == f"cycle:{gap.isoformat()}"]
    assert len(on_gap) == 3
    assert {r.outcome for r in on_gap} == {DecisionOutcome.SKIPPED_STALE_DATA}
    assert any(e.startswith("2024-01-10:skipped_stale_data") for e in result.manifest.exclusions)


def test_bootstrap_fill_failure_fails_initialization_for_all(tmp_path):
    runner, result = _run(tmp_path, ports=make_ports(missing={date(2024, 1, 3)}))
    assert result.status == "failed"
    assert any(f.startswith("initialization_failed") for f in result.failures)
    assert result.manifest.status == "failed" and verify_manifest(result.manifest)


def test_empty_bootstrap_bucket_fails_initialization(tmp_path):
    ports = make_ports(instruments=DEFAULT_INSTRUMENTS[:4])
    runner, result = _run(tmp_path, ports=ports)
    assert result.status == "failed"
    assert "initialization_failed:empty_bootstrap_bucket:longer" in result.failures
    outcomes = list(runner.outcomes.values())
    assert outcomes and all(o.outcome == DecisionOutcome.FAILED_DEPENDENCY for o in outcomes)


class _AgentLike:
    strategy_id = "llm_market"
    kind = StrategyKind.SINGLE_AGENT
    invested = False
    deterministic = False

    def __init__(self):
        self.config = {"version": "fake-agent-v1", "modelId": "reference-heuristic-v1"}
        self.calls = 0

    def decide(self, ctx):
        self.calls += 1
        return make_result(ctx, self, DecisionOutcome.COMPLETED_HOLD, action=DecisionAction.HOLD)


def test_recorded_and_fresh_response_modes_are_distinct(tmp_path):
    agent = _AgentLike()
    end = date(2024, 1, 4)
    cfg = _config(("cash", "llm_market"), end=end)
    runner, result = _run(tmp_path, "recorded", config=cfg, strategies={"llm_market": agent})
    agent_outcomes = [r for r in runner.outcomes.values() if r.strategy_id == "llm_market"]
    assert agent.calls == 0
    assert {r.reasons[0] for r in agent_outcomes} == {"recorded_response_missing"}
    assert result.manifest.response_mode == "recorded_replay"

    fresh_cfg = _config(("cash", "llm_market"), end=end, response_mode="fresh_inference")
    fresh_runner, fresh = _run(
        tmp_path, "fresh", config=fresh_cfg, strategies={"llm_market": agent}
    )
    assert agent.calls == len(fresh_runner.sessions)
    assert fresh.manifest.response_mode == "fresh_inference"

    recorded = {
        r.decision_id: r for r in fresh_runner.outcomes.values() if r.strategy_id == "llm_market"
    }
    replay_runner, _ = _run(
        tmp_path,
        "replayed",
        config=cfg,
        strategies={"llm_market": agent},
        recorded_outcomes=recorded,
    )
    replayed = [r for r in replay_runner.outcomes.values() if r.strategy_id == "llm_market"]
    assert {r.outcome for r in replayed} == {DecisionOutcome.COMPLETED_HOLD}
    assert agent.calls == len(fresh_runner.sessions)  # no new model calls in recorded mode


class _Malformed(_AgentLike):
    strategy_id = "llm_rag"

    def decide(self, ctx):
        good = make_result(ctx, self, DecisionOutcome.COMPLETED_HOLD, action=DecisionAction.HOLD)
        bad_proposal = Proposal.model_construct(
            action=DecisionAction.REBALANCE,
            target_weights=[TargetWeight(security_id="SYN-USD-NOTE-003", weight=Decimal("0.5"))],
            supporting_claim_ids=[],
            supporting_calculation_ids=[],
        )
        return StrategyResult.model_construct(
            **{
                **dict(good),
                "outcome": DecisionOutcome.COMPLETED_PROPOSAL,
                "proposal": bad_proposal,
            }
        )


class _Crashing(_AgentLike):
    strategy_id = "llm_graph"

    def decide(self, ctx):
        raise RuntimeError("provider down")


def test_malformed_or_failing_strategy_cannot_write_state(tmp_path):
    cfg = _config(
        ("llm_graph", "llm_rag", "static_ladder"),
        end=date(2024, 1, 5),
        response_mode="fresh_inference",
    )
    runner, result = _run(
        tmp_path, config=cfg, strategies={"llm_rag": _Malformed(), "llm_graph": _Crashing()}
    )
    assert result.status == "completed"
    outcomes = {r.strategy_id: r for r in runner.outcomes.values()}
    assert outcomes["llm_rag"].outcome == DecisionOutcome.FAILED_INVALID_OUTPUT
    assert outcomes["llm_graph"].outcome == DecisionOutcome.FAILED_DEPENDENCY
    for sid in ("llm_rag", "llm_graph"):
        commands = [p.command_type for p in runner.store.committed(runner._pid(sid))]
        assert CommandType.SUBMIT_DECISION not in commands
        assert runner.store.state(runner._pid(sid)).positions == []
    # The healthy competitor is unaffected by the others' failures.
    assert runner.store.state(runner._pid("static_ladder")).positions


def test_manifest_contents_and_immutability(tmp_path):
    runner, result = _run(tmp_path, config=_config(end=date(2024, 1, 5)))
    manifest = result.manifest
    assert manifest.finalized and verify_manifest(manifest)
    assert "requirements.txt" in manifest.dependency_lock_hashes
    assert manifest.engine_version.startswith("research-engine/")
    assert manifest.cost_sensitivity_profiles == [
        "synthetic-half-spread-0.00-v1",
        "synthetic-half-spread-0.02-v1",
        "synthetic-half-spread-0.05-v1",
    ]
    assert {s.strategy_id for s in manifest.strategies} == {
        "cash",
        "quant_duration",
        "static_ladder",
    }
    assert manifest.schedule["decision"] == "19:00:00"
    assert manifest.curve_manifests and manifest.artifacts
    assert manifest.realized_usage["cyclesCompleted"] == len(runner.sessions)
    with pytest.raises(ManifestImmutable):
        amend_manifest(manifest, failures=["rewritten"])
    on_disk = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert on_disk["manifestHash"] == manifest.manifest_hash
    with pytest.raises(RuntimeError):
        ReplayRunner(_config(end=date(2024, 1, 5)), *make_ports(), tmp_path / "run", KEY).run()
