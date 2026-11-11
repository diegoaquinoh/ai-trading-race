"""Evidence endpoints: retrieval, bundles, chunks, bounded graph provenance, research notes.

Retrieval uses an already loaded READY index (503 if none) and never ingests or
builds. An *evidence snapshot* is the exact document-version set of a corpus
manifest (``evs-...``); capabilities lists the snapshot of every READY build.
Research notes are informational: they never contain orders or target weights.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from research_engine.contracts.common import short_id, utc_to_str
from research_engine.contracts.decisions import (
    Citation,
    DocumentaryClaim,
    ResearchNote,
    ResearchStatus,
    RetrievalMode,
)
from research_engine.contracts.evidence import RetrievalBudget, RetrievalRequest

from ..common import in_threadpool, json_response, page_bounds
from ..engine import Engine, evidence_snapshot_id, get_engine
from ..errors import not_found, unavailable, unprocessable
from ..openapi_models import contract_body
from ..schemas import EvidenceRetrieveRequest, ResearchNoteRequest
from ..strategies import ProviderUnavailable
from ..wire import parse_model, read_object

router = APIRouter(prefix="/internal/v1", tags=["evidence"])

MAX_GRAPH_NODES = 200
MAX_GRAPH_EDGES = 300
NOTE_METHOD = "reference-extractive-note-v1"
MAX_NOTE_CLAIMS = 4


def permission_scope(experiment_id: Optional[str], strategy_id: Optional[str]) -> str:
    parts = ["public"]
    if experiment_id:
        parts.append(f"experiment:{experiment_id}")
    if strategy_id:
        parts.append(f"strategy:{strategy_id}")
    return "|".join(parts)


def run_retrieval(
    engine: Engine,
    *,
    question: str,
    as_of: datetime,
    mode: RetrievalMode,
    evidence_snapshot: Optional[str],
    index_build_id: Optional[str],
    max_chunks: int = 12,
    scope: str = "public",
):
    from research_engine.knowledge.graph_store import GraphRetrievalUnavailable
    from research_engine.retrieval import IndexNotReady, retrieve

    index = engine.evidence.resolve(evidence_snapshot, index_build_id)
    request = RetrievalRequest(
        question=question,
        decision_as_of=as_of,
        mode=mode,
        index_build_id=index.build_id,
        permission_scope=scope,
        budget=RetrievalBudget(max_chunks=max_chunks),
    )
    try:
        run, bundle = retrieve(request, engine.evidence.store, index)
    except GraphRetrievalUnavailable as exc:
        raise unavailable("graph_unavailable", str(exc)) from exc
    except IndexNotReady as exc:
        raise unavailable("evidence_index_unavailable", str(exc)) from exc
    return index, run, bundle


@router.post(
    "/evidence/retrieve",
    summary="Retrieve a scoped evidence bundle at a strict cutoff",
    openapi_extra=contract_body("EvidenceRetrieveRequest"),
)
async def evidence_retrieve(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    body = await read_object(request)
    req = parse_model(EvidenceRetrieveRequest, body)
    engine.requests.bind("evidence.retrieve", req.request_id, req.to_wire())
    index, run, bundle = await in_threadpool(
        run_retrieval,
        engine,
        question=req.query,
        as_of=req.as_of,
        mode=req.retrieval_mode,
        evidence_snapshot=req.evidence_snapshot_id,
        index_build_id=req.index_build_id,
        max_chunks=req.max_chunks,
        scope=permission_scope(req.experiment_id, req.strategy_id),
    )
    return json_response(
        {
            "schemaVersion": req.schema_version,
            "requestId": req.request_id,
            "evidenceSnapshotId": evidence_snapshot_id(index.build.member_version_ids),
            "indexBuildId": index.build_id,
            "retrievalRun": run.to_wire(),
            "bundle": bundle.to_wire(),
        }
    )


@router.get("/evidence/bundles/{bundle_id}", summary="Delivered passages and provenance (paged)")
async def evidence_bundle(
    bundle_id: str,
    page: int = Query(1),
    pageSize: int = Query(50),
    engine: Engine = Depends(get_engine),
) -> Response:
    engine.require_signing()
    start, stop = page_bounds(page, pageSize)
    bundle = await in_threadpool(engine.evidence.store.get_bundle, bundle_id)
    if bundle is None:
        raise not_found("unknown_bundle", f"evidence bundle {bundle_id!r} does not exist")
    wire = bundle.to_wire()
    chunks = wire.pop("chunks")
    return json_response(
        {
            **wire,
            "page": page,
            "pageSize": pageSize,
            "totalChunks": len(chunks),
            "chunks": chunks[start:stop],
        }
    )


def chunk_document(engine: Engine, chunk_id: str) -> dict:
    from research_engine.retrieval import ChunkNotFound, resolve_chunk

    store = engine.evidence.store
    try:
        chunk = resolve_chunk(store, chunk_id)
    except ChunkNotFound as exc:
        raise not_found("unknown_chunk", f"chunk {chunk_id!r} does not exist") from exc
    version = store.get_version(chunk.version_id)
    document = store.get_document(chunk.document_id)
    version_meta = None
    if version is not None:
        version_meta = {
            "versionId": version.version_id,
            "documentId": version.document_id,
            "sourceId": version.source_id,
            "documentType": version.document_type.value,
            "title": version.title,
            "sourceUrl": version.source_url,
            "publishedAt": utc_to_str(version.published_at),
            "publishedAtPrecision": version.published_at_precision,
            "availableAt": utc_to_str(version.available_at),
            "availabilityPolicy": version.availability_policy,
            "ingestedAt": utc_to_str(version.ingested_at),
            "status": version.status.value,
            "supersedes": version.supersedes,
            "fidelityFlags": list(version.fidelity_flags),
            "synthetic": version.synthetic,
            "contentHash": version.content_hash,
            "normalizedTextHash": version.normalized_text_hash,
            "parserVersion": version.parser_version,
            "mediaType": version.media_type,
        }
    return {
        "chunkId": chunk.chunk_id,
        "versionId": chunk.version_id,
        "documentId": chunk.document_id,
        "text": chunk.text,
        "textHash": chunk.text_hash,
        "startOffset": chunk.start_offset,
        "endOffset": chunk.end_offset,
        "offsetBasis": "normalized_document_text",
        "headingPath": list(chunk.heading_path),
        "ordinal": chunk.ordinal,
        "tokenCount": chunk.token_count,
        "tokenizerVersion": chunk.tokenizer_version,
        "chunkerVersion": chunk.chunker_version,
        "availableAt": utc_to_str(chunk.available_at),
        "documentVersion": version_meta,
        "document": (
            {"canonicalUrl": document.canonical_url, "eventId": document.event_id}
            if document is not None
            else None
        ),
    }


@router.get("/evidence/chunks/{chunk_id}", summary="Stored normalized chunk text and provenance")
async def evidence_chunk(chunk_id: str, engine: Engine = Depends(get_engine)) -> Response:
    engine.require_signing()
    return json_response(await in_threadpool(chunk_document, engine, chunk_id))


def _node_record(store, entities: dict, node_id: str) -> Optional[dict]:
    entity = entities.get(node_id)
    if entity is not None:
        return {
            "nodeId": entity.entity_id,
            "nodeType": entity.entity_type.value,
            "label": entity.canonical_name,
            "availableAt": entity.available_at,
        }
    version = store.get_version(node_id)
    if version is not None:
        return {
            "nodeId": version.version_id,
            "nodeType": "DocumentVersion",
            "label": version.title,
            "availableAt": version.available_at,
        }
    chunk = store.get_chunk(node_id)
    if chunk is not None:
        return {
            "nodeId": chunk.chunk_id,
            "nodeType": "Chunk",
            "label": f"{chunk.document_id}#{chunk.ordinal}",
            "availableAt": chunk.available_at,
        }
    return None


def graph_document(engine: Engine, bundle_id: str) -> dict:
    store = engine.evidence.store
    bundle = store.get_bundle(bundle_id)
    if bundle is None:
        raise not_found("unknown_bundle", f"evidence bundle {bundle_id!r} does not exist")
    run = store.get_retrieval_run(bundle.retrieval_run_id)
    trace = run.graph if run is not None else None
    cutoff = bundle.decision_as_of
    roles: dict[str, set[str]] = {}
    assertion_ids: list[str] = []
    seeds = []
    if trace is not None:
        seeds = [s.to_wire() for s in trace.seeds]
        for seed in trace.seeds:
            roles.setdefault(seed.seed_id, set()).add("seed")
        assertion_ids.extend(trace.visited_assertion_ids)
    for chunk in bundle.chunks:
        graph = chunk.provenance.graph
        if graph is not None:
            assertion_ids.extend(graph.path_assertion_ids)
            roles.setdefault(chunk.chunk_id, set()).add("delivered_chunk")
            roles.setdefault(graph.seed_id, set()).add("seed")
    assertion_ids.extend(f.assertion_id for f in bundle.structured_facts)
    wanted = list(dict.fromkeys(assertion_ids))
    by_id = {a.assertion_id: a for a in store.list_assertions()} if wanted else {}
    edges = []
    truncated = False
    for assertion_id in wanted:
        assertion = by_id.get(assertion_id)
        if assertion is None or assertion.available_at > cutoff:
            continue
        if len(edges) >= MAX_GRAPH_EDGES:
            truncated = True
            break
        edges.append(
            {
                "assertionId": assertion.assertion_id,
                "relation": assertion.relation.value,
                "subjectId": assertion.subject_id,
                "subjectType": assertion.subject_type.value,
                "objectId": assertion.object_id,
                "objectType": assertion.object_type.value,
                "availableAt": utc_to_str(assertion.available_at),
                "extractionMethod": assertion.extraction_method,
                "extractionVersion": assertion.extraction_version,
                "validationStatus": assertion.validation_status.value,
                "confidence": str(assertion.confidence),
                "support": [s.to_wire() for s in assertion.support],
            }
        )
        roles.setdefault(assertion.subject_id, set()).add("traversed")
        roles.setdefault(assertion.object_id, set()).add("traversed")
    entities = {e.entity_id: e for e in store.list_entities()} if roles else {}
    nodes = []
    for node_id in sorted(roles):
        if len(nodes) >= MAX_GRAPH_NODES:
            truncated = True
            break
        record = _node_record(store, entities, node_id)
        if record is None or record["availableAt"] > cutoff:
            continue
        record["availableAt"] = utc_to_str(record["availableAt"])
        record["roles"] = sorted(roles[node_id])
        nodes.append(record)
    kept = {n["nodeId"] for n in nodes}
    edges = [e for e in edges if e["subjectId"] in kept and e["objectId"] in kept]
    return {
        "bundleId": bundle.bundle_id,
        "retrievalRunId": bundle.retrieval_run_id,
        "indexBuildId": bundle.index_build_id,
        "mode": bundle.mode.value,
        "decisionAsOf": utc_to_str(cutoff),
        "graphBackend": trace.graph_backend if trace is not None else None,
        "seeds": seeds,
        "limitsHit": list(trace.limits_hit) if trace is not None else [],
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
        "limits": {"maxNodes": MAX_GRAPH_NODES, "maxEdges": MAX_GRAPH_EDGES},
        "scope": "evidence_provenance_only",
        "note": (
            None
            if trace is not None
            else f"bundle mode {bundle.mode.value} has no graph traversal; only structured facts"
        ),
    }


@router.get("/evidence/graph", summary="Bounded graph provenance of an evidence bundle")
async def evidence_graph(
    bundleId: str = Query(...), engine: Engine = Depends(get_engine)
) -> Response:
    engine.require_signing()
    return json_response(await in_threadpool(graph_document, engine, bundleId))


_SENTENCE = re.compile(r"[^.!?\n]{40,400}[.!?]")


def extractive_note(bundle, question: str) -> tuple[ResearchNote, list]:
    """Deterministic reference note: verbatim quotes of the top delivered passages."""
    from research_engine.retrieval import validate_citation

    claims: list[DocumentaryClaim] = []
    citations: list[Citation] = []
    validation = []
    for chunk in bundle.chunks[:MAX_NOTE_CLAIMS]:
        match = _SENTENCE.search(chunk.text)
        if match is None:
            continue
        quote = match.group(0).strip()
        start = chunk.text.find(quote)
        citation = Citation(
            citation_id=short_id("cit", {"b": bundle.bundle_id, "c": chunk.chunk_id}),
            bundle_id=bundle.bundle_id,
            chunk_id=chunk.chunk_id,
            document_version_id=chunk.version_id,
            quote=quote,
            start_offset=start,
            end_offset=start + len(quote),
        )
        checks = validate_citation(citation, bundle)
        validation.extend(checks)
        ok = all(c.passed for c in checks)
        citations.append(citation)
        claims.append(
            DocumentaryClaim(
                claim_id=short_id("clm", {"cit": citation.citation_id}),
                text=f"{chunk.title} states: “{quote}”",
                citation_ids=[citation.citation_id],
                material=False,
                validation_status="valid" if ok else "invalid",
            )
        )
    if not claims:
        note = ResearchNote(
            status=ResearchStatus.INSUFFICIENT_EVIDENCE,
            coverage_gaps=[f"no eligible passages answer: {question}"],
            retrieval_run_ids=[bundle.retrieval_run_id],
            explanation=(
                "No evidence available at the cutoff was retrieved for this question "
                f"({NOTE_METHOD})."
            ),
        )
        return note, validation
    note = ResearchNote(
        status=ResearchStatus.SUPPORTED,
        claims=claims,
        citations=citations,
        coverage_gaps=[
            "extractive reference note: passages are quoted verbatim; no synthesis, "
            "interpretation or forecast is made"
        ],
        retrieval_run_ids=[bundle.retrieval_run_id],
        explanation=(
            f"{NOTE_METHOD}: quotes the highest-ranked eligible passages for the question. "
            "Informational only; it carries no order authority."
        ),
    )
    return note, validation


def _agent_note(engine: Engine, req: ResearchNoteRequest, as_of: datetime, index, key: bytes):
    """Cited note from the agents workflow with the configured provider, or None."""
    try:
        from research_engine.agents import research_note as agent_research_note
    except Exception:
        return None
    service = engine.strategies
    if req.response_mode not in service.compatible_modes():
        raise unavailable(
            "provider_mode_unavailable",
            f"responseMode {req.response_mode} is not available with the configured provider "
            f"{service.provider_name!r}",
        )
    try:
        provider = service.provider()
    except ProviderUnavailable as exc:
        raise unavailable("model_provider_unavailable", str(exc)) from exc
    return agent_research_note(
        req.question,
        as_of,
        evidence=engine.evidence_port(index),
        provider=provider,
        mode=req.retrieval_mode,
        pricing=engine.pricing,
        market=engine.market,
        signing_key=key,
    )


def build_research_note(engine: Engine, req: ResearchNoteRequest, key: bytes) -> dict:
    if req.retrieval_mode == RetrievalMode.NONE:
        raise unprocessable(
            "invalid_request", "research notes need an evidence retrieval mode (not 'none')"
        )
    as_of = req.as_of or datetime.now(timezone.utc).replace(microsecond=0)
    index = engine.evidence.resolve(req.evidence_snapshot_id, req.index_build_id)
    base = {
        "schemaVersion": req.schema_version,
        "requestId": req.request_id,
        "question": req.question,
        "asOf": utc_to_str(as_of),
        "responseMode": req.response_mode,
        "requestedBy": req.requested_by,
        "evidenceSnapshotId": evidence_snapshot_id(index.build.member_version_ids),
        "indexBuildId": index.build_id,
        "retrievalMode": req.retrieval_mode.value,
        "orderAuthority": False,
    }
    result = _agent_note(engine, req, as_of, index, key)
    if result is not None:
        wire = result.to_wire()
        return {
            **base,
            "noteId": result.note_id,
            "status": result.status,
            "generatedBy": {
                "method": "research_engine.agents.research_note",
                "provider": result.versions.provider,
                "model": result.versions.model,
            },
            "researchNote": wire.get("researchNote"),
            "validation": wire.get("validation", []),
            "bundleIds": list(result.evidence_bundle_ids),
            "result": wire,
        }
    _, run, bundle = run_retrieval(
        engine,
        question=req.question,
        as_of=as_of,
        mode=req.retrieval_mode,
        evidence_snapshot=req.evidence_snapshot_id,
        index_build_id=index.build_id,
        scope="public|research-note",
    )
    note, validation = extractive_note(bundle, req.question)
    payload = {
        **base,
        "status": "completed" if note.status == ResearchStatus.SUPPORTED else note.status.value,
        "generatedBy": {"method": NOTE_METHOD, "provider": "reference", "model": None},
        "researchNote": note.to_wire(),
        "validation": [v.to_wire() for v in validation],
        "bundleIds": [bundle.bundle_id],
    }
    payload["noteId"] = short_id("note", payload)
    return payload


@router.post(
    "/research-notes",
    summary="Informational research note with citations (never orders)",
    openapi_extra=contract_body("ResearchNoteRequest"),
)
async def research_notes(request: Request, engine: Engine = Depends(get_engine)) -> Response:
    key = engine.require_signing()
    body = await read_object(request)
    req = parse_model(ResearchNoteRequest, body)
    engine.requests.bind("research-notes", req.request_id, req.to_wire())
    return json_response(await in_threadpool(build_research_note, engine, req, key))
