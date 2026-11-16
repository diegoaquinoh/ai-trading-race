"""Common bootstrap allocation and deterministic baselines (spec 10.1)."""

from datetime import date
from decimal import Decimal

import pytest

from research_engine.contracts.decisions import DecisionOutcome
from research_engine.contracts.portfolio import DecisionAction, RiskPolicy
from research_engine.experiments.baselines import (
    BootstrapError,
    bootstrap_allocation,
    duration_targets,
    maturity_bucket,
)
from research_engine.experiments.strategy import create_strategy
from tests.simulation.fakes import DEFAULT_INSTRUMENTS, MATURING, make_ports

D = date(2024, 1, 2)


def test_bootstrap_allocation_is_30_34_30_6_with_documented_buckets():
    pricing, _ = make_ports(instruments=DEFAULT_INSTRUMENTS + [MATURING])
    allocation = bootstrap_allocation(pricing.universe(D), D, RiskPolicy())
    weights = {t.security_id: t.weight for t in allocation.targets}
    assert sum(weights.values()) == Decimal("1")
    assert "SYN-USD-NOTE-007" not in weights  # inside six months: excluded
    assert allocation.buckets == {
        "short": ["SYN-USD-NOTE-001", "SYN-USD-NOTE-002"],
        "intermediate": ["SYN-USD-NOTE-003", "SYN-USD-NOTE-004"],
        "longer": ["SYN-USD-NOTE-005", "SYN-USD-NOTE-006"],
    }
    assert weights["SYN-USD-NOTE-001"] == Decimal("0.15")
    assert weights["SYN-USD-NOTE-003"] == Decimal("0.17")
    assert weights["CASH-USD"] == Decimal("0.06")
    assert maturity_bucket(MATURING, D) is None


def test_empty_bucket_fails_bootstrap():
    pricing, _ = make_ports(instruments=DEFAULT_INSTRUMENTS[:4])
    with pytest.raises(BootstrapError, match="longer"):
        bootstrap_allocation(pricing.universe(D), D, RiskPolicy())


def test_registry_creates_baselines():
    assert create_strategy("cash").invested is False
    assert create_strategy("static_ladder").invested is True
    quant = create_strategy("quant_duration", {"targetDurationYears": "3.5"})
    assert quant.target == Decimal("3.5")
    with pytest.raises(KeyError):
        create_strategy("does_not_exist")


class _Snap:
    """Minimal decision snapshot double for the duration optimizer."""

    def __init__(self, pv, durations, cash, nav=Decimal("1000000")):
        self.nav = nav
        self.durations = durations
        self.universe = sorted(durations)
        self.tradable = {s: True for s in durations}
        self.cash_settled = cash
        self.payables = Decimal("0")
        self.contractual_cash = cash

        class _Detail:
            pass

        self.detail = _Detail()
        self.detail.pv = pv

    def weight(self, sid):
        return self.detail.pv.get(sid, Decimal("0")) / self.nav


def test_duration_optimizer_sells_longest_first_when_too_long():
    snap = _Snap(
        pv={"SA1": Decimal("400000"), "SB1": Decimal("400000")},
        durations={"SA1": Decimal("2"), "SB1": Decimal("8"), "SC1": Decimal("8")},
        cash=Decimal("200000"),
    )  # duration = 0.4 * 2 + 0.4 * 8 = 4.0
    targets, projected, _ = duration_targets(snap, RiskPolicy(), Decimal("3.5"), Decimal("0.01"))
    w = {t.security_id: t.weight for t in targets}
    assert w["SB1"] < Decimal("0.4") and w["SA1"] == Decimal("0.4")
    assert abs(projected - Decimal("3.5")) < Decimal("0.0001")
    assert sum(w.values()) == Decimal("1")


def test_duration_optimizer_buys_longest_with_settled_cash_and_breaks_ties_by_id():
    snap = _Snap(
        pv={"SA1": Decimal("600000")},
        durations={"SA1": Decimal("2"), "SB1": Decimal("8"), "SC1": Decimal("8")},
        cash=Decimal("400000"),
    )
    targets, projected, _ = duration_targets(snap, RiskPolicy(), Decimal("4.0"), Decimal("0.01"))
    w = {t.security_id: t.weight for t in targets}
    assert "SC1" not in w and w["SB1"] > 0  # B wins the tie with C
    assert projected <= Decimal("4.0")
    assert w["SB1"] <= Decimal("0.19")  # turnover budget 20% minus 1pp margin


def test_strategies_in_a_replay_context(tmp_path):
    from research_engine.experiments.runner import ReplayConfig, ReplayRunner, StrategySpec

    pricing, market = make_ports()
    config = ReplayConfig(
        experiment_id="exp-b",
        run_id="run-b",
        start_date=D,
        end_date=date(2024, 1, 5),
        strategies=[StrategySpec(strategy_id=s) for s in ("cash", "static_ladder")],
    )
    runner = ReplayRunner(config, pricing, market, tmp_path / "run", b"k")
    runner.run()
    by_strategy = {}
    for result in runner.outcomes.values():
        by_strategy.setdefault(result.strategy_id, []).append(result)
    assert all(r.outcome == DecisionOutcome.COMPLETED_HOLD for r in by_strategy["cash"])
    ladder = sorted(by_strategy["static_ladder"], key=lambda r: r.decision_id)
    assert ladder[0].proposal.action == DecisionAction.BOOTSTRAP
    assert all(r.proposal.action == DecisionAction.HOLD for r in ladder[1:])
