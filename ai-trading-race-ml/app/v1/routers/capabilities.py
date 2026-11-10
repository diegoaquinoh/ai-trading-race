"""``GET /internal/v1/capabilities``: engine, schema, convention and readiness detail.

Reports configured providers/models but never credentials. ``ready`` means the
numerical engine is loaded and results can be signed; evidence readiness is
reported separately (decisions that need evidence return 503 until it is READY).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.config import environment
from research_engine import ENGINE_VERSION as RESEARCH_ENGINE_VERSION
from research_engine.contracts.common import SCHEMA_VERSION, utc_to_str
from research_engine.contracts.decisions import RetrievalMode
from research_engine.contracts.portfolio import EVENT_PRIORITY_TABLE_VERSION
from research_engine.pricing.quantlib_env import (
    CONVENTIONS_VERSION,
    ENGINE_VERSION as NUMERICAL_ENGINE_VERSION,
    LIBRARY,
    QUANTLIB_VERSION,
)
from research_engine.risk.scenarios import SCENARIO_LIBRARY_V1
from research_engine.simulation.clock import SCHEDULE
from research_engine.simulation.engine import SIMULATION_VERSION, engine_version

from ..common import in_threadpool, json_response
from ..engine import Engine, evidence_snapshot_id, get_engine

router = APIRouter(prefix="/internal/v1", tags=["capabilities"])

ENDPOINTS = [
    "POST /internal/v1/simulation/transitions",
    "POST /internal/v1/simulation/bootstrap-allocation",
    "POST /internal/v1/strategies/decisions",
    "POST /internal/v1/analytics/price",
    "POST /internal/v1/analytics/risk",
    "POST /internal/v1/analytics/performance",
    "POST /internal/v1/evidence/retrieve",
    "GET /internal/v1/evidence/bundles/{bundleId}",
    "GET /internal/v1/evidence/chunks/{chunkId}",
    "GET /internal/v1/evidence/graph?bundleId=",
    "POST /internal/v1/research-notes",
    "POST /internal/v1/admin/ingestions",
    "POST /internal/v1/admin/index-builds",
    "GET /internal/v1/admin/jobs/{jobId}",
    "GET /internal/v1/market/sessions",
    "GET /internal/v1/curves/{snapshotId}",
    "GET /internal/v1/instruments",
    "GET /internal/v1/instruments/{securityId}/valuation",
    "POST /internal/v1/instruments/payment-calendar",
    "GET /internal/v1/capabilities",
]


def _market(engine: Engine) -> dict[str, Any]:
    from research_engine.market.admission import coverage_report
    from research_engine.market.treasury import default_treasury_dataset

    market = engine.market
    coverage = coverage_report(default_treasury_dataset().observations, market.start, market.end)
    admission = engine.warmup.get("admission")
    curve_builds = None
    admission_status = "not_evaluated"
    gate_failures: list[str] = []
    if admission is not None:
        gate_failures = list(getattr(admission, "gate_failures", []) or [])
        eligible = getattr(admission, "eligible_for_benchmark", None)
        admission_status = "admitted" if eligible else "not_admitted"
        if admission.curve_builds is not None:
            curve_builds = admission.curve_builds.to_wire()
    return {
        "dataMode": market.data_mode.value,
        "datasetId": market.dataset_id,
        "start": market.start.isoformat(),
        "end": market.end.isoformat(),
        "calendarId": market.calendar_id,
        "curveSpecification": f"{market.spec.spec_id}:{market.spec.version}",
        "coverage": {
            "expectedSessions": coverage.expected_sessions,
            "observedSessions": coverage.observed_sessions,
            "missingSessions": len(coverage.missing_sessions),
            "sessionCoverageRatio": str(coverage.session_coverage_ratio),
            "missingValueRatio": str(coverage.missing_value_ratio),
        },
        "curveWarmup": engine.warmup.get("curves"),
        "curveBuilds": curve_builds,
        "admissionStatus": admission_status,
        "gateFailures": gate_failures,
        "informationPolicy": "reconstructed_publication_plus_lag_v1",
    }


def _evidence(engine: Engine) -> dict[str, Any]:
    state = engine.evidence
    builds = []
    with state.lock:
        loaded = dict(state.indexes)
        active = state.active_build_id
        home = state.home
    for build_id, index in sorted(loaded.items()):
        build = index.build
        builds.append(
            {
                "buildId": build_id,
                "status": build.status.value,
                "active": build_id == active,
                "evidenceSnapshotId": evidence_snapshot_id(build.member_version_ids),
                "memberVersionCount": len(build.member_version_ids),
                "chunkCount": build.member_chunk_count,
                "embeddingModel": f"{build.embedding_provider}:{build.embedding_model}",
                "graphBackend": build.graph_backend,
                "graphReady": index.graph_error is None,
                "includesSynthetic": build.includes_synthetic,
                "createdAt": utc_to_str(build.created_at),
            }
        )
    sources = []
    if home is not None:
        from research_engine.evidence import fed

        for source_id in (fed.SOURCE_ID,):
            source = home.store.get_source(source_id)
            runs = home.store.list_fetch_runs(source_id)
            last = runs[-1] if runs else None
            health = source.health if source is not None else None
            sources.append(
                {
                    "sourceId": source_id,
                    "name": source.name if source is not None else None,
                    "health": health.to_wire() if health is not None else None,
                    "lastIngestion": (
                        {
                            "fetchRunId": last.fetch_run_id,
                            "outcome": last.outcome.value,
                            "mode": last.mode,
                            "startedAt": utc_to_str(last.started_at),
                            "completedAt": utc_to_str(last.completed_at),
                            "newVersions": last.items_new_versions,
                            "failed": last.items_failed,
                        }
                        if last is not None
                        else None
                    ),
                    "outage": bool(last is not None and last.outcome.value == "outage"),
                    "recentOutages": sum(1 for r in runs[-20:] if r.outcome.value == "outage"),
                }
            )
    return {
        "status": state.status,
        "ready": bool(loaded),
        "error": state.error,
        "activeIndexBuildId": active,
        "readyIndexBuilds": builds,
        "evidenceSnapshotIds": sorted({b["evidenceSnapshotId"] for b in builds}),
        "sources": sources,
        "retrievalModes": [m.value for m in RetrievalMode],
        "recentJobs": [
            {"jobId": j.job_id, "kind": j.kind, "state": j.state.value}
            for j in engine.jobs.recent(limit=10)
        ],
    }


def capabilities_document(engine: Engine) -> dict[str, Any]:
    contract = engine.market.universe_contract
    signing_ok = engine.signing_key is not None
    return {
        "engineVersion": engine_version(engine.pricing),
        "ready": signing_ok,
        "schemaVersions": [SCHEMA_VERSION],
        "environment": environment(),
        "researchEngineVersion": RESEARCH_ENGINE_VERSION,
        "numerical": {
            "ready": True,
            "engineVersion": NUMERICAL_ENGINE_VERSION,
            "library": LIBRARY,
            "quantlibVersion": QUANTLIB_VERSION,
            "conventionsVersion": CONVENTIONS_VERSION,
            "simulationVersion": SIMULATION_VERSION,
            "eventPriorityTable": EVENT_PRIORITY_TABLE_VERSION,
            "schedule": SCHEDULE,
            "quantlibSettingsIsolation": "process-wide lock around evaluation-date blocks",
            "scenarios": sorted(SCENARIO_LIBRARY_V1),
            "priceType": (
                "curve_model" if engine.market.data_mode.value == "synthetic_curve" else "observed"
            ),
        },
        "conventions": {
            "dayCount": "ACT/ACT-ICMA",
            "yieldConvention": "street_semiannual_act_act_icma_v1",
            "settlementLagBusinessDays": 1,
            "calendarId": engine.market.calendar_id,
            "wireFormat": "camelCase JSON, decimal strings, UTC Z instants, ISO dates",
            "hash": "sha256 over canonical JSON",
            "signature": "hmac-sha256 over the hash string",
        },
        "instruments": {
            "universeId": contract.universe_id,
            "universeVersion": contract.version,
            "classification": contract.classification.value,
            "count": len(contract.securities),
            "universeHash": engine.market.universe_hash,
        },
        "curveDataset": _market(engine),
        "evidence": _evidence(engine),
        "providers": engine.strategies.describe(),
        "strategies": engine.strategies.describe_strategies(),
        "signing": {
            "configured": engine.signing_configured,
            "available": signing_ok,
            "developmentKey": signing_ok and not engine.signing_configured,
            "algorithm": "hmac-sha256",
            "signs": ["TransitionProposal", "StrategyResult"],
            "error": engine.signing_error,
        },
        "concurrency": {
            "maxConcurrentDecisions": engine.max_decisions,
            "decisionsInFlight": engine.decisions_in_flight,
            "retryAfterSeconds": engine.settings.decision_retry_after_seconds,
        },
        "endpoints": ENDPOINTS,
        "startedAt": utc_to_str(engine.started_at),
    }


@router.get("/capabilities", summary="Engine/model/schema/convention capabilities and readiness")
async def capabilities(engine: Engine = Depends(get_engine)) -> Response:
    return json_response(await in_threadpool(capabilities_document, engine))
