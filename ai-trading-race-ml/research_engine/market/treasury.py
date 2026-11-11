"""U.S. Treasury daily par yield curve CSV adapter (spec 7.1, 7.2).

Treasury's daily par yield curve is derived from *indicative, bid-side*
quotations; it is a reference-curve input, never a security-level execution
feed. Observations are labelled ``indicative_bid_side_par_yield`` and
``executable=False``.

Time fields (declared assumptions, policy ``reconstructed_publication_plus_lag_v1``):

* ``observed_at``  = session date 15:30 America/New_York (curve measurement time)
* ``published_at`` = unknown for history (None)
* ``available_at`` = session date 18:00 America/New_York, labelled *reconstructed*
* ``ingested_at``  = when the raw CSV bytes were retrieved

Parsing handles the year-dependent column sets dynamically (e.g. the 4-month
column appears in late 2022 and a 1.5-month column in 2025). Percent values are
converted to decimal rates at this boundary; blank cells stay missing.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx

from research_engine.contracts.common import (
    InformationPolicy,
    sha256_bytes,
    short_id,
)
from research_engine.contracts.market import (
    CurveObservation,
    ParYieldPoint,
    SourceArtifactRef,
    TenorUnit,
    TimestampConfidence,
)
from research_engine.instruments.calendar import is_business_day, new_york_instant

from .paths import treasury_fixture_dir

log = logging.getLogger(__name__)

SOURCE_ID = "us-treasury-daily-par-yield-curve"
ALLOWED_HOSTS = frozenset({"home.treasury.gov"})
URL_TEMPLATE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
LICENSE_NOTE = (
    "U.S. Department of the Treasury daily par yield curve rates; work of the U.S. "
    "government, public domain in the United States (17 U.S.C. 105)."
)
OBSERVED_LOCAL_TIME = time(15, 30)
AVAILABLE_LOCAL_TIME = time(18, 0)
MANIFEST_NAME = "manifest.json"
MAX_ABS_RATE = Decimal("0.25")  # plausibility bound for a decimal par yield
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

_TENOR_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(wk|wks|week|weeks|mo|mos|month|months|yr|yrs|year|years)\s*$",
    re.IGNORECASE,
)


class TreasuryFetchError(RuntimeError):
    pass


class HostNotAllowedError(TreasuryFetchError):
    pass


class ArtifactConflictError(RuntimeError):
    """Re-import produced different bytes for an already stored artifact."""


# --------------------------------------------------------------------------- #
# Fetching (network; never used by tests)
# --------------------------------------------------------------------------- #


def treasury_csv_url(year: int) -> str:
    if not 1990 <= year <= 2100:
        raise ValueError(f"implausible year {year}")
    return URL_TEMPLATE.format(year=year)


def check_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise HostNotAllowedError(f"host not allowlisted for Treasury fetch: {parsed.hostname!r}")


def fetch_treasury_year(
    year: int,
    *,
    client: Optional[httpx.Client] = None,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    max_redirects: int = 3,
    sleep: Callable[[float], None] = _time.sleep,
) -> bytes:
    """Download one year's CSV with bounded retries and allowlisted redirects."""
    url = treasury_csv_url(year)
    check_host(url)
    own_client = client is None
    http = client or httpx.Client(
        timeout=30.0,
        follow_redirects=False,
        headers={"User-Agent": "fi-research-lab/1.0 (research; contact: repository owner)"},
    )
    redirects = 0
    attempt = 0
    last_error: Optional[str] = None
    try:
        while attempt < max_attempts:
            attempt += 1
            try:
                response = http.get(url)
            except httpx.TransportError as exc:
                last_error = f"transport error: {exc.__class__.__name__}"
            else:
                if response.is_redirect:
                    redirects += 1
                    if redirects > max_redirects:
                        raise TreasuryFetchError("too many redirects")
                    target = urljoin(url, response.headers.get("location", ""))
                    check_host(target)
                    url = target
                    attempt -= 1  # a validated redirect is not a failed attempt
                    continue
                if response.status_code == 200:
                    raw = response.content
                    _validate_csv_bytes(raw)
                    return raw
                if response.status_code not in RETRYABLE_STATUS:
                    raise TreasuryFetchError(f"HTTP {response.status_code} for {year}")
                last_error = f"HTTP {response.status_code}"
            if attempt < max_attempts:
                sleep(backoff_seconds * (2 ** (attempt - 1)))
        raise TreasuryFetchError(f"failed after {max_attempts} attempts: {last_error}")
    finally:
        if own_client:
            http.close()


def _validate_csv_bytes(raw: bytes) -> None:
    head = raw[:200].decode("utf-8-sig", errors="replace")
    if not head.lstrip().lower().startswith("date"):
        raise TreasuryFetchError("response is not a Treasury par yield CSV (no Date header)")


# --------------------------------------------------------------------------- #
# Raw artifact storage with checksum manifest (idempotent)
# --------------------------------------------------------------------------- #


