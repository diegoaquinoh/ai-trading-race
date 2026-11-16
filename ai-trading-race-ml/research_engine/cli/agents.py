"""``fi-research decide | research-note | record`` (workstream E).

* ``decide --strategy llm_rag --date 2023-06-14 [--provider reference|recorded|anthropic|openai]``
  runs a short offline replay (bootstrap a few sessions earlier, then decide on
  ``--date``) for one LLM strategy and prints the final StrategyResult.
  ``--record DIR`` captures responses; ``--provider recorded --recordings DIR``
  replays them without provider access. Hosted providers need
  ``--price-schedule`` and ``--max-cost-usd`` (spec 10.4).
* ``research-note --question ... --as-of 2023-06-14`` prints a cited research
  note (no order authority).
* ``record --experiment NAME --from D --to D`` captures reference-model
  responses for the four LLM strategies under ``fixtures/recorded/NAME`` and
  verifies that recorded replay reproduces identical StrategyResults.

The reference provider is a deterministic rule-based model
(``reference-heuristic-v1``), reported as provider ``reference``; it is not an LLM.
Evidence comes from the offline Fed corpus under ``--home`` / ``$FI_RESEARCH_HOME``.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

TRANSITION_KEY_ENV = "FI_TRANSITION_SIGNING_KEY"
DEV_TRANSITION_KEY = b"dev-only-insecure-cli-transition-key"


def _evidence(args):
    from research_engine.agents.ports import open_default_evidence_port

    return open_default_evidence_port(args.home or os.environ.get("FI_RESEARCH_HOME"))


def _provider(args):
    from research_engine.agents.providers import RecordingProvider, build_provider

    name = {"openai": "openai_compatible"}.get(args.provider, args.provider)
    provider = build_provider(
        name, model=args.model, recordings=args.recordings, base_url=args.base_url
    )
    if getattr(args, "record", None):
        provider = RecordingProvider(provider, args.record)
    return provider


def _price_schedule(args):
    if not getattr(args, "price_schedule", None):
        return None
    from research_engine.agents.budget import PriceSchedule

    return PriceSchedule.model_validate_json(Path(args.price_schedule).read_text())


def _emit(payload, out):
    text = json.dumps(payload, indent=2, sort_keys=True)
    if out:
        Path(out).write_text(text + "\n")
        print(json.dumps({"written": str(out)}))
    else:
        print(text)


def _cmd_decide(args) -> int:
    from research_engine.agents import create_llm_strategy
    from research_engine.experiments.runner import ReplayConfig, ReplayRunner, StrategySpec
    from research_engine.market.store import load_default_market

    pricing, market = load_default_market(
        args.date - timedelta(days=90), args.date + timedelta(days=14)
    )
    sessions = market.sessions(args.date - timedelta(days=40), args.date)
    if not sessions or sessions[-1] != args.date:
        print(json.dumps({"error": f"{args.date} is not a supported session"}))
        return 2
    start = sessions[-(args.lookback_sessions + 1)]
    evidence = _evidence(args) if args.strategy != "llm_market" else None
    config = {"maxCostUsd": args.max_cost_usd} if args.max_cost_usd else {}
    provider = _provider(args)
    strategy = create_llm_strategy(
        args.strategy,
        config,
        provider=provider,
        evidence=evidence,
        price_schedule=_price_schedule(args),
    )
    key = os.environ.get(TRANSITION_KEY_ENV, "").encode() or DEV_TRANSITION_KEY
    # Recorded responses are a replay mode, never labelled fresh inference (spec 6.5).
    mode = (
        {"response_mode": "recorded_replay", "replay_source": "recorded_responses"}
        if getattr(provider, "replay", False)
        else {"response_mode": "fresh_inference"}
    )
    replay = ReplayConfig(
        experiment_id="cli-decide",
        run_id=f"cli-{args.strategy}-{args.date.isoformat()}",
        start_date=start,
        end_date=args.date,
        strategies=[StrategySpec(strategy_id=args.strategy, config=strategy.config)],
        **mode,
    )
    with tempfile.TemporaryDirectory() as tmp:
        result = ReplayRunner(
            replay, pricing, market, Path(tmp) / "run", key, strategies={args.strategy: strategy}
        ).run()
        lines = (Path(tmp) / "run" / "outcomes.jsonl").read_text().splitlines()
    final = json.loads(lines[-1])["result"]
    _emit(final, args.out)
    return 0 if result.status == "completed" else 1


def _as_of(text: str) -> datetime:
    from research_engine.simulation.clock import decision_at

    if "T" in text:
        from datetime import timezone

        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("--as-of instants need an offset (e.g. Z)")
        return value.astimezone(timezone.utc)
    return decision_at(date.fromisoformat(text))


def _cmd_research_note(args) -> int:
    from research_engine.agents.research_note import research_note
    from research_engine.contracts.decisions import RetrievalMode
    from research_engine.market.store import load_default_market

    as_of = _as_of(args.as_of)
    day = as_of.date()
    pricing, market = load_default_market(day - timedelta(days=90), day + timedelta(days=1))
    mode = RetrievalMode.GRAPH_RAG if args.mode == "graph" else RetrievalMode.HYBRID_RAG
    result = research_note(
        args.question,
        as_of,
        evidence=_evidence(args),
        provider=_provider(args),
        mode=mode,
        pricing=pricing,
        market=market,
        price_schedule=_price_schedule(args),
    )
    _emit(result.to_wire(), args.out)
    return (
        0
        if result.status in ("completed", "insufficient_evidence", "contradictory_evidence")
        else 1
    )


def _cmd_record(args) -> int:
    from research_engine.agents.recording import (
        FIXTURES_RECORDED,
        record_experiment,
        replay_experiment,
    )
    from research_engine.agents.strategies import LLM_STRATEGY_IDS

    evidence = _evidence(args)
    ids = args.strategies.split(",") if args.strategies else list(LLM_STRATEGY_IDS)
    summary = record_experiment(
        args.experiment,
        args.from_date,
        args.to_date,
        evidence=evidence,
        out_root=Path(args.out_root) if args.out_root else FIXTURES_RECORDED,
        strategy_ids=ids,
        overwrite=args.overwrite,
    )
    payload = {
        "experimentDir": str(summary.experiment_dir),
        "status": summary.status,
        "decisions": len(summary.outcomes),
        "recordedResponses": summary.responses,
        "failures": summary.failures,
    }
    if not args.no_verify:
        verification = replay_experiment(summary.experiment_dir, evidence=evidence)
        payload["replayIdentical"] = verification.identical
        payload["mismatches"] = verification.mismatches
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if summary.status == "completed" and payload.get("replayIdentical", True) else 1


def _provider_args(parser) -> None:
    parser.add_argument(
        "--provider",
        default="reference",
        choices=["reference", "recorded", "anthropic", "openai"],
        help="reference = deterministic rule-based model (not an LLM)",
    )
    parser.add_argument("--model", help="pinned model id for hosted providers")
    parser.add_argument("--base-url", help="provider base URL (OpenAI-compatible/Azure/local)")
    parser.add_argument("--recordings", help="recordings directory for --provider recorded")
    parser.add_argument("--price-schedule", help="versioned price schedule JSON (hosted runs)")
    parser.add_argument("--home", help="evidence home (default $FI_RESEARCH_HOME)")
    parser.add_argument("--out", help="write the JSON result to this file")


def register(subparsers) -> None:
    from research_engine.agents.strategies import LLM_STRATEGY_IDS

    decide = subparsers.add_parser("decide", help="run one LLM strategy decision offline")
    decide.add_argument("--strategy", required=True, choices=sorted(LLM_STRATEGY_IDS))
    decide.add_argument("--date", required=True, type=date.fromisoformat)
    decide.add_argument("--lookback-sessions", type=int, default=3)
    decide.add_argument("--record", help="capture responses into this recordings directory")
    decide.add_argument("--max-cost-usd", help="monetary ceiling for priced hosted runs")
    _provider_args(decide)
    decide.set_defaults(func=_cmd_decide)

    note = subparsers.add_parser("research-note", help="cited research note (no order authority)")
    note.add_argument("--question", required=True)
    note.add_argument("--as-of", required=True, help="YYYY-MM-DD (19:00 New York) or ISO instant")
    note.add_argument("--mode", choices=["graph", "hybrid"], default="graph")
    _provider_args(note)
    note.set_defaults(func=_cmd_research_note, record=None)

    record = subparsers.add_parser("record", help="capture and verify recorded demo responses")
    record.add_argument("--experiment", required=True)
    record.add_argument("--from", dest="from_date", required=True, type=date.fromisoformat)
    record.add_argument("--to", dest="to_date", required=True, type=date.fromisoformat)
    record.add_argument("--strategies", help="comma-separated subset of LLM strategy ids")
    record.add_argument("--out-root", help="default ai-trading-race-ml/fixtures/recorded")
    record.add_argument("--home", help="evidence home (default $FI_RESEARCH_HOME)")
    record.add_argument("--overwrite", action="store_true")
    record.add_argument("--no-verify", action="store_true")
    record.set_defaults(func=_cmd_record)
