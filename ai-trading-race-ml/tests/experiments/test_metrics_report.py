"""Metrics unavailability rules, attribution reconciliation, reports (spec 16.3, 17.1)."""

import json
from datetime import date
from decimal import Decimal

from research_engine.experiments.metrics import (
    max_drawdown,
    paired_block_bootstrap,
    portfolio_metrics,
    sharpe_ratio,
)
from research_engine.experiments.report import (
    build_run_report,
    combine_reports,
    load_run,
    render_markdown,
    write_report,
)
from research_engine.experiments.runner import ReplayConfig, ReplayRunner, StrategySpec
from tests.simulation.fakes import make_ports


def test_sharpe_unavailability_rules():
    returns = [0.001, -0.002, 0.0015] * 30  # 90 observations
    assert sharpe_ratio(returns, None)["unavailableReason"] == "missing_risk_free_series"
    assert sharpe_ratio(returns[:59], [0.0] * 59)["unavailableReason"] == "fewer_than_60_returns"
    flat = [0.0001] * 70
    assert sharpe_ratio(flat, [0.0] * 70)["unavailableReason"] == "zero_variance"
    ok = sharpe_ratio(returns, [0.0] * 90)
    assert ok["value"] is not None and ok["unavailableReason"] is None


def test_drawdown_and_recovery():
    dd = max_drawdown([100.0, 110.0, 99.0, 105.0, 111.0, 108.0])
    assert abs(dd["maxDrawdown"] - (99 / 110 - 1)) < 1e-12
    assert dd["recoveryObservations"] == 2 and dd["recovered"]
    unrecovered = max_drawdown([100.0, 90.0, 95.0])
    assert unrecovered["recoveryObservations"] is None and not unrecovered["recovered"]


def test_block_bootstrap_is_deterministic_and_declares_policy():
    a = [0.001 * ((i % 7) - 3) for i in range(40)]
    b = [0.0005 * ((i % 5) - 2) for i in range(40)]
    first = paired_block_bootstrap(a, b, seed=7)
    assert first == paired_block_bootstrap(a, b, seed=7)
    assert first["available"] and first["ciLow"] <= first["meanDifference"] <= first["ciHigh"]
    assert first["blockPolicy"]["method"] == "moving_block_bootstrap_v1"
    assert not paired_block_bootstrap(a[:6], b[:6])["available"]
    assert paired_block_bootstrap(a, b[:30])["reason"] == "unpaired_series"


def _replay(tmp_path, name="run", mode_kwargs=None, end=date(2024, 3, 8)):
    pricing, market = make_ports()
    config = ReplayConfig(
        experiment_id="exp-m",
        run_id=f"run-{name}",
        start_date=date(2024, 1, 2),
        end_date=end,
        strategies=[
            StrategySpec(strategy_id=s) for s in ("cash", "quant_duration", "static_ladder")
        ],
        **(mode_kwargs or {}),
    )
    runner = ReplayRunner(config, pricing, market, tmp_path / name, b"k")
    runner.run()
    return runner


def test_portfolio_metrics_reconcile_and_report_unavailability(tmp_path):
    runner = _replay(tmp_path)
    pid = runner._pid("static_ladder")
    outcomes = [o for o in runner.outcomes.values() if o.strategy_id == "static_ladder"]
    metrics = portfolio_metrics(runner.store.committed(pid), outcomes)
    attribution = metrics["attribution"]
    assert attribution["reconciles"]
    assert Decimal(attribution["residualUsd"]) == 0  # book equity reconciled to economic NAV
    assert metrics["annualizedReturn"] is None
    assert metrics["annualizedUnavailableReason"] == "fewer_than_252_returns"
    assert metrics["sharpe"]["value"] is None
    assert metrics["fillCount"] == 6 and Decimal(metrics["couponIncomeUsd"]) > 0
    assert metrics["grossReturn"] > metrics["netReturn"]  # costs are visible
    assert metrics["decisionCount"] == len(runner.sessions)
    assert Decimal(metrics["startEquityUsd"]) == Decimal("1000000.00")


def test_report_json_and_markdown(tmp_path):
    runner = _replay(tmp_path, end=date(2024, 1, 19))
    json_path, md_path = write_report(tmp_path / "run")
    report = json.loads(json_path.read_text())
    assert report["dataMode"] == "synthetic_curve"
    assert "SYNTHETIC" in report["dataModeLabel"]
    assert report["manifestVerified"]
    assert set(report["ranking"]) == {"cash", "quant_duration", "static_ladder"}
    assert report["limitations"]
    markdown = md_path.read_text()
    assert "model prices, not market quotes" in markdown and "## Limitations" in markdown
    assert runner.run_dir == tmp_path / "run"


def test_failed_decisions_stay_visible_and_incompatible_runs_are_not_ranked_together(tmp_path):
    pricing, market = make_ports(missing={date(2024, 1, 10)})
    config = ReplayConfig(
        experiment_id="exp-m",
        run_id="run-gap",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 19),
        strategies=[StrategySpec(strategy_id=s) for s in ("cash", "static_ladder")],
    )
    ReplayRunner(config, pricing, market, tmp_path / "gap", b"k").run()
    manifest, proposals, outcomes = load_run(tmp_path / "gap")
    report = build_run_report(manifest, proposals, outcomes)
    skipped = report["strategies"][0]["failedOrSkippedDecisions"]
    assert any(item["outcome"] == "skipped_stale_data" for item in skipped)
    assert "skipped_stale_data" in render_markdown(report) or report["exclusions"]

    other = dict(report)
    other.update(
        {
            "runId": "run-observed",
            "dataMode": "observed_security",
            "compatibilityKey": "observed_security|x|y|z|w",
        }
    )
    combined = combine_reports([report, other])
    assert len(combined["groups"]) == 2
    for group in combined["groups"]:
        assert {e["runId"] for e in group["ranking"]} <= set(group["runs"])
