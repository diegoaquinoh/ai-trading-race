"""Evidence retrieval: eligible snapshots, BM25 + exact vector, RRF, graph expansion.

Public API (other workstreams):

* ``open_default_evidence(home=None, include_synthetic=False)``
  -> ``(EvidenceHome, EvidenceIndex)``:
  offline-ingests the Federal Reserve fixtures (idempotent), builds/validates the
  default index (READY) and loads it.
* ``retrieve(request, store, index)`` -> ``(RetrievalRun, EvidenceBundle)``.
* ``resolve_chunk(store, chunk_id)``, ``validate_quote(text, quote, start, end)``,
  ``validate_citation(citation, bundle, store)`` for citation validation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .citations import ChunkNotFound, QuoteCheck, resolve_chunk, validate_citation, validate_quote
from .index import EvidenceIndex, IndexNotReady, activate_index, build_index, load_index
from .service import retrieve

__all__ = [
    "ChunkNotFound",
    "EvidenceIndex",
    "IndexNotReady",
    "QuoteCheck",
    "activate_index",
    "build_index",
    "load_index",
    "open_default_evidence",
    "resolve_chunk",
    "retrieve",
    "validate_citation",
    "validate_quote",
]


def open_default_evidence(
    home: Path | str | None = None,
    *,
    include_synthetic: bool = False,
    max_available_at: Optional[datetime] = None,
    graph=None,  # type: ignore[no-untyped-def]
    clock: Optional[Callable[[], datetime]] = None,
):
    """Offline corpus + READY index from fixtures; safe to call repeatedly."""
    from research_engine.evidence.ingest import EvidenceHome, FedIngestor, utc_now
    from research_engine.knowledge.graph_store import InMemoryGraphStore

    clock = clock or utc_now
    evidence_home = EvidenceHome.open(home)
    FedIngestor(evidence_home, offline=True, clock=clock).run(include_synthetic=include_synthetic)
    graph = graph or InMemoryGraphStore()
    build = build_index(
        evidence_home.store,
        graph,
        include_synthetic=include_synthetic,
        max_available_at=max_available_at,
        clock=clock,
    )
    if build.status.value != "READY":
        raise IndexNotReady(
            f"default index build {build.build_id} is {build.status.value}: {build.error}"
        )
    if evidence_home.store.active_index_id() != build.build_id:
        activate_index(evidence_home.store, build.build_id, clock)
    return evidence_home, load_index(evidence_home.store, build.build_id, graph=graph)
