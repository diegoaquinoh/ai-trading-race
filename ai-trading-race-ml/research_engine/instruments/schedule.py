"""Coupon schedules, accrual, settlement and entitlement for fixed-rate notes.

Conventions (U.S. Treasury note style, ``usd-treasury-conventions-v1``):

* Schedule: QuantLib ``Schedule`` generated *backward* from maturity at a
  semiannual frequency on the U.S. government-bond calendar.
* Accrual periods use **unadjusted** coupon dates.
* Payment dates are the coupon dates adjusted **Following**.
* Accrual day count: ACT/ACT (ICMA). A regular period pays exactly
  ``100 * coupon_rate / 2``; a short first period pays
  ``100 * coupon_rate / 2 * days(start, end) / days(end - 6M, end)``.
* Settlement: trade date + ``settlement_lag_business_days`` (T+1) business days.
* Entitlement (``settlement_strictly_before_payment_v1``): a flow belongs to the
  holder whose settlement date is *strictly before* its adjusted payment date.
  Hence the dirty price at settlement ``s`` includes exactly the flows with
  ``payment_date > s``. Because payment dates are Following-adjusted, any
  business day ``s`` with ``accrual_end <= s`` also satisfies
  ``payment_date <= s``, so accrued interest and entitlement never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

import QuantLib as ql

from research_engine.contracts.instruments import (
    BusinessDayConvention,
    DayCountConvention,
    SecurityTerms,
)
from research_engine.pricing.quantlib_env import from_ql_date, to_ql_date
from research_engine.simulation.ports import ScheduledCashFlow

from .calendar import advance_business_days, calendar_for

_BDC = {
    BusinessDayConvention.FOLLOWING: ql.Following,
    BusinessDayConvention.MODIFIED_FOLLOWING: ql.ModifiedFollowing,
    BusinessDayConvention.UNADJUSTED: ql.Unadjusted,
}


class InstrumentNotTradableError(ValueError):
    pass


class UnsupportedTermsError(ValueError):
    pass


@dataclass(frozen=True)
class CouponPeriod:
    accrual_start: date  # unadjusted
    accrual_end: date  # unadjusted coupon date
    reference_start: date  # ICMA quasi-period start (== accrual_start when regular)
    payment_date: date  # adjusted Following
    coupon_per_100: Decimal
    principal_per_100: Decimal
    regular: bool

    @property
    def amount_per_100(self) -> Decimal:
        return self.coupon_per_100 + self.principal_per_100


def _months_back(day: date, months: int) -> date:
    return from_ql_date(to_ql_date(day) - ql.Period(months, ql.Months))


def build_coupon_periods(terms: SecurityTerms) -> list[CouponPeriod]:
    if terms.conventions.day_count is not DayCountConvention.ACT_ACT_ICMA:
        raise UnsupportedTermsError("only ACT/ACT-ICMA coupon accrual is supported")
    freq = terms.economics.coupon_frequency
    months = 12 // freq
    cal = calendar_for(terms.conventions.calendar_id)
    first = terms.dates.first_coupon_date
    schedule = ql.Schedule(
        to_ql_date(terms.dates.dated_date),
        to_ql_date(terms.dates.maturity_date),
        ql.Period(months, ql.Months),
        cal,
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        terms.schedule.end_of_month,
        to_ql_date(first) if first else ql.Date(),
    )
    dates = [from_ql_date(d) for d in schedule]
    payment_bdc = _BDC[terms.schedule.payment_adjustment]
    rate = terms.economics.coupon_rate
    regular_coupon = Decimal(100) * rate / Decimal(freq)
    periods: list[CouponPeriod] = []
    for index, (start, end) in enumerate(zip(dates[:-1], dates[1:])):
        ref_start = _months_back(end, months)
        if ref_start == start:
            coupon = regular_coupon
            regular = True
        elif ref_start < start and index == 0:
            days = Decimal((end - start).days)
            ref_days = Decimal((end - ref_start).days)
            coupon = regular_coupon * days / ref_days
            regular = False
        else:
            raise UnsupportedTermsError(
                f"{terms.security_id}: irregular period {start}..{end} is not a short first stub"
            )
        is_last = index == len(dates) - 2
        periods.append(
            CouponPeriod(
                accrual_start=start,
                accrual_end=end,
                reference_start=ref_start,
                payment_date=from_ql_date(cal.adjust(to_ql_date(end), payment_bdc)),
                coupon_per_100=coupon,
                principal_per_100=terms.economics.redemption_per_100 if is_last else Decimal(0),
                regular=regular,
            )
        )
    return periods


class InstrumentModel:
    """Pre-computed schedule and convention helpers for one terms version."""

    def __init__(self, terms: SecurityTerms):
        self.terms = terms
        self.security_id = terms.security_id
        self.periods = build_coupon_periods(terms)
        self.final_payment_date = self.periods[-1].payment_date
        self.calendar_id = terms.conventions.calendar_id
        self.settlement_lag = terms.conventions.settlement_lag_business_days

    # -- schedule ------------------------------------------------------------
    def cash_flows(self) -> list[ScheduledCashFlow]:
        return [
            ScheduledCashFlow(
                security_id=self.security_id,
                payment_date=p.payment_date,
                unadjusted_date=p.accrual_end,
                accrual_start=p.accrual_start,
                accrual_end=p.accrual_end,
                coupon_per_100=p.coupon_per_100,
                principal_per_100=p.principal_per_100,
            )
            for p in self.periods
        ]

    def entitled_periods(self, settlement: date) -> list[CouponPeriod]:
        """Flows a holder settling on ``settlement`` receives: payment_date > settlement."""
        return [p for p in self.periods if p.payment_date > settlement]

    # -- settlement ----------------------------------------------------------
    def settlement_date(self, trade_date: date) -> date:
        return advance_business_days(trade_date, self.settlement_lag, self.calendar_id)

    def is_outstanding(self, as_of: date) -> bool:
        return self.terms.dates.original_issue_date <= as_of < self.final_payment_date

    def is_tradable(self, trade_date: date) -> bool:
        if trade_date < self.terms.dates.original_issue_date:
            return False
        return self.settlement_date(trade_date) < self.final_payment_date

    # -- accrual -------------------------------------------------------------
    def current_period(self, settlement: date) -> Optional[CouponPeriod]:
        for period in self.periods:
            if period.accrual_start <= settlement < period.accrual_end:
                return period
        return None

    def accrued_per_100(self, settlement: date) -> Decimal:
        """ACT/ACT-ICMA accrued interest per 100 face at ``settlement`` (exact Decimal)."""
        if settlement < self.terms.dates.dated_date:
            raise InstrumentNotTradableError(
                f"{self.security_id}: settlement {settlement} precedes dated date"
            )
        period = self.current_period(settlement)
        if period is None:
            return Decimal(0)  # on/after maturity
        freq = self.terms.economics.coupon_frequency
        regular_coupon = Decimal(100) * self.terms.economics.coupon_rate / Decimal(freq)
        elapsed = Decimal((settlement - period.accrual_start).days)
        quasi = Decimal((period.accrual_end - period.reference_start).days)
        return regular_coupon * elapsed / quasi

    def remaining_maturity_years(self, as_of: date) -> float:
        return max(0.0, (self.terms.dates.maturity_date - as_of).days / 365.25)
