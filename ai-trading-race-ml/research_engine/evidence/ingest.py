"""Federal Reserve ingestion pipeline and evidence home (spec 11, 15.3).

``EvidenceHome`` bundles the research store (SQLite file by default) and the
content-addressed artifact store under one root:

* ``FI_RESEARCH_HOME`` or ``~/.cache/fi-research`` by default;
* ``research.sqlite`` + ``artifacts/sha256/...`` under that root;
* ``FI_RESEARCH_DB_URL`` overrides the database (e.g. SQL Server, schema ``research``).

``FedIngestor.run`` walks every pinned document through the state machine,
storing raw bytes before normalization. Identical content plus unchanged
processing configuration reuses the existing version (idempotent). A changed
page creates a *new* version that supersedes the old one and is only available
from its own receipt time; nothing is overwritten.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from research_engine.contracts.common import sha256_text, short_id
from research_engine.contracts.evidence import (
    Chunk,
    Document,
    DocumentType,
    DocumentVersion,
    Entity,
    FetchRunOutcome,
    IngestionAttempt,
    IngestionState,
    SourceFetchRun,
    VersionStatus,
)
from research_engine.contracts.common import InformationPolicy

from . import fed
from .artifacts import ArtifactStore
from .chunking import CHUNKER_VERSION, TOKENIZER_VERSION, chunk_document
from .fetch import AllowlistedFetcher, FetchError, HostNotAllowed
from .parsing import HTML_PARSER_VERSION, ParseError, ParsedDocument
from .state import IllegalTransition, check_transition, next_health
from .store import ResearchStore

HOME_ENV = "FI_RESEARCH_HOME"
DB_URL_ENV = "FI_RESEARCH_DB_URL"
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_home() -> Path:
    return Path(os.environ.get(HOME_ENV) or Path.home() / ".cache" / "fi-research")


@dataclass
class EvidenceHome:
    root: Path
    store: ResearchStore
    artifacts: ArtifactStore

    @classmethod
    def open(cls, root: Path | str | None = None, db_url: Optional[str] = None) -> "EvidenceHome":
        root = Path(root) if root else default_home()
        root.mkdir(parents=True, exist_ok=True)
        url = db_url or os.environ.get(DB_URL_ENV)
        store = (
            ResearchStore(url) if url else ResearchStore(f"sqlite:///{root / 'research.sqlite'}")
        )
        store.create()
        return cls(root=root, store=store, artifacts=ArtifactStore(root / "artifacts"))


@dataclass
class IngestReport:
    fetch_run: SourceFetchRun
    new_version_ids: list[str] = field(default_factory=list)
    unchanged_document_ids: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    quarantined: dict[str, str] = field(default_factory=dict)
    review_required: dict[str, str] = field(default_factory=dict)
    calendar_problems: list[str] = field(default_factory=list)


def version_id_for(document_id: str, normalized_text_hash: str, parser_version: str) -> str:
    return short_id("dv", {"d": document_id, "t": normalized_text_hash, "p": parser_version}, 20)


def chunk_id_for(version_id: str, ordinal: int, start: int, end: int, text_hash: str) -> str:
    return short_id(
        "chk",
        {
            "v": version_id,
            "o": ordinal,
            "s": start,
            "e": end,
            "h": text_hash,
            "c": CHUNKER_VERSION,
            "t": TOKENIZER_VERSION,
        },
        20,
    )


def make_chunks(version: DocumentVersion, parsed: ParsedDocument) -> list[Chunk]:
    chunks: list[Chunk] = []
    for ordinal, span in enumerate(chunk_document(parsed.text, parsed.blocks)):
        text = parsed.text[span.start : span.end]
        text_hash = sha256_text(text)
        chunks.append(
            Chunk(
                chunk_id=chunk_id_for(version.version_id, ordinal, span.start, span.end, text_hash),
                version_id=version.version_id,
                document_id=version.document_id,
                heading_path=list(span.heading_path),
                ordinal=ordinal,
                text=text,
                text_hash=text_hash,
                start_offset=span.start,
                end_offset=span.end,
                token_count=span.token_count,
                tokenizer_version=TOKENIZER_VERSION,
                chunker_version=CHUNKER_VERSION,
                available_at=version.available_at,
            )
        )
    return chunks


def seed_knowledge(store: ResearchStore, clock: Clock = utc_now) -> None:
    """Insert frozen vocabulary, policy events, releases and their assertions."""
    from research_engine.knowledge import extraction, vocabulary

    entities, aliases = vocabulary.all_seed_records()
    store.put_entities(entities)
    store.put_aliases(aliases)
    by_id = {e.entity_id: e for e in entities}
    for run, assertions in (
        extraction.extract_event_series(list(by_id.values()), clock()),
        extraction.extract_releases(vocabulary.load_releases(), by_id, clock()),
    ):
        _put_run(store, run, assertions)


def _put_run(store: ResearchStore, run, assertions) -> None:  # type: ignore[no-untyped-def]
    existing = {r.extraction_run_id for r in store.list_extraction_runs()}
    if run.extraction_run_id not in existing:
        store.put_extraction_run(run)
    store.put_assertions(assertions)


class FedIngestor:
    def __init__(
        self,
        home: EvidenceHome,
        *,
        offline: bool = True,
        fetcher: Optional[AllowlistedFetcher] = None,
        clock: Clock = utc_now,
        fixture_root: Path = fed.RAW_ROOT,
    ):
        self.home = home
        self.store = home.store
        self.artifacts = home.artifacts
        self.offline = offline
        self.fetcher = fetcher
        self.clock = clock
        self.fixture_root = fixture_root
        self._manifest = fed.load_manifest(fixture_root / "MANIFEST.json") if offline else {}
        self._run_id = ""

    # ------------------------------------------------------------ helpers
    def _attempt(
        self,
        document_id: str,
        stage: str,
        to_state: IngestionState,
        outcome: str = "ok",
        *,
        version_id: Optional[str] = None,
        artifact_hash: Optional[str] = None,
        error: Optional[str] = None,
        update_state: bool = True,
    ) -> None:
        current = self.store.item_state(fed.SOURCE_ID, document_id)
        current_state = current[0] if current else None
        if update_state:
            check_transition(current_state, to_state)
        at = self.clock()
        attempt = IngestionAttempt(
            attempt_id=short_id(
                "att",
                {
                    "d": document_id,
                    "s": stage,
                    "t": to_state.value,
                    "r": self._run_id,
                    "at": at.isoformat(),
                },
                20,
            ),
            source_id=fed.SOURCE_ID,
            document_id=document_id,
            fetch_run_id=self._run_id,
            stage=stage,
            from_state=current_state,
            to_state=to_state,
            outcome=outcome,  # type: ignore[arg-type]
            attempt_number=(current[2] + 1) if current else 1,
            attempted_at=at,
            version_id=version_id,
            artifact_hash=artifact_hash,
            error=error,
        )
        self.store.record_attempt(
            attempt, update_state=update_state, bump_attempts=(stage == "download")
        )

    def _enter_pipeline(self, document_id: str) -> None:
        current = self.store.item_state(fed.SOURCE_ID, document_id)
        state = current[0] if current else None
        if state != IngestionState.DISCOVERED:
            self._attempt(document_id, "discover", IngestionState.DISCOVERED)

    def _fail(self, document_id: str, stage: str, exc: Exception, report: IngestReport) -> None:
        quarantine = isinstance(exc, HostNotAllowed) or getattr(exc, "quarantine", False)
        if isinstance(exc, FetchError) and not exc.retryable and exc.status == 404:
            quarantine = True
        state = IngestionState.QUARANTINED if quarantine else IngestionState.FAILED_RETRYABLE
        current = self.store.item_state(fed.SOURCE_ID, document_id)
        try:
            check_transition(current[0] if current else None, state)
            legal = True
        except IllegalTransition:
            legal = False  # still recorded as an attempt; state left untouched
        self._attempt(document_id, stage, state, "failed", error=str(exc), update_state=legal)
        (report.quarantined if quarantine else report.failed)[document_id] = str(exc)

    # ------------------------------------------------------------ discovery
    def _calendar(self, report: IngestReport) -> None:
        if self.offline:
            raw = (self.fixture_root / "fed-fomc/calendar/fomccalendars.htm").read_bytes()
        else:
            assert self.fetcher is not None
            raw = self.fetcher.fetch(fed.CALENDAR_URL).content
        self.artifacts.put(raw)
        report.calendar_problems = fed.validate_against_calendar(fed.parse_calendar(raw))

    def _download(self, spec: fed.FedDocumentSpec) -> tuple[bytes, datetime]:
        if self.offline:
            entry = self._manifest[spec.url]
            raw = (self.fixture_root / entry.path).read_bytes()
            if fed.sha256_bytes(raw) != entry.sha256:
                raise FetchError(f"fixture checksum mismatch for {entry.path}", retryable=False)
            return raw, datetime.fromisoformat(entry.fetched_at.replace("Z", "+00:00"))
        assert self.fetcher is not None
        result = self.fetcher.fetch(spec.url)
        return result.content, result.fetched_at

    # ------------------------------------------------------------ main loop
    def run(self, include_synthetic: bool = False) -> IngestReport:
        started = self.clock()
        self._run_id = short_id("fr", {"s": fed.SOURCE_ID, "at": started.isoformat()}, 20)
        self.store.upsert_source(fed.fed_source())
        seed_knowledge(self.store, self.clock)
        report = IngestReport(
            fetch_run=SourceFetchRun(
                fetch_run_id=self._run_id,
                source_id=fed.SOURCE_ID,
                started_at=started,
                completed_at=started,
                outcome=FetchRunOutcome.OUTAGE,
                mode="offline_fixture" if self.offline else "online",
            )
        )
        try:
            self._calendar(report)
        except (FetchError, HostNotAllowed, OSError) as exc:
            return self._finish(report, FetchRunOutcome.OUTAGE, f"discovery failed: {exc}", None)

        specs = fed.document_specs()
        transport_failures = 0
        observed: list[datetime] = []
        for spec in specs:
            try:
                ok = self._process(spec, report, observed)
            except Exception as exc:  # recorded per item; the run continues
                self._fail(spec.document_id, "process", exc, report)
                ok = False
            if not ok and spec.document_id in report.failed:
                transport_failures += 1
        if include_synthetic:
            for correction in _load_corrections():
                self._process_correction(correction, report)
        if transport_failures == len(specs):
            outcome = FetchRunOutcome.OUTAGE
        elif report.failed or report.quarantined or report.review_required:
            outcome = FetchRunOutcome.PARTIAL
        else:
            outcome = FetchRunOutcome.SUCCESS
        error = "; ".join(f"{k}: {v}" for k, v in sorted(report.failed.items())) or None
        return self._finish(report, outcome, error, max(observed) if observed else None)

    def _finish(
        self,
        report: IngestReport,
        outcome: FetchRunOutcome,
        error: Optional[str],
        observed_at: Optional[datetime],
    ) -> IngestReport:
        run = report.fetch_run.model_copy(
            update={
                "completed_at": self.clock(),
                "outcome": outcome,
                "error": error,
                "source_observed_at": observed_at if outcome == FetchRunOutcome.SUCCESS else None,
                "items_discovered": len(fed.PINNED_MEETINGS) * 2,
                "items_new_versions": len(report.new_version_ids),
                "items_unchanged": len(report.unchanged_document_ids),
                "items_failed": len(report.failed) + len(report.quarantined),
            }
        )
        run = SourceFetchRun.model_validate(run.model_dump())
        report.fetch_run = run
        self.store.add_fetch_run(run)
        source = self.store.get_source(fed.SOURCE_ID)
        assert source is not None
        self.store.set_source_health(fed.SOURCE_ID, next_health(source.health, run))
        return report

    def _document(self, spec: fed.FedDocumentSpec) -> Document:
        return Document(
            document_id=spec.document_id,
            source_id=fed.SOURCE_ID,
            document_type=spec.document_type,
            canonical_url=spec.url,
            publisher_entity_id=fed.FED_ENTITY_ID,
            event_id=spec.meeting.event_id,
            source_native_id=spec.source_native_id,
        )

    def _process(
        self, spec: fed.FedDocumentSpec, report: IngestReport, observed: list[datetime]
    ) -> bool:
        doc_id = spec.document_id
        self.store.put_document(self._document(spec))
        try:
            raw, fetched_at = self._download(spec)
        except (FetchError, HostNotAllowed, OSError, KeyError) as exc:
            self._enter_pipeline(doc_id)
            self._fail(doc_id, "download", exc, report)
            return False
        observed.append(fetched_at)
        raw_ref = self.artifacts.put(raw)
        parser_version = f"{fed.ADAPTER_VERSION}+{HTML_PARSER_VERSION}"
        known = [
            v
            for v in self.store.list_versions(doc_id)
            if v.content_hash == raw_ref.content_hash and v.parser_version == parser_version
        ]
        if known:  # identical bytes + unchanged processing configuration: reuse
            self._attempt(
                doc_id,
                "download",
                IngestionState.DOWNLOADED,
                "skipped_unchanged",
                version_id=known[0].version_id,
                artifact_hash=raw_ref.content_hash,
                update_state=False,
            )
            report.unchanged_document_ids.append(doc_id)
            return True
        try:
            parsed = fed.parse_fed_document(raw, spec)
        except ParseError as exc:
            self._enter_pipeline(doc_id)
            self._attempt(
                doc_id, "download", IngestionState.DOWNLOADED, artifact_hash=raw_ref.content_hash
            )
            self._fail(doc_id, "parse", exc, report)
            return False
        text_hash = sha256_text(parsed.text)
        version_id = version_id_for(doc_id, text_hash, parsed.parser_version)
        if self.store.get_version(version_id) is not None:
            existing = self.store.get_version(version_id)
            note = None
            if existing is not None and existing.content_hash != raw_ref.content_hash:
                note = "raw bytes changed; normalized text unchanged; existing version reused"
            self._attempt(
                doc_id,
                "download",
                IngestionState.DOWNLOADED,
                "skipped_unchanged",
                version_id=version_id,
                artifact_hash=raw_ref.content_hash,
                error=note,
                update_state=False,
            )
            report.unchanged_document_ids.append(doc_id)
            return True

        self._enter_pipeline(doc_id)
        self._attempt(
            doc_id, "download", IngestionState.DOWNLOADED, artifact_hash=raw_ref.content_hash
        )
        norm_ref = self.artifacts.put_text(parsed.text)
        previous = [
            v
            for v in self.store.list_versions(doc_id, include_synthetic=False)
            if v.status == VersionStatus.ACTIVE
        ]
        status = VersionStatus.ACTIVE
        review_reason = None
        if (
            spec.document_type == DocumentType.FOMC_STATEMENT
            and not fed.statement_release_time_matches(parsed)
        ):
            status = VersionStatus.REVIEW_REQUIRED
            review_reason = "statement release-time line does not confirm 2:00 p.m. ET"
        if previous:
            # A changed page discovered later: the original publication time of the
            # revision is unknown, so it is available only from receipt (spec 6.2).
            supersedes = previous[-1].version_id
            published_at = fetched_at
            available_at = fetched_at
            basis = "revision detected at platform receipt; original publication time unknown"
            policy = InformationPolicy.FORWARD_RECEIPT.value
            precision = "minute"
        else:
            supersedes = None
            published_at = spec.published_at
            available_at = spec.available_at
            basis = (
                f"{fed.TIMESTAMP_RULE}: 14:00 America/New_York on "
                + (
                    "final meeting day"
                    if spec.document_type == DocumentType.FOMC_STATEMENT
                    else "calendar minutes release date"
                )
                + (
                    f" ({parsed.metadata['release_time_text']})"
                    if parsed.metadata.get("release_time_text")
                    else ""
                )
            )
            policy = fed.AVAILABILITY_POLICY
            precision = "minute"
        version = DocumentVersion(
            version_id=version_id,
            document_id=doc_id,
            source_id=fed.SOURCE_ID,
            document_type=spec.document_type,
            content_hash=raw_ref.content_hash,
            normalized_text_hash=text_hash,
            title=parsed.title,
            source_url=spec.url,
            published_at=published_at,
            published_at_precision=precision,  # type: ignore[arg-type]
            publication_time_basis=basis,
            available_at=available_at,
            availability_policy=policy,
            ingested_at=fetched_at,
            raw_artifact_uri=raw_ref.uri,
            normalized_artifact_uri=norm_ref.uri,
            media_type=parsed.media_type,
            parser_version=parsed.parser_version,
            status=status,
            supersedes=supersedes,
            fidelity_flags=[fed.FIDELITY_CURRENT_WEB],
            event_id=spec.meeting.event_id,
            char_count=len(parsed.text),
            blocks=list(parsed.blocks),
        )
        return self._finish_version(version, parsed, report, review_reason)

    def _finish_version(
        self,
        version: DocumentVersion,
        parsed: ParsedDocument,
        report: IngestReport,
        review_reason: Optional[str],
    ) -> bool:
        from research_engine.knowledge import extraction

        doc_id = version.document_id
        self.store.put_version(version)
        self._attempt(doc_id, "parse", IngestionState.PARSED, version_id=version.version_id)
        if review_reason:
            self._attempt(
                doc_id, "parse", IngestionState.REVIEW_REQUIRED, "failed", error=review_reason
            )
            report.review_required[doc_id] = review_reason
            return False
        chunks = make_chunks(version, parsed)
        self.store.put_chunks(chunks)
        self._attempt(doc_id, "chunk", IngestionState.CHUNKED, version_id=version.version_id)
        entities = {e.entity_id: e for e in self.store.list_entities()}
        superseded = self.store.get_version(version.supersedes) if version.supersedes else None
        event: Optional[Entity] = entities.get(version.event_id or "")
        for run, assertions in (
            extraction.extract_metadata(
                version, chunks, entities[fed.FED_ENTITY_ID], event, superseded, self.clock()
            ),
            extraction.extract_lexicon(version, chunks, entities, self.clock()),
        ):
            _put_run(self.store, run, assertions)
        self._attempt(doc_id, "extract", IngestionState.EXTRACTED, version_id=version.version_id)
        report.new_version_ids.append(version.version_id)
        return True

    # ------------------------------------------------------------ synthetic
    def _process_correction(self, correction: dict, report: IngestReport) -> None:
        doc_id = correction["document_id"]
        raw = (fed.FIXTURE_ROOT / correction["file"]).read_bytes()
        if fed.sha256_bytes(raw) != correction["sha256"]:
            raise RuntimeError("synthetic correction fixture checksum mismatch")
        spec = next(s for s in fed.document_specs() if s.document_id == doc_id)
        parsed = fed.parse_fed_document(raw, spec)
        parsed = ParsedDocument(
            title=f"{parsed.title} [SYNTHETIC CORRECTION]",
            text=parsed.text,
            blocks=parsed.blocks,
            parser_version=parsed.parser_version,
            media_type=parsed.media_type,
            metadata=parsed.metadata,
        )
        text_hash = sha256_text(parsed.text)
        version_id = version_id_for(doc_id, text_hash, parsed.parser_version)
        if self.store.get_version(version_id) is not None:
            report.unchanged_document_ids.append(f"{doc_id}#synthetic")
            return
        originals = [
            v
            for v in self.store.list_versions(doc_id, include_synthetic=False)
            if v.status == VersionStatus.ACTIVE
        ]
        if not originals:
            raise RuntimeError(f"no original version to correct for {doc_id}")
        raw_ref = self.artifacts.put(raw)
        norm_ref = self.artifacts.put_text(parsed.text)
        published = datetime.fromisoformat(correction["published_at"].replace("Z", "+00:00"))
        self._enter_pipeline(doc_id)
        self._attempt(
            doc_id, "download", IngestionState.DOWNLOADED, artifact_hash=raw_ref.content_hash
        )
        version = DocumentVersion(
            version_id=version_id,
            document_id=doc_id,
            source_id=fed.SOURCE_ID,
            document_type=spec.document_type,
            content_hash=raw_ref.content_hash,
            normalized_text_hash=text_hash,
            title=parsed.title,
            source_url=spec.url,
            published_at=published,
            published_at_precision="minute",
            publication_time_basis=correction["published_at_basis"],
            available_at=fed.available_instant(published),
            availability_policy=fed.AVAILABILITY_POLICY,
            ingested_at=published + timedelta(minutes=fed.AVAILABILITY_LAG_MINUTES),
            raw_artifact_uri=raw_ref.uri,
            normalized_artifact_uri=norm_ref.uri,
            media_type=parsed.media_type,
            parser_version=parsed.parser_version,
            status=VersionStatus.ACTIVE,
            supersedes=originals[-1].version_id,
            fidelity_flags=[fed.FIDELITY_SYNTHETIC],
            synthetic=True,
            event_id=spec.meeting.event_id,
            char_count=len(parsed.text),
            blocks=list(parsed.blocks),
        )
        self._finish_version(version, parsed, report, None)


def _load_corrections() -> list[dict]:
    path = fed.SYNTHETIC_ROOT / "corrections.json"
    return json.loads(path.read_text())["corrections"]
