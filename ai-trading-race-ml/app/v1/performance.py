"""Application-path evaluation metrics (``POST /internal/v1/analytics/performance``).

The platform (.NET) stores valuations, accounting balances, fills, cash flows,
orders and decision outcomes; it sends them here and never computes evaluation
metrics itself. This module only maps the stored values onto the
``research_engine.experiments.metrics`` inputs (:class:`EquityPoint`,
:class:`SeriesActivity`) and calls :func:`series_metrics` - the function the
offline report uses - so both paths share one implementation.
"""

from __future__ import annotations

from typing import Optional

from research_engine.contracts.common import content_hash
from research_engine.contracts.decisions import DecisionOutcome
from research_engine.contracts.portfolio import OrderStatus
from research_engine.experiments.metrics import (
    METRICS_VERSION,
    TRADING_DAYS,
    EquityPoint,
    SeriesActivity,
    accrued_purchased_usd,
    accrued_value_usd,
    paired_block_bootstrap,
    series_metrics,
)
from research_engine.simulation.clock import ny_date

from .errors import unprocessable
from .schemas import PerformancePortfolio, PerformanceRequest, PerformanceValuation

ORDER_STATUSES = {s.value for s in OrderStatus}
OUTCOMES = {o.value for o in DecisionOutcome}
SHARPE_ANNUALIZATION = f"sqrt({TRADING_DAYS})"


def equity_point(valuation: PerformanceValuation) -> EquityPoint:
    ledger = valuation.ledger
    return EquityPoint(
        valuation_at=valuation.valuation_at,
        session=ny_date(valuation.valuation_at),
        complete=valuation.complete,
        equity=valuation.equity_usd,
        cash=valuation.cash_usd,
        dv01=valuation.parallel_dv01_usd,
        duration=valuation.effective_duration_years,
        accrued_value=accrued_value_usd(
            (m.economic_face, m.accrued_per_100) for m in valuation.marks
        ),
        accrued_purchased=accrued_purchased_usd(ledger.lot_accrued_purchased_usd),
        capital=ledger.external_capital_usd,
        income=ledger.interest_income_usd,
        realized=ledger.realized_gain_loss_usd,
        unrealized=ledger.booked_unrealized_usd,
        fees=ledger.transaction_fees_usd,
        spread=ledger.spread_cost_usd,
    )


def _check_portfolio(portfolio: PerformancePortfolio) -> None:
    pid = portfolio.portfolio_id
    previous = None
    for valuation in portfolio.valuations:
        key = (valuation.valuation_at, valuation.state_version)
        if previous is not None and key <= previous:
            raise unprocessable(
                "valuations_not_chronological",
                f"valuations of {pid} must be in strictly increasing (valuationAt, stateVersion) "
                f"order; {valuation.valuation_id} breaks it",
            )
        previous = key
        if valuation.complete and valuation.equity_usd is None:
            raise unprocessable(
                "invalid_valuation",
                f"complete valuation {valuation.valuation_id} of {pid} has no equityUsd",
            )
    unknown_status = sorted(set(portfolio.order_status_counts) - ORDER_STATUSES)
    if unknown_status:
        raise unprocessable(
            "invalid_request", f"unknown order statuses for {pid}: {unknown_status}"
        )
    unknown_outcomes = sorted(set(portfolio.decision_outcomes) - OUTCOMES)
    if unknown_outcomes:
        raise unprocessable(
            "invalid_request", f"unknown decision outcomes for {pid}: {unknown_outcomes}"
        )
    negative = [
        k
        for k, v in {**portfolio.order_status_counts, **portfolio.decision_outcomes}.items()
        if v < 0
    ]
    if negative:
        raise unprocessable("invalid_request", f"negative counts for {pid}: {sorted(negative)}")
    if portfolio.policy_rejections > portfolio.policy_evaluations:
        raise unprocessable(
            "invalid_request", f"policyRejections exceeds policyEvaluations for {pid}"
        )


def activity(portfolio: PerformancePortfolio) -> SeriesActivity:
    return SeriesActivity(
        fill_considerations_usd=tuple(f.consideration_usd for f in portfolio.fills),
        cash_flows=tuple((cf.kind, cf.amount_usd) for cf in portfolio.cash_flows),
        orders_created=portfolio.orders_created,
        order_status_counts=dict(portfolio.order_status_counts),
        policy_evaluations=portfolio.policy_evaluations,
        policy_rejections=portfolio.policy_rejections,
        decision_outcome_counts=dict(portfolio.decision_outcomes),
    )


def compute_performance(req: PerformanceRequest, engine_version: Optional[str] = None) -> dict:
    ids = [p.portfolio_id for p in req.portfolios]
    duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
    if duplicates:
        raise unprocessable("invalid_request", f"duplicate portfolio ids: {duplicates}")
    for portfolio in req.portfolios:
        _check_portfolio(portfolio)
    known = set(ids)
    for pair in req.pairs:
        missing = {pair.portfolio_id, pair.versus_portfolio_id} - known
        if missing:
            raise unprocessable(
                "invalid_request", f"pair references unknown portfolios {sorted(missing)}"
            )
    risk_free = None
    if req.risk_free is not None:
        risk_free = {o.session_date: float(o.daily_return) for o in req.risk_free.observations}

    entries = []
    returns: dict[str, list[float]] = {}
    for portfolio in req.portfolios:
        metrics = series_metrics(
            [equity_point(v) for v in portfolio.valuations],
            activity(portfolio),
            risk_free=risk_free,
            min_sharpe_obs=req.min_sharpe_observations,
            annualize_min_obs=req.annualize_min_observations,
        )
        daily = metrics.pop("dailyReturns", [])
        returns[portfolio.portfolio_id] = daily
        if req.include_daily_returns:
            metrics["dailyReturns"] = daily
        entries.append(
            {
                "portfolioId": portfolio.portfolio_id,
                "strategyId": portfolio.strategy_id,
                "repetition": portfolio.repetition,
                "metrics": metrics,
            }
        )
    policy = req.bootstrap
    pairs = [
        {
            "portfolioId": pair.portfolio_id,
            "versusPortfolioId": pair.versus_portfolio_id,
            **paired_block_bootstrap(
                returns[pair.portfolio_id],
                returns[pair.versus_portfolio_id],
                block_length=policy.block_length,
                resamples=policy.resamples,
                seed=policy.seed,
            ),
        }
        for pair in req.pairs
    ]
    return {
        "schemaVersion": req.schema_version,
        "requestId": req.request_id,
        "runId": req.run_id,
        "inputHash": content_hash(req.to_wire()),
        "metricsVersion": METRICS_VERSION,
        "engineVersion": engine_version,
        "conventions": {
            "returns": "daily (E_t - E_{t-1} - F_t) / E_{t-1} over complete valuations",
            "incompleteValuations": "counted and excluded, never interpolated",
            "annualizeMinObservations": req.annualize_min_observations,
            "sharpeMinObservations": req.min_sharpe_observations,
            "sharpeAnnualization": SHARPE_ANNUALIZATION,
            "riskFreeSeriesId": req.risk_free.series_id if req.risk_free else None,
            "sharpeNote": "reporting threshold, not a statistical significance claim",
        },
        "portfolios": entries,
        "pairedComparisons": pairs,
    }


__all__ = ["compute_performance", "equity_point", "activity"]
