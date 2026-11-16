"""Deterministic fake ports for simulation/experiment tests.

Flat continuously-compounded curves per session; semiannual fixed coupons with
following-business-day payment adjustment; ACT/ACT-style accrual over the
unadjusted period; weekends plus a small holiday list. These fakes exist only
to exercise the accounting engine; parity fixtures use the real ports.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from research_engine.contracts.common import DataMode, content_hash
from research_engine.contracts.portfolio import MarkType
from research_engine.simulation.clock import (
    AVAILABILITY_TIME,
    OBSERVATION_TIME,
    ny_date,
    ny_instant,
)
from research_engine.simulation.ports import (
    CurveSnapshotInfo,
    InstrumentInfo,
    PositionValuationResult,
    PriceResult,
    ScheduledCashFlow,
)
from research_engine.simulation.valuation import ObservedMark

HOLIDAYS = {date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 5, 27)}


def _d(value: float, places: int = 10) -> Decimal:
    return Decimal(repr(round(value, places)))


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    last = [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last))


def _instrument(sid, coupon, issue, maturity) -> InstrumentInfo:
    return InstrumentInfo(
        security_id=sid,
        synthetic=True,
        coupon_rate=Decimal(coupon),
        coupon_frequency=2,
        issue_date=issue,
        dated_date=issue,
        maturity_date=maturity,
        settlement_lag_business_days=1,
        min_face_usd=Decimal("1000"),
        face_increment_usd=Decimal("1000"),
        calendar_id="fake-us-gov",
        day_count="ACT/ACT",
        terms_version="terms-v1",
    )


DEFAULT_INSTRUMENTS = [
    _instrument("SYN-USD-NOTE-001", "0.045", date(2023, 3, 15), date(2025, 3, 15)),
    _instrument("SYN-USD-NOTE-002", "0.0425", date(2023, 6, 30), date(2025, 6, 30)),
    _instrument("SYN-USD-NOTE-003", "0.04", date(2023, 1, 31), date(2028, 1, 31)),
    _instrument("SYN-USD-NOTE-004", "0.03875", date(2023, 8, 15), date(2028, 8, 15)),
    _instrument("SYN-USD-NOTE-005", "0.035", date(2023, 2, 15), date(2033, 2, 15)),
    _instrument("SYN-USD-NOTE-006", "0.0425", date(2023, 11, 15), date(2033, 11, 15)),
]
MATURING = _instrument("SYN-USD-NOTE-007", "0.015", date(2022, 1, 31), date(2024, 1, 31))


class FakeCalendar:
    def __init__(self, holidays=HOLIDAYS):
        self.holidays = set(holidays)

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def advance(self, day: date, n: int) -> date:
        step = 1 if n >= 0 else -1
        remaining = abs(n)
        while remaining:
            day = day + timedelta(days=step)
            if self.is_business_day(day):
                remaining -= 1
        return day

    def adjust(self, day: date) -> date:
        while not self.is_business_day(day):
            day += timedelta(days=1)
        return day


class FakeMarketPort:
    data_mode = DataMode.SYNTHETIC_CURVE

    def __init__(
        self,
        calendar: Optional[FakeCalendar] = None,
        base_rate: float = 0.04,
        rate_overrides: Optional[dict[date, float]] = None,
        missing: Optional[set[date]] = None,
        late: Optional[dict[date, datetime]] = None,
        not_ready: Optional[set[date]] = None,
        wobble: float = 0.002,
    ):
        self.calendar = calendar or FakeCalendar()
        self.base_rate = base_rate
        self.rate_overrides = dict(rate_overrides or {})
        self.missing = set(missing or ())
        self.late = dict(late or {})
        self.not_ready = set(not_ready or ())
        self.wobble = wobble

    def rate(self, session: date) -> float:
        if session in self.rate_overrides:
            return self.rate_overrides[session]
        return self.base_rate + self.wobble * math.sin(session.toordinal() / 5.0)

    def sessions(self, start: date, end: date) -> list[date]:
        out, day = [], start
        while day <= end:
            if self.calendar.is_business_day(day):
                out.append(day)
            day += timedelta(days=1)
        return out

    def curve_for_session(self, session_date: date) -> Optional[CurveSnapshotInfo]:
        if session_date in self.missing or not self.calendar.is_business_day(session_date):
            return None
        rate = self.rate(session_date)
        return CurveSnapshotInfo(
            curve_snapshot_id=f"curve-{session_date.isoformat()}",
            content_hash=content_hash({"session": session_date, "rate": repr(rate)}),
            session_date=session_date,
            observed_at=ny_instant(session_date, OBSERVATION_TIME),
            available_at=self.late.get(session_date, ny_instant(session_date, AVAILABILITY_TIME)),
            status="FAILED" if session_date in self.not_ready else "READY",
        )

    def latest_available_curve(self, as_of: datetime) -> Optional[CurveSnapshotInfo]:
        day = ny_date(as_of)
        for _ in range(15):
            curve = self.curve_for_session(day)
            if curve is not None and curve.status == "READY" and curve.available_at <= as_of:
                return curve
            day -= timedelta(days=1)
        return None

    def market_snapshot_id(self, session_date: date) -> tuple[str, str]:
        curve = self.curve_for_session(session_date)
        payload = {"session": session_date, "curve": curve.content_hash if curve else None}
        return f"mkt-{session_date.isoformat()}", content_hash(payload)


class FakePricingPort:
    engine_version = "fake-pricing/1"

    def __init__(
        self, market: FakeMarketPort, instruments=None, fail_value=(), fail_discount=False
    ):
        self.market = market
        self.calendar = market.calendar
        self.instruments = {i.security_id: i for i in (instruments or DEFAULT_INSTRUMENTS)}
        self.fail_value = set(fail_value)
        self.fail_discount = fail_discount
        self.calls = 0

    # -- terms ---------------------------------------------------------------

    def instrument(self, security_id: str) -> InstrumentInfo:
        return self.instruments[security_id]

    def universe(self, as_of: date) -> list[InstrumentInfo]:
        return [
            i
            for _, i in sorted(self.instruments.items())
            if i.issue_date <= as_of < i.maturity_date
        ]

    def cash_flows(self, security_id: str) -> list[ScheduledCashFlow]:
        info = self.instruments[security_id]
        dates = []
        current = info.maturity_date
        while current > info.dated_date:
            dates.append(current)
            current = _add_months(current, -6)
        dates.reverse()
        coupon = info.coupon_rate * 100 / 2
        flows = []
        start = _add_months(dates[0], -6)
        for end in dates:
            flows.append(
                ScheduledCashFlow(
                    security_id=security_id,
                    payment_date=self.calendar.adjust(end),
                    unadjusted_date=end,
                    accrual_start=start,
                    accrual_end=end,
                    coupon_per_100=coupon,
                    principal_per_100=Decimal("100") if end == info.maturity_date else Decimal("0"),
                )
            )
            start = end
        return flows

    def is_business_day(self, day: date) -> bool:
        return self.calendar.is_business_day(day)

    def advance_business_days(self, day: date, n: int) -> date:
        return self.calendar.advance(day, n)

    def settlement_date(self, security_id: str, trade_date: date) -> date:
        return self.calendar.advance(
            trade_date, self.instruments[security_id].settlement_lag_business_days
        )

    def accrued_per_100(self, security_id: str, settlement_date: date) -> Decimal:
        for cf in self.cash_flows(security_id):
            if cf.accrual_start <= settlement_date < cf.accrual_end:
                days = (settlement_date - cf.accrual_start).days
                period = (cf.accrual_end - cf.accrual_start).days
                return _d(float(cf.coupon_per_100) * days / period)
        return Decimal("0")

    # -- curve math ----------------------------------------------------------

    def _curve(self, curve_snapshot_id: str) -> tuple[date, float]:
        session = date.fromisoformat(curve_snapshot_id.removeprefix("curve-"))
        return session, self.market.rate(session)

    @staticmethod
    def _df(rate: float, anchor: date, day: date) -> float:
        return math.exp(-rate * (day - anchor).days / 365.0)

    def _pv_per_100(self, security_id, session, rate, anchor) -> float:
        total = 0.0
        for cf in self.cash_flows(security_id):
            if cf.payment_date > anchor:
                amount = float(cf.coupon_per_100 + cf.principal_per_100)
                total += (
                    amount
                    * self._df(rate, session, cf.payment_date)
                    / self._df(rate, session, anchor)
                )
        return total

    def price(self, security_id: str, curve_snapshot_id: str, settlement_date: date) -> PriceResult:
        self.calls += 1
        session, rate = self._curve(curve_snapshot_id)
        dirty = _d(self._pv_per_100(security_id, session, rate, settlement_date))
        accrued = self.accrued_per_100(security_id, settlement_date)
        return PriceResult(
            security_id=security_id,
            curve_snapshot_id=curve_snapshot_id,
            settlement_date=settlement_date,
            clean_price_per_100=dirty - accrued,
            accrued_per_100=accrued,
            dirty_price_per_100=dirty,
            calculation_id=f"calc-price-{security_id}-{curve_snapshot_id}-{settlement_date}",
        )

    def value_position(
        self, security_id: str, curve_snapshot_id: str, valuation_date: date, face: Decimal
    ) -> PositionValuationResult:
        self.calls += 1
        if security_id in self.fail_value:
            raise RuntimeError("risk output unavailable")
        session, rate = self._curve(curve_snapshot_id)
        scale = float(face) / 100.0
        pv = self._pv_per_100(security_id, session, rate, valuation_date) * scale
        up = self._pv_per_100(security_id, session, rate + 0.0001, valuation_date) * scale
        down = self._pv_per_100(security_id, session, rate - 0.0001, valuation_date) * scale
        dv01 = (down - up) / 2
        settle = self.settlement_date(security_id, valuation_date)
        price = self.price(security_id, curve_snapshot_id, settle)
        return PositionValuationResult(
            security_id=security_id,
            curve_snapshot_id=curve_snapshot_id,
            valuation_date=valuation_date,
            face=face,
            pv_dirty_usd=_d(pv, 6),
            clean_price_per_100=price.clean_price_per_100,
            accrued_per_100=price.accrued_per_100,
            parallel_dv01_usd=_d(dv01, 6),
            effective_duration_years=_d(dv01 * 1e4 / pv if pv else 0.0, 8),
            calculation_id=f"calc-val-{security_id}-{curve_snapshot_id}-{valuation_date}",
        )

    def discount_factor(self, curve_snapshot_id: str, anchor: date, payment_date: date) -> Decimal:
        if self.fail_discount:
            raise RuntimeError("short-end curve support unavailable")
        session, rate = self._curve(curve_snapshot_id)
        return _d(self._df(rate, session, payment_date) / self._df(rate, session, anchor), 12)


class FakeObservedMarks:
    """Observed-mark policy source returning a fixed clean price below the model."""

    mark_policy = "observed_mid_v1"

    def __init__(self, pricing: FakePricingPort, clean_by_security: dict[str, Decimal]):
        self.pricing = pricing
        self.clean = clean_by_security

    def mark(self, security_id: str, valuation_at: datetime) -> Optional[ObservedMark]:
        if security_id not in self.clean:
            return None
        day = ny_date(valuation_at)
        settle = self.pricing.settlement_date(security_id, day)
        return ObservedMark(
            security_id=security_id,
            mark_type=MarkType.OBSERVED_MID,
            clean_price_per_100=self.clean[security_id],
            accrued_per_100=self.pricing.accrued_per_100(security_id, settle),
            settlement_date=settle,
            observed_at=ny_instant(day, OBSERVATION_TIME),
        )


def make_ports(**market_kwargs):
    instruments = market_kwargs.pop("instruments", None)
    fail_value = market_kwargs.pop("fail_value", ())
    fail_discount = market_kwargs.pop("fail_discount", False)
    market = FakeMarketPort(**market_kwargs)
    pricing = FakePricingPort(
        market, instruments=instruments, fail_value=fail_value, fail_discount=fail_discount
    )
    return pricing, market
