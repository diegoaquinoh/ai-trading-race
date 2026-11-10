"""Offline/application parity fixture exporter (spec 5.3, 16.5).

Runs a deterministic replay with the supplied ports and writes, to
``<repo>/contracts/fixtures/parity/`` by default:

* ``transitions.jsonl`` - every committed transition in commit order:
  ``{"sequence", "commandId", "portfolioId", "request", "proposal"}`` (wire form);
* ``expected.json`` - final state versions/hashes, cumulative ledger totals per
  account (debit positive), last valuation equity per portfolio, signing key,
  engine version and counts;
* ``config.json`` - the replay configuration.

The .NET parity test replays the requests through its commit path (verifying
hash, signature, versions, balance) and must reproduce the same final state
hashes and ledger totals. Output is byte-for-byte deterministic for identical
ports and configuration (no wall-clock or git metadata is included).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from research_engine.simulation.engine import engine_version
from research_engine.simulation.ledger import ledger_totals
from research_engine.simulation.store import verify_proposal

from .runner import ReplayConfig, ReplayRunner, StrategySpec

PARITY_SIGNING_KEY = b"parity-fixture-signing-key"
PARITY_FIXTURE_VERSION = "parity-fixture-v1"


def default_parity_config(
    start: date = date(2024, 1, 2), end: date = date(2024, 2, 9)
) -> ReplayConfig:
    return ReplayConfig(
        experiment_id="exp-parity",
        run_id="run-parity",
        start_date=start,
        end_date=end,
        strategies=[
            StrategySpec(strategy_id="cash"),
            StrategySpec(strategy_id="quant_duration"),
            StrategySpec(strategy_id="static_ladder"),
        ],
        signing_key_id="parity-fixture",
    )


def default_output_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "parity"


def _dump(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export_parity_fixture(
    pricing,
    market,
    out_dir: Optional[Path] = None,
    config: Optional[ReplayConfig] = None,
    signing_key: bytes = PARITY_SIGNING_KEY,
) -> dict[str, Path]:
    config = config or default_parity_config()
    out = Path(out_dir) if out_dir else default_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="parity-replay-"))
    try:
        runner = ReplayRunner(config, pricing, market, work / "run", signing_key)
        result = runner.run()
        store = runner.store
        lines = []
        journals_by_portfolio: dict[str, list] = {}
        last_valuation: dict[str, dict] = {}
        for record in store.iter_log():
            proposal = record.proposal
            verify_proposal(proposal, signing_key)
            request = store.request_for(proposal.command_id)
            lines.append(
                json.dumps(
                    {
                        "sequence": record.sequence,
                        "commandId": proposal.command_id,
                        "portfolioId": proposal.portfolio_id,
                        "request": request.to_wire() if request is not None else None,
                        "proposal": proposal.to_wire(),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            journals_by_portfolio.setdefault(proposal.portfolio_id, []).extend(proposal.journals)
            if proposal.valuation is not None:
                last_valuation[proposal.portfolio_id] = {
                    "valuationId": proposal.valuation.valuation_id,
                    "complete": proposal.valuation.complete,
                    "equityUsd": proposal.valuation.to_wire()["equityUsd"],
                }
        transitions = out / "transitions.jsonl"
        transitions.write_text("\n".join(lines) + "\n", encoding="utf-8")
        final = {
            state.portfolio_id: {
                "version": state.version,
                "stateHash": state.compute_hash(),
                "cashUsd": state.to_wire()["cashUsd"],
            }
            for state in result.final_states.values()
        }
        expected = {
            "fixtureVersion": PARITY_FIXTURE_VERSION,
            "runStatus": result.status,
            "engineVersion": engine_version(pricing),
            "signingKeyUtf8": signing_key.decode("utf-8"),
            "transitionCount": len(lines),
            "finalStates": final,
            "ledgerTotals": {
                pid: ledger_totals(journals)
                for pid, journals in sorted(journals_by_portfolio.items())
            },
            "lastValuations": last_valuation,
            "configHash": config.compute_hash(),
        }
        expected_path = out / "expected.json"
        _dump(expected_path, expected)
        config_path = out / "config.json"
        _dump(config_path, config.to_wire())
        scenarios = write_application_scenarios(transitions, out, config, engine_version(pricing))
        return {
            "transitions": transitions,
            "expected": expected_path,
            "config": config_path,
            **{f"scenario:{name}": path for name, path in scenarios.items()},
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _account_totals(journals: list[dict]) -> dict[str, dict[str, str]]:
    from decimal import Decimal

    totals: dict[str, list[Decimal]] = {}
    for journal in journals:
        for line in journal["lines"]:
            debit_credit = totals.setdefault(line["account"], [Decimal("0"), Decimal("0")])
            debit_credit[0] += Decimal(line["debitUsd"])
            debit_credit[1] += Decimal(line["creditUsd"])
    return {
        account: {"debitUsd": f"{dc[0]:.2f}", "creditUsd": f"{dc[1]:.2f}"}
        for account, dc in sorted(totals.items())
    }


def write_application_scenarios(
    transitions_path: Path, out_dir: Path, config: ReplayConfig, engine: str
) -> dict[str, Path]:
    """Split the replay log into one application-path scenario per portfolio.

    Layout consumed by ``AiTradingRace.Tests/FixedIncome/ParityFixtureTests.cs``
    (see ``contracts/fixtures/parity/README.md``): ``<scenario>/manifest.json``,
    ``expected.json`` and ``proposals/NNNN.json`` holding the exact signed
    ``TransitionProposal.to_wire()`` bodies the offline store committed.
    """
    records: dict[str, list[dict]] = {}
    for line in transitions_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records.setdefault(record["portfolioId"], []).append(record)
    written: dict[str, Path] = {}
    for portfolio_id, items in sorted(records.items()):
        items.sort(key=lambda r: r["sequence"])
        first = items[0]
        if first["request"] is None:
            raise ValueError(f"missing genesis request for {portfolio_id}")
        genesis = first["request"]["portfolioState"]
        strategy_id = first["proposal"]["strategyId"]
        scenario_id = f"replay-{config.run_id}-{strategy_id}"
        scenario_dir = out_dir / scenario_id
        if scenario_dir.exists():
            shutil.rmtree(scenario_dir)
        (scenario_dir / "proposals").mkdir(parents=True)
        proposal_files: list[str] = []
        state_hashes: dict[str, str] = {"0": first["proposal"]["inputHashes"]["portfolioState"]}
        journals: list[dict] = []
        counts = {
            "journals": 0,
            "orders": 0,
            "fills": 0,
            "settlements": 0,
            "cashFlows": 0,
            "valuations": 0,
        }
        last = first["proposal"]
        for index, record in enumerate(items, start=1):
            proposal = record["proposal"]
            name = f"proposals/{index:04d}.json"
            _dump(scenario_dir / name, proposal)
            proposal_files.append(name)
            state_hashes[str(proposal["newVersion"])] = proposal["newStateHash"]
            journals.extend(proposal["journals"])
            counts["journals"] += len(proposal["journals"])
            counts["orders"] += len(proposal["ordersCreated"])
            counts["fills"] += len(proposal["fills"])
            counts["settlements"] += len(proposal["settlementsCreated"])
            counts["cashFlows"] += len(proposal["cashFlows"])
            counts["valuations"] += 1 if proposal.get("valuation") else 0
            last = proposal
        manifest = {
            "schemaVersion": "1.0",
            "scenarioId": scenario_id,
            "description": (
                f"Offline replay {config.start_date}..{config.end_date} for {strategy_id} "
                "with real QuantLib pricing ports (synthetic_curve mode)."
            ),
            "signingKeyUtf8": PARITY_SIGNING_KEY.decode("utf-8"),
            "engineVersion": engine,
            "portfolio": {
                "portfolioId": portfolio_id,
                "strategyId": strategy_id,
                "runId": config.run_id,
                "repetition": config.repetition,
                "riskPolicyId": config.risk_policy.policy_id,
                "dataMode": "synthetic_curve",
            },
            "riskPolicy": config.risk_policy.to_wire(),
            "genesisState": genesis,
            "proposals": proposal_files,
            "expected": "expected.json",
        }
        expected = {
            "finalVersion": last["newVersion"],
            "finalStateHash": last["newStateHash"],
            "stateHashes": state_hashes,
            "ledgerTotals": _account_totals(journals),
            "counts": counts,
        }
        _dump(scenario_dir / "manifest.json", manifest)
        _dump(scenario_dir / "expected.json", expected)
        written[scenario_id] = scenario_dir
    return written
