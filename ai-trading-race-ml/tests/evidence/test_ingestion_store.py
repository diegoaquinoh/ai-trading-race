"""Artifact store, research store, ingestion state machine, idempotency, outages, fetch safety."""

from __future__ import annotations

import os
import stat

import httpx
import pytest

from research_engine.contracts.common import sha256_bytes
from research_engine.contracts.evidence import (
    FetchRunOutcome,
    IngestionState,
    SourceHealthStatus,
)
from research_engine.evidence import fed
from research_engine.evidence.artifacts import ArtifactIntegrityError, ArtifactStore
from research_engine.evidence.fetch import AllowlistedFetcher, HostNotAllowed, validate_url
from research_engine.evidence.ingest import EvidenceHome, FedIngestor
from research_engine.evidence.state import IllegalTransition, check_transition, freshness
from research_engine.evidence.store import ImmutableRecordConflict, ResearchStore

from .conftest import TickClock, utc


def test_artifact_store_is_content_addressed_and_immutable(tmp_path):
    store = ArtifactStore(tmp_path)
    ref = store.put(b"hello")
    assert ref.content_hash == sha256_bytes(b"hello")
    assert ref.uri.startswith("artifact://sha256/")
    assert store.put(b"hello") == ref  # idempotent
    assert store.get(ref.uri) == b"hello"
    path = tmp_path / "sha256" / ref.content_hash[7:9] / ref.content_hash[7:]
    assert not os.stat(path).st_mode & stat.S_IWUSR  # read-only
    os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)
    path.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError):
        store.get(ref.uri)


def test_store_create_is_idempotent_and_versioned(tmp_path):
    store = ResearchStore.sqlite(tmp_path / "r.sqlite")
    assert store.schema_version() == 1
    assert store.create() == 1
    again = ResearchStore.sqlite(tmp_path / "r.sqlite")
    assert again.schema_version() == 1


def test_canonical_records_are_immutable(home):
    version = home.store.list_versions()[0]
    assert home.store.put_version(version) is False  # same payload: no-op
    changed = version.model_copy(update={"title": "rewritten"})
    with pytest.raises(ImmutableRecordConflict):
        home.store.put_version(changed)


def test_reingest_identical_content_reuses_everything(home):
    before_versions = len(home.store.list_versions())
    before_chunks = sum(
        1
        for v in home.store.list_versions()
        for _ in home.store.chunks_for_versions([v.version_id])
    )
    report = FedIngestor(home, offline=True, clock=TickClock(utc(2026, 11, 7))).run(
        include_synthetic=True
    )
    assert report.new_version_ids == []
    assert len(report.unchanged_document_ids) == 33
    assert len(home.store.list_versions()) == before_versions
    after_chunks = sum(
        1
        for v in home.store.list_versions()
        for _ in home.store.chunks_for_versions([v.version_id])
    )
    assert after_chunks == before_chunks
    skipped = [
        a for a in home.store.list_attempts(fed.SOURCE_ID) if a.outcome == "skipped_unchanged"
    ]
    assert len(skipped) >= 32  # every attempt is recorded, even unchanged ones


def test_every_stage_attempt_is_recorded(home):
    attempts = [
        a
        for a in home.store.list_attempts(fed.SOURCE_ID)
        if a.document_id == "doc-fed-fomc-minutes-20240131"
    ]
    stages = [a.to_state for a in attempts if a.outcome == "ok"]
    for state in (
        IngestionState.DISCOVERED,
        IngestionState.DOWNLOADED,
        IngestionState.PARSED,
        IngestionState.CHUNKED,
        IngestionState.EXTRACTED,
    ):
        assert state in stages


def test_versions_preserve_time_fields_and_fidelity(home):
    versions = {v.document_id: v for v in home.store.list_versions(include_synthetic=False)}
    minutes = versions["doc-fed-fomc-minutes-20240131"]
    statement = versions["doc-fed-fomc-statement-20240131"]
    assert statement.published_at == utc(2024, 1, 31, 19, 0)
    assert minutes.published_at == utc(2024, 2, 21, 19, 0)
    assert minutes.available_at == utc(2024, 2, 21, 21, 0)
    assert minutes.availability_policy == "reconstructed_publication_plus_lag_v1"
    assert fed.FIDELITY_CURRENT_WEB in minutes.fidelity_flags
    assert minutes.ingested_at > minutes.available_at  # fetched in 2026: reconstructed availability
    text = ArtifactStore(home.root / "artifacts").get_text(minutes.normalized_artifact_uri)
    for chunk in home.store.chunks_for_versions([minutes.version_id]):
        assert text[chunk.start_offset : chunk.end_offset] == chunk.text


def test_state_machine_rejects_skips():
    check_transition(None, IngestionState.DISCOVERED)
    with pytest.raises(IllegalTransition):
        check_transition(None, IngestionState.PARSED)
    with pytest.raises(IllegalTransition):
        check_transition(IngestionState.DOWNLOADED, IngestionState.ACTIVE)
    with pytest.raises(IllegalTransition):
        check_transition(IngestionState.QUARANTINED, IngestionState.PARSED)


