"""Operator-triggered background jobs: source ingestion and index builds (spec 14.2-14.3).

``POST`` returns ``202`` with the job record; ``GET /admin/jobs/{jobId}`` polls
it. Jobs run on one background worker, never inside a decision request. Index
builds create new immutable builds (never mutating an old manifest); a READY
build is loaded read-only into the engine and, when
``ML_SERVICE_ACTIVATE_INDEX_BUILDS`` is true, becomes the active index.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..common import json_response
from ..engine import Engine, evidence_snapshot_id, get_engine
from ..errors import not_found, unprocessable
from ..openapi_models import contract_body
from ..schemas import IndexBuildRequest, IngestionRequest
from ..wire import parse_model, read_object

router = APIRouter(prefix="/internal/v1/admin", tags=["admin"])

KNOWN_SOURCES = ("fed-fomc",)


def _home(engine: Engine):
    from research_engine.evidence.ingest import EvidenceHome

    state = engine.evidence
    with state.lock:
        if state.home is None:
            state.home = EvidenceHome.open(None)
        return state.home


def ingestion_job(engine: Engine, req: IngestionRequest) -> dict[str, Any]:
    from research_engine.evidence import fed
    from research_engine.evidence.fetch import AllowlistedFetcher
    from research_engine.evidence.ingest import FedIngestor

    home = _home(engine)
    online = engine.settings.ingestion_online
    results = []
    failed = False
    for source_id in req.source_ids:
        fetcher = AllowlistedFetcher(allowed_hosts=fed.ALLOWED_HOSTS) if online else None
        report = FedIngestor(home, offline=not online, fetcher=fetcher).run(
            include_synthetic=engine.settings.evidence_include_synthetic
        )
        source = home.store.get_source(source_id)
        outage = report.fetch_run.outcome.value == "outage"
        failed = failed or outage
        results.append(
            {
                "sourceId": source_id,
                "mode": "online" if online else "offline_fixture",
                "fetchRun": report.fetch_run.to_wire(),
                "newVersionIds": report.new_version_ids,
                "unchanged": len(report.unchanged_document_ids),
                "failed": report.failed,
                "quarantined": report.quarantined,
                "reviewRequired": report.review_required,
                "calendarProblems": report.calendar_problems,
                "sourceHealth": source.health.to_wire() if source else None,
            }
        )
    return {"sources": results, "failed": failed}


def index_build_job(engine: Engine, req: IndexBuildRequest) -> dict[str, Any]:
    from research_engine.knowledge.graph_store import InMemoryGraphStore
    from research_engine.retrieval import IndexNotReady, activate_index, build_index, load_index
    from research_engine.retrieval.index import rebuild_graph, select_members

    home = _home(engine)
    store = home.store
    members = None
    base = None
    if req.base_index_build_id:
        base = store.get_index_build(req.base_index_build_id)
        if base is None:
            return {"failed": True, "error": f"unknown base index build {req.base_index_build_id}"}
        members = list(base.member_version_ids)
    if req.evidence_snapshot_id:
        candidates = {}
        current = select_members(
            store, include_synthetic=engine.settings.evidence_include_synthetic
        )
        candidates[evidence_snapshot_id(current)] = current
        for build in store.list_index_builds():
            candidates.setdefault(
                evidence_snapshot_id(build.member_version_ids), list(build.member_version_ids)
            )
        if req.evidence_snapshot_id not in candidates:
            return {
                "failed": True,
                "error": f"unknown evidence snapshot {req.evidence_snapshot_id}",
            }
        if members is not None and sorted(members) != sorted(candidates[req.evidence_snapshot_id]):
            return {"failed": True, "error": "baseIndexBuildId and evidenceSnapshotId disagree"}
        members = candidates[req.evidence_snapshot_id]
    if req.validate_only:
        build_id = req.base_index_build_id or store.active_index_id()
        if not build_id:
            return {"failed": True, "error": "no build to validate (no base and no active index)"}
        try:
            index = load_index(store, build_id, graph=InMemoryGraphStore())
        except IndexNotReady as exc:
            return {"failed": True, "buildId": build_id, "valid": False, "error": str(exc)}
        rebuilt = rebuild_graph(store, index.build, InMemoryGraphStore())
        loaded = index.graph.membership(build_id) if index.graph else (set(), set())
        same = (frozenset(loaded[0]), frozenset(loaded[1])) == rebuilt.membership()
        valid = same and not index.graph_error
        return {
            "failed": not valid,
            "validateOnly": True,
            "buildId": build_id,
            "valid": valid,
            "embeddingMatrixReproduced": True,
            "graphRebuildMembershipEqual": same,
            "graphError": index.graph_error,
            "evidenceSnapshotId": evidence_snapshot_id(index.build.member_version_ids),
        }
    graph = InMemoryGraphStore()
    build = build_index(
        store,
        graph,
        member_version_ids=members,
        include_synthetic=engine.settings.evidence_include_synthetic,
    )
    result: dict[str, Any] = {
        "validateOnly": False,
        "buildId": build.build_id,
        "status": build.status.value,
        "evidenceSnapshotId": evidence_snapshot_id(build.member_version_ids),
        "memberVersionCount": len(build.member_version_ids),
        "chunkCount": build.member_chunk_count,
        "validationChecks": list(build.validation_checks),
        "error": build.error,
        "activated": False,
        "loaded": False,
    }
    if build.status.value != "READY":
        result["failed"] = True
        return result
    activate = engine.settings.activate_index_builds
    if activate and store.active_index_id() != build.build_id:
        activate_index(store, build.build_id)
    index = load_index(store, build.build_id, graph=graph)
    engine.evidence.attach(home, index, activate=activate)
    result.update(activated=activate, loaded=True, failed=False)
    return result


@router.post(
    "/ingestions",
    status_code=202,
    summary="Start an operator-triggered source ingestion job",
    openapi_extra=contract_body("IngestionRequest"),
)
async def ingestions(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    body = await read_object(request)
    req = parse_model(IngestionRequest, body)
    unknown = [s for s in req.source_ids if s not in KNOWN_SOURCES]
    if unknown:
        raise unprocessable(
            "unknown_source", f"unknown source ids {unknown}; known: {list(KNOWN_SOURCES)}"
        )
    job, created = engine.jobs.submit(
        "ingestion", req.request_id, req.to_wire(), lambda: ingestion_job(engine, req)
    )
    return json_response(job.to_wire(), status=202 if created else 200)


@router.post(
    "/index-builds",
    status_code=202,
    summary="Start an index build or validation job (never mutates an old manifest)",
    openapi_extra=contract_body("IndexBuildRequest"),
)
async def index_builds(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    body = await read_object(request)
    req = parse_model(IndexBuildRequest, body)
    job, created = engine.jobs.submit(
        "index_build", req.request_id, req.to_wire(), lambda: index_build_job(engine, req)
    )
    return json_response(job.to_wire(), status=202 if created else 200)


@router.get("/jobs/{job_id}", summary="Background job status and result")
async def job_status(job_id: str, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    job = engine.jobs.get(job_id)
    if job is None:
        raise not_found("unknown_job", f"job {job_id!r} does not exist")
    return json_response(job.to_wire())
