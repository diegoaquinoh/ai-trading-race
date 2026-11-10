"""``CurveMarketDataPort``: point-in-time curve access implementing ``MarketDataPort``.

* Sessions are business days of the U.S. government-bond calendar inside the
  dataset window. A session with no observation, or whose curve fails to
  build, is a *flagged gap*; it is never filled from a neighbouring day.
* Curves are built lazily per session and cached by snapshot id.
* ``latest_available_curve(as_of)`` only considers observations whose
  ``available_at <= as_of`` and returns the latest READY one.
* ``market_snapshot_id`` hashes the curve snapshot id/hash/status together
  with the instrument-universe id/version/hash and the curve specification.
"""

from __future__ import annotations

import threading
from bisect import bisect_right
from datetime import date, datetime, timezone
from typing import Mapping, Optional

from research_engine.contracts.common import DataMode, content_hash, short_id
from research_engine.contracts.instruments import InstrumentUniverse
from research_engine.contracts.market import (
    CurveObservation,
    CurveSnapshot,
    CurveSpecification,
    CurveStatus,
)
from research_engine.instruments.calendar import CALENDAR_ID, business_days_between
from research_engine.instruments.schedule import InstrumentModel
from research_engine.simulation.ports import CurveSnapshotInfo

from .curves import DEFAULT_CURVE_SPEC, build_curve_snapshot

DEFAULT_START = date(2023, 1, 1)
DEFAULT_END = date(2024, 12, 31)
DEFAULT_DATASET_ID = "usd-treasury-par-2023-2024"


class SessionStatus:
    READY = "READY"
    FAILED = "FAILED"
    MISSING_OBSERVATION = "MISSING_OBSERVATION"
    NOT_A_SESSION = "NOT_A_SESSION"
    OUTSIDE_DATASET = "OUTSIDE_DATASET"


def snapshot_info(snapshot: CurveSnapshot) -> CurveSnapshotInfo:
    assert snapshot.content_hash is not None
    return CurveSnapshotInfo(
        curve_snapshot_id=snapshot.curve_snapshot_id,
        content_hash=snapshot.content_hash,
        session_date=snapshot.session_date,
        observed_at=snapshot.valuation_at,
        available_at=snapshot.available_at,
        status=snapshot.status.value,
        data_mode=snapshot.data_mode,
    )