def test_url_allowlist_and_redirect_validation():
    validate_url("https://www.federalreserve.gov/x.htm", fed.ALLOWED_HOSTS)
    for bad in (
        "http://www.federalreserve.gov/x.htm",
        "https://evil.example/x.htm",
        "https://user:pw@www.federalreserve.gov/x",
        "https://www.federalreserve.gov:8443/x",
    ):
        with pytest.raises(HostNotAllowed):
            validate_url(bad, fed.ALLOWED_HOSTS)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/stolen"})

    fetcher = AllowlistedFetcher(
        allowed_hosts=fed.ALLOWED_HOSTS,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
    )
    with pytest.raises(HostNotAllowed):
        fetcher.fetch("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")


def test_same_host_redirect_is_followed():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/old.htm":
            return httpx.Response(301, headers={"location": "/new.htm"})
        return httpx.Response(200, content=b"ok", headers={"content-type": "text/html"})

    fetcher = AllowlistedFetcher(
        allowed_hosts=fed.ALLOWED_HOSTS,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
    )
    result = fetcher.fetch("https://www.federalreserve.gov/old.htm")
    assert result.final_url == "https://www.federalreserve.gov/new.htm"
    assert result.redirects == ("https://www.federalreserve.gov/new.htm",)


def test_source_outage_is_visible_and_does_not_advance_freshness(tmp_path):
    clock = TickClock(utc(2026, 11, 6))
    evidence_home = EvidenceHome.open(tmp_path / "home")
    ok = FedIngestor(evidence_home, offline=True, clock=clock).run()
    assert ok.fetch_run.outcome == FetchRunOutcome.SUCCESS
    healthy = evidence_home.store.get_source(fed.SOURCE_ID).health
    assert healthy.status == SourceHealthStatus.HEALTHY
    observed = healthy.last_success_at
    assert observed is not None
    versions_before = {v.version_id for v in evidence_home.store.list_versions()}

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    fetcher = AllowlistedFetcher(
        allowed_hosts=fed.ALLOWED_HOSTS, transport=httpx.MockTransport(down), sleep=lambda s: None
    )
    outage = FedIngestor(evidence_home, offline=False, fetcher=fetcher, clock=clock).run()
    assert outage.fetch_run.outcome == FetchRunOutcome.OUTAGE
    health = evidence_home.store.get_source(fed.SOURCE_ID).health
    assert health.status == SourceHealthStatus.OUTAGE
    assert health.last_success_at == observed  # freshness not advanced
    assert health.consecutive_failures == 1
    assert health.last_attempt_at > observed
    runs = evidence_home.store.list_fetch_runs(fed.SOURCE_ID)
    assert [r.outcome for r in runs] == [FetchRunOutcome.SUCCESS, FetchRunOutcome.OUTAGE]
    assert {v.version_id for v in evidence_home.store.list_versions()} == versions_before
    # Stale check uses the last *successful* observation, never wall time of attempts.
    source = evidence_home.store.get_source(fed.SOURCE_ID)
    recovered = source.model_copy(
        update={"health": source.health.model_copy(update={"status": SourceHealthStatus.HEALTHY})}
    )
    assert freshness(recovered, utc(2027, 6, 1)).status == SourceHealthStatus.STALE


def test_document_download_failures_are_partial_not_silent(tmp_path):
    clock = TickClock(utc(2026, 11, 6))
    evidence_home = EvidenceHome.open(tmp_path / "home")
    calendar = (fed.RAW_ROOT / "fed-fomc/calendar/fomccalendars.htm").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("fomccalendars.htm"):
            return httpx.Response(200, content=calendar)
        if "fomcminutes20240131" in path:
            return httpx.Response(404)
        if "monetary20240131a" in path:
            return httpx.Response(503)
        for spec in fed.document_specs():
            if spec.url.endswith(path):
                return httpx.Response(200, content=(fed.RAW_ROOT / spec.fixture_path).read_bytes())
        return httpx.Response(404)

    fetcher = AllowlistedFetcher(
        allowed_hosts=fed.ALLOWED_HOSTS,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
    )
    report = FedIngestor(evidence_home, offline=False, fetcher=fetcher, clock=clock).run()
    assert report.fetch_run.outcome == FetchRunOutcome.PARTIAL
    assert "doc-fed-fomc-minutes-20240131" in report.quarantined  # permanent 404 -> coverage gap
    assert "doc-fed-fomc-statement-20240131" in report.failed  # 503 after retries -> retryable
    state = evidence_home.store.item_state(fed.SOURCE_ID, "doc-fed-fomc-statement-20240131")
    assert state[0] == IngestionState.FAILED_RETRYABLE
    health = evidence_home.store.get_source(fed.SOURCE_ID).health
    assert health.status == SourceHealthStatus.DEGRADED
    assert health.last_success_at is None
