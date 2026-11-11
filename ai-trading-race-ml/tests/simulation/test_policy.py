"""Sizing and whole-order-set policy evaluation (spec 9.2, 9.3)."""

from datetime import date
from decimal import Decimal

from research_engine.contracts.portfolio import (
    DecisionAction,
    RiskPolicy,
    Side,
    TargetWeight,
)

from .harness import Harness, book_state, lot, position, weights

JAN = lambda d: date(2024, 1, d)  # noqa: E731
N3 = "SYN-USD-NOTE-003"


def _funded(**kwargs):
    h = Harness(**kwargs)
    h.capital()
    return h


def _initialized():
    h = _funded()
    h.decide(
        JAN(2),
        weights(n1="0.15", n3="0.30", n5="0.30", cash="0.25"),
        action=DecisionAction.BOOTSTRAP,
    )
    h.process(JAN(3))
    h.process(JAN(4))
    return h


def test_weight_validation_rejects_without_writing_state():
    h = _funded()
    bad = [
        TargetWeight(security_id="SYN-USD-NOTE-999", weight=Decimal("0.2")),
        TargetWeight(security_id=N3, weight=Decimal("-0.1")),
        TargetWeight(security_id="CASH-USD", weight=Decimal("0.5")),
    ]
    proposal = h.decide(JAN(2), bad)
    reasons = proposal.policy_evaluation.rejected_reasons
    assert "security_not_in_frozen_universe:SYN-USD-NOTE-999" in reasons
    assert f"negative_weight:{N3}" in reasons
    assert any(r.startswith("weights_do_not_sum_to_one") for r in reasons)
    assert proposal.no_op and proposal.orders_created == []


def test_individually_valid_orders_that_jointly_exceed_turnover_are_rejected():
    single = _funded().decide(JAN(2), weights(n3="0.10", cash="0.90"))
    assert single.policy_evaluation.passed
    joint = _funded().decide(JAN(2), weights(n3="0.10", n4="0.08", n5="0.08", cash="0.74"))
    evaluation = joint.policy_evaluation
    assert not evaluation.passed
    assert "max_daily_turnover_ratio:turnover_cap_exceeded" in evaluation.rejected_reasons
    assert evaluation.turnover_ratio > Decimal("0.20")
    assert len(evaluation.sized_orders) == 3 and joint.orders_created == []


def test_jointly_excessive_dv01_is_rejected_even_with_bootstrap_exemption():
    one = _funded().decide(JAN(2), weights(n5="0.40", cash="0.60"), action=DecisionAction.BOOTSTRAP)
    assert one.policy_evaluation.passed
    both = _funded().decide(
        JAN(2), weights(n5="0.40", n6="0.40", cash="0.20"), action=DecisionAction.BOOTSTRAP
    )
    evaluation = both.policy_evaluation
    assert not evaluation.passed
    assert "parallel_dv01_usd:limit_exceeded" in evaluation.rejected_reasons
    assert evaluation.post_trade_parallel_dv01_usd > Decimal("600")


def test_post_trade_metrics_are_filled_for_dotnet_recheck():
    proposal = _funded().decide(JAN(2), weights(n3="0.15", cash="0.85"))
    e = proposal.policy_evaluation
    assert e.passed and e.order_count == 1
    for value in (
        e.post_trade_nav_usd,
        e.post_trade_cash_ratio,
        e.post_trade_max_security_ratio,
        e.post_trade_parallel_dv01_usd,
        e.turnover_ratio,
    ):
        assert value is not None
    ids = {c.check_id for c in e.checks}
    assert {
        "min_cash_ratio",
        "parallel_dv01_usd",
        "max_daily_turnover_ratio",
        "max_orders_per_decision",
        "funding_settled_cash",
        "long_only",
        f"max_single_security_ratio:{N3}",
    } <= ids
    assert e.sized_orders[0].estimated_consideration_usd > 0
    assert e.calculation_ids


def test_small_changes_produce_no_order():
    h = _initialized()
    nav_weights = weights(n1="0.16", n3="0.30", n5="0.30", cash="0.24")
    proposal = h.decide(JAN(4), nav_weights)
    e = proposal.policy_evaluation
    assert e.passed and e.order_count == 0
    assert any(n.startswith("below_min_weight_change") for n in e.normalization_notes)


