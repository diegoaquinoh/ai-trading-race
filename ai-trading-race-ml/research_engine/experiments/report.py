"""Replay reports: JSON + Markdown (spec 16.2, 16.3, 17.1).

* Every report carries the data-mode label; synthetic-curve runs state that
  execution prices are model observations, not market quotes.
* Failed, skipped and missing decisions remain visible per strategy.
* Runs are ranked only inside a compatibility group (data mode, execution
  model, risk policy, evaluation window); incompatible groups are listed
  separately and never ranked together.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from research_engine.contracts.common import DataMode
from research_engine.contracts.decisions import DecisionOutcome, StrategyResult
from research_engine.contracts.portfolio import TransitionProposal

from .manifest import ExperimentManifest, verify_manifest
from .metrics import paired_block_bootstrap, portfolio_metrics

REPORT_VERSION = "replay-report-v1"

LIMITATIONS = {
    DataMode.SYNTHETIC_CURVE.value: [
        "Synthetic instruments priced from curve inputs; execution prices are model "
        "observations plus declared half-spread, not market quotes.",
        "Same-curve marks and fills: any rich/cheap signal is mechanically neutral.",
        "Spread assumptions (0.00/0.02/0.05 per 100 face) are illustrative, not measured costs.",
        "Daily-only data: fills are labelled next-session close observations.",
        "Short replays do not support statistical significance claims.",
    ],
    DataMode.OBSERVED_SECURITY.value: [
        "Observed quotes may be indicative; capacity/depth is not modelled.",
        "Short replays do not support statistical significance claims.",
    ],
}
COMMON_LIMITATIONS = [
    "Retrospective LLM runs may reflect pretrained knowledge of later events.",
    "Cash earns the configured cash return only (fixture: zero).",
]


def load_run(
    run_dir: Path,
) -> tuple[ExperimentManifest, list[TransitionProposal], list[StrategyResult]]:
    run_dir = Path(run_dir)
    manifest = ExperimentManifest.model_validate_json((run_dir / "manifest.json").read_text())
    proposals: list[TransitionProposal] = []
    commits = run_dir / "commits.jsonl"
    if commits.exists():
        for line in commits.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                if record.get("kind") == "commit":
                    proposals.append(TransitionProposal.model_validate(record["proposal"]))
    outcomes: list[StrategyResult] = []
    path = run_dir / "outcomes.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                outcomes.append(StrategyResult.model_validate(json.loads(line)["result"]))
    return manifest, proposals, outcomes


def compatibility_key(manifest: ExperimentManifest) -> str:
    return "|".join(
        [
            manifest.data_mode.value,
            manifest.execution_model.execution_model_id,
            manifest.risk_policy.policy_id,
            manifest.start_date.isoformat(),
            manifest.end_date.isoformat(),
        ]
    )


def build_run_report(
    manifest: ExperimentManifest,
    proposals: Iterable[TransitionProposal],
    outcomes: Iterable[StrategyResult],
    *,
    risk_free=None,
) -> dict:
    proposals = list(proposals)
    outcomes = list(outcomes)
    strategies = []
    returns_by_strategy: dict[str, list[float]] = {}
    for entry in manifest.strategies:
        sid = entry.strategy_id
        own = [p for p in proposals if p.strategy_id == sid]
        own_outcomes = [o for o in outcomes if o.strategy_id == sid]
        metrics = portfolio_metrics(own, own_outcomes, risk_free=risk_free)
        returns_by_strategy[sid] = metrics.pop("dailyReturns", [])
        failed = [
            {"decisionId": o.decision_id, "outcome": o.outcome.value, "reasons": o.reasons}
            for o in own_outcomes
            if o.outcome not in (DecisionOutcome.COMPLETED_HOLD, DecisionOutcome.COMPLETED_PROPOSAL)
        ]
        rejected = [
            {
                "decisionId": p.policy_evaluation.decision_id,
                "reasons": p.policy_evaluation.rejected_reasons,
            }
            for p in own
            if p.policy_evaluation is not None and not p.policy_evaluation.passed
        ]
        expected = len(manifest.decision_sessions)
        strategies.append(
            {
                "strategyId": sid,
                "kind": entry.kind,
                "invested": entry.invested,
                "configHash": entry.config_hash,
                "metrics": metrics,
                "failedOrSkippedDecisions": failed,
                "rejectedProposals": rejected,
                "missingDecisions": max(expected - len(own_outcomes), 0),
            }
        )
    ranked = sorted(
        (s for s in strategies if s["metrics"].get("netReturn") is not None),
        key=lambda s: (-s["metrics"]["netReturn"], s["strategyId"]),
    )
    comparisons = []
    reference = "cash" if "cash" in returns_by_strategy else None
    if reference:
        for sid, series in sorted(returns_by_strategy.items()):
            if sid == reference:
                continue
            comparisons.append(
                {
                    "strategyId": sid,
                    "versus": reference,
                    **paired_block_bootstrap(series, returns_by_strategy[reference]),
                }
            )
    mode = manifest.data_mode.value
    return {
        "reportVersion": REPORT_VERSION,
        "experimentId": manifest.experiment_id,
        "runId": manifest.run_id,
        "status": manifest.status,
        "manifestHash": manifest.manifest_hash,
        "manifestVerified": verify_manifest(manifest) if manifest.manifest_hash else False,
        "dataMode": mode,
        "dataModeLabel": (
            "SYNTHETIC CURVE SIMULATION (model prices, not market quotes)"
            if mode == DataMode.SYNTHETIC_CURVE.value
            else "OBSERVED SECURITY QUOTES"
        ),
        "responseMode": manifest.response_mode,
        "responseSource": manifest.response_source,
        "strategyResponseSources": {e.strategy_id: e.response_source for e in manifest.strategies},
        "compatibilityKey": compatibility_key(manifest),
        "window": {
            "start": manifest.start_date.isoformat(),
            "end": manifest.end_date.isoformat(),
            "sessions": len(manifest.decision_sessions),
        },
        "executionModel": manifest.execution_model.execution_model_id,
        "riskPolicy": manifest.risk_policy.policy_id,
        "strategies": strategies,
        "ranking": [s["strategyId"] for s in ranked],
        "pairedComparisons": comparisons,
        "failures": manifest.failures,
        "exclusions": manifest.exclusions,
        "limitations": LIMITATIONS.get(mode, []) + COMMON_LIMITATIONS,
    }


def combine_reports(reports: Iterable[dict]) -> dict:
    """Group run reports by compatibility; rank only within a group."""
    groups: dict[str, list[dict]] = {}
    for report in reports:
        groups.setdefault(report["compatibilityKey"], []).append(report)
    out = []
    for key in sorted(groups):
        members = groups[key]
        entries = [
            {
                "runId": r["runId"],
                "strategyId": s["strategyId"],
                "netReturn": s["metrics"].get("netReturn"),
            }
            for r in members
            for s in r["strategies"]
        ]
        ranked = sorted(
            (e for e in entries if e["netReturn"] is not None),
            key=lambda e: (-e["netReturn"], e["runId"], e["strategyId"]),
        )
        out.append(
            {
                "compatibilityKey": key,
                "dataMode": members[0]["dataMode"],
                "runs": [r["runId"] for r in members],
                "ranking": ranked,
            }
        )
    return {
        "reportVersion": REPORT_VERSION,
        "groups": out,
        "note": (
            "Groups differ in data mode, cost policy, risk policy or window and are never "
            "ranked together."
        ),
    }


def _fmt(value, pct=False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value * 100:.3f}%" if pct else f"{value:.4f}"
    return str(value)


def render_markdown(report: dict) -> str:
    lines = [
        f"# Replay report — {report['runId']}",
        "",
        f"**Data mode:** {report['dataModeLabel']}  ",
        f"**Status:** {report['status']} · **Response mode:** {report['responseMode']}"
        + (f" ({report['responseSource']})" if report.get("responseSource") else "")
        + "  ",
        f"**Window:** {report['window']['start']} → {report['window']['end']} "
        f"({report['window']['sessions']} sessions)  ",
        f"**Execution model:** {report['executionModel']} · "
        f"**Risk policy:** {report['riskPolicy']}  ",
        f"**Manifest:** `{report['manifestHash']}` (verified: {report['manifestVerified']})",
        "",
        "## Results (ranked within this compatibility group only)",
        "",
        "| Strategy | Net return | Gross return | Max drawdown | Fills | Expiries | Rejections | "
        "Avg DV01 | End duration | Costs (USD) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    by_id = {s["strategyId"]: s for s in report["strategies"]}
    order = report["ranking"] + [s for s in by_id if s not in report["ranking"]]
    for sid in order:
        m = by_id[sid]["metrics"]
        dd = (m.get("drawdown") or {}).get("maxDrawdown")
        costs = None
        if m.get("spreadCostUsd") is not None:
            costs = f"{m['spreadCostUsd']} spread + {m['feesUsd']} fees"
        lines.append(
            f"| {sid} | {_fmt(m.get('netReturn'), True)} | {_fmt(m.get('grossReturn'), True)} | "
            f"{_fmt(dd, True)} | {m.get('fillCount', 0)} | {m.get('expiryCount', 0)} | "
            f"{m.get('policyRejections', 0)} | {_fmt(m.get('averageDv01Usd'))} | "
            f"{_fmt(m.get('endEffectiveDurationYears'))} | {costs or 'n/a'} |"
        )
    lines += ["", "## Decisions, failures and exclusions", ""]
    for sid in order:
        entry = by_id[sid]
        m = entry["metrics"]
        lines.append(
            f"- **{sid}**: {m.get('decisionCount', 0)} decisions {m.get('decisionOutcomes', {})}; "
            f"{len(entry['failedOrSkippedDecisions'])} failed/skipped; "
            f"{len(entry['rejectedProposals'])} rejected proposals; "
            f"{entry['missingDecisions']} missing."
        )
        attribution = m.get("attribution")
        if attribution:
            lines.append(
                f"  - Attribution: carry {attribution['carryUsd']}, "
                f"price {attribution['priceUsd']}, "
                f"costs {attribution['costsUsd']}, residual {attribution['residualUsd']} "
                f"(total {attribution['totalUsd']})"
            )
        sharpe = m.get("sharpe") or {}
        lines.append(
            f"  - Sharpe: {_fmt(sharpe.get('value'))}"
            + (
                f" (unavailable: {sharpe.get('unavailableReason')})"
                if sharpe.get("value") is None
                else ""
            )
        )
    if report["failures"]:
        lines += ["", "Run failures:"] + [f"- {f}" for f in report["failures"]]
    if report["exclusions"]:
        lines += ["", "Exclusions:"] + [f"- {e}" for e in report["exclusions"]]
    if report["pairedComparisons"]:
        lines += ["", "## Paired comparisons (block bootstrap; not significance claims)", ""]
        for c in report["pairedComparisons"]:
            if c.get("available"):
                lines.append(
                    f"- {c['strategyId']} vs {c['versus']}: "
                    f"mean daily diff {c['meanDifference']:.6f} "
                    f"[{c['ciLow']:.6f}, {c['ciHigh']:.6f}] "
                    f"(block {c['blockPolicy']['blockLength']})"
                )
            else:
                lines.append(f"- {c['strategyId']} vs {c['versus']}: unavailable ({c['reason']})")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def write_report(
    run_dir: Path, out_dir: Optional[Path] = None, *, risk_free=None
) -> tuple[Path, Path]:
    manifest, proposals, outcomes = load_run(run_dir)
    report = build_run_report(manifest, proposals, outcomes, risk_free=risk_free)
    out = Path(out_dir or run_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "report.json"
    md_path = out / "report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    md_path.write_text(render_markdown(report))
    return json_path, md_path
