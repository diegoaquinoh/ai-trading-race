"""Decision-wide budget ledger: atomic reservations, unique evidence, deadline, cost."""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest

from research_engine.agents.budget import (
    BudgetExceeded,
    BudgetLedger,
    ModelPrice,
    PriceSchedule,
    TaskAllowance,
)
from research_engine.contracts.decisions import DecisionBudget


def test_reserve_commit_release_and_actuals_recorded():
    ledger = BudgetLedger(DecisionBudget(max_generation_calls=2, max_input_tokens=1000))
    first = ledger.reserve("a", generation_calls=1, input_tokens=600)
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve("b", generation_calls=1, input_tokens=500)  # 600 reserved + 500 > 1000
    assert info.value.resource == "input_tokens"
    ledger.commit(first, generation_calls=1, input_tokens=400)  # actual below the reservation
    second = ledger.reserve("b", generation_calls=1, input_tokens=500)
    ledger.release(second)
    assert ledger.remaining()["generation_calls"] == 1
    third = ledger.reserve("c", generation_calls=1, input_tokens=100)
    ledger.commit(third, generation_calls=1, input_tokens=700)  # provider over-reports
    usage = ledger.usage()
    assert usage.input_tokens == 1100 and usage.generation_calls == 2
    assert usage.budget_exhausted == "input_tokens"
    with pytest.raises(BudgetExceeded):
        ledger.reserve("d", tool_calls=1)


def test_parallel_reservations_cannot_overspend():
    budget = DecisionBudget(max_generation_calls=6, max_tool_calls=12, max_input_tokens=32000)
    ledger = BudgetLedger(budget)
    barrier = threading.Barrier(40)
    granted, denied = [], []

    def worker(i):
        barrier.wait()
        try:
            reservation = ledger.reserve(f"w{i}", generation_calls=1, input_tokens=5000)
        except BudgetExceeded:
            denied.append(i)
            return
        granted.append(i)
        ledger.commit(reservation, generation_calls=1, input_tokens=5000)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    usage = ledger.usage()
    assert len(granted) == 6 and len(denied) == 34  # input: 6 x 5000 <= 32000 < 7 x 5000
    assert usage.generation_calls == 6 and usage.input_tokens == 30000


def test_unique_chunks_counted_once_and_capped_under_concurrency():
    ledger = BudgetLedger(DecisionBudget(max_unique_evidence_chunks=12, max_evidence_tokens=8000))
    admitted, rejected = ledger.register_chunks([("c1", 500), ("c2", 500)])
    assert admitted == ["c1", "c2"] and not rejected
    again, _ = ledger.register_chunks([("c1", 500), ("c3", 500)])
    assert again == ["c1", "c3"] and ledger.usage().unique_evidence_chunks == 3
    barrier = threading.Barrier(8)

    def worker(i):
        barrier.wait()
        ledger.register_chunks([(f"t{i}-{k}", 400) for k in range(4)])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    usage = ledger.usage()
    assert usage.unique_evidence_chunks == 12
    assert usage.evidence_tokens <= 8000


def test_deadline_and_monetary_ceiling():
    now = [0.0]
    ledger = BudgetLedger(DecisionBudget(deadline_seconds=90), monotonic=lambda: now[0])
    ledger.reserve("ok", tool_calls=1)
    now[0] = 91.0
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve("late", tool_calls=1)
    assert info.value.resource == "deadline"
    schedule = PriceSchedule(
        schedule_id="test-prices-v1",
        effective_date=date(2026, 1, 1),
        source="unit test values (not real prices)",
        prices=[
            ModelPrice(
                provider="p",
                model="m",
                input_usd_per_million_tokens=Decimal("2"),
                output_usd_per_million_tokens=Decimal("10"),
            )
        ],
    )
    priced = BudgetLedger(DecisionBudget(max_cost_usd=Decimal("0.05")), price_schedule=schedule)
    cost = priced.estimate_cost("p", "m", 10000, 2000)
    assert cost == Decimal("0.040000")
    r = priced.reserve("a", cost=cost, generation_calls=1)
    with pytest.raises(BudgetExceeded) as info:
        priced.reserve("b", cost=cost, generation_calls=1)
    assert info.value.resource == "cost_usd"
    priced.commit(r, cost=cost, generation_calls=1)
    usage = priced.usage()
    assert (
        usage.estimated_cost_usd == Decimal("0.04") and usage.price_schedule_id == "test-prices-v1"
    )


def test_task_allowance_caps_on_top_of_global_ledger():
    ledger = BudgetLedger(DecisionBudget())
    allowance = TaskAllowance(
        label="task:x", caps={"generation_calls": 1, "unique_evidence_chunks": 1}
    )
    r = ledger.reserve("x", allowance=allowance, generation_calls=1)
    with pytest.raises(BudgetExceeded):
        ledger.reserve("x2", allowance=allowance, generation_calls=1)
    ledger.commit(r, generation_calls=1)
    admitted, rejected = ledger.register_chunks([("a", 10), ("b", 10)], allowance=allowance)
    assert admitted == ["a"] and rejected == ["b"]
    assert allowance.usage() == {
        "generation_calls": 1,
        "unique_evidence_chunks": 1,
        "evidence_tokens": 10,
    }
