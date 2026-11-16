"""Simulation clock conventions and content-derived identifiers.

All instants are UTC; the market schedule is expressed in America/New_York so
that daylight-saving transitions are handled by the IANA database (spec 6.1).

Proposed platform schedule (``schedule-ny-v1``, spec 6.4 and ports.py):

=====================  =====  ==================================================
Event                  NY     Meaning
=====================  =====  ==================================================
capital flow           08:00  initial/external capital on the first session
cash events            09:00  settlements, coupons, redemptions on their
                              business-day-adjusted payment/settlement date
execution observation  15:30  the session's curve observation (fills)
session end            17:00  next-session-only orders expire here
data availability      18:00  reconstructed availability of the session curve
decision               19:00  scheduled strategy decision / order submission
valuation              20:00  end-of-day valuation mark
=====================  =====  ==================================================

No function here reads the wall clock.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from research_engine.contracts.common import content_hash

SCHEDULE_VERSION = "schedule-ny-v1"
MARKET_TZ_NAME = "America/New_York"
MARKET_TZ = ZoneInfo(MARKET_TZ_NAME)

CAPITAL_TIME = time(8, 0)
CASH_EVENT_TIME = time(9, 0)
OBSERVATION_TIME = time(15, 30)
SESSION_END_TIME = time(17, 0)
AVAILABILITY_TIME = time(18, 0)
DECISION_TIME = time(19, 0)
VALUATION_TIME = time(20, 0)

SCHEDULE = {
    "version": SCHEDULE_VERSION,
    "timezone": MARKET_TZ_NAME,
    "capitalFlow": CAPITAL_TIME.isoformat(),
    "cashEvents": CASH_EVENT_TIME.isoformat(),
    "executionObservation": OBSERVATION_TIME.isoformat(),
    "sessionEnd": SESSION_END_TIME.isoformat(),
    "dataAvailability": AVAILABILITY_TIME.isoformat(),
    "decision": DECISION_TIME.isoformat(),
    "valuation": VALUATION_TIME.isoformat(),
}

_MAX_ID = 160


def ny_instant(day: date, at: time) -> datetime:
    """UTC instant of a New York wall-clock time on ``day``."""
    return datetime.combine(day, at, tzinfo=MARKET_TZ).astimezone(timezone.utc)


def ny_date(instant: datetime) -> date:
    """New York calendar date of a UTC instant."""
    return instant.astimezone(MARKET_TZ).date()


def cash_event_at(day: date) -> datetime:
    return ny_instant(day, CASH_EVENT_TIME)


def observation_at(day: date) -> datetime:
    return ny_instant(day, OBSERVATION_TIME)


def session_end_at(day: date) -> datetime:
    return ny_instant(day, SESSION_END_TIME)


def decision_at(day: date) -> datetime:
    return ny_instant(day, DECISION_TIME)


def valuation_at(day: date) -> datetime:
    return ny_instant(day, VALUATION_TIME)


_DIGEST_CHARS = 32
_HEAD_CHARS = _MAX_ID - _DIGEST_CHARS - 1


def make_id(*parts: object) -> str:
    """Deterministic identifier ``a:b:c``.

    Ids must satisfy ``OpaqueId`` (<= 160 chars, ``[A-Za-z0-9_\\-.:]``). A longer id
    keeps its first 127 characters verbatim (readable and order-preserving: two ids
    that differ there sort as their full texts do) and replaces only the tail with
    a 32-hex digest of the full text. Event ordering never relies on id text alone
    (see ``fills.batch_order_key``).
    """
    text = ":".join(str(part) for part in parts)
    if len(text) <= _MAX_ID:
        return text
    digest = content_hash(text)[len("sha256:") :][:_DIGEST_CHARS]
    return f"{text[:_HEAD_CHARS]}:{digest}"


def compact_instant(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
