"""Dataset release gate (spec 7.3).

Produces a coverage summary, missingness report, revision policy,
timestamp-confidence report, market-mode label and checksum manifest. Only a
dataset with ``eligible_for_benchmark=True`` may back a benchmark comparison;
a failing dataset may be kept for debugging.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Optional

from research_engine.contracts.common import DataMode, InformationPolicy, content_hash, short_id
from research_engine.contracts.market import (
    ArtifactChecksum,
    CoverageReport,
    CurveBuildSummary,
    CurveObservation,
    CurveStatus,
    DatasetAdmissionReport,
    TenorCoverage,
)
from research_engine.instruments.calendar import CALENDAR_ID, business_days_between

from .paths import treasury_fixture_dir
from .store import DEFAULT_DATASET_ID, CurveMarketDataPort
from .treasury import (
    SOURCE_ID,
    TreasuryDataset,
    load_manifest,
    tenor_sort_key,
    verify_artifact,
)

RATIO_Q = Decimal("1e-6")
MIN_SESSION_COVERAGE = Decimal("0.98")
MAX_MISSING_VALUE_RATIO = Decimal("0.02")
MIN_READY_RATIO = Decimal("0.98")

REVISION_POLICY = (
    "Treasury daily par yield CSVs are frozen as retrieved (sha256 manifest). Treasury does "
    "not publish a vintage history for these files, so later revisions cannot be "
    "reconstructed point-in-time; a re-download with different bytes is stored as a separate "
    "artifact and flagged as a conflict, never silently merged. Macro series use ALFRED "
    "vintages selected at the decision cutoff."
)


def coverage_report(
    observations: Mapping[date, CurveObservation],
    start: date,
    end: date,
    *,
    calendar_id: str = CALENDAR_ID,
    source_id: str = SOURCE_ID,
) -> CoverageReport:
    expected = business_days_between(start, end, calendar_id)
    expected_set = set(expected)
    in_window = {d: o for d, o in observations.items() if start <= d <= end}
    observed = [d for d in expected if d in in_window]
    off_calendar = sorted(d for d in in_window if d not in expected_set)
    present: Counter[str] = Counter()
    values: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    order: dict[str, Decimal] = {}
    for obs in in_window.values():
        for point in obs.points:
            present[point.tenor] += 1
            values[point.tenor] += 1
            order[point.tenor] = tenor_sort_key(point.period_count, point.period_unit)
        for tenor in obs.missing_tenors:
            present[tenor] += 1
            missing[tenor] += 1
    tenors = sorted(present, key=lambda t: order.get(t, Decimal(10**6)))
    total_cells = sum(present.values())
    return CoverageReport(
        source_id=source_id,
        start=start,
        end=end,
        calendar_id=calendar_id,
        expected_sessions=len(expected),
        observed_sessions=len(observed),
        missing_sessions=[d for d in expected if d not in in_window],
        observations_on_non_business_days=off_calendar,
        tenor_coverage=[
            TenorCoverage(
                tenor=t,
                columns_present_sessions=present[t],
                observed_values=values[t],
                missing_values=missing[t],
            )
            for t in tenors
        ],
        session_coverage_ratio=(
            (Decimal(len(observed)) / Decimal(len(expected))).quantize(RATIO_Q)
            if expected
            else Decimal(0)
        ),
        missing_value_ratio=(
            (Decimal(sum(missing.values())) / Decimal(total_cells)).quantize(RATIO_Q)
            if total_cells
            else Decimal(0)
        ),
    )


def checksum_manifest(root: Optional[Path] = None) -> list[ArtifactChecksum]:
    root = Path(root or treasury_fixture_dir())
    out = []
    for entry in load_manifest(root)["artifacts"]:
        ok, actual = verify_artifact(root, entry)
        out.append(
            ArtifactChecksum(
                artifact_id=entry["artifactId"],
                local_path=f"market/treasury/{entry['localPath']}",
                expected_sha256=entry["sha256"],
                actual_sha256=actual if actual.startswith("sha256:") else None,
                size_bytes=entry["sizeBytes"],
                verified=ok,
            )
        )
    return out


def curve_build_summary(market: CurveMarketDataPort, start: date, end: date) -> CurveBuildSummary:
    ready = failed = 0
    failed_sessions: list[date] = []
    reasons: Counter[str] = Counter()
    max_res = Decimal(0)
    for day in market.sessions(start, end):
        snap = market.curve_snapshot_for_session(day)
        if snap is None:
            continue
        if snap.status is CurveStatus.READY:
            ready += 1
            if snap.max_abs_price_residual_per_100 is not None:
                max_res = max(max_res, snap.max_abs_price_residual_per_100)
        else:
            failed += 1
            failed_sessions.append(day)
            for reason in snap.failure_reasons:
                reasons[reason.split(":", 1)[0]] += 1
    return CurveBuildSummary(
        sessions_attempted=ready + failed,
        ready=ready,
        failed=failed,
        failed_sessions=failed_sessions,
        failure_reason_counts=dict(sorted(reasons.items())),
        max_abs_price_residual_per_100=max_res,
    )


def build_dataset_admission_report(
    dataset: TreasuryDataset,
    start: date,
    end: date,
    *,
    market: Optional[CurveMarketDataPort] = None,
    root: Optional[Path] = None,
    dataset_id: str = DEFAULT_DATASET_ID,
    market_mode: DataMode = DataMode.SYNTHETIC_CURVE,
) -> DatasetAdmissionReport:
    coverage = coverage_report(dataset.observations, start, end)
    checksums = checksum_manifest(root)
    gate_failures: list[str] = []
    warnings: list[str] = [
        "available_at is reconstructed (session 18:00 America/New_York), not a verified "
        "publication instant",
        "Treasury par yields are indicative bid-side inputs, not executable security quotes",
    ]
    if not checksums:
        gate_failures.append("checksum_manifest_empty")
    for item in checksums:
        if not item.verified:
            gate_failures.append(f"checksum_mismatch:{item.local_path}")
    if coverage.session_coverage_ratio < MIN_SESSION_COVERAGE:
        gate_failures.append(
            f"session_coverage {coverage.session_coverage_ratio} < {MIN_SESSION_COVERAGE}"
        )
    if coverage.missing_value_ratio > MAX_MISSING_VALUE_RATIO:
        gate_failures.append(
            f"missing_value_ratio {coverage.missing_value_ratio} > {MAX_MISSING_VALUE_RATIO}"
        )
    if coverage.observations_on_non_business_days:
        warnings.append(
            f"{len(coverage.observations_on_non_business_days)} observations on calendar "
            "non-business days (kept, flagged)"
        )
    if dataset.conflicts:
        gate_failures.append(f"conflicting_revisions:{len(dataset.conflicts)}")
    summary = None
    universe_id = universe_hash = None
    if market is not None:
        summary = curve_build_summary(market, start, end)
        attempted = summary.sessions_attempted
        ready_ratio = Decimal(summary.ready) / Decimal(attempted) if attempted else Decimal(0)
        if ready_ratio < MIN_READY_RATIO:
            gate_failures.append(f"curve_ready_ratio {ready_ratio.quantize(RATIO_Q)} too low")
        universe_id = market.universe_contract.universe_id
        universe_hash = market.universe_hash
        if market.universe_contract.classification.value == "synthetic":
            warnings.append("instrument universe is hypothetical (synthetic_curve mode)")
    else:
        gate_failures.append("curve_builds_not_evaluated")
    missingness = {
        t.tenor: str(
            (Decimal(t.missing_values) / Decimal(t.columns_present_sessions)).quantize(RATIO_Q)
        )
        for t in coverage.tenor_coverage
    }
    missingness["_sessions_missing"] = str(len(coverage.missing_sessions))
    label = (
        "SYNTHETIC CURVE SIMULATION: hypothetical instruments priced from observed Treasury par "
        "curves; model prices are not market quotes"
        if market_mode is DataMode.SYNTHETIC_CURVE
        else "OBSERVED SECURITY"
    )
    version = short_id(
        "dsv",
        {
            "datasetId": dataset_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "artifacts": sorted(c.expected_sha256 for c in checksums),
            "universeHash": universe_hash,
        },
    )
    report = DatasetAdmissionReport(
        dataset_id=dataset_id,
        dataset_version=version,
        market_mode=market_mode,
        market_mode_label=label,
        coverage=coverage,
        missingness=missingness,
        revision_policy=REVISION_POLICY,
        timestamp_confidence={
            "observed_at": "declared convention: session 15:30 America/New_York",
            "published_at": "unknown for historical sessions (not recorded)",
            "available_at": "reconstructed: session 18:00 America/New_York "
            "(reconstructed_publication_plus_lag_v1)",
            "ingested_at": "verified: retrieval time of the raw artifact",
        },
        information_policy=InformationPolicy.RECONSTRUCTED_PUBLICATION_PLUS_LAG,
        checksum_manifest=checksums,
        curve_builds=summary,
        instrument_universe_id=universe_id,
        instrument_universe_hash=universe_hash,
        eligible_for_benchmark=not gate_failures,
        gate_failures=gate_failures,
        warnings=warnings,
    )
    return report.model_copy(update={"content_hash": content_hash(report)})
