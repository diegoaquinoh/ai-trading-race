"""Federal Reserve FOMC statements and minutes adapter (2023-01 .. 2024-12).

Discovery: a pinned meeting table, validated against the FOMC calendar page
(``pinned_list_validated_by_calendar``). Only ``www.federalreserve.gov`` is
fetched; redirects are re-validated (``fetch.AllowlistedFetcher``).

Timestamp rule ``fomc_release_1400_et_v1``:

* Statements: 14:00 America/New_York on the final meeting day. The statement
  page itself carries "For release at 2:00 p.m. EST/EDT", recorded as evidence.
* Minutes: 14:00 America/New_York on the release date shown on the FOMC
  calendar ("Released <date>"), about three weeks after the meeting.

Availability policy ``reconstructed_publication_plus_lag_v1``: ``available_at =
published_at + 120 minutes`` (declared conservative acquisition/processing lag).
This is *reconstructed* availability for historical replay (spec 6.2).

Fidelity: the stored bytes are the *current* web versions fetched in 2026, not
archived originals. Every version carries the ``current_web_version_not_archived_original``
flag; nothing here claims the text is byte-identical to the original release.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from research_engine.contracts.common import sha256_bytes, utc_to_str
from research_engine.contracts.evidence import (
    DiscoveryMethod,
    DocumentType,
    RetryPolicy,
    Source,
)

from .fetch import AllowlistedFetcher
from .parsing import HtmlParseConfig, ParsedDocument, parse_html

SOURCE_ID = "fed-fomc"
ALLOWED_HOSTS = ("www.federalreserve.gov",)
BASE_URL = "https://www.federalreserve.gov"
CALENDAR_URL = f"{BASE_URL}/monetarypolicy/fomccalendars.htm"
ADAPTER_VERSION = "fed-fomc-adapter-v1"
TIMESTAMP_RULE = "fomc_release_1400_et_v1"
AVAILABILITY_POLICY = "reconstructed_publication_plus_lag_v1"
AVAILABILITY_LAG_MINUTES = 120
NEW_YORK = ZoneInfo("America/New_York")
RELEASE_TIME = time(14, 0)
FIDELITY_CURRENT_WEB = "current_web_version_not_archived_original"
FIDELITY_SYNTHETIC = "synthetic_test_fixture_not_a_federal_reserve_publication"
FED_ENTITY_ID = "inst-fomc"
FED_BOARD_ENTITY_ID = "inst-frb-board"

ML_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ML_ROOT / "fixtures" / "evidence"
RAW_ROOT = FIXTURE_ROOT / "raw"
MANIFEST_PATH = RAW_ROOT / "MANIFEST.json"
SYNTHETIC_ROOT = FIXTURE_ROOT / "synthetic"


@dataclass(frozen=True)
class FomcMeeting:
    start: date
    end: date
    minutes_released: date

    @property
    def key(self) -> str:
        return self.end.strftime("%Y%m%d")

    @property
    def event_id(self) -> str:
        return f"event-fomc-{self.key}"

    @property
    def statement_url(self) -> str:
        return f"{BASE_URL}/newsevents/pressreleases/monetary{self.key}a.htm"

    @property
    def minutes_url(self) -> str:
        return f"{BASE_URL}/monetarypolicy/fomcminutes{self.key}.htm"

    @property
    def label(self) -> str:
        if self.start.month == self.end.month:
            span = f"{self.start:%B} {self.start.day}–{self.end.day}, {self.end.year}"
        else:
            span = (
                f"{self.start:%B} {self.start.day}–{self.end:%B} {self.end.day}, "
                f"{self.end.year}"
            )
        return f"FOMC meeting {span}"


def _d(text: str) -> date:
    return date.fromisoformat(text)


# Pinned meeting table. Minutes release dates are validated against the FOMC
# calendar page fixture (``validate_against_calendar``) by tests.
PINNED_MEETINGS: tuple[FomcMeeting, ...] = (
    FomcMeeting(_d("2023-01-31"), _d("2023-02-01"), _d("2023-02-22")),
    FomcMeeting(_d("2023-03-21"), _d("2023-03-22"), _d("2023-04-12")),
    FomcMeeting(_d("2023-05-02"), _d("2023-05-03"), _d("2023-05-24")),
    FomcMeeting(_d("2023-06-13"), _d("2023-06-14"), _d("2023-07-05")),
    FomcMeeting(_d("2023-07-25"), _d("2023-07-26"), _d("2023-08-16")),
    FomcMeeting(_d("2023-09-19"), _d("2023-09-20"), _d("2023-10-11")),
    FomcMeeting(_d("2023-10-31"), _d("2023-11-01"), _d("2023-11-21")),
    FomcMeeting(_d("2023-12-12"), _d("2023-12-13"), _d("2024-01-03")),
    FomcMeeting(_d("2024-01-30"), _d("2024-01-31"), _d("2024-02-21")),
    FomcMeeting(_d("2024-03-19"), _d("2024-03-20"), _d("2024-04-10")),
    FomcMeeting(_d("2024-04-30"), _d("2024-05-01"), _d("2024-05-22")),
    FomcMeeting(_d("2024-06-11"), _d("2024-06-12"), _d("2024-07-03")),
    FomcMeeting(_d("2024-07-30"), _d("2024-07-31"), _d("2024-08-21")),
    FomcMeeting(_d("2024-09-17"), _d("2024-09-18"), _d("2024-10-09")),
    FomcMeeting(_d("2024-11-06"), _d("2024-11-07"), _d("2024-11-26")),
    FomcMeeting(_d("2024-12-17"), _d("2024-12-18"), _d("2025-01-08")),
)


def meeting_by_key(key: str) -> FomcMeeting:
    for meeting in PINNED_MEETINGS:
        if meeting.key == key:
            return meeting
    raise KeyError(key)


def release_instant(day: date) -> datetime:
    """14:00 America/New_York on ``day`` as a UTC instant (DST-aware)."""
    return datetime.combine(day, RELEASE_TIME, tzinfo=NEW_YORK).astimezone(timezone.utc)


def available_instant(published_at: datetime) -> datetime:
    return published_at + timedelta(minutes=AVAILABILITY_LAG_MINUTES)


@dataclass(frozen=True)
class FedDocumentSpec:
    document_id: str
    document_type: DocumentType
    url: str
    meeting: FomcMeeting
    published_at: datetime
    fixture_path: str  # relative to RAW_ROOT

    @property
    def available_at(self) -> datetime:
        return available_instant(self.published_at)

    @property
    def source_native_id(self) -> str:
        return self.url.rsplit("/", 1)[-1].removesuffix(".htm")


def document_specs(meetings: Iterable[FomcMeeting] = PINNED_MEETINGS) -> list[FedDocumentSpec]:
    specs: list[FedDocumentSpec] = []
    for meeting in meetings:
        specs.append(
            FedDocumentSpec(
                document_id=f"doc-fed-fomc-statement-{meeting.key}",
                document_type=DocumentType.FOMC_STATEMENT,
                url=meeting.statement_url,
                meeting=meeting,
                published_at=release_instant(meeting.end),
                fixture_path=f"fed-fomc/statements/monetary{meeting.key}a.htm",
            )
        )
        specs.append(
            FedDocumentSpec(
                document_id=f"doc-fed-fomc-minutes-{meeting.key}",
                document_type=DocumentType.FOMC_MINUTES,
                url=meeting.minutes_url,
                meeting=meeting,
                published_at=release_instant(meeting.minutes_released),
                fixture_path=f"fed-fomc/minutes/fomcminutes{meeting.key}.htm",
            )
        )
    return specs


# --------------------------------------------------------------------------- #
# Source registry entry
# --------------------------------------------------------------------------- #


def fed_source() -> Source:
    return Source(
        source_id=SOURCE_ID,
        name="Federal Reserve FOMC policy statements and minutes",
        owner="workstream-b-evidence",
        publisher_entity_id=FED_ENTITY_ID,
        allowed_hosts=list(ALLOWED_HOSTS),
        discovery_method=DiscoveryMethod.PINNED_LIST_VALIDATED_BY_CALENDAR,
        discovery_urls=[CALENDAR_URL],
        document_types=[DocumentType.FOMC_STATEMENT, DocumentType.FOMC_MINUTES],
        expected_cadence="8 scheduled meetings per year; minutes about 3 weeks after each",
        parser_version=f"{ADAPTER_VERSION}+html-bs4-v1",
        adapter_version=ADAPTER_VERSION,
        timestamp_rule=TIMESTAMP_RULE,
        availability_policy=AVAILABILITY_POLICY,
        availability_lag_minutes=AVAILABILITY_LAG_MINUTES,
        retry=RetryPolicy(),
        freshness_expectation_hours=24 * 60,
        license_note=(
            "U.S. federal government work (Board of Governors of the Federal Reserve "
            "System); public domain in the United States."
        ),
    )


# --------------------------------------------------------------------------- #
# Calendar discovery
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CalendarMeeting:
    year: int
    month_label: str
    date_label: str
    statement_url: Optional[str]
    minutes_url: Optional[str]
    minutes_released: Optional[date]


_RELEASED = re.compile(r"Released\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")


def parse_calendar(raw: bytes) -> list[CalendarMeeting]:
    soup = BeautifulSoup(raw, "html.parser")
    meetings: list[CalendarMeeting] = []
    for panel in soup.select("div.panel.panel-default"):
        heading = panel.select_one(".panel-heading")
        match = re.search(r"(\d{4}) FOMC Meetings", heading.get_text(" ") if heading else "")
        if not match:
            continue
        year = int(match.group(1))
        for row in panel.select("div.fomc-meeting"):
            month = row.select_one(".fomc-meeting__month")
            day = row.select_one(".fomc-meeting__date")
            statement = None
            minutes = None
            for link in row.find_all("a", href=True):
                href = link["href"]
                if re.search(r"/newsevents/pressreleases/monetary\d{8}a\.htm$", href):
                    statement = BASE_URL + href if href.startswith("/") else href
                if re.search(r"/monetarypolicy/fomcminutes\d{8}\.htm$", href):
                    minutes = BASE_URL + href if href.startswith("/") else href
            released = None
            block = row.select_one(".fomc-meeting__minutes")
            if block is not None:
                found = _RELEASED.search(block.get_text(" "))
                if found:
                    released = datetime.strptime(found.group(1), "%B %d, %Y").date()
            meetings.append(
                CalendarMeeting(
                    year=year,
                    month_label=month.get_text(" ", strip=True) if month else "",
                    date_label=day.get_text(" ", strip=True) if day else "",
                    statement_url=statement,
                    minutes_url=minutes,
                    minutes_released=released,
                )
            )
    return meetings


def validate_against_calendar(
    calendar: list[CalendarMeeting], meetings: Iterable[FomcMeeting] = PINNED_MEETINGS
) -> list[str]:
    """Return discrepancies between the pinned table and the calendar page."""
    by_statement = {m.statement_url: m for m in calendar if m.statement_url}
    problems: list[str] = []
    for meeting in meetings:
        found = by_statement.get(meeting.statement_url)
        if found is None:
            problems.append(f"{meeting.key}: statement URL not on calendar")
            continue
        if found.minutes_url != meeting.minutes_url:
            problems.append(f"{meeting.key}: minutes URL differs ({found.minutes_url})")
        if found.minutes_released != meeting.minutes_released:
            problems.append(
                f"{meeting.key}: minutes release {found.minutes_released} != "
                f"pinned {meeting.minutes_released}"
            )
    return problems


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

STATEMENT_CONFIG = HtmlParseConfig(
    content_selectors=("#article > div.col-xs-12.col-sm-8.col-md-8:not(.heading)",),
    title_selector="#article h3.title",
    drop_selectors=(
        "script",
        "style",
        "noscript",
        "#article ul.list-unstyled",
        "#article .shareDL__dropdown",
    ),
    metadata_selectors=(
        ("release_date", "#article p.article__time"),
        ("release_time_text", "#article p.releaseTime"),
    ),
)

MINUTES_CONFIG = HtmlParseConfig(
    content_selectors=("#article",),
    title_selector="#article > h3",
    drop_selectors=(
        "script",
        "style",
        "noscript",
        '#article a[href^="#fn"]',
        '#article a[href^="#f"]',
        "#article a[name]",
        "#article ul.list-unstyled",
    ),
    strong_lead_headings=True,
)

_RELEASE_TIME = re.compile(r"For release at (\d{1,2}):(\d{2}) ([ap])\.m\. (EST|EDT|ET)", re.I)


def parse_fed_document(raw: bytes, spec: FedDocumentSpec) -> ParsedDocument:
    if spec.document_type == DocumentType.FOMC_STATEMENT:
        parsed = parse_html(raw, STATEMENT_CONFIG)
        metadata = dict(parsed.metadata)
        date_text = metadata.get("release_date", spec.meeting.end.strftime("%B %-d, %Y"))
        title = f"{parsed.title} ({date_text})"
    else:
        parsed = parse_html(raw, MINUTES_CONFIG)
        metadata = dict(parsed.metadata)
        first_para = next(
            (b for b in parsed.blocks if b.kind == "paragraph"),
            None,
        )
        date_text = ""
        if first_para is not None:
            date_text = parsed.text[first_para.start_offset : first_para.end_offset]
            date_text = date_text.split("\n", 1)[0].strip()
            if not re.search(r"\d{4}$", date_text):
                date_text = ""
        metadata["meeting_date_text"] = date_text
        title = f"{parsed.title} ({date_text})" if date_text else parsed.title
    return ParsedDocument(
        title=title,
        text=parsed.text,
        blocks=parsed.blocks,
        parser_version=f"{ADAPTER_VERSION}+{parsed.parser_version}",
        media_type=parsed.media_type,
        metadata=metadata,
    )


def statement_release_time_matches(parsed: ParsedDocument) -> bool:
    """The page's own release-time line must say 2:00 p.m. (timestamp rule check)."""
    text = parsed.metadata.get("release_time_text", "")
    found = _RELEASE_TIME.search(text)
    return bool(
        found and found.group(1) == "2" and found.group(2) == "00" and found.group(3).lower() == "p"
    )


