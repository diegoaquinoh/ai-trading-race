"""Ports between the simulation/accounting engine and the numerical core.

The simulation engine (``research_engine.simulation``) depends only on these
protocols. The numerical core implements them:

* ``research_engine.pricing.port.QuantLibPricingPort``  -> ``PricingPort``
* ``research_engine.market.store.CurveMarketDataPort``  -> ``MarketDataPort``

Tests may use simple fakes, but parity/replay fixtures use the real ports.

Daily chronology (spec 6.4), proposed platform schedule:

* curve observation: session date 15:30 America/New_York (``observed_at``)
* reconstructed availability: session date 18:00 America/New_York (``available_at``)
* scheduled decision: session date 19:00 America/New_York (``decision_as_of``)
* fills: next supported session's observation, strictly after submission
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Protocol, runtime_checkable

from research_engine.contracts.common import (
    ContentHash,
    ContractModel,
    DataMode,
    DecimalStr,
    OpaqueId,
    SecurityId,
    UtcDatetime,
)


class ScheduledCashFlow(ContractModel):
    security_id: SecurityId
    payment_date: date  # business-day adjusted
    unadjusted_date: date
    accrual_start: date
    accrual_end: date
    coupon_per_100: DecimalStr
    principal_per_100: DecimalStr  # 100 at maturity, else 0


class InstrumentInfo(ContractModel):
    """Subset of security-master terms the simulation needs."""

    security_id: SecurityId
    synthetic: bool
    coupon_rate: DecimalStr  # decimal annual rate
    coupon_frequency: int
    issue_date: date
    dated_date: date
    maturity_date: date
    settlement_lag_business_days: int
    min_face_usd: DecimalStr
    face_increment_usd: DecimalStr
    calendar_id: str
    day_count: str
    terms_version: OpaqueId


class PriceResult(ContractModel):
    security_id: SecurityId
    curve_snapshot_id: OpaqueId
    settlement_date: date
    clean_price_per_100: DecimalStr
    accrued_per_100: DecimalStr
    dirty_price_per_100: DecimalStr
    calculation_id: OpaqueId


class PositionValuationResult(ContractModel):
    security_id: SecurityId
    curve_snapshot_id: OpaqueId
    valuation_date: date
    face: DecimalStr
    pv_dirty_usd: DecimalStr  # valuation-date present value of remaining flows
    clean_price_per_100: DecimalStr  # at standard settlement, for display
    accrued_per_100: DecimalStr
    parallel_dv01_usd: DecimalStr  # positive = gain for 1bp downward shift
    effective_duration_years: DecimalStr
    calculation_id: OpaqueId


class CurveSnapshotInfo(ContractModel):
    curve_snapshot_id: OpaqueId
    content_hash: ContentHash
    session_date: date
    observed_at: UtcDatetime
    available_at: UtcDatetime
    status: str  # READY only is usable
    data_mode: DataMode = DataMode.SYNTHETIC_CURVE


@runtime_checkable
class PricingPort(Protocol):
    engine_version: str

    def instrument(self, security_id: str) -> InstrumentInfo: ...

    def universe(self, as_of: date) -> list[InstrumentInfo]:
        """Instruments issued on/before ``as_of`` and not yet matured."""
        ...

    def cash_flows(self, security_id: str) -> list[ScheduledCashFlow]: ...

    def is_business_day(self, day: date) -> bool: ...

    def advance_business_days(self, day: date, n: int) -> date: ...

    def settlement_date(self, security_id: str, trade_date: date) -> date: ...

    def accrued_per_100(self, security_id: str, settlement_date: date) -> Decimal: ...

    def price(self, security_id: str, curve_snapshot_id: str, settlement_date: date) -> PriceResult:
        """Curve-consistent model price at a settlement anchor (spec 8.3)."""
        ...

    def value_position(
        self, security_id: str, curve_snapshot_id: str, valuation_date: date, face: Decimal
    ) -> PositionValuationResult:
        """Valuation-date PV and risk for a face-scaled position (spec 8.5, 9.1)."""
        ...

    def discount_factor(self, curve_snapshot_id: str, anchor: date, payment_date: date) -> Decimal:
        """D(v, t) / D(v, anchor) for discounting pending settlement cash."""
        ...


@runtime_checkable
class MarketDataPort(Protocol):
    data_mode: DataMode

    def sessions(self, start: date, end: date) -> list[date]:
        """Supported market sessions (business days with READY curves or gaps flagged)."""
        ...

    def curve_for_session(self, session_date: date) -> Optional[CurveSnapshotInfo]: ...

    def latest_available_curve(self, as_of: datetime) -> Optional[CurveSnapshotInfo]:
        """Latest READY curve whose ``available_at`` <= ``as_of`` (never later data)."""
        ...

    def market_snapshot_id(self, session_date: date) -> tuple[str, str]:
        """(market_snapshot_id, content_hash) for the frozen inputs of a session."""
        ...
