"""Schedules, holiday adjustment, accrual, entitlement and settlement (spec 16.5).

Expected values are worked by hand: coupon dates from the contract terms,
U.S. holidays from their statutory rules (MLK Day = third Monday of January,
Juneteenth = 19 June, Christmas = 25 December), ACT/ACT-ICMA accrual as
days elapsed / days in the coupon period.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from research_engine.instruments.schedule import (
    InstrumentModel,
    InstrumentNotTradableError,
)
from tests.numerical.helpers import make_terms


def third_monday_of_january(year: int) -> date:
    first = date(year, 1, 1)
    offset = (0 - first.weekday()) % 7  # Monday = 0
    return first + timedelta(days=offset + 14)


def test_mlk_rule_used_by_hand_oracle():
    assert third_monday_of_january(2022) == date(2022, 1, 17)
    assert third_monday_of_january(2023) == date(2023, 1, 16)
    assert third_monday_of_january(2024) == date(2024, 1, 15)


def test_regular_schedule_dates_and_amounts(universe):
    # SYN-USD-NOTE-005: 1.45% semiannual, dated 2020-01-15, maturity 2025-01-15.
    model = InstrumentModel(universe.get("SYN-USD-NOTE-005"))
    flows = model.cash_flows()
    unadjusted = [date(y, m, 15) for y in range(2020, 2025) for m in (7, 1) if (y, m) != (2020, 1)]
    unadjusted = sorted(unadjusted + [date(2025, 1, 15)])
    assert [f.unadjusted_date for f in flows] == unadjusted
    # Payment dates adjusted Following on the government-bond calendar:
    expected_payment = {
        date(2022, 1, 15): date(2022, 1, 18),  # Sat -> Mon 17 is MLK Day -> Tue 18
        date(2023, 1, 15): date(2023, 1, 17),  # Sun -> Mon 16 is MLK Day -> Tue 17
        date(2023, 7, 15): date(2023, 7, 17),  # Sat -> Mon
        date(2024, 1, 15): date(2024, 1, 16),  # Mon is MLK Day 2024 -> Tue
    }
    for f in flows:
        assert f.payment_date == expected_payment.get(f.unadjusted_date, f.unadjusted_date)
        # Accrual periods use unadjusted dates.
        assert f.accrual_end == f.unadjusted_date
        # Regular ACT/ACT-ICMA coupon = 100 * 1.45% / 2 exactly.
        assert f.coupon_per_100 == Decimal("0.725")
    assert [f.principal_per_100 for f in flows] == [Decimal(0)] * 9 + [Decimal(100)]
    assert sum(f.coupon_per_100 for f in flows) == Decimal("7.25")


def test_accrued_act_act_icma_hand_values(universe):
    model = InstrumentModel(universe.get("SYN-USD-NOTE-005"))
    # Period 2023-01-15 .. 2023-07-15 has 181 days; 2023-03-16 is 60 days in.
    assert model.accrued_per_100(date(2023, 3, 16)) == Decimal("0.725") * 60 / 181
    # Period 2023-07-15 .. 2024-01-15 has 184 days.
    assert model.accrued_per_100(date(2023, 10, 2)) == Decimal("0.725") * 79 / 184


def test_coupon_boundary_and_holiday_entitlement(universe):
    """The 2023-07-15 (Saturday) coupon is paid Monday 2023-07-17.

    Settlement on Friday 07-14 is strictly before payment: the buyer is entitled
    and pays accrued for 180 of 181 days. Settlement on 07-17 (= payment date)
    is not strictly before payment: the coupon belongs to the seller and the
    buyer pays 2 days of the new 184-day period.
    """
    model = InstrumentModel(universe.get("SYN-USD-NOTE-005"))
    before = model.entitled_periods(date(2023, 7, 14))
    on = model.entitled_periods(date(2023, 7, 17))
    assert before[0].payment_date == date(2023, 7, 17)
    assert on[0].payment_date == date(2024, 1, 16)
    assert len(before) == len(on) + 1
    assert model.accrued_per_100(date(2023, 7, 14)) == Decimal("0.725") * 180 / 181
    assert model.accrued_per_100(date(2023, 7, 17)) == Decimal("0.725") * 2 / 184


def test_mlk_coupon_settlement_on_payment_day(pricing):
    # Trade Friday 2023-01-13 settles Tuesday 2023-01-17 (Mon 16 = MLK Day), which is
    # also the adjusted payment date of the 2023-01-15 coupon -> not entitled.
    assert pricing.settlement_date("SYN-USD-NOTE-001", date(2023, 1, 13)) == date(2023, 1, 17)
    model = InstrumentModel(pricing.terms("SYN-USD-NOTE-001"))
    entitled = model.entitled_periods(date(2023, 1, 17))
    assert all(p.payment_date > date(2023, 1, 17) for p in entitled)
    assert len(entitled) == 1  # only the maturity flow on 2023-07-17 remains
    # 0.30% coupon: 0.15 per period; 2 days of 181 (2023-01-15 .. 2023-07-15).
    assert model.accrued_per_100(date(2023, 1, 17)) == Decimal("0.15") * 2 / 181


@pytest.mark.parametrize(
    "trade,settle",
    [
        (date(2023, 3, 15), date(2023, 3, 16)),  # ordinary weekday
        (date(2023, 3, 17), date(2023, 3, 20)),  # Friday -> Monday
        (date(2023, 6, 16), date(2023, 6, 20)),  # Mon 19 June = Juneteenth
        (date(2023, 12, 22), date(2023, 12, 26)),  # Mon 25 Dec = Christmas
        (date(2024, 1, 12), date(2024, 1, 16)),  # Mon 15 Jan 2024 = MLK Day
    ],
)
def test_settlement_t_plus_one_business_day(pricing, trade, settle):
    assert pricing.settlement_date("SYN-USD-NOTE-009", trade) == settle


def test_maturity_on_weekend_and_outstanding_window(pricing, universe):
    model = InstrumentModel(universe.get("SYN-USD-NOTE-001"))
    # Maturity 2023-07-15 is a Saturday -> principal paid Monday 2023-07-17.
    assert model.final_payment_date == date(2023, 7, 17)
    assert model.periods[-1].amount_per_100 == Decimal("100.15")
    ids_0714 = {i.security_id for i in pricing.universe(date(2023, 7, 14))}
    ids_0717 = {i.security_id for i in pricing.universe(date(2023, 7, 17))}
    assert "SYN-USD-NOTE-001" in ids_0714 and "SYN-USD-NOTE-001" not in ids_0717
    # Trading on 07-14 would settle on the final payment date: not tradable.
    assert not pricing.is_tradable("SYN-USD-NOTE-001", date(2023, 7, 14))
    assert pricing.is_tradable("SYN-USD-NOTE-001", date(2023, 7, 13))
    # Issued inside the dataset: absent the day before issue, present on issue.
    assert "SYN-USD-NOTE-003" not in {i.security_id for i in pricing.universe(date(2023, 8, 14))}
    assert "SYN-USD-NOTE-003" in {i.security_id for i in pricing.universe(date(2023, 8, 15))}


def test_short_first_stub_icma():
    # Dated 2023-02-01, regular dates on the 15th: first period 2023-02-01..2023-07-15
    # (164 days) inside the quasi-period 2023-01-15..2023-07-15 (181 days).
    terms = make_terms("SYN-USD-NOTE-901", date(2023, 2, 1), date(2025, 7, 15), "0.04")
    model = InstrumentModel(terms)
    first = model.periods[0]
    assert (first.accrual_start, first.accrual_end) == (date(2023, 2, 1), date(2023, 7, 15))
    assert not first.regular
    assert first.coupon_per_100 == Decimal(2) * 164 / 181
    assert all(p.coupon_per_100 == Decimal(2) for p in model.periods[1:])
    assert model.accrued_per_100(date(2023, 3, 1)) == Decimal(2) * 28 / 181


def test_settlement_before_dated_date_rejected():
    terms = make_terms("SYN-USD-NOTE-902", date(2023, 2, 1), date(2025, 7, 15), "0.04")
    with pytest.raises(InstrumentNotTradableError):
        InstrumentModel(terms).accrued_per_100(date(2023, 1, 31))
