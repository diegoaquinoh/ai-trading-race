"""Parity fixture export and the ``fi-research`` simulation commands."""

import json
from datetime import date

import pytest

from research_engine.cli import simulation as sim_cli
from research_engine.cli.main import main
from research_engine.contracts.portfolio import TransitionProposal, TransitionRequest
from research_engine.experiments.parity import (
    PARITY_SIGNING_KEY,
    default_parity_config,
    export_parity_fixture,
)
from research_engine.experiments.runner import ReplayConfig, StrategySpec
from research_engine.simulation.engine import propose_transition
from research_engine.simulation.ledger import ledger_totals
from research_engine.simulation.store import OfflineStateStore
from tests.simulation.fakes import make_ports

SHORT = default_parity_config(end=date(2024, 1, 12))


def test_parity_export_is_deterministic_and_replayable(tmp_path):
    first = export_parity_fixture(*make_ports(), tmp_path / "a", config=SHORT)
    second = export_parity_fixture(*make_ports(), tmp_path / "b", config=SHORT)
    for key in ("transitions", "expected", "config"):
        assert first[key].read_bytes() == second[key].read_bytes()
    expected = json.loads(first["expected"].read_text())
    assert expected["runStatus"] == "completed"
    key = expected["signingKeyUtf8"].encode()
    assert key == PARITY_SIGNING_KEY

    # Re-apply every recorded request: recompute, compare and commit through a fresh store.
    pricing, market = make_ports()
    store = OfflineStateStore(key)
    journals = {}
    lines = first["transitions"].read_text().splitlines()
    assert len(lines) == expected["transitionCount"]
    for line in lines:
        record = json.loads(line)
        request = TransitionRequest.model_validate(record["request"])
        recorded = TransitionProposal.model_validate(record["proposal"])
        if (
            request.portfolio_state.version == 0
            and request.portfolio_state.portfolio_id not in store.portfolios()
        ):
            store.register(request.portfolio_state)
        recomputed = propose_transition(request, pricing, market, key)
        assert recomputed.proposal_hash == recorded.proposal_hash
        store.commit(recorded, request)
        journals.setdefault(recorded.portfolio_id, []).extend(recorded.journals)
    for pid, final in expected["finalStates"].items():
        assert store.state(pid).compute_hash() == final["stateHash"]
        assert ledger_totals(journals[pid]) == expected["ledgerTotals"][pid]


def test_cli_replay_run_resume_report_and_parity(tmp_path, monkeypatch):
    monkeypatch.setenv(sim_cli.KEY_ENV, "cli-test-key")
    config = ReplayConfig(
        experiment_id="exp-cli",
        run_id="run-cli",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 9),
        strategies=[StrategySpec(strategy_id="cash"), StrategySpec(strategy_id="static_ladder")],
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config.to_wire()))
    run_dir = tmp_path / "run"
    ports = "tests.simulation.fakes:make_ports"
    assert (
        main(
            [
                "replay",
                "run",
                "--config",
                str(config_path),
                "--run-dir",
                str(run_dir),
                "--ports",
                ports,
            ]
        )
        == 0
    )
    assert main(["replay", "resume", "--run-dir", str(run_dir), "--ports", ports]) == 0
    assert main(["replay", "report", "--run-dir", str(run_dir)]) == 0
    assert (run_dir / "report.md").exists() and (run_dir / "report.json").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["generatedAt"] is not None and manifest["status"] == "completed"

    parity_config = tmp_path / "parity-config.json"
    parity_config.write_text(json.dumps(SHORT.to_wire()))
    out = tmp_path / "parity"
    assert (
        main(
            [
                "parity",
                "export",
                "--out",
                str(out),
                "--config",
                str(parity_config),
                "--ports",
                ports,
            ]
        )
        == 0
    )
    assert (out / "transitions.jsonl").exists() and (out / "expected.json").exists()


def test_cli_fails_clearly_without_ports_or_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(sim_cli.KEY_ENV, raising=False)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(SHORT.to_wire()))
    code = main(
        [
            "replay",
            "run",
            "--config",
            str(config_path),
            "--run-dir",
            str(tmp_path / "r"),
            "--ports",
            "tests.simulation.fakes:make_ports",
        ]
    )
    assert code == 3 and sim_cli.KEY_ENV in capsys.readouterr().err

    real_import = sim_cli.importlib.import_module

    def missing(name, *args):
        if name.startswith(("research_engine.pricing", "research_engine.market")):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import(name, *args)

    monkeypatch.setattr(sim_cli.importlib, "import_module", missing)
    with pytest.raises(sim_cli.PortsUnavailable, match="not importable yet"):
        sim_cli.default_ports()
    monkeypatch.delenv(sim_cli.PORTS_ENV, raising=False)
    code = main(["parity", "export", "--out", str(tmp_path / "p")])
    assert code == 3 and "numerical core" in capsys.readouterr().err