def test_unfundable_simultaneous_rotation_is_rejected():
    state = book_state(JAN(2), "70000.00", positions=[position(N3, [lot(N3, "930000", JAN(1))])])
    h = Harness(state)
    proposal = h.decide(JAN(3), weights(n3="0.78", n5="0.15", cash="0.07"))
    e = proposal.policy_evaluation
    assert [o.side for o in e.sized_orders] == [Side.SELL, Side.BUY]
    assert not e.passed
    assert any(r.startswith("funding_settled_cash") for r in e.rejected_reasons)


def test_missing_risk_output_blocks_the_order():
    h = _funded(fail_value={"SYN-USD-NOTE-004"})
    proposal = h.decide(JAN(2), weights(n4="0.10", cash="0.90"))
    e = proposal.policy_evaluation
    assert not e.passed
    assert any(r.startswith("missing_risk_output:SYN-USD-NOTE-004") for r in e.rejected_reasons)


def test_breach_mode_processes_mandatory_flows_and_blocks_risk_increase():
    held = [lot(N3, "500000", JAN(10), clean="99.5", accrued="8750.00")]
    state = book_state(
        JAN(29),
        "500000.00",
        positions=[position(N3, held)],
        risk_breaches=[f"max_single_security_ratio:{N3}"],
    )
    h = Harness(state)
    flows = h.process(JAN(31))
    assert [cf.kind for cf in flows.cash_flows] == ["COUPON"]  # processed despite the breach
    more = h.decide(JAN(31), weights(n3="0.55", cash="0.45"))
    e = more.policy_evaluation
    assert e.breach_mode and not e.passed
    assert f"max_single_security_ratio:{N3}:risk_increasing_during_breach" in e.rejected_reasons
    reduce = h.decide(JAN(31), weights(n3="0.49", cash="0.51"))  # < 2pp but restores the limit
    e = reduce.policy_evaluation
    assert e.passed and e.breach_mode
    assert [o.side for o in reduce.orders_created] == [Side.SELL]
    check = [c for c in e.checks if c.check_id == f"max_single_security_ratio:{N3}"][0]
    assert check.reason == "breach_not_worsened"


def test_bootstrap_only_for_uninitialized_and_turnover_cap_otherwise():
    h = _initialized()
    again = h.decide(JAN(4), weights(n3="0.30", cash="0.70"), action=DecisionAction.BOOTSTRAP)
    assert (
        "bootstrap_not_permitted_after_initialization" in again.policy_evaluation.rejected_reasons
    )
    big = _funded().decide(JAN(2), weights(n1="0.30", n3="0.34", n5="0.30", cash="0.06"))
    assert not big.policy_evaluation.passed
    assert not big.policy_evaluation.bootstrap_exemption_applied


def test_stale_decision_snapshot_blocks_discretionary_action():
    h = Harness()
    h.capital(day=JAN(2))
    from .harness import snapshot_ref

    proposal = h.decide(
        JAN(5), weights(n3="0.10", cash="0.90"), market_snapshot=snapshot_ref(h.market, JAN(2))
    )
    reasons = proposal.policy_evaluation.rejected_reasons
    assert "stale_marks_block_discretionary_action" in reasons


def test_hold_and_projection_mode():
    h = _funded()
    hold = h.decide(JAN(2), [], action=DecisionAction.HOLD)
    assert hold.policy_evaluation.passed and hold.no_op
    projection = RiskPolicy(projection_mode="deterministic_projection_v1")
    proposal = h.decide(JAN(2), weights(n3="0.10", cash="0.90"), risk_policy=projection)
    assert "projection_mode_not_implemented:deterministic_projection_v1" in (
        proposal.policy_evaluation.rejected_reasons
    )


def test_max_orders_per_decision():
    tight = RiskPolicy(max_orders_per_decision=1, policy_id="tight-v1")
    proposal = _funded().decide(
        JAN(2), weights(n3="0.08", n4="0.08", cash="0.84"), risk_policy=tight
    )
    assert "max_orders_per_decision:too_many_orders" in proposal.policy_evaluation.rejected_reasons


# --------------------------------------------------------------------------- #
# Pre-trade metrics and the breach policy on reported values (spec 9.3)
# --------------------------------------------------------------------------- #

MILLION = Decimal("1000000")