# --------------------------------------------------------------------------- #
# Raw fixture manifest
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    url: str
    final_url: str
    sha256: str
    size: int
    fetched_at: str
    content_type: str
    last_modified: Optional[str]
    kind: str


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, ManifestEntry]:
    data = json.loads(path.read_text())
    return {e["url"]: ManifestEntry(**e) for e in data["entries"]}


def verify_fixtures(root: Path = RAW_ROOT) -> list[str]:
    """Checksum every raw fixture against the manifest; returns problems."""
    problems: list[str] = []
    for entry in load_manifest(root / "MANIFEST.json").values():
        file = root / entry.path
        if not file.exists():
            problems.append(f"missing {entry.path}")
            continue
        raw = file.read_bytes()
        if sha256_bytes(raw) != entry.sha256 or len(raw) != entry.size:
            problems.append(f"checksum mismatch {entry.path}")
    return problems


def fetch_fixtures(
    fetcher: Optional[AllowlistedFetcher] = None, root: Path = RAW_ROOT
) -> list[ManifestEntry]:
    """Fetch the calendar page and all pinned documents once; write manifest.

    Sequential and polite (``RetryPolicy.politeness_delay_ms``). Existing files
    are never overwritten; a changed remote page would need a new fixture set.
    """
    fetcher = fetcher or AllowlistedFetcher(allowed_hosts=ALLOWED_HOSTS)
    targets: list[tuple[str, str, str]] = [
        (CALENDAR_URL, "fed-fomc/calendar/fomccalendars.htm", "calendar")
    ]
    targets += [(s.url, s.fixture_path, s.document_type.value) for s in document_specs()]
    entries: list[ManifestEntry] = []
    for url, rel, kind in targets:
        dest = root / rel
        result = fetcher.fetch(url)
        if dest.exists() and dest.read_bytes() != result.content:
            raise RuntimeError(f"refusing to overwrite existing fixture {rel}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(result.content)
        entries.append(
            ManifestEntry(
                path=rel,
                url=url,
                final_url=result.final_url,
                sha256=sha256_bytes(result.content),
                size=len(result.content),
                fetched_at=utc_to_str(result.fetched_at.replace(microsecond=0)),
                content_type=result.content_type,
                last_modified=result.last_modified,
                kind=kind,
            )
        )
    manifest = {
        "description": (
            "Raw bytes of Federal Reserve FOMC pages fetched once for offline fixtures. "
            "Current web versions, not archived originals."
        ),
        "adapter_version": ADAPTER_VERSION,
        "fidelity_flag": FIDELITY_CURRENT_WEB,
        "entries": [e.__dict__ for e in entries],
    }
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return entries
