"""Immutable experiment manifests (spec 6.5, 16.1).

A manifest is ``registered``/``running`` while a run progresses and becomes
immutable once ``completed`` or ``failed``: :func:`finalize_manifest` stamps
``manifest_hash`` (sha256 over the canonical wire form without the hash) and
any later attempt to finalize or amend it raises :class:`ManifestImmutable`.
Recovery never rewrites a finalized manifest (spec 15.3).
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import Field

from research_engine import ENGINE_VERSION
from research_engine.contracts.common import (
    SCHEMA_VERSION,
    ContentHash,
    ContractModel,
    DataMode,
    OpaqueId,
    UtcDatetime,
    content_hash,
    sha256_bytes,
)
from research_engine.contracts.portfolio import (
    EVENT_PRIORITY_TABLE_VERSION,
    ExecutionModel,
    RiskPolicy,
    TargetWeight,
)
from research_engine.simulation.clock import SCHEDULE
from research_engine.simulation.ledger import LOT_METHOD, POSTING_TEMPLATES

MANIFEST_VERSION = "experiment-manifest-v1"
SPEC_VERSION = "1.0"
CONFIG_SCHEMA_VERSION = "replay-config-v1"

ManifestStatus = Literal["registered", "running", "completed", "failed"]


class ManifestImmutable(RuntimeError):
    pass


class ArtifactRef(ContractModel):
    path: str
    checksum: ContentHash
    role: str = "artifact"


class CurveManifestEntry(ContractModel):
    session_date: date
    curve_snapshot_id: Optional[OpaqueId] = None
    content_hash: Optional[ContentHash] = None
    status: str


class StrategyManifestEntry(ContractModel):
    strategy_id: str
    kind: str
    invested: bool
    deterministic: bool
    config: dict[str, Any] = Field(default_factory=dict)
    config_hash: ContentHash
    provider: Optional[str] = None
    model_id: Optional[str] = None
    prompt_version: Optional[str] = None
    tool_schema_version: Optional[str] = None
    retrieval_mode: str = "none"
    index_build_id: Optional[str] = None
    evidence_snapshot_id: Optional[str] = None
    # deterministic_code | stored_strategy_result | recorded_responses:<provider>/<model>
    # | provider_call:<provider>/<model>[:captured]
    response_source: Optional[str] = None


class ExperimentManifest(ContractModel):
    manifest_version: str = MANIFEST_VERSION
    experiment_id: OpaqueId
    run_id: OpaqueId
    status: ManifestStatus = "registered"
    # Code and configuration versions
    git_commit: Optional[str] = None
    spec_version: str = SPEC_VERSION
    schema_version: str = SCHEMA_VERSION
    config_schema_version: str = CONFIG_SCHEMA_VERSION
    config_hash: Optional[ContentHash] = None
    dependency_lock_hashes: dict[str, str] = Field(default_factory=dict)
    engine_version: str = ENGINE_VERSION
    pricing_engine_version: Optional[str] = None
    event_priority_table: str = EVENT_PRIORITY_TABLE_VERSION
    posting_templates: list[str] = Field(default_factory=lambda: list(POSTING_TEMPLATES))
    lot_method: str = LOT_METHOD
    # Data
    data_mode: DataMode
    universe_version: OpaqueId
    terms_versions: dict[str, str] = Field(default_factory=dict)
    source_artifacts: list[ArtifactRef] = Field(default_factory=list)
    curve_manifests: list[CurveManifestEntry] = Field(default_factory=list)
    calendar_version: str = "us-gov-calendar-v1"
    convention_version: str = "conventions-v1"
    # Schedule, information and execution
    start_date: date
    end_date: date
    schedule: dict[str, str] = Field(default_factory=lambda: dict(SCHEDULE))
    decision_sessions: list[date] = Field(default_factory=list)
    information_policy: str
    execution_model: ExecutionModel
    cost_sensitivity_profiles: list[str] = Field(default_factory=list)
    settlement_config: dict[str, str] = Field(default_factory=dict)
    risk_policy: RiskPolicy
    cash_return_assumption: str = "zero_cash_interest_v1"
    # Strategies and AI configuration
    strategies: list[StrategyManifestEntry] = Field(default_factory=list)
    bootstrap_allocation_version: Optional[str] = None
    bootstrap_allocation: list[TargetWeight] = Field(default_factory=list)
    retrieval_versions: dict[str, str] = Field(default_factory=dict)
    response_mode: Literal["fresh_inference", "recorded_replay"] = "recorded_replay"
    # stored_strategy_results | recorded_provider_responses | fresh_provider_calls
    response_source: Optional[str] = None
    # Methodology
    splits: dict[str, Any] = Field(default_factory=dict)
    fitted_artifacts: list[ArtifactRef] = Field(default_factory=list)
    seeds: dict[str, int] = Field(default_factory=dict)
    repetitions: list[int] = Field(default_factory=lambda: [0])
    # Resources and outcomes
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    realized_usage: dict[str, Any] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    generated_at: Optional[UtcDatetime] = None
    manifest_hash: Optional[ContentHash] = None

    def hash_payload(self) -> dict:
        wire = self.to_wire()
        wire.pop("manifestHash", None)
        return wire

    @property
    def finalized(self) -> bool:
        return self.status in ("completed", "failed") and self.manifest_hash is not None


def file_checksum(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def dependency_lock_hashes(project_root: Path) -> dict[str, str]:
    """Hashes of dependency lock inputs (requirements.txt; pyproject.toml if present)."""
    out = {}
    for name in ("requirements.txt", "pyproject.toml"):
        path = Path(project_root) / name
        if path.exists():
            out[name] = file_checksum(path)
    return out


def git_commit(repo_root: Path) -> Optional[str]:
    """Read-only ``git rev-parse HEAD``; ``None`` when unavailable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def amend_manifest(manifest: ExperimentManifest, **updates) -> ExperimentManifest:
    """Return an updated copy of a not-yet-finalized manifest."""
    if manifest.finalized:
        raise ManifestImmutable(f"manifest {manifest.run_id} is finalized")
    return ExperimentManifest.model_validate({**manifest.model_dump(), **updates})


def finalize_manifest(
    manifest: ExperimentManifest, status: ManifestStatus = "completed", **updates
) -> ExperimentManifest:
    if status not in ("completed", "failed"):
        raise ValueError("finalized manifests are completed or failed")
    amended = amend_manifest(manifest, status=status, **updates)
    return amended.model_copy(update={"manifest_hash": content_hash(amended.hash_payload())})


def verify_manifest(manifest: ExperimentManifest) -> bool:
    return manifest.manifest_hash == content_hash(manifest.hash_payload())
