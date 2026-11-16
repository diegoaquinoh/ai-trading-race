"""Narrow evidence port used by agent tools and validation.

:class:`EvidencePort` is what the agents need from the evidence workstream:
scoped retrieval at a strict cutoff (``hybrid_rag_v1`` / ``graph_rag_v1``) and
lookup of stored normalized chunk text for quote validation.
:class:`RetrievalEvidencePort` adapts ``research_engine.retrieval``:

* ``retrieve`` builds a :class:`RetrievalRequest` bound to the port's READY index
  build and returns the persisted :class:`EvidenceBundle`;
* ``GraphRetrievalUnavailable`` becomes :class:`GraphUnavailable` and
  ``IndexNotReady`` becomes :class:`EvidenceUnavailable`. There is never a
  fallback from graph mode to plain RAG.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol, Sequence, runtime_checkable

from research_engine.contracts.decisions import RetrievalMode
from research_engine.contracts.evidence import EvidenceBundle


class EvidenceUnavailable(RuntimeError):
    """Required evidence infrastructure (index, store) is unavailable."""


class GraphUnavailable(EvidenceUnavailable):
    """The graph needed by graph_rag_v1 is missing, not READY or failing."""


@runtime_checkable
class EvidencePort(Protocol):
    index_build_id: str
    evidence_snapshot_id: Optional[str]

    def retrieve(
        self,
        *,
        question: str,
        decision_as_of: datetime,
        mode: RetrievalMode,
        max_chunks: int,
        max_evidence_tokens: int,
        explicit_identifiers: Sequence[str] = (),
        permission_scope: str = "public",
    ) -> EvidenceBundle: ...

    def chunk_text(self, chunk_id: str) -> Optional[str]:
        """Stored normalized chunk text, or None when the chunk is unknown."""
        ...


class RetrievalEvidencePort:
    """Adapter over ``research_engine.retrieval`` (store + loaded READY index)."""

    def __init__(self, store, index, *, source_scope: Sequence[str] = ("fed-fomc",)):
        self.store = store
        self.index = index
        self.index_build_id = index.build_id
        self.evidence_snapshot_id = None  # eligible snapshots are derived per cutoff
        self.source_scope = list(source_scope)

    def retrieve(
        self,
        *,
        question: str,
        decision_as_of: datetime,
        mode: RetrievalMode,
        max_chunks: int,
        max_evidence_tokens: int,
        explicit_identifiers: Sequence[str] = (),
        permission_scope: str = "public",
    ) -> EvidenceBundle:
        from research_engine.contracts.evidence import RetrievalBudget, RetrievalRequest
        from research_engine.knowledge.graph_store import GraphRetrievalUnavailable
        from research_engine.retrieval import IndexNotReady, retrieve

        request = RetrievalRequest(
            question=question,
            decision_as_of=decision_as_of,
            mode=mode,
            index_build_id=self.index_build_id,
            source_scope=self.source_scope,
            explicit_identifiers=list(explicit_identifiers),
            permission_scope=permission_scope,
            budget=RetrievalBudget(
                max_chunks=max(1, max_chunks), max_evidence_tokens=max(1, max_evidence_tokens)
            ),
        )
        try:
            _, bundle = retrieve(request, self.store, self.index)
        except GraphRetrievalUnavailable as exc:
            raise GraphUnavailable(str(exc)) from exc
        except IndexNotReady as exc:
            raise EvidenceUnavailable(str(exc)) from exc
        return bundle

    def chunk_text(self, chunk_id: str) -> Optional[str]:
        chunk = self.store.get_chunk(chunk_id)
        return chunk.text if chunk is not None else None


def open_default_evidence_port(home: Path | str | None = None) -> RetrievalEvidencePort:
    """Offline Fed corpus + READY default index (idempotent; no network)."""
    from research_engine.retrieval import open_default_evidence

    evidence_home, index = open_default_evidence(home)
    return RetrievalEvidencePort(evidence_home.store, index)
