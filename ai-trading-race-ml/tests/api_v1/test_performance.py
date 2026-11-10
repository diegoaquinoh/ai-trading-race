"""``POST /internal/v1/analytics/performance`` and ``/instruments/payment-calendar``.

The application path must reproduce the offline report's metrics exactly: the
request is built from the values the platform stores (valuation columns and
marks, the committed state's balances, fills, cash flows, order statuses and
decision outcomes) and both paths call ``series_metrics``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from research_engine.contracts.common import money
from research_engine.contracts.portfolio import (
    CommandType,
    PendingSettlement,
    Position,
    Side,
)
from research_engine.experiments.metrics import portfolio_metrics
from research_engine.experiments.runner import ReplayConfig, ReplayRunner, StrategySpec
from tests.simulation.fakes import make_ports

from app.v1.performance import compute_performance
from app.v1.schemas import PerformanceRequest

from .conftest import initial_state

STRATEGIES = ("cash", "quant_duration", "static_ladder")


def _replay(tmp_path, end=date(2024, 3, 8)):
    pricing, market = make_ports()
    config = ReplayConfig(
        experiment_id="exp-perf",
        run_id="run-perf",
        start_date=date(2024, 1, 2),
        end_date=end,
        strategies=[StrategySpec(strategy_id=s) for s in STRATEGIES],
    )
    runner = ReplayRunner(config, pricing, market, tmp_path / "run", b"k")
    runner.run()
    return runner


def _stored_portfolio(runner, sid: str) -> dict:
    """What the .NET side stores and sends for one portfolio (no derived numbers)."""
    pid = runner._pid(sid)
    proposals = runner.store.committed(pid)
    valuations = []
    for p in proposals:
        if p.command_type != CommandType.VALUE_PORTFOLIO or p.valuation is None:
            continue
        v, state = p.valuation, p.new_state
        valuations.append(
            {
                "valuationId": v.valuation_id,
                "valuationAt": v.to_wire()["valuationAt"],
                "stateVersion": p.new_version,
                "complete": v.complete,
                "cashUsd": str(v.cash_usd),
                "equityUsd": None if v.equity_usd is None else str(v.equity_usd),
                "bondValueUsd": None if v.bond_value_usd is None else str(v.bond_value_usd),
                "parallelDv01Usd": (
                    None if v.parallel_dv01_usd is None else str(v.parallel_dv01_usd)
                ),
                "effectiveDurationYears": (
                    None if v.effective_duration_years is None else str(v.effective_duration_years)
                ),
                "marks": [
                    {
                        "economicFace": m["economicFace"],
                        "accruedPer100": m.get("accruedPer100"),
                    }
                    for m in v.to_wire()["marks"]
                ],
                "ledger": {
                    "externalCapitalUsd": str(state.external_capital_usd),
                    "interestIncomeUsd": str(state.interest_income_usd),
                    "realizedGainLossUsd": str(state.realized_gain_loss_usd),
                    "bookedUnrealizedUsd": str(state.booked_unrealized_usd),
                    "transactionFeesUsd": str(state.transaction_fees_usd),
                    "spreadCostUsd": str(state.spread_cost_usd),
                    "lotAccruedPurchasedUsd": [
                        str(lot.accrued_purchased_usd)
                        for pos in state.positions
                        for lot in pos.lots
                    ],
                },
            }
        )
    final_orders: dict[str, str] = {}
    for p in proposals:
        for order in p.orders_created:
            final_orders[order.order_id] = order.status.value
        for change in p.order_status_changes:
            final_orders[change.order_id] = change.status.value
    status_counts: dict[str, int] = {}
    for status in final_orders.values():
        if status != "ACCEPTED":
            status_counts[status] = status_counts.get(status, 0) + 1
    evaluations = [p.policy_evaluation for p in proposals if p.policy_evaluation is not None]
    outcomes: dict[str, int] = {}
    for o in runner.outcomes.values():
        if o.strategy_id == sid:
            outcomes[o.outcome.value] = outcomes.get(o.outcome.value, 0) + 1
    return {
        "portfolioId": pid,
        "strategyId": sid,
        "valuations": valuations,
        "fills": [
            {
                "fillId": f.fill_id,
                "executedAt": f.to_wire()["executedAt"],
                "considerationUsd": str(f.consideration_usd),
                "feesUsd": str(f.fees_usd),
                "spreadCostUsd": str(f.spread_cost_usd),
            }
            for p in proposals
            for f in p.fills
        ],
        "cashFlows": [
            {
                "cashFlowId": cf.cash_flow_id,
                "kind": cf.kind,
                "paymentDate": cf.payment_date.isoformat(),
                "amountUsd": str(cf.amount_usd),
            }
            for p in proposals
            for cf in p.cash_flows
        ],
        "ordersCreated": len(final_orders),
        "orderStatusCounts": status_counts,
        "policyEvaluations": len(evaluations),
        "policyRejections": sum(1 for e in evaluations if not e.passed),
        "decisionOutcomes": outcomes,
    }


def _request(runner, **extra) -> dict:
    body = {
        "schemaVersion": "1.0",
        "requestId": "perf-1",
        "runId": "run-perf",
        "portfolios": [_stored_portfolio(runner, sid) for sid in STRATEGIES],
        "pairs": [
            {"portfolioId": runner._pid(sid), "versusPortfolioId": runner._pid("cash")}
            for sid in STRATEGIES
            if sid != "cash"
        ],
    }
    body.update(extra)
    return body


def test_application_metrics_equal_offline_metrics(tmp_path):
    runner = _replay(tmp_path)
    result = compute_performance(PerformanceRequest.model_validate(_request(runner)))
    assert result["metricsVersion"] == "metrics-v1"
    for entry, sid in zip(result["portfolios"], STRATEGIES):
        pid = runner._pid(sid)
        outcomes = [o for o in runner.outcomes.values() if o.strategy_id == sid]
        offline = portfolio_metrics(runner.store.committed(pid), outcomes)
        offline.pop("dailyReturns")
        assert entry["portfolioId"] == pid
        assert entry["metrics"] == offline, sid
    ladder = result["portfolios"][2]["metrics"]
    assert ladder["attribution"]["reconciles"]
    assert Decimal(ladder["couponIncomeUsd"]) > 0
    assert ladder["sharpe"]["unavailableReason"] == "missing_risk_free_series"
    assert ladder["annualizedUnavailableReason"] == "fewer_than_252_returns"
    assert [p["versusPortfolioId"] for p in result["pairedComparisons"]] == [
        runner._pid("cash")
    ] * 2
    assert all(
        p["blockPolicy"]["method"] == "moving_block_bootstrap_v1"
        for p in result["pairedComparisons"]
    )


def test_risk_free_series_is_aligned_by_session(tmp_path):
    runner = _replay(tmp_path)
    body = _request(runner)
    sessions = runner.sessions
    body["riskFree"] = {
        "seriesId": "rf-zero",
        "observations": [{"sessionDate": d.isoformat(), "dailyReturn": "0"} for d in sessions],
    }
    body["minSharpeObservations"] = 10
    result = compute_performance(PerformanceRequest.model_validate(body))
    ladder = result["portfolios"][2]["metrics"]
    assert ladder["sharpe"]["value"] is not None
    assert result["conventions"]["riskFreeSeriesId"] == "rf-zero"
    cash = result["portfolios"][0]["metrics"]
    assert cash["sharpe"]["unavailableReason"] == "zero_variance"
    body["riskFree"]["observations"] = body["riskFree"]["observations"][:-3]
    partial = compute_performance(PerformanceRequest.model_validate(body))
    assert partial["portfolios"][2]["metrics"]["sharpe"]["unavailableReason"] in (
        "risk_free_series_misaligned",
        "fewer_than_10_returns",
    )


def test_performance_endpoint_and_validation(client, tmp_path):
    runner = _replay(tmp_path, end=date(2024, 1, 19))
    body = _request(runner)
    response = client.post("/internal/v1/analytics/performance", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["portfolios"]) == 3 and data["inputHash"].startswith("sha256:")
    assert "dailyReturns" not in data["portfolios"][0]["metrics"]

    shuffled = _request(runner, requestId="perf-2")
    shuffled["portfolios"][2]["valuations"].reverse()
    bad = client.post("/internal/v1/analytics/performance", json=shuffled)
    assert bad.status_code == 422 and bad.json()["code"] == "valuations_not_chronological"

    floats = _request(runner, requestId="perf-3")
    floats["portfolios"][0]["valuations"][0]["cashUsd"] = 1.5
    assert client.post("/internal/v1/analytics/performance", json=floats).status_code == 422

    unknown = _request(runner, requestId="perf-4")
    unknown["portfolios"][0]["decisionOutcomes"] = {"won_the_lottery": 1}
    assert client.post("/internal/v1/analytics/performance", json=unknown).status_code == 422

    reused = _request(runner)  # same requestId as the first call, different payload
    reused["includeDailyReturns"] = True
    assert client.post("/internal/v1/analytics/performance", json=reused).status_code == 409


def test_payment_calendar_projects_entitled_payments(client, engine):
    asof = date(2024, 3, 1)
    securities = sorted(
        (
            t
            for t in engine.market.universe_contract.securities
            if t.dates.original_issue_date <= asof < t.dates.maturity_date
        ),
        key=lambda t: t.security_id,
    )
    held = securities[0].security_id
    pending = securities[1].security_id
    base = initial_state()
    flows_held = [
        cf for cf in engine.pricing.cash_flows(held) if cf.payment_date > date(2024, 3, 1)
    ]
    first_payment = flows_held[0].payment_date
    state = base.model_copy(
        update={
            "cash_usd": Decimal("100000"),
            "positions": [
                Position(
                    security_id=held, economic_face=Decimal("50000"), settled_face=Decimal("50000")
                ),
                Position(
                    security_id=pending, economic_face=Decimal("20000"), settled_face=Decimal("0")
                ),
            ],
            "pending_settlements": [
                PendingSettlement(
                    settlement_id="stl-1",
                    fill_id="fill-1",
                    security_id=pending,
                    side=Side.BUY,
                    face=Decimal("20000"),
                    settlement_date=date(2024, 3, 5),
                    cash_usd=Decimal("20100.00"),
                ),
                PendingSettlement(
                    settlement_id="stl-2",
                    fill_id="fill-2",
                    security_id=held,
                    side=Side.SELL,
                    face=Decimal("10000"),
                    settlement_date=first_payment,  # settles on the payment date: still entitled
                    cash_usd=Decimal("10050.00"),
                ),
            ],
        }
    )
    body = {
        "schemaVersion": "1.0",
        "requestId": "cal-1",
        "portfolioState": state.to_wire(),
        "portfolioStateHash": state.compute_hash(),
        "after": "2024-03-01",
        "horizonDays": 800,
    }
    response = client.post("/internal/v1/instruments/payment-calendar", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["basis"] == "projected_from_current_state_v1"
    assert data["through"] == (date(2024, 3, 1) + timedelta(days=800)).isoformat()
    items = data["items"]
    assert items == sorted(items, key=lambda i: (i["paymentDate"], i["securityId"], i["kind"]))
    held_items = [i for i in items if i["securityId"] == held and i["kind"] == "COUPON"]
    assert held_items[0]["paymentDate"] == first_payment.isoformat()
    assert held_items[0]["projectedEntitledFaceUsd"] == "50000"
    later = [i for i in held_items if i["paymentDate"] > first_payment.isoformat()]
    assert all(i["projectedEntitledFaceUsd"] == "40000" for i in later)
    coupon = Decimal(held_items[0]["amountPer100"])
    assert Decimal(held_items[0]["projectedAmountUsd"]) == money(Decimal(50000) * coupon / 100)
    pending_items = [i for i in items if i["securityId"] == pending]
    assert pending_items and all(i["projectedEntitledFaceUsd"] == "20000" for i in pending_items)
    total = sum(Decimal(i["projectedAmountUsd"]) for i in items)
    assert Decimal(data["totals"]["totalUsd"]) == total

    tampered = dict(body, portfolioStateHash="sha256:" + "0" * 64)
    assert (
        client.post("/internal/v1/instruments/payment-calendar", json=tampered).status_code == 409
    )
