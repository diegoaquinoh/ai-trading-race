"""Decision snapshot, weight validation, deterministic sizing and policy (spec 9.2, 9.3).

The whole order set is evaluated against the projected post-trade state,
including pending commitments (filled-but-unsettled trades). Rules are
documented in ``docs/fixed-income/execution-and-policy.md``:

* weights: finite, >= 0, frozen universe incl. ``CASH-USD``, sum 1 +/- 1e-6;
  held securities omitted from the target are normalized to 0 (recorded), except
  held securities that are no longer tradable (e.g. too close to maturity): they
  keep their face until redemption and create no order (recorded); an explicit
  target that would require trading one is rejected;
* sizing uses the decision snapshot (NAV and model dirty prices at the
  decision session); face rounds *down* to the instrument increment and
  targets below the minimum face round to zero;
* per-instrument weight changes below ``min_weight_change`` produce no order
  unless the order restores a breached mandatory limit;
* sells first (by security id), then buys (by security id);
* funding = settled cash - reservations - committed payables; unsettled sale
  receivables never fund purchases, so an unfundable rotation is rejected;
* limits: max orders, turnover (bootstrap exemption), min cash after
  committed settlements, max single-security economic dirty value, parallel
  DV01 per 1M NAV, long-only; missing risk output blocks (never zero risk);
* breach mode: a limit already breached before the decision passes only if
  the order set does not worsen it; no new breach may be created. Pre- and
  post-trade metrics are published (``pre_trade_*`` / ``post_trade_*``) and every
  limit decision compares exactly those reported values (ratios at 8 dp, USD at
  cents), the same rule the .NET gate applies;
* projection mode is not implemented: failures return explicit reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Optional

from research_engine.contracts.common import CASH_SECURITY_ID, DataMode, money
from research_engine.contracts.portfolio import (
    DecisionAction,
    ExecutionModel,
    OrderIntent,
    OrderStatus,
    PolicyCheck,
    PolicyEvaluation,
    RiskPolicy,
    Side,
    SizedOrder,
    TargetWeight,
    ValuationSnapshot,
)

from .clock import make_id, ny_date, session_end_at
from .ledger import HUNDRED, MILLION, ZERO, Book
from .valuation import (
    CurveRef,
    MarkSource,
    ValuationDetail,
    business_days_between,
    value_book,
)

RESERVATION_BUFFER_PER_100 = Decimal("0.25")
RATIO_QUANTUM = Decimal("0.00000001")
ONE = Decimal("1")


def q_ratio(value: Decimal) -> Decimal:
    return value.quantize(RATIO_QUANTUM)


# --------------------------------------------------------------------------- #
# Decision snapshot
# --------------------------------------------------------------------------- #


@dataclass
class DecisionSnapshot:
    """Frozen numerical inputs for one decision (own portfolio + common curve)."""

    session_date: date
    decision_time: datetime
    eligible_session: date
    curve: Optional[CurveRef]
    valuation: ValuationSnapshot
    detail: ValuationDetail
    universe: list[str]
    instruments: dict[str, object]
    dirty: dict[str, Decimal] = field(default_factory=dict)
    durations: dict[str, Decimal] = field(default_factory=dict)  # per-instrument effective
    tradable: dict[str, bool] = field(default_factory=dict)
    price_calc_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    cash_settled: Decimal = ZERO
    receivables: Decimal = ZERO
    payables: Decimal = ZERO
    curve_age_business_days: Optional[int] = None
    stale_curve: bool = False

    @property
    def nav(self) -> Optional[Decimal]:
        return self.valuation.equity_usd

    @property
    def complete(self) -> bool:
        return self.valuation.complete and not self.reasons and self.nav is not None

    @property
    def contractual_cash(self) -> Decimal:
        """Settled cash after committed settlements (receivables - payables)."""
        return self.cash_settled + self.receivables - self.payables

    def weight(self, security_id: str) -> Decimal:
        nav = self.nav
        if not nav:
            return ZERO
        return self.detail.pv.get(security_id, ZERO) / nav

    def portfolio_duration(self) -> Optional[Decimal]:
        return self.valuation.effective_duration_years


def build_decision_snapshot(
    book: Book,
    pricing,
    *,
    curve: Optional[CurveRef],
    decision_time: datetime,
    data_mode: DataMode,
    policy: RiskPolicy,
    mark_source: Optional[MarkSource] = None,
) -> DecisionSnapshot:
    session = ny_date(decision_time) if curve is None else curve.session_date
    valuation, detail = value_book(
        book,
        pricing,
        valuation_id=make_id("dsnap", book.portfolio_id, book.version),
        valuation_at=decision_time,
        curve=curve,
        data_mode=data_mode,
        policy=policy,
        state_version=book.version,
        mark_source=mark_source,
    )
    eligible = pricing.advance_business_days(ny_date(decision_time), 1)
    instruments = {info.security_id: info for info in pricing.universe(session)}
    for sid in book.held_securities():
        if sid not in instruments:
            try:
                instruments[sid] = pricing.instrument(sid)
            except Exception:
                pass
    snapshot = DecisionSnapshot(
        session_date=session,
        decision_time=decision_time,
        eligible_session=eligible,
        curve=curve,
        valuation=valuation,
        detail=detail,
        universe=sorted(info.security_id for info in pricing.universe(session)),
        instruments=instruments,
        cash_settled=book.cash,
        receivables=book.receivables(),
        payables=book.payables(),
    )
    if curve is None:
        snapshot.reasons.append("no_decision_curve")
        return snapshot
    age = business_days_between(pricing, curve.session_date, ny_date(decision_time))
    snapshot.curve_age_business_days = age
    if age > policy.max_mark_age_business_days:
        snapshot.stale_curve = True
        snapshot.reasons.append(f"stale_decision_curve:{age}_business_days")
    for sid in sorted(instruments):
        info = instruments[sid]
        try:
            settle = pricing.settlement_date(sid, session)
            price = pricing.price(sid, curve.curve_snapshot_id, settle)
            snapshot.dirty[sid] = Decimal(price.dirty_price_per_100)
            snapshot.price_calc_ids.append(price.calculation_id)
            fill_settle = pricing.settlement_date(sid, eligible)
            snapshot.tradable[sid] = (
                sid in snapshot.universe
                and info.issue_date <= eligible
                and fill_settle < info.maturity_date
                and settle < info.maturity_date
            )
        except Exception:
            snapshot.tradable[sid] = False
        try:
            per_100 = pricing.value_position(
                sid, curve.curve_snapshot_id, session, info.min_face_usd or Decimal("1000")
            )
            snapshot.durations[sid] = Decimal(per_100.effective_duration_years)
        except Exception:
            pass
    return snapshot


# --------------------------------------------------------------------------- #
# Limit checks
# --------------------------------------------------------------------------- #


@dataclass
class RiskMetrics:
    """Risk metrics of one (pre- or post-trade) state.

    Limit decisions use the *reported* values (``reported_*``: ratios quantized to
    8 dp, USD to cents) - exactly the numbers published in ``PolicyEvaluation`` and
    re-compared by the .NET policy gate - so both sides take the same decision.
    """

    nav: Decimal
    cash: Decimal
    pv: dict[str, Decimal]
    dv01: Decimal

    @property
    def cash_ratio(self) -> Decimal:
        return self.cash / self.nav if self.nav else ZERO

    def ratio(self, security_id: str) -> Decimal:
        return self.pv.get(security_id, ZERO) / self.nav if self.nav else ZERO

    @property
    def max_ratio(self) -> Decimal:
        return max((self.ratio(s) for s in self.pv), default=ZERO)

    def dv01_limit(self, policy: RiskPolicy) -> Decimal:
        return policy.max_parallel_dv01_usd_per_million_nav * self.nav / MILLION

    # -- reported (published) values ------------------------------------------------
    @property
    def reported_nav(self) -> Decimal:
        return money(self.nav)

    @property
    def reported_cash_ratio(self) -> Decimal:
        return q_ratio(self.cash_ratio)

    def reported_ratio(self, security_id: str) -> Decimal:
        return q_ratio(self.ratio(security_id))

    @property
    def reported_max_ratio(self) -> Decimal:
        return q_ratio(self.max_ratio)

    @property
    def reported_dv01(self) -> Decimal:
        return money(self.dv01)

    def dv01_exceeds_limit(self, policy: RiskPolicy) -> bool:
        """``|dv01| * 1e6 > cap * nav`` on the reported DV01 and NAV (as the .NET gate)."""
        cap = policy.max_parallel_dv01_usd_per_million_nav
        return abs(self.reported_dv01) * MILLION > cap * self.reported_nav


def breaches(metrics: RiskMetrics, policy: RiskPolicy) -> list[str]:
    found: list[str] = []
    if metrics.reported_cash_ratio < policy.min_cash_ratio:
        found.append("min_cash_ratio")
    for sid in sorted(metrics.pv):
        if metrics.reported_ratio(sid) > policy.max_single_security_ratio:
            found.append(f"max_single_security_ratio:{sid}")
    if metrics.dv01_exceeds_limit(policy):
        found.append("parallel_dv01")
    return found


def breach_not_worsened_passes(
    *, within: bool, pre_breached: bool, not_worse: bool
) -> tuple[bool, Optional[str]]:
    """Breach policy (spec 9.3): within the limit, or already breached and not worse.

    Upper limits: ``post <= limit or (pre > limit and post <= pre)``; the minimum
    cash ratio: ``post >= min or (pre < min and post >= pre)``. Callers pass the
    comparisons evaluated on the reported pre/post values.
    """
    if within:
        return True, None
    if pre_breached and not_worse:
        return True, "breach_not_worsened"
    return False, "risk_increasing_during_breach" if pre_breached else "limit_exceeded"


def valuation_metrics(valuation: ValuationSnapshot, detail: ValuationDetail, book: Book):
    if valuation.equity_usd is None:
        return None
    cash = book.cash + book.receivables() - book.payables()
    return RiskMetrics(
        nav=valuation.equity_usd, cash=cash, pv=dict(detail.pv), dv01=detail.total_dv01
    )


# --------------------------------------------------------------------------- #
# Weight validation and sizing
# --------------------------------------------------------------------------- #


def validate_weights(
    targets: list[TargetWeight], universe: list[str], policy: RiskPolicy
) -> list[str]:
    reasons: list[str] = []
    if not targets:
        return ["empty_targets"]
    seen: set[str] = set()
    allowed = set(universe) | {CASH_SECURITY_ID}
    total = ZERO
    for target in targets:
        weight = target.weight
        if not weight.is_finite():
            reasons.append(f"non_finite_weight:{target.security_id}")
            continue
        if weight < 0:
            reasons.append(f"negative_weight:{target.security_id}")
        if target.security_id in seen:
            reasons.append(f"duplicate_target:{target.security_id}")
        seen.add(target.security_id)
        if target.security_id not in allowed:
            reasons.append(f"security_not_in_frozen_universe:{target.security_id}")
        total += weight
    if abs(total - ONE) > policy.weight_sum_tolerance:
        reasons.append(f"weights_do_not_sum_to_one:{total}")
    return reasons


def floor_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        raise ValueError("face increment must be positive")
    units = (value / increment).to_integral_value(rounding=ROUND_FLOOR)
    return max(units, ZERO) * increment


@dataclass
class _Sized:
    security_id: str
    side: Side
    face: Decimal
    est_dirty: Decimal  # model dirty at decision session
    exec_dirty: Decimal  # incl. half-spread/slippage
    consideration: Decimal
    fees: Decimal
    spread_cost: Decimal
    reservation: Decimal


def _check(check_id, limit, observed, unit, passed, reason=None) -> PolicyCheck:
    return PolicyCheck(
        check_id=check_id,
        limit=limit,
        observed=observed,
        unit=unit,
        passed=passed,
        reason=reason,
    )


def evaluate_decision(
    book: Book,
    snapshot: DecisionSnapshot,
    *,
    decision_id: str,
    action: DecisionAction,
    targets: list[TargetWeight],
    policy: RiskPolicy,
    execution: ExecutionModel,
    pricing,
    submitted_at: datetime,
) -> tuple[PolicyEvaluation, list[OrderIntent]]:
    """Validate, size and risk-check a decision; returns (evaluation, order intents)."""
    notes: list[str] = []
    rejected: list[str] = []
    checks: list[PolicyCheck] = []
    calc_ids = sorted(set(snapshot.valuation.calculation_ids + snapshot.price_calc_ids))
    pre = valuation_metrics(snapshot.valuation, snapshot.detail, book)
    pre_breaches = breaches(pre, policy) if pre is not None else []
    breach_mode = bool(pre_breaches)

    def finish(passed: bool, sized=(), post=None, turnover=None, orders=(), exemption=False):
        metrics = post or pre
        evaluation = PolicyEvaluation(
            policy_id=policy.policy_id,
            decision_id=decision_id,
            action=action,
            passed=passed,
            breach_mode=breach_mode,
            bootstrap_exemption_applied=exemption,
            original_targets=list(targets),
            normalized_targets=normalized,
            normalization_notes=notes,
            sized_orders=[
                SizedOrder(
                    security_id=s.security_id,
                    side=s.side,
                    face=s.face,
                    estimated_dirty_price_per_100=s.exec_dirty,
                    estimated_consideration_usd=s.consideration,
                )
                for s in sized
            ],
            rejected_reasons=rejected,
            checks=checks,
            post_trade_nav_usd=metrics.reported_nav if metrics else None,
            post_trade_cash_ratio=metrics.reported_cash_ratio if metrics else None,
            post_trade_max_security_ratio=metrics.reported_max_ratio if metrics else None,
            post_trade_parallel_dv01_usd=metrics.reported_dv01 if metrics else None,
            pre_trade_nav_usd=pre.reported_nav if metrics and pre else None,
            pre_trade_cash_ratio=pre.reported_cash_ratio if metrics and pre else None,
            pre_trade_max_security_ratio=pre.reported_max_ratio if metrics and pre else None,
            pre_trade_parallel_dv01_usd=pre.reported_dv01 if metrics and pre else None,
            turnover_ratio=q_ratio(turnover) if turnover is not None else ZERO,
            order_count=len(orders),
            calculation_ids=calc_ids,
        )
        return evaluation, list(orders)

    normalized: list[TargetWeight] = []
    if action == DecisionAction.HOLD:
        if targets:
            notes.append("hold_ignores_target_weights")
        return finish(True)

    rejected.extend(validate_weights(targets, snapshot.universe, policy))
    if policy.projection_mode != "disabled":
        rejected.append(f"projection_mode_not_implemented:{policy.projection_mode}")
    if not snapshot.complete:
        detail_reasons = snapshot.reasons + snapshot.valuation.incomplete_reasons
        if snapshot.detail.stale or snapshot.stale_curve:
            rejected.append("stale_marks_block_discretionary_action")
        rejected.append("decision_snapshot_incomplete:" + ",".join(sorted(set(detail_reasons))))
    initialized = bool(book.held_securities()) or bool(book.pending)
    exemption = False
    if action == DecisionAction.BOOTSTRAP:
        if initialized:
            rejected.append("bootstrap_not_permitted_after_initialization")
        elif policy.bootstrap_turnover_exemption:
            exemption = True
    if rejected:
        return finish(False)

    nav = snapshot.nav
    target_map = {t.security_id: t.weight for t in targets}
    for sid in book.held_securities():
        if sid in target_map or book.economic_face(sid) <= 0:
            continue
        if snapshot.tradable.get(sid, False):
            target_map[sid] = ZERO
            notes.append(f"held_security_without_target_set_to_zero:{sid}")
        else:
            # Cannot be traded (e.g. too close to maturity): keep the current face until
            # redemption instead of forcing an impossible sale; no order is created.
            notes.append(f"held_untradable_security_kept_until_redemption:{sid}")
    if CASH_SECURITY_ID not in target_map:
        notes.append("cash_weight_implied_zero")
    normalized = [
        TargetWeight(security_id=sid, weight=target_map[sid]) for sid in sorted(target_map)
    ]

    cash_breached = "min_cash_ratio" in pre_breaches
    dv01_breached = "parallel_dv01" in pre_breaches
    sized: list[_Sized] = []
    for sid in sorted(s for s in target_map if s != CASH_SECURITY_ID):
        weight = target_map[sid]
        info = snapshot.instruments.get(sid)
        dirty = snapshot.dirty.get(sid)
        if info is None or dirty is None or dirty <= 0:
            rejected.append(f"missing_price:{sid}")
            continue
        current_face = book.economic_face(sid)
        target_face = floor_to_increment(weight * nav * HUNDRED / dirty, info.face_increment_usd)
        if ZERO < target_face < info.min_face_usd:
            target_face = ZERO
            notes.append(f"below_min_face_rounded_to_zero:{sid}")
        delta = target_face - current_face
        if delta == 0:
            continue
        change = abs(weight - snapshot.weight(sid))
        restoring = delta < 0 and (
            cash_breached or dv01_breached or f"max_single_security_ratio:{sid}" in pre_breaches
        )
        if change < policy.min_weight_change and not restoring:
            notes.append(f"below_min_weight_change:{sid}")
            continue
        if not snapshot.tradable.get(sid, False):
            rejected.append(f"instrument_not_tradable:{sid}")
            continue
        side = Side.SELL if delta < 0 else Side.BUY
        face = -delta if delta < 0 else delta
        cost = execution.half_spread_per_100 + execution.slippage_per_100
        exec_dirty = dirty + cost if side == Side.BUY else dirty - cost
        consideration = money(face * exec_dirty / HUNDRED)
        fees = money(face * execution.commission_usd_per_million_face / MILLION)
        reservation = ZERO
        if side == Side.BUY:
            reservation = money(face * (exec_dirty + RESERVATION_BUFFER_PER_100) / HUNDRED) + fees
        sized.append(
            _Sized(
                security_id=sid,
                side=side,
                face=face,
                est_dirty=dirty,
                exec_dirty=exec_dirty,
                consideration=consideration,
                fees=fees,
                spread_cost=money(face * cost / HUNDRED),
                reservation=reservation,
            )
        )
    sized.sort(key=lambda s: (0 if s.side == Side.SELL else 1, s.security_id))

    # -- projected post-trade state ---------------------------------------------------
    post_pv = dict(snapshot.detail.pv)
    post_dv01 = dict(snapshot.detail.dv01)
    for order in sized:
        new_face = book.economic_face(order.security_id) + (
            order.face if order.side == Side.BUY else -order.face
        )
        if new_face < 0:
            rejected.append(f"long_only_violation:{order.security_id}")
            continue
        if new_face == 0:
            post_pv.pop(order.security_id, None)
            post_dv01.pop(order.security_id, None)
            continue
        try:
            result = pricing.value_position(
                order.security_id,
                snapshot.curve.curve_snapshot_id,
                snapshot.session_date,
                new_face,
            )
            post_pv[order.security_id] = money(result.pv_dirty_usd)
            post_dv01[order.security_id] = Decimal(result.parallel_dv01_usd)
            calc_ids.append(result.calculation_id)
        except Exception as exc:
            rejected.append(f"missing_risk_output:{order.security_id}:{type(exc).__name__}")
    for sid in sorted(post_pv):
        if sid not in post_dv01:
            rejected.append(f"missing_risk_output:{sid}")
    calc_ids = sorted(set(calc_ids))

    total_costs = sum((o.spread_cost + o.fees for o in sized), ZERO)
    buys = [o for o in sized if o.side == Side.BUY]
    sells = [o for o in sized if o.side == Side.SELL]
    post_cash = (
        snapshot.contractual_cash
        - sum((o.consideration + o.fees for o in buys), ZERO)
        + sum((o.consideration - o.fees for o in sells), ZERO)
    )
    post = RiskMetrics(
        nav=nav - total_costs,
        cash=post_cash,
        pv=post_pv,
        dv01=sum(post_dv01.values(), ZERO),
    )
    turnover = sum((o.consideration for o in sized), ZERO) / nav if nav else ZERO

    # -- checks -----------------------------------------------------------------------
    count_ok = len(sized) <= policy.max_orders_per_decision
    checks.append(
        _check(
            "max_orders_per_decision",
            Decimal(policy.max_orders_per_decision),
            Decimal(len(sized)),
            "COUNT",
            count_ok,
            None if count_ok else "too_many_orders",
        )
    )
    reserved_after_cancel = book.reserved - sum(
        (o.reserved_cash_usd for o in book.open_orders.values()), ZERO
    )
    available = book.cash - reserved_after_cancel - book.payables()
    needed = sum((o.reservation for o in buys), ZERO)
    funding_ok = needed <= available
    checks.append(
        _check(
            "funding_settled_cash",
            money(available),
            money(needed),
            "USD",
            funding_ok,
            None if funding_ok else "unfundable_purchases_receivables_do_not_fund",
        )
    )
    long_ok = not any(r.startswith("long_only_violation") for r in rejected)
    checks.append(_check("long_only", None, None, "BOOL", long_ok))
    if exemption:
        checks.append(
            _check(
                "max_daily_turnover_ratio",
                policy.max_daily_turnover_ratio,
                q_ratio(turnover),
                "RATIO",
                True,
                "bootstrap_turnover_exemption",
            )
        )
    else:
        turnover_ok = turnover <= policy.max_daily_turnover_ratio
        checks.append(
            _check(
                "max_daily_turnover_ratio",
                policy.max_daily_turnover_ratio,
                q_ratio(turnover),
                "RATIO",
                turnover_ok,
                None if turnover_ok else "turnover_cap_exceeded",
            )
        )

    def limit(check_id, limit_value, observed, unit, *, within, pre_breached, not_worse):
        passed, reason = breach_not_worsened_passes(
            within=within, pre_breached=pre_breached, not_worse=not_worse
        )
        checks.append(_check(check_id, limit_value, observed, unit, passed, reason))

    # Every comparison below uses the reported pre/post values (see RiskMetrics).
    post_cash = post.reported_cash_ratio
    pre_cash = pre.reported_cash_ratio if pre else None
    limit(
        "min_cash_ratio",
        policy.min_cash_ratio,
        post_cash,
        "RATIO",
        within=post_cash >= policy.min_cash_ratio,
        pre_breached=pre_cash is not None and pre_cash < policy.min_cash_ratio,
        not_worse=pre_cash is not None and post_cash >= pre_cash,
    )
    for sid in sorted(post_pv):
        ratio = post.reported_ratio(sid)
        pre_ratio = pre.reported_ratio(sid) if pre else None
        limit(
            f"max_single_security_ratio:{sid}",
            policy.max_single_security_ratio,
            ratio,
            "RATIO",
            within=ratio <= policy.max_single_security_ratio,
            pre_breached=pre_ratio is not None and pre_ratio > policy.max_single_security_ratio,
            not_worse=pre_ratio is not None and ratio <= pre_ratio,
        )
    # DV01 limits scale with NAV: post-trade NAV for ``post``, pre-trade NAV for ``pre``.
    limit(
        "parallel_dv01_usd",
        money(post.dv01_limit(policy)),
        post.reported_dv01,
        "USD_PER_BP",
        within=not post.dv01_exceeds_limit(policy),
        pre_breached=pre is not None and pre.dv01_exceeds_limit(policy),
        not_worse=pre is not None and post.reported_dv01 <= pre.reported_dv01,
    )

    failed = [c for c in checks if not c.passed]
    for check in failed:
        rejected.append(f"{check.check_id}:{check.reason or 'failed'}")
    passed = not rejected
    orders: list[OrderIntent] = []
    if passed:
        expires = session_end_at(snapshot.eligible_session)
        for priority, order in enumerate(sized):
            orders.append(
                OrderIntent(
                    order_id=make_id("ord", decision_id, order.security_id),
                    decision_id=decision_id,
                    security_id=order.security_id,
                    side=order.side,
                    face=order.face,
                    submitted_at=submitted_at,
                    eligible_session_date=snapshot.eligible_session,
                    expires_at=expires,
                    status=OrderStatus.ACCEPTED,
                    reserved_cash_usd=order.reservation,
                    batch_priority=priority,
                    bootstrap=action == DecisionAction.BOOTSTRAP,
                )
            )
    return finish(passed, sized, post, turnover, orders, exemption)
