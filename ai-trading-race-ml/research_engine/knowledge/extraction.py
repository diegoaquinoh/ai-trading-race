"""Deterministic relationship extraction (spec 12.1, 18.5). No LLM is used.

Methods (each recorded as an ``ExtractionRun`` per primary input so runs stay
stable as the corpus grows):

* ``metadata_v1`` - PUBLISHED_BY, DOCUMENTS_EVENT, HAS_CHUNK, SUPERSEDES from
  verified source metadata of one document version.
* ``event_series_v1`` - PREVIOUS_EVENT between consecutive scheduled meetings.
* ``rule_lexicon_v1`` - MENTIONS_TOPIC / REFERS_TO_SERIES from explicit lexicon
  matches in chunk text, with exact support spans (chunk offsets + quote).
* ``release_fixture_v1`` - RELEASE_OF from the public CPI release-date fixture.

Every assertion's ``available_at`` is the latest ``available_at`` of all of its
inputs (subject, object and supporting records), so derived graph content can
never be visible before the evidence it rests on (spec 6.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

from research_engine.contracts.common import content_hash, short_id
from research_engine.contracts.evidence import (
    AssertionStatus,
    Chunk,
    DocumentVersion,
    Entity,
    ExtractionRun,
    NodeType,
    RelationshipAssertion,
    RelationType,
    SupportSpan,
    score_decimal,
)

from .ontology import GRAPH_SCHEMA_VERSION, check_assertion
from .vocabulary import LEXICON_VERSION, SERIES, TOPICS, MacroReleaseRow, VocabularyEntry

METADATA_METHOD = "metadata_v1"
EVENT_SERIES_METHOD = "event_series_v1"
LEXICON_METHOD = LEXICON_VERSION
RELEASE_METHOD = "release_fixture_v1"
MAX_SPANS_PER_ASSERTION = 3


@dataclass(frozen=True)
class Timed:
    """Any record id with its availability, used to compute inherited availability."""

    record_id: str
    available_at: datetime


def _assertion(
    *,
    subject: str,
    subject_type: NodeType,
    relation: RelationType,
    obj: str,
    object_type: NodeType,
    support: list[SupportSpan],
    inputs: list[Timed],
    method: str,
    run_id: str,
    status: AssertionStatus = AssertionStatus.APPROVED,
    confidence: Decimal = Decimal("1"),
) -> RelationshipAssertion:
    ids = sorted({t.record_id for t in inputs})
    available = max(t.available_at for t in inputs)
    identity = {
        "s": subject,
        "r": relation.value,
        "o": obj,
        "m": method,
        "support": [s.model_dump(mode="json") for s in support],
    }
    assertion = RelationshipAssertion(
        assertion_id=short_id("as", identity, 20),
        subject_id=subject,
        subject_type=subject_type,
        relation=relation,
        object_id=obj,
        object_type=object_type,
        support=support,
        input_ids=ids,
        available_at=available,
        extraction_method=method.split(":")[0],
        extraction_version=method,
        extraction_run_id=run_id,
        validation_status=status,
        confidence=score_decimal(confidence),
    )
    check_assertion(assertion)
    return assertion


def _run(
    method: str,
    input_ids: list[str],
    input_payload: object,
    assertions: list[RelationshipAssertion],
    generated_at: datetime,
    errors: Optional[list[str]] = None,
) -> ExtractionRun:
    return ExtractionRun(
        extraction_run_id=_run_id(method, input_payload),
        method=method,
        method_version=method,
        graph_schema_version=GRAPH_SCHEMA_VERSION,
        input_ids=sorted(input_ids),
        input_hash=content_hash(input_payload),
        output_hash=content_hash([a.to_wire() for a in assertions]),
        assertion_count=len(assertions),
        review_count=sum(
            a.validation_status == AssertionStatus.REVIEW_REQUIRED for a in assertions
        ),
        errors=errors or [],
        generated_at=generated_at,
    )


def _run_id(method: str, input_payload: object) -> str:
    return short_id("xr", {"method": method, "input": content_hash(input_payload)}, 20)


def _timed_entity(entity: Entity) -> Timed:
    return Timed(entity.entity_id, entity.available_at)


# --------------------------------------------------------------------------- #
# metadata_v1
# --------------------------------------------------------------------------- #


def extract_metadata(
    version: DocumentVersion,
    chunks: list[Chunk],
    publisher: Entity,
    event: Optional[Entity],
    superseded: Optional[DocumentVersion],
    generated_at: datetime,
) -> tuple[ExtractionRun, list[RelationshipAssertion]]:
    payload = {
        "version": version.version_id,
        "chunks": [c.chunk_id for c in chunks],
        "publisher": publisher.entity_id,
        "event": event.entity_id if event else None,
        "supersedes": superseded.version_id if superseded else None,
    }
    run_id = _run_id(METADATA_METHOD, payload)
    v = Timed(version.version_id, version.available_at)
    meta = SupportSpan(
        kind="metadata",
        version_id=version.version_id,
        source_ref=f"document_version:{version.version_id}",
    )
    out = [
        _assertion(
            subject=version.version_id,
            subject_type=NodeType.DOCUMENT_VERSION,
            relation=RelationType.PUBLISHED_BY,
            obj=publisher.entity_id,
            object_type=NodeType.INSTITUTION,
            support=[meta],
            inputs=[v, _timed_entity(publisher)],
            method=METADATA_METHOD,
            run_id=run_id,
        )
    ]
    if event is not None:
        out.append(
            _assertion(
                subject=version.version_id,
                subject_type=NodeType.DOCUMENT_VERSION,
                relation=RelationType.DOCUMENTS_EVENT,
                obj=event.entity_id,
                object_type=NodeType.POLICY_EVENT,
                support=[meta],
                inputs=[v, _timed_entity(event)],
                method=METADATA_METHOD,
                run_id=run_id,
            )
        )
    for chunk in chunks:
        out.append(
            _assertion(
                subject=version.version_id,
                subject_type=NodeType.DOCUMENT_VERSION,
                relation=RelationType.HAS_CHUNK,
                obj=chunk.chunk_id,
                object_type=NodeType.CHUNK,
                support=[
                    SupportSpan(
                        kind="metadata",
                        chunk_id=chunk.chunk_id,
                        version_id=version.version_id,
                        source_ref=f"chunk:{chunk.chunk_id}",
                    )
                ],
                inputs=[v, Timed(chunk.chunk_id, chunk.available_at)],
                method=METADATA_METHOD,
                run_id=run_id,
            )
        )
    if superseded is not None:
        out.append(
            _assertion(
                subject=version.version_id,
                subject_type=NodeType.DOCUMENT_VERSION,
                relation=RelationType.SUPERSEDES,
                obj=superseded.version_id,
                object_type=NodeType.DOCUMENT_VERSION,
                support=[meta],
                inputs=[v, Timed(superseded.version_id, superseded.available_at)],
                method=METADATA_METHOD,
                run_id=run_id,
            )
        )
    return _run(METADATA_METHOD, [version.version_id], payload, out, generated_at), out


# --------------------------------------------------------------------------- #
# event_series_v1
# --------------------------------------------------------------------------- #


def extract_event_series(
    events: list[Entity], generated_at: datetime
) -> tuple[ExtractionRun, list[RelationshipAssertion]]:
    ordered = sorted(
        (e for e in events if e.entity_type == NodeType.POLICY_EVENT),
        key=lambda e: (e.properties.get("meeting_end", ""), e.entity_id),
    )
    payload = {"events": [e.entity_id for e in ordered]}
    run_id = _run_id(EVENT_SERIES_METHOD, payload)
    out: list[RelationshipAssertion] = []
    for prev, cur in zip(ordered, ordered[1:]):
        out.append(
            _assertion(
                subject=cur.entity_id,
                subject_type=NodeType.POLICY_EVENT,
                relation=RelationType.PREVIOUS_EVENT,
                obj=prev.entity_id,
                object_type=NodeType.POLICY_EVENT,
                support=[
                    SupportSpan(
                        kind="source_row",
                        source_ref=(
                            "research_engine/evidence/fed.py#PINNED_MEETINGS "
                            f"{prev.entity_id}->{cur.entity_id}"
                        ),
                    )
                ],
                inputs=[_timed_entity(cur), _timed_entity(prev)],
                method=EVENT_SERIES_METHOD,
                run_id=run_id,
            )
        )
    return _run(EVENT_SERIES_METHOD, list(payload["events"]), payload, out, generated_at), out


# --------------------------------------------------------------------------- #
# rule_lexicon_v1
# --------------------------------------------------------------------------- #


def _entry_matches(entry: VocabularyEntry, text: str) -> tuple[list[tuple[int, int]], bool]:
    """Return (spans, review) for one vocabulary entry; approved spans win overlaps."""
    approved: list[tuple[int, int]] = []
    review: list[tuple[int, int]] = []
    for pattern in entry.patterns:
        for match in pattern.compile().finditer(text):
            (review if pattern.review else approved).append((match.start(), match.end()))
    if approved:
        return sorted(set(approved)), False
    return sorted(set(review)), True


def extract_lexicon(
    version: DocumentVersion,
    chunks: list[Chunk],
    vocabulary_entities: dict[str, Entity],
    generated_at: datetime,
) -> tuple[ExtractionRun, list[RelationshipAssertion]]:
    payload = {
        "version": version.version_id,
        "chunks": [[c.chunk_id, c.text_hash] for c in chunks],
        "lexicon": LEXICON_VERSION,
    }
    run_id = _run_id(LEXICON_METHOD, payload)
    out: list[RelationshipAssertion] = []
    targets = [(e, RelationType.MENTIONS_TOPIC, NodeType.MACRO_TOPIC) for e in TOPICS] + [
        (e, RelationType.REFERS_TO_SERIES, NodeType.MACRO_SERIES) for e in SERIES
    ]
    for chunk in chunks:
        for entry, relation, node_type in targets:
            spans, review = _entry_matches(entry, chunk.text)
            if not spans:
                continue
            support = [
                SupportSpan(
                    kind="chunk_span",
                    chunk_id=chunk.chunk_id,
                    version_id=chunk.version_id,
                    start_offset=start,
                    end_offset=end,
                    quote=chunk.text[start:end],
                )
                for start, end in spans[:MAX_SPANS_PER_ASSERTION]
            ]
            entity = vocabulary_entities[entry.entity_id]
            out.append(
                _assertion(
                    subject=chunk.chunk_id,
                    subject_type=NodeType.CHUNK,
                    relation=relation,
                    obj=entry.entity_id,
                    object_type=node_type,
                    support=support,
                    inputs=[Timed(chunk.chunk_id, chunk.available_at), _timed_entity(entity)],
                    method=LEXICON_METHOD,
                    run_id=run_id,
                    status=AssertionStatus.REVIEW_REQUIRED if review else AssertionStatus.APPROVED,
                    confidence=Decimal("0.5") if review else Decimal("0.9"),
                )
            )
    return _run(LEXICON_METHOD, [version.version_id], payload, out, generated_at), out


# --------------------------------------------------------------------------- #
# release_fixture_v1
# --------------------------------------------------------------------------- #


def extract_releases(
    rows: Iterable[MacroReleaseRow], entities: dict[str, Entity], generated_at: datetime
) -> tuple[ExtractionRun, list[RelationshipAssertion]]:
    rows = list(rows)
    payload = {
        "rows": [[r.release_id, r.reference_period, r.release_date.isoformat()] for r in rows]
    }
    run_id = _run_id(RELEASE_METHOD, payload)
    out: list[RelationshipAssertion] = []
    for row in rows:
        release = entities[row.release_id]
        for series_id in row.series_ids:
            series = entities[series_id]
            out.append(
                _assertion(
                    subject=row.release_id,
                    subject_type=NodeType.MACRO_RELEASE,
                    relation=RelationType.RELEASE_OF,
                    obj=series_id,
                    object_type=NodeType.MACRO_SERIES,
                    support=[SupportSpan(kind="source_row", source_ref=row.row_ref)],
                    inputs=[_timed_entity(release), _timed_entity(series)],
                    method=RELEASE_METHOD,
                    run_id=run_id,
                )
            )
    return _run(RELEASE_METHOD, [r.release_id for r in rows], payload, out, generated_at), out
