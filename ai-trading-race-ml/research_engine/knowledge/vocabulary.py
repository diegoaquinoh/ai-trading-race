"""Frozen entity vocabulary, controlled alias table and lexicon ``rule_lexicon_v1``.

* Stable entity ids: ``inst-*``, ``topic-*``, ``series-*``, ``event-fomc-YYYYMMDD``,
  ``release-cpi-YYYYMMDD``.
* The topic/series vocabulary was frozen before the corpus period
  (``VOCAB_FROZEN_AT``). Aliases carry their own ``available_at`` and version;
  aliases added later (e.g. ``recalibration``) cannot influence earlier cutoffs.
* Ambiguous aliases (one surface form, several entities) are kept on purpose
  and are routed to review by the resolver; entities are never merged because
  names look alike.
* ``LEXICON`` patterns are explicit mentions only. Patterns flagged ``review``
  produce ``review_required`` assertions that retrieval never traverses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from research_engine.contracts.common import short_id, utc
from research_engine.contracts.evidence import (
    AliasStatus,
    Entity,
    EntityAlias,
    NodeType,
)
from research_engine.evidence import fed
from research_engine.evidence.textnorm import alias_key

VOCABULARY_VERSION = "topic-vocab-v1"
LEXICON_VERSION = "rule_lexicon_v1"
VOCAB_FROZEN_AT = utc(2022, 12, 31)
RELEASE_FIXTURE = fed.FIXTURE_ROOT / "macro_releases.json"
_NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class AliasSpec:
    surface: str
    available_at: datetime = VOCAB_FROZEN_AT
    version: int = 1
    provenance: str = f"{VOCABULARY_VERSION}: frozen controlled vocabulary"


@dataclass(frozen=True)
class LexiconPattern:
    regex: str
    case_sensitive: bool = False
    review: bool = False

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.regex, 0 if self.case_sensitive else re.IGNORECASE)


@dataclass(frozen=True)
class VocabularyEntry:
    entity_id: str
    entity_type: NodeType
    canonical_name: str
    aliases: tuple[AliasSpec, ...]
    expansion_terms: tuple[str, ...] = ()
    patterns: tuple[LexiconPattern, ...] = ()
    properties: tuple[tuple[str, str], ...] = ()


def _a(*surfaces: str) -> tuple[AliasSpec, ...]:
    return tuple(AliasSpec(s) for s in surfaces)


def _p(*regexes: str, cs: bool = False, review: bool = False) -> tuple[LexiconPattern, ...]:
    return tuple(LexiconPattern(r, cs, review) for r in regexes)


INSTITUTIONS: tuple[VocabularyEntry, ...] = (
    VocabularyEntry(
        fed.FED_ENTITY_ID,
        NodeType.INSTITUTION,
        "Federal Open Market Committee",
        _a("FOMC", "Federal Open Market Committee"),
    ),
    VocabularyEntry(
        fed.FED_BOARD_ENTITY_ID,
        NodeType.INSTITUTION,
        "Board of Governors of the Federal Reserve System",
        _a("Federal Reserve Board", "Board of Governors"),
    ),
    VocabularyEntry(
        "inst-bls",
        NodeType.INSTITUTION,
        "U.S. Bureau of Labor Statistics",
        _a("BLS", "Bureau of Labor Statistics"),
    ),
)

TOPICS: tuple[VocabularyEntry, ...] = (
    VocabularyEntry(
        "topic-inflation",
        NodeType.MACRO_TOPIC,
        "Inflation",
        _a("inflation", "price pressures", "price stability", "disinflation"),
        ("inflation", "price", "prices"),
        _p(r"\binflation\b(?!\s+expectations)", r"\bprice pressures\b", r"\bdisinflation\b"),
    ),
    VocabularyEntry(
        "topic-inflation-expectations",
        NodeType.MACRO_TOPIC,
        "Inflation expectations",
        _a("inflation expectations", "longer-term inflation expectations"),
        ("inflation", "expectations", "anchored"),
        _p(r"\binflation expectations\b"),
    ),
    VocabularyEntry(
        "topic-labor-market",
        NodeType.MACRO_TOPIC,
        "Labor market",
        _a("labor market", "employment", "jobs", "job gains", "unemployment", "wages"),
        ("labor", "market", "employment", "job", "unemployment"),
        _p(
            r"\blabor market\b",
            r"\bjob gains\b",
            r"\blabor demand\b",
            r"\bunemployment rate\b",
            r"\bpayroll",
            r"\bwage growth\b",
        ),
    ),
    VocabularyEntry(
        "topic-policy-rate",
        NodeType.MACRO_TOPIC,
        "Policy rate",
        (
            *_a(
                "federal funds rate",
                "policy rate",
                "interest rates",
                "rate hike",
                "rate hikes",
                "rate increase",
                "rate cut",
                "rate cuts",
                "target range",
            ),
            AliasSpec(
                "recalibration",
                available_at=utc(2024, 9, 18, 20, 0),
                provenance=(
                    f"{VOCABULARY_VERSION}: controlled alias added after the September 2024 "
                    "meeting for easing language; not visible to earlier cutoffs"
                ),
            ),
        ),
        ("federal", "funds", "rate", "target", "range"),
        _p(r"\bfederal funds rate\b", r"\bpolicy rate\b", r"\btarget range\b"),
    ),
    VocabularyEntry(
        "topic-balance-sheet",
        NodeType.MACRO_TOPIC,
        "Balance sheet",
        _a("balance sheet", "quantitative tightening", "QT", "runoff", "securities holdings"),
        ("balance", "sheet", "holdings", "securities", "runoff"),
        _p(
            r"\bbalance sheet\b",
            r"\bholdings of Treasury securities\b",
            r"\bagency mortgage-backed securities\b",
            r"\brunoff\b",
            r"\bredemption caps?\b",
        ),
    ),
    VocabularyEntry(
        "topic-economic-growth",
        NodeType.MACRO_TOPIC,
        "Economic growth",
        _a("economic activity", "economic growth", "growth", "output"),
        ("economic", "activity", "growth"),
        _p(r"\beconomic activity\b", r"\beconomic growth\b", r"\breal GDP\b"),
    ),
    VocabularyEntry(
        "topic-financial-conditions",
        NodeType.MACRO_TOPIC,
        "Financial conditions",
        _a("financial conditions", "credit conditions", "credit availability"),
        ("financial", "conditions", "credit"),
        _p(r"\bfinancial conditions\b", r"\bcredit conditions\b", r"\btighter credit\b"),
    ),
    VocabularyEntry(
        "topic-banking-sector",
        NodeType.MACRO_TOPIC,
        "Banking sector",
        (
            *_a("banking system", "banking sector", "bank stress", "banking stress", "banks"),
            AliasSpec(
                "Silicon Valley Bank",
                available_at=utc(2023, 3, 12),
                provenance=(
                    f"{VOCABULARY_VERSION}: alias admitted after the March 2023 bank failures"
                ),
            ),
            AliasSpec(
                "SVB",
                available_at=utc(2023, 3, 12),
                provenance=(
                    f"{VOCABULARY_VERSION}: alias admitted after the March 2023 bank failures"
                ),
            ),
        ),
        ("banking", "bank", "system", "sector"),
        _p(
            r"\bbanking (?:system|sector)\b",
            r"\bbank failures?\b",
            r"\bdeposit outflows\b",
            r"\bSilicon Valley Bank\b",
        ),
    ),
    VocabularyEntry(
        "topic-consumer-spending",
        NodeType.MACRO_TOPIC,
        "Consumer spending",
        _a("consumer spending", "household spending", "PCE"),
        ("consumer", "spending", "household"),
        _p(r"\bconsumer spending\b", r"\bhousehold spending\b"),
    ),
    VocabularyEntry(
        "topic-housing",
        NodeType.MACRO_TOPIC,
        "Housing",
        _a("housing", "residential investment"),
        ("housing", "residential"),
        _p(r"\bhousing\b", r"\bresidential investment\b"),
    ),
    VocabularyEntry(
        "topic-foreign-economies",
        NodeType.MACRO_TOPIC,
        "Foreign economies",
        _a("foreign economies", "global growth", "international developments"),
        ("foreign", "economies", "international"),
        _p(r"\bforeign econom(?:y|ies|ic)\b", r"\binternational developments\b"),
    ),
)

SERIES: tuple[VocabularyEntry, ...] = (
    VocabularyEntry(
        "series-cpi",
        NodeType.MACRO_SERIES,
        "Consumer Price Index for All Urban Consumers: All Items",
        _a("CPI", "consumer price index", "headline CPI"),
        ("consumer", "price", "index", "cpi"),
        (
            *_p(r"\bconsumer price index\b"),
            *_p(r"(?<!core )\bCPI\b", cs=True),
        ),
        (("fred_id", "CPIAUCSL"), ("publisher", "inst-bls")),
    ),
    VocabularyEntry(
        "series-core-cpi",
        NodeType.MACRO_SERIES,
        "Consumer Price Index for All Urban Consumers: All Items Less Food and Energy",
        _a("core CPI"),
        ("core", "cpi"),
        _p(r"\bcore CPI\b"),
        (("fred_id", "CPILFESL"), ("publisher", "inst-bls")),
    ),
    VocabularyEntry(
        "series-pce-price",
        NodeType.MACRO_SERIES,
        "Personal Consumption Expenditures: Chain-type Price Index",
        _a("PCE price index", "PCE inflation", "PCE", "headline PCE"),
        ("pce", "price", "index"),
        (
            *_p(
                r"\b(?<!core )PCE price (?:index|inflation)\b",
                r"\bprice index for (?:total )?personal consumption expenditures\b",
                r"\btotal PCE price\b",
            ),
            *_p(r"\b(?<!core )PCE\b(?! price)", cs=True, review=True),
        ),
        (("fred_id", "PCEPI"), ("publisher", "BEA")),
    ),
    VocabularyEntry(
        "series-core-pce",
        NodeType.MACRO_SERIES,
        "Personal Consumption Expenditures Excluding Food and Energy (Chain-Type Price Index)",
        _a("core PCE", "core PCE price index", "core PCE inflation"),
        ("core", "pce", "price"),
        _p(r"\bcore PCE\b"),
        (("fred_id", "PCEPILFE"), ("publisher", "BEA")),
    ),
    VocabularyEntry(
        "series-unemployment-rate",
        NodeType.MACRO_SERIES,
        "Unemployment Rate",
        _a("unemployment rate", "jobless rate"),
        ("unemployment", "rate"),
        _p(r"\bunemployment rate\b"),
        (("fred_id", "UNRATE"), ("publisher", "inst-bls")),
    ),
    VocabularyEntry(
        "series-nonfarm-payrolls",
        NodeType.MACRO_SERIES,
        "All Employees, Total Nonfarm",
        _a("nonfarm payrolls", "payroll employment", "payrolls"),
        ("nonfarm", "payroll", "employment"),
        _p(r"\bnonfarm payroll", r"\bpayroll employment\b", r"\bpayroll gains\b"),
        (("fred_id", "PAYEMS"), ("publisher", "inst-bls")),
    ),
    VocabularyEntry(
        "series-real-gdp",
        NodeType.MACRO_SERIES,
        "Real Gross Domestic Product",
        _a("real GDP", "GDP", "gross domestic product"),
        ("real", "gdp", "gross", "domestic", "product"),
        _p(r"\breal GDP\b", r"\breal gross domestic product\b"),
        (("fred_id", "GDPC1"), ("publisher", "BEA")),
    ),
)

VOCABULARY: tuple[VocabularyEntry, ...] = INSTITUTIONS + TOPICS + SERIES
VOCAB_BY_ID: dict[str, VocabularyEntry] = {v.entity_id: v for v in VOCABULARY}


# --------------------------------------------------------------------------- #
# Policy events and macro releases
# --------------------------------------------------------------------------- #


def _event_aliases(meeting: fed.FomcMeeting) -> list[str]:
    months = {meeting.end.strftime("%B")}
    months.add(meeting.start.strftime("%B"))
    year = meeting.end.year
    out: list[str] = []
    for month in sorted(months):
        out += [f"{month} {year} meeting", f"{month} {year} FOMC meeting", f"{month} {year} FOMC"]
    out.append(f"{meeting.end:%B} {meeting.end.day}, {year}")
    out.append(meeting.end.isoformat())
    return out


def policy_event_entities(
    meetings: Iterable[fed.FomcMeeting] = fed.PINNED_MEETINGS,
) -> tuple[list[Entity], list[EntityAlias]]:
    entities: list[Entity] = []
    aliases: list[EntityAlias] = []
    for meeting in meetings:
        available = fed.available_instant(fed.release_instant(meeting.end))
        entities.append(
            Entity(
                entity_id=meeting.event_id,
                entity_type=NodeType.POLICY_EVENT,
                canonical_name=meeting.label,
                available_at=available,
                properties={
                    "meeting_start": meeting.start.isoformat(),
                    "meeting_end": meeting.end.isoformat(),
                    "series": "fomc-scheduled-meetings",
                },
                provenance=f"{fed.ADAPTER_VERSION}: pinned meeting table validated by calendar",
            )
        )
        for surface in _event_aliases(meeting):
            aliases.append(
                _alias(meeting.event_id, AliasSpec(surface, available, 1, "fomc meeting labels"))
            )
    return entities, aliases


@dataclass(frozen=True)
class MacroReleaseRow:
    release_id: str
    series_ids: tuple[str, ...]
    reference_period: str
    release_date: date
    release_time: str
    published_at: datetime
    available_at: datetime
    row_ref: str


def load_releases(path: Path = RELEASE_FIXTURE) -> list[MacroReleaseRow]:
    data = json.loads(path.read_text())
    lag = timedelta(minutes=int(data["availability_lag_minutes"]))
    rows: list[MacroReleaseRow] = []
    for row in data["releases"]:
        day = date.fromisoformat(row["release_date"])
        hh, mm = (int(x) for x in data["release_time_et"].split(":"))
        published = datetime.combine(day, time(hh, mm), tzinfo=_NY).astimezone(timezone.utc)
        rows.append(
            MacroReleaseRow(
                release_id=f"release-cpi-{day:%Y%m%d}",
                series_ids=tuple(data["series_ids"]),
                reference_period=row["reference_period"],
                release_date=day,
                release_time=data["release_time_et"],
                published_at=published,
                available_at=published + lag,
                row_ref=f"fixtures/evidence/macro_releases.json#{row['reference_period']}",
            )
        )
    return rows


def release_entities(rows: Iterable[MacroReleaseRow]) -> tuple[list[Entity], list[EntityAlias]]:
    entities: list[Entity] = []
    aliases: list[EntityAlias] = []
    for row in rows:
        ref = datetime.strptime(row.reference_period, "%Y-%m")
        name = f"CPI release for {ref:%B %Y} (published {row.release_date.isoformat()})"
        entities.append(
            Entity(
                entity_id=row.release_id,
                entity_type=NodeType.MACRO_RELEASE,
                canonical_name=name,
                available_at=row.available_at,
                properties={
                    "reference_period": row.reference_period,
                    "release_date": row.release_date.isoformat(),
                    "release_time_et": row.release_time,
                    "published_at": row.published_at.isoformat(),
                },
                provenance=row.row_ref,
            )
        )
        aliases.append(
            _alias(row.release_id, AliasSpec(f"{ref:%B %Y} CPI", row.available_at, 1, row.row_ref))
        )
    return entities, aliases


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def _alias(entity_id: str, spec: AliasSpec) -> EntityAlias:
    key = alias_key(spec.surface)
    return EntityAlias(
        alias_id=short_id("alias", {"e": entity_id, "k": key, "v": spec.version}),
        entity_id=entity_id,
        alias=spec.surface,
        normalized_alias=key,
        alias_version=spec.version,
        available_at=spec.available_at,
        status=AliasStatus.APPROVED,
        provenance=spec.provenance,
    )


def vocabulary_records() -> tuple[list[Entity], list[EntityAlias]]:
    entities: list[Entity] = []
    aliases: list[EntityAlias] = []
    for entry in VOCABULARY:
        entities.append(
            Entity(
                entity_id=entry.entity_id,
                entity_type=entry.entity_type,
                canonical_name=entry.canonical_name,
                available_at=VOCAB_FROZEN_AT,
                properties=dict(entry.properties),
                provenance=VOCABULARY_VERSION,
            )
        )
        surfaces = list(entry.aliases) + [AliasSpec(entry.canonical_name)]
        seen: set[str] = set()
        for spec in surfaces:
            key = alias_key(spec.surface)
            if key in seen:
                continue
            seen.add(key)
            aliases.append(_alias(entry.entity_id, spec))
    return entities, aliases


def all_seed_records() -> tuple[list[Entity], list[EntityAlias]]:
    entities, aliases = vocabulary_records()
    ev_e, ev_a = policy_event_entities()
    rel_e, rel_a = release_entities(load_releases())
    return entities + ev_e + rel_e, aliases + ev_a + rel_a
