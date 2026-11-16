"""Interleaved valuations with different evaluation dates (spec 8.3, 16.5).

QuantLib's evaluation date is process-global. These tests run concurrent
requests with different as-of dates and require results identical to a
sequential run, plus direct checks that the guarded block always sees its own
evaluation date and that the previous date is restored.
"""

from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import QuantLib as ql

from research_engine.market.curves import build_curve_snapshot
from research_engine.pricing.quantlib_env import (
    current_evaluation_date,
    evaluation_date,
    from_ql_date,
)


def test_concurrent_curve_builds_equal_sequential(market):
    sessions = market.sessions(date(2023, 1, 1), date(2024, 12, 31))[::12]
    observations = [market.observation(d) for d in sessions]
    sequential = {o.session_date: build_curve_snapshot(o).content_hash for o in observations}
    shuffled = observations * 3
    random.Random(7).shuffle(shuffled)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda o: (o.session_date, build_curve_snapshot(o)), shuffled))
    for session, snap in results:
        assert snap.status.value == "READY"
        assert snap.content_hash == sequential[session]


def test_concurrent_pricing_equals_sequential(pricing, market):
    jobs = []
    for session in market.sessions(date(2023, 1, 1), date(2024, 12, 31))[::25]:
        curve_id = market.curve_for_session(session).curve_snapshot_id
        for info in pricing.universe(session):
            if pricing.is_tradable(info.security_id, session):
                settle = pricing.settlement_date(info.security_id, session)
                jobs.append((info.security_id, curve_id, settle))

    def run(job):
        return pricing.price(*job)

    sequential = [run(j) for j in jobs]
    order = list(range(len(jobs))) * 2
    random.Random(11).shuffle(order)
    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(lambda i: (i, run(jobs[i])), order))
    for i, result in concurrent:
        assert result == sequential[i]


def _maturity_under(day: date) -> tuple[date, date, date]:
    """Inside the guarded block: a QuantLib helper whose dates depend on the global
    evaluation date, read before and after yielding the GIL."""
    with evaluation_date(day):
        helper = ql.DepositRateHelper(
            0.01,
            ql.Period(1, ql.Months),
            0,
            ql.UnitedStates(ql.UnitedStates.GovernmentBond),
            ql.Following,
            False,
            ql.Actual365Fixed(),
        )
        seen_before = current_evaluation_date()
        time.sleep(0.001)  # invite another thread to run
        maturity = from_ql_date(helper.maturityDate())
        seen_after = current_evaluation_date()
    return seen_before, seen_after, maturity


def test_evaluation_date_isolated_across_threads():
    days = [date(2023, 1, 3), date(2023, 6, 30), date(2024, 2, 29), date(2024, 11, 29)]
    expected = {d: _maturity_under(d)[2] for d in days}
    original = current_evaluation_date()
    work = days * 25
    random.Random(3).shuffle(work)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda d: (d, _maturity_under(d)), work))
    for day, (before, after, maturity) in results:
        assert before == day and after == day
        assert maturity == expected[day]
    assert current_evaluation_date() == original


def test_second_block_waits_and_date_is_restored():
    original = current_evaluation_date()
    a_inside = threading.Event()
    release_a = threading.Event()
    b_entered = threading.Event()
    observed: dict[str, date] = {}

    def thread_a():
        with evaluation_date(date(2023, 3, 15)):
            a_inside.set()
            release_a.wait(5)
            observed["a"] = current_evaluation_date()

    def thread_b():
        a_inside.wait(5)
        with evaluation_date(date(2024, 9, 13)):
            b_entered.set()
            observed["b"] = current_evaluation_date()

    ta, tb = threading.Thread(target=thread_a), threading.Thread(target=thread_b)
    ta.start()
    tb.start()
    a_inside.wait(5)
    assert not b_entered.wait(0.1)  # B is blocked while A holds the settings lock
    release_a.set()
    ta.join(5)
    tb.join(5)
    assert observed == {"a": date(2023, 3, 15), "b": date(2024, 9, 13)}
    assert current_evaluation_date() == original


def test_date_restored_after_exception():
    original = current_evaluation_date()
    try:
        with evaluation_date(date(2020, 1, 2)):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert current_evaluation_date() == original
