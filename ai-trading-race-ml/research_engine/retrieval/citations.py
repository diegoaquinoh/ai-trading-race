"""Deterministic citation checks (spec 13.2 steps 2-4, 16.4).

* ``resolve_chunk`` - a chunk id resolves to its stored, immutable record.
* ``validate_quote`` - an exact quote and/or offsets against the stored
  normalized chunk text (offsets are relative to the chunk text; add
  ``chunk.start_offset`` for document-version offsets).
* ``validate_citation`` - membership in the delivered bundle, version match,
  temporal eligibility at the bundle cutoff, stored-text integrity and the
  quote/offset check. Semantic support is *not* judged here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from research_engine.contracts.common import sha256_text
from research_engine.contracts.decisions import Citation, ValidationResult
from research_engine.contracts.evidence import Chunk, EvidenceBundle
from research_engine.evidence.store import ResearchStore


class ChunkNotFound(KeyError):
    pass


@dataclass(frozen=True)
class QuoteCheck:
    valid: bool
    start_offset: Optional[int]
    end_offset: Optional[int]
    reasons: tuple[str, ...]


def resolve_chunk(store: ResearchStore, chunk_id: str) -> Chunk:
    chunk = store.get_chunk(chunk_id)
    if chunk is None:
        raise ChunkNotFound(chunk_id)
    return chunk


def validate_quote(
    text: str,
    quote: Optional[str] = None,
    start_offset: Optional[int] = None,
    end_offset: Optional[int] = None,
) -> QuoteCheck:
    """Exact check against normalized chunk text; no fuzzy matching."""
    reasons: list[str] = []
    if quote is None and start_offset is None and end_offset is None:
        return QuoteCheck(True, None, None, ("no quote or offsets supplied",))
    if (start_offset is None) != (end_offset is None):
        return QuoteCheck(False, start_offset, end_offset, ("both offsets are required",))
    if start_offset is not None and end_offset is not None:
        if not (0 <= start_offset < end_offset <= len(text)):
            return QuoteCheck(False, start_offset, end_offset, ("offsets out of range",))
        span = text[start_offset:end_offset]
        if quote is not None and span != quote:
            reasons.append("quote does not equal text at offsets")
            return QuoteCheck(False, start_offset, end_offset, tuple(reasons))
        return QuoteCheck(True, start_offset, end_offset, ())
    assert quote is not None
    if not quote:
        return QuoteCheck(False, None, None, ("empty quote",))
    position = text.find(quote)
    if position < 0:
        return QuoteCheck(False, None, None, ("quote is not an exact substring of the chunk",))
    return QuoteCheck(True, position, position + len(quote), ())


def validate_citation(
    citation: Citation, bundle: EvidenceBundle, store: Optional[ResearchStore] = None
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    delivered = bundle.chunk(citation.chunk_id)
    member_ok = citation.bundle_id == bundle.bundle_id and delivered is not None
    results.append(
        ValidationResult(
            step="citation_membership",
            passed=member_ok,
            details=(
                [] if member_ok else [f"{citation.chunk_id} not delivered in {bundle.bundle_id}"]
            ),
        )
    )
    if delivered is None:
        return results
    version_ok = delivered.version_id == citation.document_version_id
    results.append(
        ValidationResult(
            step="citation_version",
            passed=version_ok,
            details=[] if version_ok else ["document version does not match the delivered chunk"],
        )
    )
    temporal_ok = delivered.available_at <= bundle.decision_as_of
    results.append(
        ValidationResult(
            step="temporal",
            passed=temporal_ok,
            details=[] if temporal_ok else ["cited evidence was not available at the cutoff"],
        )
    )
    text = delivered.text
    integrity = sha256_text(text) == delivered.text_hash
    if store is not None:
        stored = store.get_chunk(citation.chunk_id)
        integrity = integrity and stored is not None and stored.text == text
    results.append(
        ValidationResult(
            step="stored_text_integrity",
            passed=integrity,
            details=[] if integrity else ["delivered text differs from stored normalized text"],
        )
    )
    check = validate_quote(text, citation.quote, citation.start_offset, citation.end_offset)
    results.append(
        ValidationResult(step="quote_offsets", passed=check.valid, details=list(check.reasons))
    )
    return results
