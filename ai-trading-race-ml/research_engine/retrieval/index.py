"""Index builds: exact manifests, validation, graph projection, loading (spec 11.3, 15.4).

``build_index`` records a BUILDING manifest with exact member version ids, the
tokenizer/chunker/normalizer/embedding/graph versions and content hashes, writes
the graph build, validates everything and only then marks the build READY. Any
failed check marks it FAILED; a READY build is immutable.

``load_index`` opens a READY build. The in-memory graph backend is process-local,
so on load the graph is rebuilt from canonical records and must reproduce the
recorded assertion-set hash and node count before it is published again — the
same rebuild-and-compare procedure used for Neo4j recovery.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np

from research_engine.contracts.common import content_hash, sha256_bytes, short_id
from research_engine.contracts.evidence import (
    Chunk,
    Document,
    DocumentVersion,
    Entity,
    IndexBuild,
    IndexBuildStatus,
    IngestionAttempt,
    IngestionState,
    VersionStatus,
)
from research_engine.evidence.chunking import CHUNKER_VERSION, HARD_MAX_TOKENS, TOKENIZER_VERSION
from research_engine.evidence.state import IllegalTransition, check_transition
from research_engine.evidence.store import ResearchStore
from research_engine.evidence.textnorm import LEX_NORMALIZER_VERSION, lexical_terms
from research_engine.knowledge.extraction import (
    EVENT_SERIES_METHOD,
    LEXICON_METHOD,
    METADATA_METHOD,
    RELEASE_METHOD,
)
from research_engine.knowledge.graph_store import (
    GraphProjection,
    GraphRetrievalUnavailable,
    GraphStore,
    InMemoryGraphStore,
    project,
)
from research_engine.knowledge.ontology import GRAPH_SCHEMA_VERSION
from research_engine.knowledge.resolver import AliasResolver

from .embedding import EmbeddingProvider, HashEmbeddingProvider

INDEX_TEXT_TEMPLATE = "title+headings+text-v1"


class IndexNotReady(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def index_text(version: DocumentVersion, chunk: Chunk) -> str:
    return f"{version.title}\n{' > '.join(chunk.heading_path)}\n{chunk.text}"


@dataclass
class _Corpus:
    versions: dict[str, DocumentVersion]
    documents: dict[str, Document]
    chunks: dict[str, Chunk]
    entities: dict[str, Entity]
    projection: GraphProjection


def _collect(store: ResearchStore, member_ids: list[str]) -> _Corpus:
    versions = {v.version_id: v for v in (store.get_version(i) for i in member_ids) if v}
    documents = {
        d.document_id: d
        for d in (store.get_document(v.document_id) for v in versions.values())
        if d
    }
    chunks = {c.chunk_id: c for c in store.chunks_for_versions(versions)}
    entities = {e.entity_id: e for e in store.list_entities()}
    projection = project(
        sorted(versions.values(), key=lambda v: v.version_id),
        sorted(chunks.values(), key=lambda c: c.chunk_id),
        sorted(entities.values(), key=lambda e: e.entity_id),
        store.list_assertions(),
    )
    return _Corpus(versions, documents, chunks, entities, projection)


def _embed(
    provider: EmbeddingProvider, corpus: _Corpus, order: list[str]
) -> tuple[np.ndarray, str]:
    texts = [
        index_text(corpus.versions[corpus.chunks[c].version_id], corpus.chunks[c]) for c in order
    ]
    matrix = provider.embed(texts) if texts else np.zeros((0, provider.dimensions), dtype=np.int64)
    canonical = np.ascontiguousarray(matrix.astype("<i8" if provider.exact_integer else "<f8"))
    return matrix, sha256_bytes(canonical.tobytes())


def select_members(
    store: ResearchStore,
    *,
    include_synthetic: bool = False,
    max_available_at: Optional[datetime] = None,
    source_ids: Optional[list[str]] = None,
) -> list[str]:
    out = []
    for version in store.list_versions(include_synthetic=include_synthetic):
        if version.status != VersionStatus.ACTIVE:
            continue
        if source_ids and version.source_id not in source_ids:
            continue
        if max_available_at is not None and version.available_at > max_available_at:
            continue
        out.append(version.version_id)
    return sorted(out)


def _mark_items(
    store: ResearchStore,
    versions: list[DocumentVersion],
    state: IngestionState,
    build_id: str,
    at: datetime,
) -> None:
    for version in versions:
        current = store.item_state(version.source_id, version.document_id)
        current_state = current[0] if current else None
        try:
            check_transition(current_state, state)
            legal = True
        except IllegalTransition:
            legal = False
        store.record_attempt(
            IngestionAttempt(
                attempt_id=short_id(
                    "att",
                    {
                        "v": version.version_id,
                        "b": build_id,
                        "s": state.value,
                        "at": at.isoformat(),
                    },
                    20,
                ),
                source_id=version.source_id,
                document_id=version.document_id,
                stage="index" if state == IngestionState.INDEXED else "activate",
                from_state=current_state,
                to_state=state,
                outcome="ok" if legal else "skipped_unchanged",
                attempted_at=at,
                version_id=version.version_id,
                error=None if legal else f"item state {current_state} not advanced by {build_id}",
            ),
            update_state=legal,
        )


def build_index(
    store: ResearchStore,
    graph: GraphStore,
    *,
    provider: Optional[EmbeddingProvider] = None,
    member_version_ids: Optional[list[str]] = None,
    include_synthetic: bool = False,
    max_available_at: Optional[datetime] = None,
    clock: Callable[[], datetime] = utc_now,
    build_salt: int = 0,
    fault: Optional[Callable[[str], None]] = None,
) -> IndexBuild:
    """Create, validate and (only if every check passes) mark an index build READY.

    ``fault`` is a test hook called before each stage name; raising from it
    simulates a crash/failure at that point.
    """
    provider = provider or HashEmbeddingProvider()
    members = sorted(
        member_version_ids
        if member_version_ids is not None
        else select_members(
            store, include_synthetic=include_synthetic, max_available_at=max_available_at
        )
    )
    corpus = _collect(store, members)
    order = sorted(
        corpus.chunks, key=lambda c: (corpus.chunks[c].version_id, corpus.chunks[c].ordinal)
    )
    config = {
        "members": members,
        "tokenizer": TOKENIZER_VERSION,
        "chunker": CHUNKER_VERSION,
        "lex": LEX_NORMALIZER_VERSION,
        "provider": provider.provider_id,
        "model": provider.model,
        "dims": provider.dimensions,
        "template": INDEX_TEXT_TEMPLATE,
        "graph_schema": GRAPH_SCHEMA_VERSION,
        "graph_backend": graph.backend_name,
        "chunks": content_hash(sorted(corpus.chunks)),
        "assertions": corpus.projection.assertion_set_hash(),
        "salt": build_salt,
    }
    build_id = short_id("ib", config, 20)
    existing = store.get_index_build(build_id)
    if existing is not None:
        return existing
    matrix, matrix_hash = _embed(provider, corpus, order)
    build = IndexBuild(
        build_id=build_id,
        status=IndexBuildStatus.BUILDING,
        member_version_ids=members,
        member_chunk_count=len(corpus.chunks),
        member_chunk_set_hash=content_hash(sorted(corpus.chunks)),
        tokenizer_version=TOKENIZER_VERSION,
        chunker_version=CHUNKER_VERSION,
        lexical_normalizer_version=LEX_NORMALIZER_VERSION,
        embedding_provider=provider.provider_id,
        embedding_model=provider.model,
        embedding_dimensions=provider.dimensions,
        embedding_matrix_hash=matrix_hash,
        index_text_template=INDEX_TEXT_TEMPLATE,
        graph_schema_version=GRAPH_SCHEMA_VERSION,
        graph_backend=graph.backend_name,
        extraction_versions=sorted(
            {METADATA_METHOD, EVENT_SERIES_METHOD, LEXICON_METHOD, RELEASE_METHOD}
        ),
        assertion_count=len(corpus.projection.assertions),
        assertion_set_hash=corpus.projection.assertion_set_hash(),
        node_count=len(corpus.projection.nodes),
        created_at=clock(),
        includes_synthetic=any(v.synthetic for v in corpus.versions.values()),
    )
    store.put_index_build(build)
    checks: list[str] = []
    try:
        problems: list[str] = []
        if fault:
            fault("members")
        for vid in members:
            v = corpus.versions.get(vid)
            if v is None or v.status != VersionStatus.ACTIVE:
                problems.append(f"member {vid} missing or not active")
        checks.append("members_active")
        for chunk in corpus.chunks.values():
            if chunk.token_count > HARD_MAX_TOKENS:
                problems.append(f"chunk {chunk.chunk_id} exceeds {HARD_MAX_TOKENS} tokens")
            if sha256_bytes(chunk.text.encode("utf-8")) != chunk.text_hash:
                problems.append(f"chunk {chunk.chunk_id} text hash mismatch")
        if any(not any(c.version_id == v for c in corpus.chunks.values()) for v in members):
            problems.append("a member version has no chunks")
        checks += ["chunk_text_hashes", "chunk_token_limit", "member_chunk_coverage"]
        if fault:
            fault("embeddings")
        if matrix.shape != (len(order), provider.dimensions):
            problems.append("embedding matrix shape mismatch")
        if not np.all(np.isfinite(matrix.astype(np.float64))):
            problems.append("non-finite embedding values")
        _, again = _embed(provider, corpus, order)
        if again != matrix_hash:
            problems.append("embedding provider is not deterministic")
        checks += ["embedding_shape_finite", "embedding_reproducible"]
        if fault:
            fault("graph_write")
        graph.begin_build(build_id, GRAPH_SCHEMA_VERSION)
        graph.write(build_id, corpus.projection)
        if fault:
            fault("graph_validate")
        problems += graph.validate(build_id, corpus.projection)
        checks += ["graph_membership", "graph_content_hash", "graph_availability_inheritance"]
        if problems:
            raise RuntimeError("; ".join(problems[:10]))
        if fault:
            fault("publish")
        graph.publish(build_id)
    except Exception as exc:  # any failure leaves the build FAILED, never READY
        graph.fail(build_id, str(exc))
        failed = build.model_copy(
            update={
                "status": IndexBuildStatus.FAILED,
                "error": str(exc),
                "validation_checks": checks,
            }
        )
        store.update_index_build(IndexBuild.model_validate(failed.model_dump()))
        return store.get_index_build(build_id)  # type: ignore[return-value]
    ready = IndexBuild.model_validate(
        {
            **build.model_dump(),
            "status": IndexBuildStatus.READY,
            "validated_at": clock(),
            "validation_checks": checks,
        }
    )
    store.update_index_build(ready)
    _mark_items(store, list(corpus.versions.values()), IngestionState.INDEXED, build_id, clock())
    return ready


def activate_index(
    store: ResearchStore, build_id: str, clock: Callable[[], datetime] = utc_now
) -> None:
    store.activate_index(build_id, clock())
    build = store.get_index_build(build_id)
    assert build is not None
    versions = [v for v in (store.get_version(i) for i in build.member_version_ids) if v]
    _mark_items(store, versions, IngestionState.ACTIVE, build_id, clock())


def rebuild_graph(store: ResearchStore, build: IndexBuild, graph: GraphStore) -> GraphProjection:
    """Rebuild a graph build from canonical records and compare with the manifest."""
    corpus = _collect(store, build.member_version_ids)
    proj = corpus.projection
    if proj.assertion_set_hash() != build.assertion_set_hash or len(proj.nodes) != build.node_count:
        raise GraphRetrievalUnavailable(
            f"canonical records no longer reproduce graph of {build.build_id}"
        )
    graph.begin_build(build.build_id, GRAPH_SCHEMA_VERSION)
    graph.write(build.build_id, proj)
    problems = graph.validate(build.build_id, proj)
    if problems:
        graph.fail(build.build_id, "; ".join(problems))
        raise GraphRetrievalUnavailable("; ".join(problems))
    graph.publish(build.build_id)
    return proj


@dataclass
class EvidenceIndex:
    """A loaded READY index build (read-only)."""

    build: IndexBuild
    versions: dict[str, DocumentVersion]
    documents: dict[str, Document]
    chunks: dict[str, Chunk]
    entities: dict[str, Entity]
    resolver: AliasResolver
    provider: EmbeddingProvider
    order: list[str]
    row: dict[str, int]
    matrix: np.ndarray
    term_counts: dict[str, Counter]
    doc_length: dict[str, int]
    graph: Optional[GraphStore]
    graph_error: Optional[str] = None
    chunks_by_version: dict[str, list[str]] = field(default_factory=dict)

    @property
    def build_id(self) -> str:
        return self.build.build_id

    def require_graph(self) -> GraphStore:
        if self.graph is None or self.graph_error:
            raise GraphRetrievalUnavailable(self.graph_error or "no graph store attached")
        status = self.graph.status(self.build_id)
        if status != IndexBuildStatus.READY:
            raise GraphRetrievalUnavailable(
                f"graph build {self.build_id} is {status.value if status else 'missing'}"
            )
        return self.graph


def load_index(
    store: ResearchStore,
    build_id: str,
    *,
    graph: Optional[GraphStore] = None,
    provider: Optional[EmbeddingProvider] = None,
) -> EvidenceIndex:
    build = store.get_index_build(build_id)
    if build is None:
        raise IndexNotReady(f"index build {build_id} not found")
    if build.status != IndexBuildStatus.READY:
        raise IndexNotReady(f"index build {build_id} is {build.status.value}")
    provider = provider or HashEmbeddingProvider()
    if (provider.provider_id, provider.model, provider.dimensions) != (
        build.embedding_provider,
        build.embedding_model,
        build.embedding_dimensions,
    ):
        raise IndexNotReady("embedding provider does not match the index build")
    corpus = _collect(store, build.member_version_ids)
    order = sorted(
        corpus.chunks, key=lambda c: (corpus.chunks[c].version_id, corpus.chunks[c].ordinal)
    )
    if content_hash(sorted(corpus.chunks)) != build.member_chunk_set_hash:
        raise IndexNotReady("stored chunks do not match the index manifest")
    matrix, matrix_hash = _embed(provider, corpus, order)
    if matrix_hash != build.embedding_matrix_hash:
        raise IndexNotReady("recomputed embeddings do not match the index manifest")
    graph_error = None
    if graph is None:
        graph = InMemoryGraphStore()
    try:
        if graph.status(build_id) != IndexBuildStatus.READY:
            if graph.status(build_id) is not None:
                graph.drop(build_id)
            rebuild_graph(store, build, graph)
    except GraphRetrievalUnavailable as exc:
        graph_error = str(exc)
    except Exception as exc:  # backend errors stay explicit for graph mode
        graph_error = f"graph backend error: {exc}"
    term_counts: dict[str, Counter] = {}
    doc_length: dict[str, int] = {}
    by_version: dict[str, list[str]] = {}
    for chunk_id in order:
        chunk = corpus.chunks[chunk_id]
        terms = lexical_terms(index_text(corpus.versions[chunk.version_id], chunk))
        term_counts[chunk_id] = Counter(terms)
        doc_length[chunk_id] = len(terms)
        by_version.setdefault(chunk.version_id, []).append(chunk_id)
    return EvidenceIndex(
        build=build,
        versions=corpus.versions,
        documents=corpus.documents,
        chunks=corpus.chunks,
        entities=corpus.entities,
        resolver=AliasResolver(store.list_aliases(), list(corpus.entities.values())),
        provider=provider,
        order=order,
        row={c: i for i, c in enumerate(order)},
        matrix=matrix,
        term_counts=term_counts,
        doc_length=doc_length,
        graph=graph,
        graph_error=graph_error,
        chunks_by_version=by_version,
    )