def _gate_accepts(e, policy: RiskPolicy) -> bool:
    """The .NET gate on the published values: a breached post-trade metric passes
    only if the pre-trade value was breached too and the order set does not worsen it.
    DV01 limits scale with the NAV of the same state (post- or pre-trade)."""
    per_million = policy.max_parallel_dv01_usd_per_million_nav
    cash_ok = e.post_trade_cash_ratio >= policy.min_cash_ratio or (
        e.pre_trade_cash_ratio < policy.min_cash_ratio
        and e.post_trade_cash_ratio >= e.pre_trade_cash_ratio
    )

    def upper(post, pre, limit):
        return post <= limit or (pre > limit and post <= pre)

    security_ok = upper(
        e.post_trade_max_security_ratio,
        e.pre_trade_max_security_ratio,
        policy.max_single_security_ratio,
    )
    post_dv01, pre_dv01 = e.post_trade_parallel_dv01_usd, e.pre_trade_parallel_dv01_usd
    dv01_ok = post_dv01 * MILLION <= per_million * e.post_trade_nav_usd or (
        pre_dv01 * MILLION > per_million * e.pre_trade_nav_usd and post_dv01 <= pre_dv01
    )
    return cash_ok and security_ok and dv01_ok


def test_pre_trade_metrics_are_published_with_post_trade_metrics():
    funded = _funded()
    hold = funded.decide(JAN(2), [], action=DecisionAction.HOLD).policy_evaluation
    assert hold.pre_trade_cash_ratio == hold.post_trade_cash_ratio == Decimal("1.00000000")
    assert hold.pre_trade_max_security_ratio == hold.post_trade_max_security_ratio == 0
    assert hold.pre_trade_parallel_dv01_usd == hold.post_trade_parallel_dv01_usd == 0
    e = _funded().decide(JAN(2), weights(n3="0.15", cash="0.85")).policy_evaluation
    assert e.passed and e.pre_trade_cash_ratio == Decimal("1.00000000")
    assert e.pre_trade_max_security_ratio == 0 and e.pre_trade_parallel_dv01_usd == 0
    assert e.post_trade_cash_ratio < e.pre_trade_cash_ratio
    assert e.pre_trade_nav_usd == Decimal("1000000.00") > e.post_trade_nav_usd  # minus costs
    assert hold.pre_trade_nav_usd == hold.post_trade_nav_usd
    wire = e.to_wire()
    assert {
        "preTradeNavUsd",
        "preTradeCashRatio",
        "preTradeMaxSecurityRatio",
        "preTradeParallelDv01Usd",
    } <= set(wire)
    assert _gate_accepts(e, RiskPolicy())


def test_partial_cure_of_a_cash_breach_passes_on_reported_pre_and_post_values():
    """Cash ratio below the minimum before and after, but improved: breach not worsened."""
    d = date(2024, 4, 10)
    sids = [f"SYN-USD-NOTE-00{i}" for i in (1, 2, 3)]
    held = [position(s, [lot(s, "330000", date(2024, 1, 10), clean="100")]) for s in sids]
    from research_engine.simulation.clock import valuation_at

    state = book_state(d, "20000", positions=held, as_of=valuation_at(date(2024, 4, 9)))
    h = Harness(state)
    keep = {"SYN-USD-NOTE-001": "0.326129", "SYN-USD-NOTE-002": "0.328439"}
    third = Decimal("0.325806") - Decimal("0.025")
    cash = 1 - sum(Decimal(v) for v in keep.values()) - third
    targets = [TargetWeight(security_id=s, weight=Decimal(w)) for s, w in keep.items()]
    targets += [
        TargetWeight(security_id="SYN-USD-NOTE-003", weight=third),
        TargetWeight(security_id="CASH-USD", weight=cash),
    ]
    e = h.decide(d, targets).policy_evaluation
    policy = RiskPolicy()
    assert e.passed and e.breach_mode, e.rejected_reasons
    assert e.pre_trade_cash_ratio < policy.min_cash_ratio
    assert e.pre_trade_cash_ratio <= e.post_trade_cash_ratio < policy.min_cash_ratio
    check = [c for c in e.checks if c.check_id == "min_cash_ratio"][0]
    assert check.passed and check.reason == "breach_not_worsened"
    assert check.observed == e.post_trade_cash_ratio
    assert _gate_accepts(e, policy)


