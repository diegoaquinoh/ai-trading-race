"""Point-in-time visibility: curves, gaps and ALFRED vintages (spec 6.2, 16.6)."""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone

import httpx
import pytest

from research_engine.instruments.calendar import NEW_YORK
from research_engine.market import fred
from research_engine.market.paths import fred_fixture_dir
from research_engine.market.store import CurveMarketDataPort
from research_engine.market.treasury import default_treasury_dataset
from tests.numerical.helpers import make_observation


def ny(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=NEW_YORK)


def test_latest_available_curve_excludes_not_yet_available(market):
    # Curve for 2023-03-15 becomes available at 18:00 New York (reconstructed policy).
    assert market.latest_available_curve(ny(date(2023, 3, 15), 17, 59)).session_date == date(
        2023, 3, 14
    )
    assert market.latest_available_curve(ny(date(2023, 3, 15), 18, 0)).session_date == date(
        2023, 3, 15
    )
    # Decision at 19:00 sees the same session; Monday morning sees Friday.
    assert market.latest_available_curve(ny(date(2023, 3, 15), 19)).session_date == date(
        2023, 3, 15
    )
    assert market.latest_available_curve(ny(date(2023, 3, 13), 10)).session_date == date(
        2023, 3, 10
    )
    assert market.latest_available_curve(ny(date(2023, 1, 3), 12)) is None
    with pytest.raises(ValueError):
        market.latest_available_curve(datetime(2023, 3, 15, 19))  # naive


def test_latest_available_curve_property(market):
    rng = random.Random(5)
    start = datetime(2023, 1, 3, tzinfo=timezone.utc)
    for _ in range(150):
        as_of = start + timedelta(minutes=rng.randrange(0, 60 * 24 * 720))
        info = market.latest_available_curve(as_of)
        if info is None:
            continue
        assert info.available_at <= as_of
        assert info.status == "READY"
        later = [
            d
            for d in market.sessions(info.session_date + timedelta(days=1), as_of.date())
            if market.observation(d) and market.observation(d).available_at <= as_of
        ]
        assert later == []


def test_gaps_are_flagged_not_filled(universe):
    observations = dict(default_treasury_dataset().observations)
    del observations[date(2023, 3, 15)]  # missing session
    broken = make_observation(
        date(2023, 3, 16), {"1M": "4.5", "2Y": "4.2", "5Y": "3.7"}, missing=("10Y",)
    )
    observations[date(2023, 3, 16)] = broken
    port = CurveMarketDataPort(
        observations, universe, start=date(2023, 3, 1), end=date(2023, 3, 31)
    )
    assert date(2023, 3, 15) in port.sessions(date(2023, 3, 1), date(2023, 3, 31))
    assert port.curve_for_session(date(2023, 3, 15)) is None
    assert port.session_status(date(2023, 3, 15)) == "MISSING_OBSERVATION"
    assert port.curve_for_session(date(2023, 3, 16)).status == "FAILED"
    gaps = dict(port.data_gaps(date(2023, 3, 1), date(2023, 3, 31)))
    assert set(gaps) == {date(2023, 3, 15), date(2023, 3, 16)}
    assert "required_tenor_missing:10Y" in gaps[date(2023, 3, 16)]
    # The 2023-03-16 evening decision must fall back to 03-14, never a filled 03-15/16.
    assert port.latest_available_curve(ny(date(2023, 3, 16), 19)).session_date == date(2023, 3, 14)
    assert port.session_status(date(2023, 3, 18)) == "NOT_A_SESSION"
    assert port.session_status(date(2023, 4, 3)) == "OUTSIDE_DATASET"


def test_market_snapshot_id_covers_curve_and_universe(market, universe):
    sid, digest = market.market_snapshot_id(date(2023, 3, 15))
    assert sid.startswith("mkt-") and digest.startswith("sha256:")
    assert market.market_snapshot_id(date(2023, 3, 15)) == (sid, digest)
    assert market.market_snapshot_id(date(2023, 3, 16))[1] != digest
    payload = market.market_snapshot_payload(date(2023, 3, 15))
    assert (
        payload["curveSnapshotId"] == market.curve_for_session(date(2023, 3, 15)).curve_snapshot_id
    )
    assert payload["universeVersion"] == universe.version
    bumped = universe.model_copy(update={"version": "synthetic_universe_v1.1"})
    other = CurveMarketDataPort(default_treasury_dataset().observations, bumped)
    assert other.market_snapshot_id(date(2023, 3, 15))[1] != digest


# --------------------------------------------------------------------------- #
# ALFRED vintages (illustrative fixture; values are hypothetical)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def alfred():
    return fred.load_fixture(fred_fixture_dir() / "alfred_illustrative_unrate.json")


def _value(vintage, period: date):
    for obs in vintage.observations:
        if obs.reference_period == period:
            return obs.value
    return "absent"


def test_alfred_vintage_excludes_revision_before_realtime_start(alfred):
    series, observations = alfred
    jan = date(2023, 1, 1)
    # The January value is revised in the vintage starting 2023-03-10.
    before = fred.vintage_as_of(observations, ny(date(2023, 3, 9), 19))
    assert str(_value(before, jan)) == "3.4"
    # On the revision's realtime_start date itself the revision is not yet usable
    # under the date-only policy (available 00:00 NY next business day).
    same_day = fred.vintage_as_of(observations, ny(date(2023, 3, 10), 19))
    assert str(_value(same_day, jan)) == "3.4"
    assert same_day.excluded_not_yet_available > 0
    after = fred.vintage_as_of(observations, ny(date(2023, 3, 13), 0))  # Monday 00:00 NY
    assert str(_value(after, jan)) == "3.5"
    assert series == "ILLUSTRATIVE_UNRATE"


def test_alfred_unreleased_periods_and_missing_values(alfred):
    _, observations = alfred
    early = fred.vintage_as_of(observations, ny(date(2023, 2, 1), 12))
    assert [o.reference_period for o in early.observations] == [date(2022, 12, 1)]
    late = fred.vintage_as_of(observations, ny(date(2023, 4, 12), 12))
    assert _value(late, date(2023, 3, 1)) is None  # "." stays missing, not zero
    assert str(_value(late, date(2023, 2, 1))) == "3.7"
    assert late.content_hash.startswith("sha256:")


def test_alfred_availability_policy():
    # 2023-03-10 is a Friday -> usable Monday 2023-03-13 00:00 New York; DST began on
    # 2023-03-12, so 00:00 EDT = 04:00Z.
    assert fred.available_at_for(date(2023, 3, 10)) == datetime(
        2023, 3, 13, 4, 0, tzinfo=timezone.utc
    )


def test_fred_requires_api_key_and_strips_it(monkeypatch):
    monkeypatch.delenv(fred.API_KEY_ENV, raising=False)
    with pytest.raises(fred.FredConfigurationError):
        fred.fetch_alfred_observations("UNRATE")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=b'{"observations": []}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setenv(fred.API_KEY_ENV, "secret-test-key")
    raw, uri = fred.fetch_alfred_observations("UNRATE", client=client)
    assert raw == b'{"observations": []}'
    assert "secret-test-key" not in uri and "api_key" not in uri
    assert seen[0].host == "api.stlouisfed.org"
    assert seen[0].params["realtime_start"] == "1776-07-04"
