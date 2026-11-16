"""Recorded replay reproduces identical StrategyResults with providers disabled."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from research_engine.agents.providers import reference as reference_module
from research_engine.agents.recording import (
    FIXTURES_RECORDED,
    load_recorded_outcomes,
    record_experiment,
    replay_experiment,
)

from .fakes import hawkish_docs, FakeEvidencePort, utc

SAMPLE = FIXTURES_RECORDED / "demo-sample-2023-06"


def _disable_providers(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a provider was contacted during recorded replay")

    monkeypatch.setattr(reference_module.ReferenceHeuristicProvider, "generate", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


@pytest.fixture(scope="module")
def recorded(tmp_path_factory, ports):
    root = tmp_path_factory.mktemp("recorded")
    evidence = FakeEvidencePort(hawkish_docs(utc(2023, 6, 13)))
    summary = record_experiment(
        "unit-exp",
        date(2023, 6, 12),
        date(2023, 6, 14),
        evidence=evidence,
        out_root=root,
        ports=ports,
    )
    return summary, evidence, root


def test_capture_writes_recordings_and_outcomes(recorded):
    summary, _, root = recorded
    exp = root / "unit-exp"
    assert summary.status == "completed" and summary.responses > 0
    assert len(summary.outcomes) == 12  # 4 strategies x 3 sessions
    meta = json.loads((exp / "experiment.json").read_text())
    assert meta["provider"] == "reference" and meta["model"] == "reference-heuristic-v1"
    assert "not a hosted LLM" in meta["disclosure"]
    outcomes = load_recorded_outcomes(exp)
    attempts = [a for r in outcomes.values() for a in r.attempts]
    assert attempts and all(a.recorded_response_id for a in attempts)
    assert {r.strategy_id for r in outcomes.values()} == {
        "llm_graph",
        "llm_market",
        "llm_rag",
        "llm_team",
    }


def test_replay_with_providers_disabled_is_identical(recorded, ports, monkeypatch):
    summary, evidence, root = recorded
    _disable_providers(monkeypatch)
    verification = replay_experiment(root / "unit-exp", evidence=evidence, ports=ports)
    assert verification.identical, verification.mismatches
    assert verification.outcomes == summary.outcomes


def test_missing_recording_fails_explicitly(recorded, ports, monkeypatch, tmp_path):
    summary, evidence, root = recorded
    import shutil

    copy = tmp_path / "unit-exp"
    shutil.copytree(root / "unit-exp", copy)
    lines = (copy / "responses" / "responses.jsonl").read_text().splitlines()
    kept = [ln for ln in lines if json.loads(ln)["role"] != "macro_researcher"]
    assert len(kept) < len(lines)
    (copy / "responses" / "responses.jsonl").write_text("\n".join(kept) + "\n")
    _disable_providers(monkeypatch)
    verification = replay_experiment(copy, evidence=evidence, ports=ports)
    assert not verification.identical
    assert any("result_differs" in m for m in verification.mismatches)
    team = sorted(
        (r for r in verification.results.values() if r.strategy_id == "llm_team" and r.attempts),
        key=lambda r: r.decision_id,
    )
    assert team
    for result in team:  # explicit failure, never a silently substituted response
        assert result.outcome.value == "failed_dependency" and result.proposal is None
        assert any(reason.startswith("recording_missing") for reason in result.reasons)
    macro = next(t for t in team[0].specialist_tasks if t.role == "macro_researcher")
    assert macro.status == "failed" and "recording_missing" in macro.findings[-1]
    others = [r for r in verification.results.values() if r.strategy_id != "llm_team"]
    assert all(r.result_hash == summary.outcomes[r.decision_id] for r in others)


@pytest.mark.skipif(not SAMPLE.exists(), reason="committed sample not generated")
def test_committed_sample_replays_identically(real_evidence, monkeypatch):
    _disable_providers(monkeypatch)
    verification = replay_experiment(SAMPLE, evidence=real_evidence)
    assert verification.identical, verification.mismatches[:5]
    meta = json.loads((SAMPLE / "experiment.json").read_text())
    assert verification.outcomes == meta["outcomes"]
