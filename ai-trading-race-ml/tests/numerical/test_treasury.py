"""Treasury par-yield CSV adapter: saved fixtures, dynamic columns, idempotency,
time fields, labelling, bounded retries and host allowlist (no network)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest

from research_engine.contracts.common import sha256_bytes
from research_engine.contracts.market import SourceArtifactRef
from research_engine.market import treasury
from research_engine.market.paths import treasury_fixture_dir
from research_engine.market.treasury import (
    ArtifactConflictError,
    HostNotAllowedError,
    TreasuryFetchError,
    check_host,
    fetch_treasury_year,
    import_treasury_dataset,
    parse_tenor_header,
    parse_treasury_csv,
    store_raw_artifact,
)

TENORS_2023 = ["1M", "2M", "3M", "4M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]


@pytest.fixture(scope="module")
def dataset():
    return import_treasury_dataset()


def _artifact() -> SourceArtifactRef:
    return SourceArtifactRef(
        artifact_id="test-csv",
        source_id=treasury.SOURCE_ID,
        uri="test://csv",
        sha256="sha256:" + "2" * 64,
        size_bytes=1,
        retrieved_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
    )


def test_saved_fixtures_parse(dataset):
    assert len(dataset.artifacts) == 2
    assert len(dataset.observations) == 500
    assert dataset.conflicts == [] and dataset.warnings == []
    assert sum(1 for d in dataset.observations if d.year == 2023) == 250
    first = dataset.observations[date(2023, 1, 3)]
    expected = "4.17 4.42 4.53 4.70 4.77 4.72 4.40 4.18 3.94 3.89 3.79 4.06 3.88".split()
    assert [p.tenor for p in first.points] == TENORS_2023
    assert [p.par_yield for p in first.points] == [Decimal(v) / 100 for v in expected]
    last = dataset.observations[date(2024, 12, 31)]
    assert last.yield_for("10Y") == Decimal("0.0458")
    assert last.yield_for("30Y") == Decimal("0.0478")
    assert first.missing_tenors == []


def test_fixture_checksums_match_manifest(dataset):
    root = treasury_fixture_dir()
    for artifact in dataset.artifacts:
        raw = (root / artifact.local_path.split("/")[-1]).read_bytes()
        assert sha256_bytes(raw) == artifact.sha256
        assert artifact.size_bytes == len(raw)
        assert "public domain" in artifact.license_note


def test_time_fields_and_labels(dataset):
    winter = dataset.observations[date(2023, 1, 3)]
    summer = dataset.observations[date(2023, 7, 3)]
    assert winter.observed_at == datetime(2023, 1, 3, 20, 30, tzinfo=timezone.utc)  # 15:30 EST
    assert winter.available_at == datetime(2023, 1, 3, 23, 0, tzinfo=timezone.utc)  # 18:00 EST
    assert summer.observed_at == datetime(2023, 7, 3, 19, 30, tzinfo=timezone.utc)  # 15:30 EDT
    assert summer.available_at == datetime(2023, 7, 3, 22, 0, tzinfo=timezone.utc)  # 18:00 EDT
    for obs in (winter, summer):
        assert obs.published_at is None
        assert obs.availability_reconstructed
        assert obs.information_policy.value == "reconstructed_publication_plus_lag_v1"
        assert obs.timestamp_confidence.value == "reconstructed"
        assert obs.executable is False
        assert obs.quote_basis == "indicative_bid_side_par_yield"
        assert obs.ingested_at == datetime(2026, 11, 5, 17, 58, 11, tzinfo=timezone.utc)
        assert obs.source_artifact.row_ref.startswith("row:")


def test_dynamic_columns_missing_values_and_unknown_columns():
    raw = (
        b'Date,"2 Yr","1 Mo","1.5 Month","10 Yr","Extra Note"\r\n'
        b"02/18/2025,4.29,4.36,4.33,,x\r\n"
        b"02/19/2025,N/A,4.35,4.32,4.53,y\r\n"
    )
    parsed = parse_treasury_csv(raw, _artifact())
    assert parsed.tenor_columns == ["2Y", "1M", "6W", "10Y"]
    assert parsed.unrecognized_columns == ["Extra Note"]
    a, b = parsed.observations
    assert a.missing_tenors == ["10Y"] and a.yield_for("10Y") is None
    assert b.missing_tenors == ["2Y"]
    assert a.yield_for("6W") == Decimal("0.0433")
    assert "unrecognized_column:Extra Note" in a.quality_flags
    assert parse_tenor_header("4 Mo") == ("4M", 4, parse_tenor_header("1 Mo")[2])
    assert parse_tenor_header("Date") is None


def test_out_of_range_and_non_business_day_flagged():
    raw = b'Date,"1 Mo","10 Yr"\n01/07/2023,4.0,30.5\n'  # Saturday; 30.5% implausible
    obs = parse_treasury_csv(raw, _artifact()).observations[0]
    assert "rate_out_of_range:10Y" in obs.quality_flags
    assert "non_business_day_session" in obs.quality_flags
    assert obs.yield_for("10Y") == Decimal("0.305")  # kept, flagged; curve builder excludes


def test_reimport_is_idempotent(tmp_path, dataset):
    root = treasury_fixture_dir()
    raw = (root / "daily_treasury_par_yield_curve_2023.csv").read_bytes()
    when = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    first = store_raw_artifact(2023, raw, tmp_path, retrieved_at=when)
    second = store_raw_artifact(2023, raw, tmp_path, retrieved_at=datetime.now(timezone.utc))
    assert first == second
    assert len(treasury.load_manifest(tmp_path)["artifacts"]) == 1
    again = import_treasury_dataset(tmp_path)
    ids = [o.observation_id for o in again.observations.values()]
    assert ids == [o.observation_id for d, o in dataset.observations.items() if d.year == 2023]
    assert again.observations == import_treasury_dataset(tmp_path).observations


def test_revised_bytes_conflict_unless_allowed(tmp_path):
    root = treasury_fixture_dir()
    raw = (root / "daily_treasury_par_yield_curve_2023.csv").read_bytes()
    store_raw_artifact(2023, raw, tmp_path)
    revised = raw.replace(b"12/29/2023,5.60", b"12/29/2023,5.61", 1)
    with pytest.raises(ArtifactConflictError):
        store_raw_artifact(2023, revised, tmp_path)
    store_raw_artifact(2023, revised, tmp_path, allow_revision=True)
    imported = import_treasury_dataset(tmp_path)
    assert imported.conflicts == [date(2023, 12, 29)]
    # The first-retrieved value is kept; the revision is flagged, not merged.
    assert imported.observations[date(2023, 12, 29)].yield_for("1M") == Decimal("0.056")


def test_tampered_artifact_rejected(tmp_path):
    root = treasury_fixture_dir()
    raw = (root / "daily_treasury_par_yield_curve_2024.csv").read_bytes()
    store_raw_artifact(2024, raw, tmp_path)
    (tmp_path / "daily_treasury_par_yield_curve_2024.csv").write_bytes(raw + b"\n")
    with pytest.raises(ArtifactConflictError):
        import_treasury_dataset(tmp_path)


def test_host_allowlist():
    check_host(treasury.treasury_csv_url(2023))
    for url in ("https://evil.example.com/x.csv", "http://home.treasury.gov/x.csv"):
        with pytest.raises(HostNotAllowedError):
            check_host(url)


CSV = b'Date,"1 Mo"\n01/03/2023,4.17\n'


def _client(responses):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        status, headers, body = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, headers=headers, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_fetch_retries_then_succeeds():
    client, calls = _client([(503, {}, b""), (200, {}, CSV)])
    sleeps: list[float] = []
    assert fetch_treasury_year(2023, client=client, sleep=sleeps.append) == CSV
    assert len(calls) == 2 and sleeps == [1.0]


def test_fetch_bounded_retries_and_non_retryable():
    client, calls = _client([(503, {}, b"")])
    with pytest.raises(TreasuryFetchError):
        fetch_treasury_year(2023, client=client, sleep=lambda _s: None, max_attempts=3)
    assert len(calls) == 3
    client, calls = _client([(404, {}, b"")])
    with pytest.raises(TreasuryFetchError):
        fetch_treasury_year(2023, client=client, sleep=lambda _s: None)
    assert len(calls) == 1


def test_fetch_rejects_redirect_to_other_host_and_non_csv():
    client, _ = _client([(302, {"location": "https://evil.example.com/a.csv"}, b"")])
    with pytest.raises(HostNotAllowedError):
        fetch_treasury_year(2023, client=client, sleep=lambda _s: None)
    client, _ = _client([(200, {}, b"<html>error</html>")])
    with pytest.raises(TreasuryFetchError):
        fetch_treasury_year(2023, client=client, sleep=lambda _s: None)