class CurveMarketDataPort:
    def __init__(
        self,
        observations: Mapping[date, CurveObservation],
        universe: InstrumentUniverse,
        *,
        start: date = DEFAULT_START,
        end: date = DEFAULT_END,
        spec: CurveSpecification = DEFAULT_CURVE_SPEC,
        data_mode: DataMode = DataMode.SYNTHETIC_CURVE,
        dataset_id: str = DEFAULT_DATASET_ID,
        calendar_id: str = CALENDAR_ID,
    ):
        if end < start:
            raise ValueError("dataset end precedes start")
        self.data_mode = data_mode
        self.start, self.end = start, end
        self.spec = spec
        self.dataset_id = dataset_id
        self.calendar_id = calendar_id
        self.universe_contract = universe
        self.universe_hash = content_hash(universe)
        self._models = [InstrumentModel(s) for s in universe.securities]
        self._observations = {d: o for d, o in observations.items() if start <= d <= end}
        self._obs_dates = sorted(self._observations)
        self._sessions = business_days_between(start, end, calendar_id)
        self._session_set = set(self._sessions)
        self._by_session: dict[date, CurveSnapshot] = {}
        self._by_id: dict[str, CurveSnapshot] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Sessions and gaps
    # ------------------------------------------------------------------ #
    def sessions(self, start: date, end: date) -> list[date]:
        lo, hi = max(start, self.start), min(end, self.end)
        return [d for d in self._sessions if lo <= d <= hi]

    def observation(self, session_date: date) -> Optional[CurveObservation]:
        return self._observations.get(session_date)

    def session_status(self, session_date: date) -> str:
        if not self.start <= session_date <= self.end:
            return SessionStatus.OUTSIDE_DATASET
        if session_date not in self._session_set:
            return SessionStatus.NOT_A_SESSION
        snapshot = self.curve_snapshot_for_session(session_date)
        if snapshot is None:
            return SessionStatus.MISSING_OBSERVATION
        return snapshot.status.value

    def data_gaps(self, start: date, end: date) -> list[tuple[date, str]]:
        """Sessions without a READY curve, with the reason (never filled)."""
        gaps = []
        for day in self.sessions(start, end):
            status = self.session_status(day)
            if status != SessionStatus.READY:
                snap = self._by_session.get(day)
                reason = status if snap is None else f"{status}:" + ";".join(snap.failure_reasons)
                gaps.append((day, reason))
        return gaps

    def required_horizon(self, session_date: date) -> Optional[date]:
        """Latest final payment date among instruments outstanding at the session."""
        live = [m.final_payment_date for m in self._models if m.is_outstanding(session_date)]
        return max(live) if live else None

    # ------------------------------------------------------------------ #
    # Curves
    # ------------------------------------------------------------------ #
    def curve_snapshot_for_session(self, session_date: date) -> Optional[CurveSnapshot]:
        with self._lock:
            cached = self._by_session.get(session_date)
            if cached is not None:
                return cached
            observation = self._observations.get(session_date)
            if observation is None:
                return None
            snapshot = build_curve_snapshot(
                observation,
                self.spec,
                required_horizon=self.required_horizon(session_date),
                data_mode=self.data_mode,
            )
            self._by_session[session_date] = snapshot
            self._by_id[snapshot.curve_snapshot_id] = snapshot
            return snapshot

    def curve_for_session(self, session_date: date) -> Optional[CurveSnapshotInfo]:
        snapshot = self.curve_snapshot_for_session(session_date)
        return snapshot_info(snapshot) if snapshot is not None else None

    def get_curve_snapshot(self, curve_snapshot_id: str) -> CurveSnapshot:
        with self._lock:
            hit = self._by_id.get(curve_snapshot_id)
            if hit is not None:
                return hit
            for day in self._obs_dates:  # cold lookup: build until found
                if day in self._by_session:
                    continue
                snapshot = self.curve_snapshot_for_session(day)
                if snapshot is not None and snapshot.curve_snapshot_id == curve_snapshot_id:
                    return snapshot
        raise KeyError(f"unknown curve snapshot {curve_snapshot_id!r}")

    def latest_available_curve(self, as_of: datetime) -> Optional[CurveSnapshotInfo]:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        as_of = as_of.astimezone(timezone.utc)
        # available_at is always after the session date's start, so no session
        # later than as_of's UTC date can qualify.
        index = bisect_right(self._obs_dates, as_of.date())
        for day in reversed(self._obs_dates[:index]):
            observation = self._observations[day]
            if observation.available_at > as_of:
                continue
            snapshot = self.curve_snapshot_for_session(day)
            if snapshot is not None and snapshot.status is CurveStatus.READY:
                if snapshot.available_at > as_of:  # defensive: never later data
                    continue
                return snapshot_info(snapshot)
        return None

    # ------------------------------------------------------------------ #
    # Market snapshot identity
    # ------------------------------------------------------------------ #
    def market_snapshot_payload(self, session_date: date) -> dict:
        snapshot = self.curve_snapshot_for_session(session_date)
        return {
            "kind": "market_snapshot_v1",
            "datasetId": self.dataset_id,
            "sessionDate": session_date.isoformat(),
            "dataMode": self.data_mode.value,
            "curveSnapshotId": snapshot.curve_snapshot_id if snapshot else None,
            "curveContentHash": snapshot.content_hash if snapshot else None,
            "curveStatus": snapshot.status.value if snapshot else None,
            "curveSpec": f"{self.spec.spec_id}:{self.spec.version}",
            "universeId": self.universe_contract.universe_id,
            "universeVersion": self.universe_contract.version,
            "universeHash": self.universe_hash,
        }

    def market_snapshot_id(self, session_date: date) -> tuple[str, str]:
        payload = self.market_snapshot_payload(session_date)
        return short_id("mkt", payload), content_hash(payload)

    def build_all(self) -> dict[date, CurveSnapshot]:
        return {
            d: s for d in self._obs_dates if (s := self.curve_snapshot_for_session(d)) is not None
        }


def load_default_market(
    start: date = DEFAULT_START,
    end: date = DEFAULT_END,
    *,
    universe_id: str = "synthetic_universe_v1",
    calc_store=None,
):
    """(QuantLibPricingPort, CurveMarketDataPort) over the saved Treasury fixtures
    and the hypothetical ``synthetic_universe_v1``. No network access."""
    from research_engine.instruments.universe import load_universe
    from research_engine.pricing.port import QuantLibPricingPort

    from .treasury import default_treasury_dataset

    dataset = default_treasury_dataset()
    universe = load_universe(universe_id)
    market = CurveMarketDataPort(dataset.observations, universe, start=start, end=end)
    pricing = QuantLibPricingPort(universe, market, calc_store=calc_store)
    return pricing, market
