"""FRED/ALFRED vintage-aware macro adapter (spec 6.2, 7.1).

ALFRED returns every (reference period, real-time period) pair when called with
``realtime_start=1776-07-04`` and ``realtime_end=9999-12-31``. The adapter keeps
all vintages and selects, for a decision cutoff, the value that was *known* at
that cutoff -- never today's revised history.

Availability policy ``alfred_realtime_date_next_business_day_v1``: ALFRED real-time
dates have day precision and no release instant. A vintage first published on
``realtime_start`` is usable from 00:00 America/New_York on the next U.S.
government-bond business day (conservative date-only policy, spec 6.2).

The API key is read from ``FRED_API_KEY``; it is never written to artifacts or
logs (stored URIs have the key removed).
"""

from __future__ import annotations

import json
import os
import time as _time
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode, urlparse

import httpx

from research_engine.contracts.common import content_hash
from research_engine.contracts.market import MacroObservation, MacroVintage, SourceArtifactRef
from research_engine.instruments.calendar import NEW_YORK, advance_business_days, new_york_instant

SOURCE_ID = "fred-alfred"
API_URL = "https://api.stlouisfed.org/fred/series/observations"
ALLOWED_HOSTS = frozenset({"api.stlouisfed.org"})
API_KEY_ENV = "FRED_API_KEY"
AVAILABILITY_POLICY = "alfred_realtime_date_next_business_day_v1"
ALL_REALTIME_START = "1776-07-04"
ALL_REALTIME_END = "9999-12-31"
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class FredConfigurationError(RuntimeError):
    pass


class FredFetchError(RuntimeError):
    pass


def available_at_for(realtime_start: date) -> datetime:
    """Conservative availability for a day-precision ALFRED vintage date."""
    return new_york_instant(advance_business_days(realtime_start, 1), time(0, 0))


def fetch_alfred_observations(
    series_id: str,
    *,
    api_key: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = _time.sleep,
) -> tuple[bytes, str]:
    """All vintages of a series. Returns (raw JSON bytes, key-free URI)."""
    key = api_key or os.environ.get(API_KEY_ENV)
    if not key:
        raise FredConfigurationError(f"{API_KEY_ENV} is not configured")
    if urlparse(API_URL).hostname not in ALLOWED_HOSTS:
        raise FredFetchError("FRED host not allowlisted")
    params = {
        "series_id": series_id,
        "realtime_start": ALL_REALTIME_START,
        "realtime_end": ALL_REALTIME_END,
        "file_type": "json",
    }
    public_uri = f"{API_URL}?{urlencode(params)}"
    own = client is None
    http = client or httpx.Client(timeout=30.0, follow_redirects=False)
    last = ""
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                response = http.get(API_URL, params={**params, "api_key": key})
            except httpx.TransportError as exc:
                last = exc.__class__.__name__
            else:
                if response.status_code == 200:
                    return response.content, public_uri
                if response.status_code not in RETRYABLE_STATUS:
                    raise FredFetchError(f"HTTP {response.status_code} for {series_id}")
                last = f"HTTP {response.status_code}"
            if attempt < max_attempts:
                sleep(backoff_seconds * (2 ** (attempt - 1)))
        raise FredFetchError(f"failed after {max_attempts} attempts: {last}")
    finally:
        if own:
            http.close()


def _parse_value(text: str) -> Optional[Decimal]:
    if text is None or text.strip() in {".", ""}:
        return None
    try:
        value = Decimal(text.strip())
    except InvalidOperation as exc:
        raise ValueError(f"invalid ALFRED value {text!r}") from exc
    if not value.is_finite():
        raise ValueError("non-finite ALFRED value")
    return value


def parse_alfred_json(
    raw: bytes, series_id: str, *, units: Optional[str] = None
) -> list[MacroObservation]:
    payload = json.loads(raw)
    unit_label = units or payload.get("units", "lin")
    out = []
    for item in payload["observations"]:
        start = date.fromisoformat(item["realtime_start"])
        out.append(
            MacroObservation(
                series_id=series_id,
                reference_period=date.fromisoformat(item["date"]),
                value=_parse_value(item.get("value", ".")),
                units=unit_label,
                realtime_start=start,
                realtime_end=date.fromisoformat(item["realtime_end"]),
                available_at=available_at_for(start),
                information_policy=AVAILABILITY_POLICY,
            )
        )
    out.sort(key=lambda o: (o.reference_period, o.realtime_start))
    return out


def vintage_as_of(
    observations: list[MacroObservation],
    known_at: datetime,
    *,
    artifact: Optional[SourceArtifactRef] = None,
) -> MacroVintage:
    """For each reference period, the latest vintage available at ``known_at``.

    A revision whose ``available_at`` is after ``known_at`` is excluded, even if
    its ``realtime_start`` date equals the cutoff date.
    """
    if known_at.tzinfo is None:
        raise ValueError("known_at must be timezone-aware")
    if not observations:
        raise ValueError("no observations")
    series_ids = {o.series_id for o in observations}
    if len(series_ids) != 1:
        raise ValueError("observations mix series")
    chosen: dict[date, MacroObservation] = {}
    excluded = 0
    for obs in observations:
        if obs.available_at > known_at:
            excluded += 1
            continue
        current = chosen.get(obs.reference_period)
        if current is None or obs.realtime_start > current.realtime_start:
            chosen[obs.reference_period] = obs
    vintage = MacroVintage(
        series_id=series_ids.pop(),
        known_at=known_at,
        vintage_realtime_date=known_at.astimezone(NEW_YORK).date(),
        observations=[chosen[d] for d in sorted(chosen)],
        excluded_not_yet_available=excluded,
        source_artifact=artifact,
    )
    return vintage.model_copy(update={"content_hash": content_hash(vintage)})


def load_fixture(path: Path | str) -> tuple[str, list[MacroObservation]]:
    """Offline ALFRED-shaped JSON (must carry ``series_id``)."""
    raw = Path(path).read_bytes()
    series_id = json.loads(raw)["series_id"]
    return series_id, parse_alfred_json(raw, series_id)
