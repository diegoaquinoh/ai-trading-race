"""Bootstrap must respect the max-orders control (exemption covers turnover only)."""

from datetime import date
from decimal import Decimal

from research_engine.contracts.portfolio import RiskPolicy
from research_engine.experiments.baselines import bootstrap_allocation
from research_engine.simulation.ports import InstrumentInfo


def _note(n: int, maturity: date) -> InstrumentInfo:
    return InstrumentInfo(
        security_id=f"SYN-USD-NOTE-{n:03d}",
        synthetic=True,
        coupon_rate=Decimal("0.04"),
        coupon_frequency=2,
        issue_date=date(2020, 1, 15),
        dated_date=date(2020, 1, 15),
        maturity_date=maturity,
        settlement_lag_business_days=1,
        min_face_usd=Decimal("1000"),
        face_increment_usd=Decimal("1000"),
        calendar_id="us-gov",
        day_count="ActAct-ISMA",
        terms_version=f"t{n}",
    )


def test_bootstrap_caps_instruments_to_order_limit():
    as_of = date(2024, 1, 2)
    universe = [
        _note(1, date(2025, 1, 15)),
        _note(2, date(2025, 7, 15)),
        _note(3, date(2026, 1, 15)),
        _note(4, date(2026, 7, 15)),
        _note(5, date(2029, 1, 15)),
        _note(6, date(2030, 1, 15)),
        _note(7, date(2033, 1, 15)),
    ]
    allocation = bootstrap_allocation(universe, as_of, RiskPolicy())
    invested = [t for t in allocation.targets if t.security_id != "CASH-USD"]
    assert len(invested) <= RiskPolicy().max_orders_per_decision
    assert sum(t.weight for t in allocation.targets) == Decimal("1")
    # Short bucket keeps the two notes closest to the 2y representative tenor.
    short = set(allocation.buckets["short"])
    assert short == {"SYN-USD-NOTE-002", "SYN-USD-NOTE-003"}
