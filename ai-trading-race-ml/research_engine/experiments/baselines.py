"""Deterministic baselines (spec 10.1) and the common bootstrap allocation.

Common bootstrap (``bootstrap-30-34-30-6-v2``): every invested competitor
receives the identical recorded allocation on the first decision session with
admitted data - 30% short, 34% intermediate, 30% longer, 6% cash - split
equally within each bucket and capped per instrument at the policy's
single-security limit (excess stays in cash). Buckets use remaining maturity
at the bootstrap session (ACT/365.25 years):

* short: 0.5 <= years <= 3 (instruments inside six months are excluded so the
  bootstrap never buys a note that is about to redeem);
* intermediate: 3 < years <= 7;
* longer: years > 7.

Bootstrap orders obey the same order-count control as every other decision
(the exemption covers turnover only), so each bucket holds at most
``max_orders_per_decision // 3`` instruments (minimum one). When a bucket has
more eligible notes, those whose remaining maturity is closest to the bucket's
representative tenor (short 2y, intermediate 5y, longer 10y) are selected, with
a security-id tie break.

Per-instrument weights are floored to 6 decimal places; the remainder goes to
cash so the weights sum exactly to 1. An empty bucket raises
:class:`BootstrapError` and the runner fails initialization for every matched
invested variant.

Baselines:

* ``cash``: always HOLD; never bootstraps (uninvested reference).
* ``static_ladder``: bootstrap, then HOLD forever; coupons/redemptions stay cash.
* ``quant_duration``: bootstrap, then target 4.0 years of portfolio effective
  duration (DV01 * 1e4 / NAV, cash at zero duration). Rebalance on the first
  supported session of a month or when |duration - 4.0| > 0.25. The sizing
  objective is lexicographic: minimize squared duration error, then turnover,
  with a stable security-id tie break. Because unsettled sale proceeds do not
  fund purchases, one decision either sells (longest duration first, which
  removes the most duration per unit of turnover) or buys with available
  settled cash (longest duration first, subject to the single-security cap),
  never both. Moves smaller than the policy's minimum weight change are
  dropped (they would not be executed). Turnover and cash use a one-point
  safety margin below the policy limits. When duration is below target and no
  cash-funded purchase is possible, ``quant-duration-v2`` performs stage 1 of a
  two-step rotation: it sells the shortest-duration holdings to cash (the
  projected duration assumes stage 2), and a later decision - triggered by the
  drift band - buys the longest eligible note once the proceeds have settled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from research_engine.contracts.common import CASH_SECURITY_ID
from research_engine.contracts.decisions import DecisionOutcome, StrategyKind, StrategyResult
from research_engine.contracts.portfolio import DecisionAction, RiskPolicy, TargetWeight

from .strategy import StrategyContext, make_result, register_strategy

BOOTSTRAP_ALLOCATION_VERSION = "bootstrap-30-34-30-6-v2"
BUCKET_WEIGHTS = {
    "short": Decimal("0.30"),
    "intermediate": Decimal("0.34"),
    "longer": Decimal("0.30"),
}
BUCKET_REPRESENTATIVE_YEARS = {
    "short": Decimal("2"),
    "intermediate": Decimal("5"),
    "longer": Decimal("10"),
}
BOOTSTRAP_CASH_WEIGHT = Decimal("0.06")
SHORT_MIN_YEARS = Decimal("0.5")
SHORT_MAX_YEARS = Decimal("3")
INTERMEDIATE_MAX_YEARS = Decimal("7")
DAYS_PER_YEAR = Decimal("365.25")
WEIGHT_QUANTUM = Decimal("0.000001")


class BootstrapError(RuntimeError):
    pass


def remaining_years(info, as_of: date) -> Decimal:
    return Decimal((info.maturity_date - as_of).days) / DAYS_PER_YEAR


def maturity_bucket(info, as_of: date) -> Optional[str]:
    years = remaining_years(info, as_of)
    if years < SHORT_MIN_YEARS:
        return None
    if years <= SHORT_MAX_YEARS:
        return "short"
    if years <= INTERMEDIATE_MAX_YEARS:
        return "intermediate"
    return "longer"


@dataclass(frozen=True)
class BootstrapAllocation:
    version: str
    session_date: date
    targets: tuple[TargetWeight, ...]
    buckets: dict = field(default_factory=dict)
    notes: tuple[str, ...] = ()


def bootstrap_allocation(universe, as_of: date, policy: RiskPolicy) -> BootstrapAllocation:
    members: dict[str, list[str]] = {name: [] for name in BUCKET_WEIGHTS}
    for info in sorted(universe, key=lambda i: i.security_id):
        bucket = maturity_bucket(info, as_of)
        if bucket is not None:
            members[bucket].append(info.security_id)
    empty = [name for name, ids in members.items() if not ids]
    if empty:
        raise BootstrapError("empty_bootstrap_bucket:" + ",".join(empty))
    notes: list[str] = []
    per_bucket = max(1, policy.max_orders_per_decision // len(BUCKET_WEIGHTS))
    by_id = {info.security_id: info for info in universe}
    for name, ids in members.items():
        if len(ids) > per_bucket:
            target_years = BUCKET_REPRESENTATIVE_YEARS[name]
            ranked = sorted(
                ids,
                key=lambda sid: (abs(remaining_years(by_id[sid], as_of) - target_years), sid),
            )
            members[name] = sorted(ranked[:per_bucket])
            notes.append(f"bucket_capped_to_order_limit:{name}:{per_bucket}")
    weights: dict[str, Decimal] = {}
    for name, ids in members.items():
        share = (BUCKET_WEIGHTS[name] / len(ids)).quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
        if share > policy.max_single_security_ratio:
            notes.append(f"per_instrument_cap_applied:{name}")
            share = policy.max_single_security_ratio
        for sid in ids:
            weights[sid] = share
    cash = Decimal("1") - sum(weights.values(), Decimal("0"))
    targets = [TargetWeight(security_id=sid, weight=w) for sid, w in sorted(weights.items())]
    targets.append(TargetWeight(security_id=CASH_SECURITY_ID, weight=cash))
    return BootstrapAllocation(
        version=BOOTSTRAP_ALLOCATION_VERSION,
        session_date=as_of,
        targets=tuple(targets),
        buckets={k: list(v) for k, v in members.items()},
        notes=tuple(notes),
    )


class CashStrategy:
    strategy_id = "cash"
    kind = StrategyKind.CASH_REFERENCE
    invested = False
    deterministic = True

    def __init__(self, config: Optional[dict] = None):
        self.config = {"version": "cash-v1", **(config or {})}

    def decide(self, ctx: StrategyContext) -> StrategyResult:
        return make_result(
            ctx,
            self,
            DecisionOutcome.COMPLETED_HOLD,
            action=DecisionAction.HOLD,
            reasons=["cash_reference_no_discretionary_trades"],
        )


class _BootstrappingStrategy:
    invested = True
    deterministic = True

    def bootstrap(self, ctx: StrategyContext) -> Optional[StrategyResult]:
        if ctx.initialized():
            return None
        if not ctx.bootstrap_targets:
            return make_result(
                ctx,
                self,
                DecisionOutcome.FAILED_DEPENDENCY,
                reasons=["bootstrap_allocation_unavailable"],
            )
        return make_result(
            ctx,
            self,
            DecisionOutcome.COMPLETED_PROPOSAL,
            action=DecisionAction.BOOTSTRAP,
            targets=list(ctx.bootstrap_targets),
            reasons=[BOOTSTRAP_ALLOCATION_VERSION],
        )


class StaticLadderStrategy(_BootstrappingStrategy):
    strategy_id = "static_ladder"
    kind = StrategyKind.QUANT_POLICY

    def __init__(self, config: Optional[dict] = None):
        self.config = {
            "version": "static-ladder-v1",
            "couponTreatment": "retain_as_cash",
            "redemptionTreatment": "retain_as_cash",
            **(config or {}),
        }

    def decide(self, ctx: StrategyContext) -> StrategyResult:
        result = self.bootstrap(ctx)
        if result is not None:
            return result
        return make_result(
            ctx,
            self,
            DecisionOutcome.COMPLETED_HOLD,
            action=DecisionAction.HOLD,
            reasons=["static_allocation_hold"],
        )


def duration_targets(
    snapshot, policy: RiskPolicy, target: Decimal, margin: Decimal
) -> tuple[list[TargetWeight], Decimal, list[str]]:
    """Deterministic lexicographic optimum (see module docstring).

    Returns (target weights, projected duration, notes).
    """
    nav = snapshot.nav
    durations = snapshot.durations
    current = {sid: snapshot.weight(sid) for sid in snapshot.detail.pv}
    weights = dict(current)
    duration = sum((weights[s] * durations.get(s, Decimal("0")) for s in weights), Decimal("0"))
    error = duration - target
    budget = policy.max_daily_turnover_ratio - margin
    notes: list[str] = []
    if error > 0:
        order = sorted(
            (s for s in weights if durations.get(s, Decimal("0")) > 0 and snapshot.tradable.get(s)),
            key=lambda s: (-durations[s], s),
        )
        for sid in order:
            if error <= 0 or budget <= 0:
                break
            delta = min(weights[sid], error / durations[sid], budget)
            if delta < policy.min_weight_change:
                notes.append(f"move_below_min_change:{sid}")
                continue
            weights[sid] -= delta
            error -= delta * durations[sid]
            budget -= delta
    elif error < 0:
        funding = (snapshot.cash_settled - snapshot.payables) / nav if nav else Decimal("0")
        contractual = snapshot.contractual_cash / nav if nav else Decimal("0")
        cash_room = min(funding, contractual) - (policy.min_cash_ratio + margin)
        cap = policy.max_single_security_ratio - margin
        order = sorted(
            (
                s
                for s in snapshot.universe
                if snapshot.tradable.get(s) and durations.get(s, Decimal("0")) > 0
            ),
            key=lambda s: (-durations[s], s),
        )
        bought = False
        for sid in order:
            if error >= 0 or budget <= 0 or cash_room <= 0:
                break
            room = cap - weights.get(sid, Decimal("0"))
            delta = min(room, -error / durations[sid], budget, cash_room)
            if delta < policy.min_weight_change:
                notes.append(f"move_below_min_change:{sid}")
                continue
            weights[sid] = weights.get(sid, Decimal("0")) + delta
            error += delta * durations[sid]
            budget -= delta
            cash_room -= delta
            bought = True
        if error < 0 and budget > 0 and not bought and order:
            # Two-step rotation, stage 1 (spec 9.4): sale proceeds fund purchases only
            # after settlement, so sell the shortest-duration holdings to cash now; a
            # later decision buys the longest eligible note with the settled cash.
            longest = order[0]
            d_long = durations[longest]
            holdings = sorted(
                (
                    s
                    for s in weights
                    if weights[s] > 0
                    and snapshot.tradable.get(s)
                    and durations.get(s, Decimal("0")) < d_long
                ),
                key=lambda s: (durations.get(s, Decimal("0")), s),
            )
            for sid in holdings:
                if error >= 0 or budget <= 0:
                    break
                gain = d_long - durations.get(sid, Decimal("0"))
                delta = min(weights[sid], -error / gain, budget)
                if delta < policy.min_weight_change:
                    notes.append(f"move_below_min_change:{sid}")
                    continue
                weights[sid] -= delta
                error += delta * gain  # projected once stage 2 buys `longest`
                budget -= delta
                notes.append(f"rotation_stage_1_sell_to_cash:{sid}->{longest}")
    targets = []
    total = Decimal("0")
    for sid in sorted(weights):
        w = max(weights[sid], Decimal("0")).quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
        if w > 0:
            targets.append(TargetWeight(security_id=sid, weight=w))
            total += w
    targets.append(TargetWeight(security_id=CASH_SECURITY_ID, weight=Decimal("1") - total))
    changed = any(
        abs(weights[s] - current.get(s, Decimal("0"))) >= policy.min_weight_change for s in weights
    )
    if not changed:
        notes.append("no_feasible_improvement")
    return targets, target + error, notes


class QuantDurationStrategy(_BootstrappingStrategy):
    strategy_id = "quant_duration"
    kind = StrategyKind.QUANT_POLICY

    def __init__(self, config: Optional[dict] = None):
        self.config = {
            "version": "quant-duration-v2",
            "targetDurationYears": "4.0",
            "driftBandYears": "0.25",
            "rebalance": "first_session_of_month_or_drift",
            "objective": "min_sq_duration_error_then_turnover_then_security_id",
            "safetyMargin": "0.01",
            **(config or {}),
        }
        self.target = Decimal(str(self.config["targetDurationYears"]))
        self.band = Decimal(str(self.config["driftBandYears"]))
        self.margin = Decimal(str(self.config["safetyMargin"]))

    def decide(self, ctx: StrategyContext) -> StrategyResult:
        result = self.bootstrap(ctx)
        if result is not None:
            return result
        snapshot = ctx.snapshot
        if not snapshot.complete or snapshot.portfolio_duration() is None:
            return make_result(
                ctx,
                self,
                DecisionOutcome.FAILED_DEPENDENCY,
                reasons=["decision_snapshot_incomplete"] + snapshot.valuation.incomplete_reasons,
            )
        duration = snapshot.portfolio_duration()
        first_of_month = (
            ctx.previous_session is None or ctx.previous_session.month != ctx.session_date.month
        )
        drift = abs(duration - self.target)
        if not first_of_month and drift <= self.band:
            return make_result(
                ctx,
                self,
                DecisionOutcome.COMPLETED_HOLD,
                action=DecisionAction.HOLD,
                reasons=[f"duration_within_band:{duration}"],
            )
        targets, projected, notes = duration_targets(
            snapshot, ctx.risk_policy, self.target, self.margin
        )
        calc_ids = snapshot.valuation.calculation_ids
        if "no_feasible_improvement" in notes:
            return make_result(
                ctx,
                self,
                DecisionOutcome.COMPLETED_HOLD,
                action=DecisionAction.HOLD,
                reasons=[f"duration:{duration}"] + notes,
                calculation_ids=calc_ids,
            )
        trigger = "first_session_of_month" if first_of_month else "drift"
        return make_result(
            ctx,
            self,
            DecisionOutcome.COMPLETED_PROPOSAL,
            action=DecisionAction.REBALANCE,
            targets=targets,
            reasons=[
                f"trigger:{trigger}",
                f"duration:{duration}",
                f"projected:{projected.quantize(WEIGHT_QUANTUM)}",
            ]
            + notes,
            calculation_ids=calc_ids,
        )


register_strategy("cash", CashStrategy)
register_strategy("static_ladder", StaticLadderStrategy)
register_strategy("quant_duration", QuantDurationStrategy)

BASELINE_IDS = ("cash", "static_ladder", "quant_duration")
