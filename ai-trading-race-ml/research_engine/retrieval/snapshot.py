"""Eligible corpus snapshots and snapshot-local lexical statistics (spec 6.3, 12.3).

A snapshot at cutoff ``t`` contains the member versions of the index build that
are in source scope, ACTIVE, ``available_at <= t`` and not superseded by another
version that is itself eligible at ``t``. A correction available after ``t``
therefore never changes the text used at ``t``.

BM25 statistics (document frequency, average length, N) are computed from the
snapshot only, so documents added later cannot change historical rankings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from research_engine.contracts.common import content_hash, short_id
from research_engine.contracts.evidence import Exclusion, VersionStatus

from .embedding import cosine_scores
from .index import EvidenceIndex

BM25_K1 = 1.2
BM25_B = 0.75
LEXICAL_VERSION = "bm25-snapshot-v1"


@dataclass(frozen=True)
class EligibleSnapshot:
    snapshot_id: str
    cutoff: datetime
    version_ids: tuple[str, ...]
    chunk_ids: tuple[str, ...]
    exclusions: tuple[Exclusion, ...]


def eligible_snapshot(
    index: EvidenceIndex, cutoff: datetime, source_scope: list[str]
) -> EligibleSnapshot:
    exclusions: list[Exclusion] = []
    candidates = []
    for version_id in sorted(index.versions):
        version = index.versions[version_id]
        if source_scope and version.source_id not in source_scope:
            exclusions.append(
                Exclusion(
                    record_id=version_id,
                    record_type="document_version",
                    reason="source_out_of_scope",
                )
            )
        elif version.status != VersionStatus.ACTIVE:
            exclusions.append(
                Exclusion(
                    record_id=version_id,
                    record_type="document_version",
                    reason=f"status:{version.status.value}",
                )
            )
        elif version.available_at > cutoff:
            exclusions.append(
                Exclusion(
                    record_id=version_id,
                    record_type="document_version",
                    reason="not_available_at_cutoff",
                )
            )
        else:
            candidates.append(version)
    eligible = {v.version_id for v in candidates}
    superseded: dict[str, str] = {}
    for version in candidates:
        if version.supersedes and version.supersedes in eligible:
            superseded[version.supersedes] = version.version_id
    version_ids = []
    for version in candidates:
        if version.version_id in superseded:
            exclusions.append(
                Exclusion(
                    record_id=version.version_id,
                    record_type="document_version",
                    reason=f"superseded_by:{superseded[version.version_id]}",
                )
            )
        else:
            version_ids.append(version.version_id)
    chunk_ids = tuple(c for v in sorted(version_ids) for c in index.chunks_by_version.get(v, []))
    snapshot_id = short_id(
        "snap", {"versions": sorted(version_ids), "chunks": content_hash(list(chunk_ids))}, 20
    )
    return EligibleSnapshot(
        snapshot_id=snapshot_id,
        cutoff=cutoff,
        version_ids=tuple(sorted(version_ids)),
        chunk_ids=chunk_ids,
        exclusions=tuple(exclusions),
    )


def bm25_scores(
    index: EvidenceIndex, snapshot: EligibleSnapshot, terms: list[str]
) -> dict[str, float]:
    """BM25 over the snapshot only (N, df and avgdl are snapshot statistics)."""
    chunk_ids = snapshot.chunk_ids
    n = len(chunk_ids)
    if n == 0:
        return {}
    unique_terms = sorted(set(terms))
    avgdl = sum(index.doc_length[c] for c in chunk_ids) / n
    df = {t: sum(1 for c in chunk_ids if index.term_counts[c].get(t)) for t in unique_terms}
    idf = {t: math.log(1.0 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in unique_terms if df[t]}
    scores: dict[str, float] = {}
    for chunk_id in chunk_ids:
        counts = index.term_counts[chunk_id]
        length = index.doc_length[chunk_id]
        score = 0.0
        for term in unique_terms:
            tf = counts.get(term, 0)
            if tf and term in idf:
                score += (
                    idf[term]
                    * tf
                    * (BM25_K1 + 1)
                    / (tf + BM25_K1 * (1 - BM25_B + BM25_B * length / avgdl))
                )
        if score > 0:
            scores[chunk_id] = score
    return scores


def vector_scores(
    index: EvidenceIndex, snapshot: EligibleSnapshot, query_text: str
) -> dict[str, float]:
    """Exact cosine over eligible chunks (no ANN index containing future members)."""
    if not snapshot.chunk_ids:
        return {}
    rows = np.array([index.row[c] for c in snapshot.chunk_ids], dtype=np.int64)
    query = index.provider.embed([query_text])[0]
    sims = cosine_scores(index.matrix[rows], query)
    return {c: float(s) for c, s in zip(snapshot.chunk_ids, sims) if s > 0}


def top_k(scores: dict[str, float], k: int) -> list[str]:
    return [c for c, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]