def artifact_file_name(year: int) -> str:
    return f"daily_treasury_par_yield_curve_{year}.csv"


def load_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    if not path.exists():
        return {
            "sourceId": SOURCE_ID,
            "licenseNote": LICENSE_NOTE,
            "urlTemplate": URL_TEMPLATE,
            "artifacts": [],
        }
    return json.loads(path.read_text())


def _write_manifest(root: Path, manifest: dict) -> None:
    manifest["artifacts"] = sorted(manifest["artifacts"], key=lambda a: a["localPath"])
    (root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def store_raw_artifact(
    year: int,
    raw: bytes,
    root: Optional[Path] = None,
    *,
    retrieved_at: Optional[datetime] = None,
    allow_revision: bool = False,
) -> SourceArtifactRef:
    """Persist raw bytes once; identical re-imports are no-ops.

    Different bytes for an already stored year raise ``ArtifactConflictError``
    unless ``allow_revision`` is set, in which case the new bytes are stored
    under a checksum-suffixed name and both remain in the manifest.
    """
    _validate_csv_bytes(raw)
    root = root or treasury_fixture_dir()
    root.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(raw)
    manifest = load_manifest(root)
    for entry in manifest["artifacts"]:
        if entry["year"] == year and entry["sha256"] == digest:
            return _artifact_from_entry(entry)
    name = artifact_file_name(year)
    if any(entry["year"] == year for entry in manifest["artifacts"]):
        if not allow_revision:
            raise ArtifactConflictError(
                f"stored Treasury {year} artifact differs from new bytes ({digest})"
            )
        name = name.replace(".csv", f"_{digest[7:19]}.csv")
    (root / name).write_bytes(raw)
    retrieved = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    entry = {
        "artifactId": f"tsy-csv-{year}-{digest[7:19]}",
        "year": year,
        "localPath": name,
        "sha256": digest,
        "sizeBytes": len(raw),
        "uri": treasury_csv_url(year),
        "retrievedAt": retrieved.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    manifest["artifacts"].append(entry)
    _write_manifest(root, manifest)
    return _artifact_from_entry(entry)


def _artifact_from_entry(entry: dict) -> SourceArtifactRef:
    return SourceArtifactRef(
        artifact_id=entry["artifactId"],
        source_id=SOURCE_ID,
        uri=entry["uri"],
        local_path=f"market/treasury/{entry['localPath']}",
        sha256=entry["sha256"],
        size_bytes=entry["sizeBytes"],
        retrieved_at=entry["retrievedAt"],
        license_note=LICENSE_NOTE,
    )


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_tenor_header(header: str) -> Optional[tuple[str, int, TenorUnit]]:
    """Map a source column header to (label, count, unit); None if not a tenor."""
    match = _TENOR_RE.match(header)
    if not match:
        return None
    number = Decimal(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("w"):
        if number != number.to_integral_value():
            return None
        return f"{int(number)}W", int(number), TenorUnit.WEEKS
    if unit.startswith("m"):
        if number == number.to_integral_value():
            return f"{int(number)}M", int(number), TenorUnit.MONTHS
        if number == Decimal("1.5"):  # Treasury's "1.5 Month" column is the 6-week bill
            return "6W", 6, TenorUnit.WEEKS
        raise ValueError(f"unsupported fractional month tenor {header!r}")
    if number != number.to_integral_value():
        return None
    return f"{int(number)}Y", int(number), TenorUnit.YEARS


def tenor_sort_key(count: int, unit: TenorUnit) -> Decimal:
    """Nominal months, for ordering only."""
    if unit is TenorUnit.WEEKS:
        return Decimal(count) * Decimal(12) / Decimal(52)
    if unit is TenorUnit.MONTHS:
        return Decimal(count)
    return Decimal(count * 12)


def _parse_session_date(text: str) -> date:
    text = text.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date {text!r}")


def _parse_percent(text: str) -> Optional[Decimal]:
    cleaned = text.strip()
    if cleaned == "" or cleaned.upper() in {"N/A", "NA", "ND", "."}:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid yield value {text!r}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite yield value {text!r}")
    return value / Decimal(100)


@dataclass(frozen=True)
class ParsedFile:
    observations: list[CurveObservation]
    tenor_columns: list[str]
    unrecognized_columns: list[str]
    warnings: list[str] = field(default_factory=list)


def parse_treasury_csv(raw: bytes, artifact: SourceArtifactRef) -> ParsedFile:
    """Parse raw CSV bytes into observations; deterministic for identical bytes."""
    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("empty Treasury CSV") from exc
    header = [h.strip() for h in header]
    if not header or header[0].lower() != "date":
        raise ValueError("first column must be Date")
    columns: list[tuple[int, str, int, TenorUnit]] = []
    unrecognized: list[str] = []
    for index, name in enumerate(header[1:], start=1):
        parsed = parse_tenor_header(name)
        if parsed is None:
            unrecognized.append(name)
            continue
        columns.append((index, *parsed))
    labels = [c[1] for c in columns]
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate tenor columns")
    warnings = [f"unrecognized_column:{name}" for name in unrecognized]
    by_date: dict[date, CurveObservation] = {}
    retrieved = artifact.retrieved_at
    for row_number, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            continue
        session = _parse_session_date(row[0])
        points: list[ParYieldPoint] = []
        missing: list[str] = []
        flags: list[str] = list(warnings)
        for index, label, count, unit in columns:
            cell = row[index] if index < len(row) else ""
            value = _parse_percent(cell)
            if value is None:
                missing.append(label)
                continue
            if abs(value) > MAX_ABS_RATE:
                flags.append(f"rate_out_of_range:{label}")
            points.append(
                ParYieldPoint(tenor=label, period_count=count, period_unit=unit, par_yield=value)
            )
        if not is_business_day(session):
            flags.append("non_business_day_session")
        flags.append("availability_reconstructed")
        observation_id = short_id(
            "tsy-obs",
            {
                "source": SOURCE_ID,
                "session": session.isoformat(),
                "points": [[p.tenor, str(p.par_yield)] for p in points],
                "missing": missing,
            },
        )
        obs = CurveObservation(
            observation_id=observation_id,
            source_id=SOURCE_ID,
            session_date=session,
            observed_at=new_york_instant(session, OBSERVED_LOCAL_TIME),
            published_at=None,
            available_at=new_york_instant(session, AVAILABLE_LOCAL_TIME),
            ingested_at=retrieved,
            information_policy=InformationPolicy.RECONSTRUCTED_PUBLICATION_PLUS_LAG,
            availability_reconstructed=True,
            timestamp_confidence=TimestampConfidence.RECONSTRUCTED,
            points=points,
            missing_tenors=missing,
            source_artifact=artifact.model_copy(update={"row_ref": f"row:{row_number}"}),
            quality_flags=sorted(set(flags)),
        )
        if session in by_date:
            if by_date[session].observation_id != obs.observation_id:
                warnings.append(f"conflicting_duplicate_session:{session.isoformat()}")
            continue
        by_date[session] = obs
    observations = [by_date[d] for d in sorted(by_date)]
    return ParsedFile(observations, labels, unrecognized, warnings)


# --------------------------------------------------------------------------- #
# Fixture dataset import
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TreasuryDataset:
    observations: dict[date, CurveObservation]
    artifacts: list[SourceArtifactRef]
    tenor_columns_by_artifact: dict[str, list[str]]
    warnings: list[str]
    conflicts: list[date]

    def between(self, start: date, end: date) -> list[CurveObservation]:
        return [obs for d, obs in self.observations.items() if start <= d <= end]


def verify_artifact(root: Path, entry: dict) -> tuple[bool, str]:
    path = root / entry["localPath"]
    if not path.exists():
        return False, "missing"
    actual = sha256_bytes(path.read_bytes())
    return actual == entry["sha256"], actual


def import_treasury_dataset(root: Optional[Path] = None) -> TreasuryDataset:
    """Parse every manifest artifact after checksum verification (idempotent)."""
    root = Path(root or treasury_fixture_dir())
    manifest = load_manifest(root)
    observations: dict[date, CurveObservation] = {}
    artifacts: list[SourceArtifactRef] = []
    tenor_columns: dict[str, list[str]] = {}
    warnings: list[str] = []
    conflicts: list[date] = []
    for entry in sorted(manifest["artifacts"], key=lambda e: (e["year"], e["retrievedAt"])):
        ok, actual = verify_artifact(root, entry)
        if not ok:
            raise ArtifactConflictError(
                f"checksum mismatch for {entry['localPath']}: expected {entry['sha256']}, "
                f"got {actual}"
            )
        artifact = _artifact_from_entry(entry)
        artifacts.append(artifact)
        parsed = parse_treasury_csv((root / entry["localPath"]).read_bytes(), artifact)
        tenor_columns[artifact.artifact_id] = parsed.tenor_columns
        warnings.extend(f"{artifact.artifact_id}:{w}" for w in parsed.warnings)
        for obs in parsed.observations:
            existing = observations.get(obs.session_date)
            if existing is not None:
                if existing.observation_id != obs.observation_id:
                    # A later artifact (revision) for the same session: keep the
                    # first-retrieved value and flag the conflict explicitly.
                    conflicts.append(obs.session_date)
                continue
            observations[obs.session_date] = obs
    ordered = {d: observations[d] for d in sorted(observations)}
    return TreasuryDataset(ordered, artifacts, tenor_columns, warnings, sorted(set(conflicts)))


@lru_cache(maxsize=4)
def _cached_dataset(root: str) -> TreasuryDataset:
    return import_treasury_dataset(Path(root))


def default_treasury_dataset() -> TreasuryDataset:
    return _cached_dataset(str(treasury_fixture_dir()))
