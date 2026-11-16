"""Financial metrics over a reconciled daily valuation series (spec 16.3).

Conventions (``metrics-v1``):

* The equity series is the sequence of *complete* end-of-day valuations
  (``VALUE_PORTFOLIO`` proposals). Incomplete/stale valuations are counted
  and excluded, never interpolated.
* Daily return ``r_t = (E_t - E_{t-1} - F_t) / E_{t-1}`` where ``F_t`` is the
  external capital flow between the two valuations.
* Net return uses actual equity (all costs included). Gross return adds back
  analytic spread cost and explicit fees.
* Annualized return is reported only with at least ``annualize_min_obs``
  (default 252) daily returns; otherwise ``None`` with a reason.
* Sharpe is unavailable with fewer than ``min_sharpe_obs`` (default 60)
  returns, zero variance, or no declared risk-free series. Annualization uses
  sqrt(252). It is a reporting quantity, not a significance claim.
* Attribution: carry = interest income + change in economic accrued value -
  change in purchased-accrued balance; costs = -(fees + spread cost);
  price = realized + unrealized - accrual component + spread cost (spread is
  embedded in execution prices); residual = total - carry - price - costs,
  which equals the book/economic difference (zero when reconciled).
* Paired comparisons use a moving-block bootstrap with a declared block
  policy and seed.

One implementation serves both paths: offline replay builds the series from
committed ``TransitionProposal`` objects (:func:`portfolio_metrics`); the
application path (``POST /internal/v1/analytics/performance``) builds the same
:class:`EquityPoint` series and :class:`SeriesActivity` from the values the
platform stored, and both call :func:`series_metrics`.

Statistics are floats (Python-internal research artifacts); money stays Decimal.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence, Union

from research_engine.contracts.common import money
from research_engine.contracts.decisions import DecisionOutcome, StrategyResult
from research_engine.contracts.portfolio import (
    CommandType,
    OrderStatus,
    TransitionProposal,
)

from research_engine.simulation.clock import ny_date

METRICS_VERSION = "metrics-v1"
TRADING_DAYS = 252
ZERO = Decimal("0")


@dataclass(frozen=True)
class EquityPoint:
    valuation_at: datetime
    session: date
    complete: bool
    equity: Optional[Decimal]
    cash: Decimal
    dv01: Optional[Decimal]
    duration: Optional[Decimal]
    accrued_value: Decimal
    accrued_purchased: Decimal
    capital: Decimal
    income: Decimal
    realized: Decimal
    unrealized: Decimal
    fees: Decimal
    spread: Decimal


def accrued_value_usd(marks: Iterable[tuple[Decimal, Optional[Decimal]]]) -> Decimal:
    """Economic accrued interest of the valued face: ``(economic_face, accrued_per_100)`` pairs."""
    return money(
        sum((face * accrued / 100 for face, accrued in marks if accrued is not None), ZERO)
    )


def accrued_purchased_usd(balances: Iterable[Decimal]) -> Decimal:
    """Remaining purchased-accrued balances of the held lots."""
    return sum(balances, ZERO)


def equity_series(proposals: Iterable[TransitionProposal]) -> list[EquityPoint]:
    points = []
    for proposal in proposals:
        if proposal.command_type != CommandType.VALUE_PORTFOLIO or proposal.valuation is None:
            continue
        valuation = proposal.valuation
        state = proposal.new_state
        accrued_value = accrued_value_usd(
            (m.economic_face, m.accrued_per_100) for m in valuation.marks
        )
        accrued_purchased = accrued_purchased_usd(
            lot.accrued_purchased_usd for p in state.positions for lot in p.lots
        )
        points.append(
            EquityPoint(
                valuation_at=valuation.valuation_at,
                session=ny_date(valuation.valuation_at),
                complete=valuation.complete,
                equity=valuation.equity_usd,
                cash=valuation.cash_usd,
                dv01=valuation.parallel_dv01_usd,
                duration=valuation.effective_duration_years,
                accrued_value=accrued_value,
                accrued_purchased=accrued_purchased,
                capital=state.external_capital_usd,
                income=state.interest_income_usd,
                realized=state.realized_gain_loss_usd,
                unrealized=state.booked_unrealized_usd,
                fees=state.transaction_fees_usd,
                spread=state.spread_cost_usd,
            )
        )
    return points


def dated_returns(points: Sequence[EquityPoint]) -> list[tuple[date, float]]:
    """Daily returns between consecutive complete valuations, keyed by the later session."""
    complete = [p for p in points if p.complete and p.equity is not None]
    returns = []
    for prev, cur in zip(complete, complete[1:]):
        flow = cur.capital - prev.capital
        if prev.equity <= 0:
            continue
        returns.append((cur.session, float((cur.equity - prev.equity - flow) / prev.equity)))
    return returns


def daily_returns(points: Sequence[EquityPoint]) -> list[float]:
    return [value for _, value in dated_returns(points)]


def max_drawdown(values: Sequence[float]) -> dict:
    """Maximum drawdown and recovery duration (observations from trough to new peak)."""
    if not values:
        return {"maxDrawdown": None, "recoveryObservations": None, "recovered": None}
    peak = values[0]
    peak_index = 0
    worst = 0.0
    worst_peak = worst_trough = 0
    for index, value in enumerate(values):
        if value > peak:
            peak, peak_index = value, index
        drawdown = (value - peak) / peak if peak else 0.0
        if drawdown < worst:
            worst, worst_peak, worst_trough = drawdown, peak_index, index
    recovery = None
    if worst < 0:
        target = values[worst_peak]
        for index in range(worst_trough, len(values)):
            if values[index] >= target:
                recovery = index - worst_trough
                break
    return {
        "maxDrawdown": worst,
        "peakIndex": worst_peak,
        "troughIndex": worst_trough,
        "recoveryObservations": recovery,
        "recovered": recovery is not None if worst < 0 else True,
    }


def sharpe_ratio(
    returns: Sequence[float],
    risk_free: Optional[Sequence[float]],
    min_obs: int = 60,
) -> dict:
    if risk_free is None:
        return {"value": None, "unavailableReason": "missing_risk_free_series"}
    if len(returns) < min_obs:
        return {"value": None, "unavailableReason": f"fewer_than_{min_obs}_returns"}
    if len(risk_free) != len(returns):
        return {"value": None, "unavailableReason": "risk_free_series_misaligned"}
    excess = [r - f for r, f in zip(returns, risk_free)]
    stdev = statistics.stdev(excess)
    if stdev == 0:
        return {"value": None, "unavailableReason": "zero_variance"}
    return {
        "value": statistics.fmean(excess) / stdev * math.sqrt(TRADING_DAYS),
        "unavailableReason": None,
        "annualization": f"sqrt({TRADING_DAYS})",
    }


def paired_block_bootstrap(
    returns_a: Sequence[float],
    returns_b: Sequence[float],
    *,
    block_length: int = 5,
    resamples: int = 1000,
    seed: int = 0,
    confidence: float = 0.95,
) -> dict:
    """Moving-block bootstrap of the mean paired daily return difference (a - b)."""
    policy = {
        "method": "moving_block_bootstrap_v1",
        "blockLength": block_length,
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
    }
    n = min(len(returns_a), len(returns_b))
    if len(returns_a) != len(returns_b):
        return {"available": False, "reason": "unpaired_series", "blockPolicy": policy}
    if n < 2 * block_length:
        return {"available": False, "reason": "too_few_observations", "blockPolicy": policy}
    diff = [a - b for a, b in zip(returns_a, returns_b)]
    rng = random.Random(seed)
    starts = n - block_length + 1
    blocks_needed = math.ceil(n / block_length)
    means = []
    for _ in range(resamples):
        sample: list[float] = []
        for _ in range(blocks_needed):
            start = rng.randrange(starts)
            sample.extend(diff[start : start + block_length])
        means.append(statistics.fmean(sample[:n]))
    means.sort()
    lo = means[int((1 - confidence) / 2 * resamples)]
    hi = means[min(resamples - 1, int((1 + confidence) / 2 * resamples))]
    return {
        "available": True,
        "meanDifference": statistics.fmean(diff),
        "ciLow": lo,
        "ciHigh": hi,
        "observations": n,
        "blockPolicy": policy,
        "note": "uncertainty estimate; not a significance claim for short samples",
    }


def _d(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


RiskFreeInput = Union[Sequence[float], Mapping[date, float], None]


@dataclass(frozen=True)
class SeriesActivity:
    """Activity of one portfolio over the measured interval (outside the valuation series)."""

    fill_considerations_usd: Sequence[Decimal] = ()
    cash_flows: Sequence[tuple[str, Decimal]] = ()  # (kind, amount_usd)
    orders_created: int = 0
    order_status_counts: Mapping[str, int] = field(default_factory=dict)  # status changes
    policy_evaluations: int = 0
    policy_rejections: int = 0
    decision_outcome_counts: Mapping[str, int] = field(default_factory=dict)


def activity_from_proposals(
    proposals: Sequence[TransitionProposal], outcomes: Sequence[StrategyResult] = ()
) -> SeriesActivity:
    status_counts: dict[str, int] = {}
    for change in (c for p in proposals for c in p.order_status_changes):
        status_counts[change.status.value] = status_counts.get(change.status.value, 0) + 1
    outcome_counts: dict[str, int] = {}
    for outcome in outcomes:
        outcome_counts[outcome.outcome.value] = outcome_counts.get(outcome.outcome.value, 0) + 1
    evaluations = [p.policy_evaluation for p in proposals if p.policy_evaluation is not None]
    return SeriesActivity(
        fill_considerations_usd=tuple(f.consideration_usd for p in proposals for f in p.fills),
        cash_flows=tuple((cf.kind, cf.amount_usd) for p in proposals for cf in p.cash_flows),
        orders_created=sum(len(p.orders_created) for p in proposals),
        order_status_counts=status_counts,
        policy_evaluations=len(evaluations),
        policy_rejections=sum(1 for e in evaluations if not e.passed),
        decision_outcome_counts=outcome_counts,
    )


def _aligned_risk_free(
    risk_free: RiskFreeInput, dated: Sequence[tuple[date, float]]
) -> Optional[Sequence[float]]:
    """Positional series pass through; a session-keyed series is aligned to the returns
    (a missing session leaves it shorter, so Sharpe reports it misaligned)."""
    if risk_free is None or not isinstance(risk_free, Mapping):
        return risk_free
    return [risk_free[day] for day, _ in dated if day in risk_free]


def series_metrics(
    points: Sequence[EquityPoint],
    activity: SeriesActivity = SeriesActivity(),
    *,
    risk_free: RiskFreeInput = None,
    min_sharpe_obs: int = 60,
    annualize_min_obs: int = TRADING_DAYS,
) -> dict:
    """Metrics for one portfolio from its valuation series and activity (both paths)."""
    complete = [p for p in points if p.complete and p.equity is not None]
    dated = dated_returns(points)
    returns = [value for _, value in dated]
    status_counts = activity.order_status_counts
    outcome_counts = dict(activity.decision_outcome_counts)
    result: dict = {
        "metricsVersion": METRICS_VERSION,
        "valuationCount": len(points),
        "completeValuationCount": len(complete),
        "incompleteValuationCount": len(points) - len(complete),
        "observationCount": len(returns),
    }
    if len(complete) < 1:
        result["unavailableReason"] = "no_complete_valuation"
        return result
    start, end = complete[0], complete[-1]
    external = end.capital - start.capital
    total_pnl = end.equity - start.equity - external
    costs = (end.fees - start.fees) + (end.spread - start.spread)
    net_return = total_pnl / start.equity if start.equity else None
    gross_return = (total_pnl + costs) / start.equity if start.equity else None
    elapsed_days = (end.session - start.session).days
    annualized = None
    annualized_reason = None
    if len(returns) >= annualize_min_obs and net_return is not None:
        years = len(returns) / TRADING_DAYS
        annualized = (1 + float(net_return)) ** (1 / years) - 1
    else:
        annualized_reason = f"fewer_than_{annualize_min_obs}_returns"
    equity_values = [float(p.equity) for p in complete]
    nav_avg = sum((p.equity for p in complete), ZERO) / len(complete)
    traded = sum(activity.fill_considerations_usd, ZERO)
    dv01s = [p.dv01 for p in complete if p.dv01 is not None]
    durations = [p.duration for p in complete if p.duration is not None]
    carry = (
        (end.income - start.income)
        + (end.accrued_value - start.accrued_value)
        - (end.accrued_purchased - start.accrued_purchased)
    )
    price = (
        (end.realized - start.realized)
        + (end.unrealized - start.unrealized)
        - (
            (end.accrued_value - start.accrued_value)
            - (end.accrued_purchased - start.accrued_purchased)
        )
        + (end.spread - start.spread)
    )
    cost_component = -costs
    residual = total_pnl - carry - price - cost_component
    result.update(
        {
            "startValuationAt": start.valuation_at.isoformat(),
            "endValuationAt": end.valuation_at.isoformat(),
            "elapsedCalendarDays": elapsed_days,
            "startEquityUsd": _d(start.equity),
            "endEquityUsd": _d(end.equity),
            "externalFlowsUsd": _d(external),
            "totalPnlUsd": _d(total_pnl),
            "netReturn": float(net_return) if net_return is not None else None,
            "grossReturn": float(gross_return) if gross_return is not None else None,
            "annualizedReturn": annualized,
            "annualizedUnavailableReason": annualized_reason,
            "dailyVolatility": statistics.stdev(returns) if len(returns) >= 2 else None,
            "drawdown": max_drawdown(equity_values),
            "sharpe": sharpe_ratio(returns, _aligned_risk_free(risk_free, dated), min_sharpe_obs),
            "turnoverRatio": float(traded / nav_avg) if nav_avg else None,
            "tradedConsiderationUsd": _d(traded),
            "spreadCostUsd": _d(end.spread - start.spread),
            "feesUsd": _d(end.fees - start.fees),
            "decisionCount": sum(outcome_counts.values()),
            "decisionOutcomes": outcome_counts,
            "proposalCount": outcome_counts.get(DecisionOutcome.COMPLETED_PROPOSAL.value, 0),
            "policyEvaluations": activity.policy_evaluations,
            "policyRejections": activity.policy_rejections,
            "ordersCreated": activity.orders_created,
            "fillCount": len(activity.fill_considerations_usd),
            "expiryCount": status_counts.get(OrderStatus.EXPIRED.value, 0),
            "rejectedOrderCount": status_counts.get(OrderStatus.REJECTED.value, 0),
            "cancelledOrderCount": status_counts.get(OrderStatus.CANCELLED.value, 0),
            "averageCashProportion": float(
                sum((p.cash / p.equity for p in complete if p.equity), ZERO) / len(complete)
            ),
            "averageDv01Usd": float(sum(dv01s, ZERO) / len(dv01s)) if dv01s else None,
            "maxDv01Usd": float(max(dv01s)) if dv01s else None,
            "averageEffectiveDurationYears": (
                float(sum(durations, ZERO) / len(durations)) if durations else None
            ),
            "endEffectiveDurationYears": float(durations[-1]) if durations else None,
            "couponIncomeUsd": _d(
                sum((amount for kind, amount in activity.cash_flows if kind == "COUPON"), ZERO)
            ),
            "redemptionsUsd": _d(
                sum((amount for kind, amount in activity.cash_flows if kind == "REDEMPTION"), ZERO)
            ),
            "realizedPnlUsd": _d(end.realized - start.realized),
            "unrealizedPnlUsd": _d(end.unrealized - start.unrealized),
            "interestIncomeUsd": _d(end.income - start.income),
            "attribution": {
                "carryUsd": _d(carry),
                "priceUsd": _d(price),
                "costsUsd": _d(cost_component),
                "residualUsd": _d(residual),
                "totalUsd": _d(total_pnl),
                "reconciles": carry + price + cost_component + residual == total_pnl,
            },
            "dailyReturns": returns,
        }
    )
    return result


def portfolio_metrics(
    proposals: Sequence[TransitionProposal],
    outcomes: Sequence[StrategyResult] = (),
    *,
    risk_free: RiskFreeInput = None,
    min_sharpe_obs: int = 60,
    annualize_min_obs: int = TRADING_DAYS,
) -> dict:
    """Metrics for one portfolio from its committed transitions and decision outcomes."""
    return series_metrics(
        equity_series(proposals),
        activity_from_proposals(proposals, outcomes),
        risk_free=risk_free,
        min_sharpe_obs=min_sharpe_obs,
        annualize_min_obs=annualize_min_obs,
    )


def strategy_outcomes(outcomes: Iterable[StrategyResult], strategy_id: str) -> list[StrategyResult]:
    return [o for o in outcomes if o.strategy_id == strategy_id]
