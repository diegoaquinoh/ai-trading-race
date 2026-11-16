"""Recorded demo responses: capture with the reference model, replay without providers.

* :func:`record_experiment` runs ``llm_market``/``llm_rag``/``llm_graph``/``llm_team``
  over a replay window in two modes (spec 6.5 keeps them separate):

  1. **capture** - ``fresh_inference`` with :class:`ReferenceHeuristicProvider`
     wrapped in :class:`RecordingProvider`;
  2. **recorded-response replay** - ``recorded_replay`` with
     ``replay_source="recorded_responses"`` on :class:`RecordedResponseProvider`
     (no provider access). This run is the canonical recorded run.

  The two runs must agree on every decision (outcome, proposal, note,
  attempts, tool traces, usage); only the request binding differs, because the
  DecisionRequest carries the response mode (:data:`REQUEST_BOUND_FIELDS`).
  Under ``fixtures/recorded/<experiment>/`` it writes:

  - ``responses/`` - ``manifest.json`` + ``responses.jsonl`` (recorded-responses-v1);
  - ``run/`` - ``config.json``, ``outcomes.jsonl`` (StrategyResults) and
    ``manifest.json`` of the recorded-response replay run;
  - ``capture/`` - ``config.json`` and ``manifest.json`` of the capture run;
  - ``experiment.json`` - window, strategies, provider/model disclosure,
    versions, ``decisionId -> resultHash`` and the capture/replay equivalence.

* :func:`replay_experiment` re-runs ``run/config.json`` with
  :class:`RecordedResponseProvider` (any missing recording fails explicitly)
  and checks that every StrategyResult is identical.
* :func:`load_recorded_outcomes` returns the recorded StrategyResults for
  result-level replay (``ReplayRunner(..., recorded_outcomes=...)`` with the
  default ``replay_source="stored_results"``).

The response source is visible in every attempt (``recordedResponseId``), in
the run manifests (``responseMode``/``responseSource``) and in ``experiment.json``.

Transition and result signatures in fixtures use published, non-secret
fixture keys so anyone can reproduce them.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Sequence

from research_engine.contracts.decisions import StrategyResult

from .ports import EvidencePort
from .prompts import PROMPT_VERSION
from .providers import RecordedResponseProvider, RecordingProvider, ReferenceHeuristicProvider
from .providers.recorded import RECORDING_FORMAT
from .providers.reference import DISCLOSURE
from .strategies import LLM_STRATEGY_IDS, build_llm_strategies
from .tool_schemas import TOOL_SCHEMA_VERSION

log = logging.getLogger(__name__)

FIXTURES_RECORDED = Path(__file__).resolve().parents[2] / "fixtures" / "recorded"
FIXTURE_TRANSITION_KEY = b"fixture-recorded-demo-transition-key-not-secret"
FIXTURE_RESULT_KEY = b"fixture-recorded-demo-result-key-not-secret"
RUN_FILES = ("config.json", "outcomes.jsonl", "manifest.json")
CAPTURE_FILES = ("config.json", "manifest.json")
REQUEST_BOUND_FIELDS = ("requestHash", "resultHash", "signature", "inputHashes.decisionRequest")
MARKET_LOOKBACK_DAYS = 60
MARKET_LOOKAHEAD_DAYS = 14


@dataclass
class RecordingSummary:
    experiment_dir: Path
    status: str
    outcomes: dict[str, str]
    responses: int
    failures: list[str] = field(default_factory=list)


@dataclass
class ReplayVerification:
    identical: bool
    outcomes: dict[str, str]
    mismatches: list[str] = field(default_factory=list)
    status: str = "completed"
    results: dict[str, StrategyResult] = field(default_factory=dict)


def default_ports(start: date, end: date):
    from research_engine.market.store import load_default_market

    return load_default_market(
        start - timedelta(days=MARKET_LOOKBACK_DAYS), end + timedelta(days=MARKET_LOOKAHEAD_DAYS)
    )


def _run(config, strategies, ports, run_dir: Path):
    from research_engine.experiments.runner import ReplayRunner

    pricing, market = ports
    runner = ReplayRunner(
        config, pricing, market, run_dir, FIXTURE_TRANSITION_KEY, strategies=strategies
    )
    return runner.run()


def recorded_response_config(config):
    """The recorded-response replay counterpart of a capture configuration."""
    from research_engine.experiments.runner import ReplayConfig

    wire = config.to_wire()
    wire.update({"responseMode": "recorded_replay", "replaySource": "recorded_responses"})
    return ReplayConfig.model_validate(wire)


def decision_payload(result: StrategyResult) -> dict:
    """StrategyResult wire form without the request binding (:data:`REQUEST_BOUND_FIELDS`)."""
    wire = result.to_wire()
    for name in ("requestHash", "resultHash", "signature"):
        wire.pop(name, None)
    wire["inputHashes"] = {
        k: v for k, v in (wire.get("inputHashes") or {}).items() if k != "decisionRequest"
    }
    return wire


def compare_capture_and_replay(
    capture: dict[str, StrategyResult], replay: dict[str, StrategyResult]
) -> list[str]:
    """Decision-level differences between a capture run and its recorded replay."""
    mismatches = []
    for decision_id in sorted(set(capture) | set(replay)):
        a, b = capture.get(decision_id), replay.get(decision_id)
        if a is None or b is None:
            mismatches.append(f"{decision_id}:missing")
        elif decision_payload(a) != decision_payload(b):
            mismatches.append(f"{decision_id}:decision_differs")
    return mismatches


def _outcomes(path: Path) -> dict[str, StrategyResult]:
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            out[record["decisionId"]] = StrategyResult.model_validate(record["result"])
    return out


def record_experiment(
    experiment_id: str,
    start: date,
    end: date,
    *,
    evidence: EvidencePort,
    out_root: Optional[Path] = None,
    strategy_ids: Sequence[str] = LLM_STRATEGY_IDS,
    ports=None,
    overwrite: bool = False,
) -> RecordingSummary:
    from research_engine.experiments.runner import ReplayConfig, StrategySpec

    exp_dir = Path(out_root or FIXTURES_RECORDED) / experiment_id
    if exp_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{exp_dir} already exists; pass overwrite=True")
        shutil.rmtree(exp_dir)
    exp_dir.mkdir(parents=True)
    provider = RecordingProvider(
        ReferenceHeuristicProvider(), exp_dir / "responses", disclosure=DISCLOSURE
    )
    ids = sorted(strategy_ids)
    strategies = build_llm_strategies(
        ids, provider=provider, evidence=evidence, signing_key=FIXTURE_RESULT_KEY
    )
    config = ReplayConfig(
        experiment_id=experiment_id,
        run_id=f"{experiment_id}-r0",
        start_date=start,
        end_date=end,
        strategies=[StrategySpec(strategy_id=s, config=strategies[s].config) for s in ids],
        response_mode="fresh_inference",
    )
    ports = ports or default_ports(start, end)
    replay_config = recorded_response_config(config)
    with tempfile.TemporaryDirectory() as tmp:
        capture = _run(config, strategies, ports, Path(tmp) / "capture")
        captured = _outcomes(Path(tmp) / "capture" / "outcomes.jsonl")
        (exp_dir / "capture").mkdir()
        for name in CAPTURE_FILES:
            shutil.copy2(Path(tmp) / "capture" / name, exp_dir / "capture" / name)
        replay_strategies = build_llm_strategies(
            ids,
            provider=RecordedResponseProvider(exp_dir / "responses"),
            evidence=evidence,
            signing_key=FIXTURE_RESULT_KEY,
        )
        result = _run(replay_config, replay_strategies, ports, Path(tmp) / "run")
        (exp_dir / "run").mkdir()
        for name in RUN_FILES:
            source = Path(tmp) / "run" / name
            if source.exists():
                shutil.copy2(source, exp_dir / "run" / name)
    replayed = _outcomes(exp_dir / "run" / "outcomes.jsonl")
    equivalence = compare_capture_and_replay(captured, replayed)
    outcomes = {k: v.result_hash for k, v in sorted(replayed.items())}
    summary = {
        "experimentId": experiment_id,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "strategies": ids,
        "provider": provider.provider,
        "model": provider.model,
        "disclosure": DISCLOSURE,
        "responseFormat": RECORDING_FORMAT,
        "promptVersion": PROMPT_VERSION,
        "toolSchemaVersion": TOOL_SCHEMA_VERSION,
        "indexBuildId": evidence.index_build_id,
        "captureResponseMode": "fresh_inference (reference model, recorded)",
        "captureStatus": capture.status,
        "runResponseMode": "recorded_replay (replay_source=recorded_responses)",
        "captureReplayEquivalent": not equivalence,
        "captureReplayMismatches": equivalence,
        "requestBoundFields": list(REQUEST_BOUND_FIELDS),
        "signingKeys": "published non-secret fixture keys (research_engine.agents.recording)",
        "status": result.status,
        "failures": result.failures,
        "outcomes": outcomes,
        "recordedResponses": len(provider.store),
    }
    (exp_dir / "experiment.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    failures = list(result.failures) + [f"capture_replay:{m}" for m in equivalence]
    status = result.status if not equivalence else "capture_replay_mismatch"
    return RecordingSummary(exp_dir, status, outcomes, len(provider.store), failures)


def replay_experiment(
    experiment_dir: Path, *, evidence: EvidencePort, ports=None
) -> ReplayVerification:
    """Re-run a recorded experiment from recordings only and compare every result."""
    from research_engine.experiments.runner import ReplayConfig

    exp_dir = Path(experiment_dir)
    provider = RecordedResponseProvider(exp_dir / "responses")
    config = ReplayConfig.model_validate_json((exp_dir / "run" / "config.json").read_text())
    if config.effective_replay_source != "recorded_responses":
        config = recorded_response_config(config)
    ids = [s.strategy_id for s in config.strategies]
    strategies = build_llm_strategies(
        ids, provider=provider, evidence=evidence, signing_key=FIXTURE_RESULT_KEY
    )
    mismatches = []
    for spec in config.strategies:
        if strategies[spec.strategy_id].config != spec.config:
            mismatches.append(f"{spec.strategy_id}:strategy_config_drift")
    if mismatches:
        return ReplayVerification(False, {}, mismatches, "config_drift")
    expected = _outcomes(exp_dir / "run" / "outcomes.jsonl")
    ports = ports or default_ports(config.start_date, config.end_date)
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(config, strategies, ports, Path(tmp) / "run")
        actual = _outcomes(Path(tmp) / "run" / "outcomes.jsonl")
    for decision_id in sorted(set(expected) | set(actual)):
        a, b = expected.get(decision_id), actual.get(decision_id)
        if a is None or b is None:
            mismatches.append(f"{decision_id}:missing")
        elif a.to_wire() != b.to_wire():
            mismatches.append(f"{decision_id}:result_differs")
    return ReplayVerification(
        not mismatches,
        {k: v.result_hash for k, v in sorted(actual.items())},
        mismatches,
        result.status,
        dict(sorted(actual.items())),
    )


def load_recorded_outcomes(experiment_dir: Path) -> dict[str, StrategyResult]:
    return _outcomes(Path(experiment_dir) / "run" / "outcomes.jsonl")