def test_risk_increase_during_breach_is_rejected_by_python_and_the_gate_alike():
    held = [lot(N3, "500000", JAN(10), clean="99.5", accrued="8750.00")]
    h = Harness(book_state(JAN(29), "500000.00", positions=[position(N3, held)]))
    worse = h.decide(JAN(30), weights(n3="0.55", cash="0.45")).policy_evaluation
    assert not worse.passed and worse.breach_mode
    assert worse.post_trade_max_security_ratio > worse.pre_trade_max_security_ratio > Decimal("0.4")
    assert not _gate_accepts(worse, RiskPolicy())
    better = h.decide(JAN(30), weights(n3="0.49", cash="0.51")).policy_evaluation
    assert better.passed and _gate_accepts(better, RiskPolicy())


# --------------------------------------------------------------------------- #
# Risk-output completeness and untradable holdings
# --------------------------------------------------------------------------- #


def test_adjustment_only_security_does_not_block_with_missing_risk_output():
    """Fully sold position whose sale settles on a coupon date: PV adjustment, zero DV01."""
    from research_engine.contracts.portfolio import PendingSettlement
    from research_engine.simulation.clock import observation_at

    sid = "SYN-USD-NOTE-001"
    day = date(2024, 3, 14)
    pending = PendingSettlement(
        settlement_id="stl:fill:x",
        fill_id="fill:x",
        security_id=sid,
        side=Side.SELL,
        face=Decimal("100000"),
        settlement_date=date(2024, 3, 15),
        cash_usd=Decimal("101000.00"),
    )
    state = book_state(
        day,
        "500000",
        positions=[position(sid, [], settled="100000")],
        pending=[pending],
        as_of=observation_at(day),
    )
    e = Harness(state).decide(day, weights(n3="0.10", cash="0.90")).policy_evaluation
    assert e.passed, e.rejected_reasons
    assert f"max_single_security_ratio:{sid}" in {c.check_id for c in e.checks}


def test_held_untradable_security_without_target_is_kept_until_redemption():
    from research_engine.simulation.clock import valuation_at

    from .fakes import DEFAULT_INSTRUMENTS, MATURING

    maturing = MATURING.security_id
    day = JAN(29)
    held = [
        position(maturing, [lot(maturing, "100000", date(2023, 6, 1))]),
        position(N3, [lot(N3, "100000", date(2023, 6, 1))]),
    ]
    state = book_state(day, "800000", positions=held, as_of=valuation_at(JAN(26)))
    h = Harness(state, instruments=DEFAULT_INSTRUMENTS + [MATURING])
    targets = [
        TargetWeight(security_id=N3, weight=Decimal("0.25")),
        TargetWeight(security_id="CASH-USD", weight=Decimal("0.75")),
    ]
    proposal = h.decide(day, targets)
    e = proposal.policy_evaluation
    assert e.passed, e.rejected_reasons
    assert f"held_untradable_security_kept_until_redemption:{maturing}" in e.normalization_notes
    assert maturing not in {t.security_id for t in e.normalized_targets}
    assert [o.security_id for o in proposal.orders_created] == [N3]
    # An explicit target that requires trading it is still rejected.
    explicit = [TargetWeight(security_id=maturing, weight=Decimal("0"))] + targets
    rejected = h.decide(day, explicit).policy_evaluation
    assert f"instrument_not_tradable:{maturing}" in rejected.rejected_reasons


def test_limit_comparisons_use_the_reported_values():
    from research_engine.simulation.policy import RiskMetrics, breaches

    policy = RiskPolicy()
    nav = Decimal("1000000.004")  # reported 1000000.00 -> DV01 cap 600.00
    just_under = RiskMetrics(nav=nav, cash=nav, pv={}, dv01=Decimal("600.004"))
    just_over = RiskMetrics(nav=nav, cash=nav, pv={}, dv01=Decimal("600.005"))
    assert just_under.reported_dv01 == Decimal("600.00") and not just_under.dv01_exceeds_limit(
        policy
    )
    assert just_over.reported_dv01 == Decimal("600.01") and "parallel_dv01" in breaches(
        just_over, policy
    )
    # 0.0499999996 reports as 0.05000000: not a cash breach on the published value.
    edge = RiskMetrics(nav=Decimal("1"), cash=Decimal("0.0499999996"), pv={}, dv01=Decimal("0"))
    assert edge.reported_cash_ratio == Decimal("0.05000000") and breaches(edge, policy) == []
