"""U.S. government-bond business-day calendar (QuantLib ``UnitedStates.GovernmentBond``).

The calendar id/version pair is recorded on every instrument and curve so a
change of holiday rules (e.g. a QuantLib upgrade) is visible in manifests.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import QuantLib as ql

from research_engine.pricing.quantlib_env import QUANTLIB_VERSION, from_ql_date, to_ql_date

CALENDAR_ID = "US-GovernmentBond"
CALENDAR_VERSION = f"quantlib-{QUANTLIB_VERSION}"
NEW_YORK = ZoneInfo("America/New_York")


@lru_cache(maxsize=1)
def us_government_bond_calendar() -> ql.Calendar:
    return ql.UnitedStates(ql.UnitedStates.GovernmentBond)


def calendar_for(calendar_id: str) -> ql.Calendar:
    if calendar_id != CALENDAR_ID:
        raise ValueError(f"unsupported calendar {calendar_id!r}; supported: {CALENDAR_ID}")
    return us_government_bond_calendar()


def is_business_day(day: date, calendar_id: str = CALENDAR_ID) -> bool:
    return bool(calendar_for(calendar_id).isBusinessDay(to_ql_date(day)))


def advance_business_days(day: date, n: int, calendar_id: str = CALENDAR_ID) -> date:
    """Move ``n`` business days (``n`` may be 0 or negative).

    ``n == 0`` returns ``day`` adjusted Following if it is a holiday, matching
    QuantLib ``Calendar.advance`` semantics.
    """
    cal = calendar_for(calendar_id)
    return from_ql_date(cal.advance(to_ql_date(day), n, ql.Days))


def adjust(day: date, convention: int = ql.Following, calendar_id: str = CALENDAR_ID) -> date:
    return from_ql_date(calendar_for(calendar_id).adjust(to_ql_date(day), convention))


def business_days_between(start: date, end: date, calendar_id: str = CALENDAR_ID) -> list[date]:
    """Business days in the closed interval [start, end]."""
    out: list[date] = []
    current = start
    while current <= end:
        if is_business_day(current, calendar_id):
            out.append(current)
        current += timedelta(days=1)
    return out


def new_york_instant(day: date, local: time) -> datetime:
    """UTC instant of a New York wall-clock time (DST-aware)."""
    return datetime.combine(day, local, tzinfo=NEW_YORK).astimezone(timezone.utc)
