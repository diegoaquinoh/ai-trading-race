"""Strategy decisions: signing, hash binding, policy authority, concurrency, evidence."""

from __future__ import annotations

from decimal import Decimal

from research_engine.contracts.decisions import StrategyResult
from research_engine.contracts.portfolio import RiskPolicy

from .conftest import NEXT_SESSION, SESSION, initial_state, make_engine, make_settings
from .helpers import advance_times, decision_body, fund, post_json, transition_body, verify_signed

PATH = "/internal/v1/strategies/decisions"
TRANSITIONS = "/internal/v1/simulation/transitions"


def funded(client, strategy_id: str) -> dict:
    state = fund(client, initial_state(strategy_id), SESSION)
    body = transition_body(state, "process_events", advance_times(SESSION)["decision"])
    response = post_json(client, TRANSITIONS, body)
    assert response.status_code == 200, response.text
    return response.json()["newState"]


def test_bootstrap_decision_is_signed_and_replayable(client):
    state = funded(client, "static_ladder")
    body = decision_body(client, state, SESSION, "static_ladder")
    first = post_json(client, PATH, body)
    assert first.status_code == 200, first.text
    result = first.json()
    verify_signed(result, "resultHash")
    parsed = StrategyResult.model_validate(result)
    assert parsed.outcome.value == "completed_proposal"
    assert parsed.proposal.action.value == "BOOTSTRAP"
    assert sum(t.weight for t in parsed.proposal.target_weights) == Decimal("1")
    assert result["inputHashes"]["portfolioState"] == body["portfolioSnapshot"]["contentHash"]
    assert result["inputHashes"]["riskPolicy"] == RiskPolicy().compute_hash()
    second = post_json(client, PATH, body)
    assert second.content == first.content


def test_hold_is_a_normal_result(client):
    state = funded(client, "cash")
    response = post_json(client, PATH, decision_body(client, state, SESSION, "cash"))
    assert response.status_code == 200
    assert response.json()["outcome"] == "completed_hold"
    verify_signed(response.json(), "resultHash")


def test_tampered_portfolio_hash_is_409(client):
    state = funded(client, "static_ladder")
    body = decision_body(client, state, SESSION, "static_ladder")
    body["portfolioSnapshot"]["contentHash"] = "sha256:" + "a" * 64
    response = post_json(client, PATH, body)
    assert response.status_code == 409
    assert response.json()["code"] == "state_hash_mismatch"


def test_tampered_state_content_is_409(client):
    state = funded(client, "static_ladder")
    body = decision_body(client, state, SESSION, "static_ladder")
    body["portfolioState"] = {**body["portfolioState"], "cashUsd": "2000000.00"}
    response = post_json(client, PATH, body)
    assert response.status_code == 409


def test_stale_version_and_market_mismatch_are_409(client):
    state = funded(client, "static_ladder")
    body = decision_body(client, state, SESSION, "static_ladder")
    body["portfolioSnapshot"]["version"] = state["version"] + 1
    assert post_json(client, PATH, body).json()["code"] == "stale_portfolio_version"
    body = decision_body(client, state, SESSION, "static_ladder")
    body["marketSnapshot"]["curveSnapshotId"] = "curve-0000000000000000"
    response = post_json(client, PATH, body)
    assert response.status_code == 409
    assert response.json()["code"] == "market_snapshot_mismatch"


def test_request_cannot_choose_the_risk_policy(client):
    state = funded(client, "static_ladder")
    body = decision_body(client, state, SESSION, "static_ladder")
    body["riskPolicy"] = RiskPolicy(policy_id="aggressive-v9").to_wire()
    response = post_json(client, PATH, body)
    assert response.status_code == 422
    assert response.json()["code"] == "risk_policy_mismatch"
    body = decision_body(client, state, SESSION, "static_ladder")
    body["riskPolicy"] = RiskPolicy(max_single_security_ratio=Decimal("0.9")).to_wire()
    assert post_json(client, PATH, body).status_code == 409
    body = decision_body(client, state, SESSION, "static_ladder", riskPolicyId="unknown-policy")
    assert post_json(client, PATH, body).json()["code"] == "unknown_risk_policy"
    body = decision_body(client, state, SESSION, "static_ladder", provider="openai")
    assert post_json(client, PATH, body).status_code == 422


def test_application_policy_object_with_matching_id_is_used(client):
    state = funded(client, "static_ladder")
    policy = RiskPolicy(policy_id="custom-ladder-v1", max_single_security_ratio=Decimal("0.10"))
    body = decision_body(client, state, SESSION, "static_ladder", riskPolicyId=policy.policy_id)
    body["riskPolicy"] = policy.to_wire()
    response = post_json(client, PATH, body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["inputHashes"]["riskPolicy"] == policy.compute_hash()
    weights = [Decimal(t["weight"]) for t in result["proposal"]["targetWeights"][:-1]]
    assert max(weights) <= Decimal("0.10")


def test_unknown_strategy_is_404(client):
    state = funded(client, "static_ladder")
    body = decision_body(client, state, SESSION, "static_ladder", strategyId="no_such_strategy")
    body["portfolioState"] = state
    response = post_json(client, PATH, body)
    assert response.status_code in (404, 422)


def test_concurrency_limit_returns_429(ports, evidence, client_for):
    pricing, market = ports
    limited = make_engine(pricing, market, make_settings(max_concurrent_decisions=1))
    client = client_for(limited)
    state = funded(client, "static_ladder")
    body = decision_body(client, state, SESSION, "static_ladder", decisionId="dec:busy")
    assert limited.try_acquire_decision()
    try:
        response = post_json(client, PATH, body)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "7"
        assert response.json()["code"] == "decision_concurrency_limit"
    finally:
        limited.release_decision()
    assert post_json(client, PATH, body).status_code == 200
    limited.shutdown()


def test_evidence_reference_without_loaded_index_is_503(ports, client_for):
    pricing, market = ports
    no_evidence = make_engine(pricing, market)
    client = client_for(no_evidence)
    state = funded(client, "cash")
    body = decision_body(client, state, SESSION, "cash", evidenceSnapshotId="evs-abc")
    response = post_json(client, PATH, body)
    assert response.status_code == 503
    no_evidence.shutdown()


def test_evidence_strategy_uses_loaded_index(client, engine):
    state = funded(client, "static_ladder")
    snapshot = next(iter(engine.evidence.indexes.values())).build.member_version_ids
    from app.v1.engine import evidence_snapshot_id

    body = decision_body(
        client, state, SESSION, "static_ladder", evidenceSnapshotId=evidence_snapshot_id(snapshot)
    )
    assert post_json(client, PATH, body).status_code == 200
    body = decision_body(client, state, SESSION, "static_ladder", evidenceSnapshotId="evs-unknown")
    assert post_json(client, PATH, body).status_code == 404


def test_full_cycle_bootstrap_fill_then_risk(client):
    """decision -> submit transition -> next-session fill -> analytics/risk."""
    state = funded(client, "static_ladder")
    result = post_json(client, PATH, decision_body(client, state, SESSION, "static_ladder")).json()
    from .helpers import market_ref

    submit = transition_body(
        state,
        "submit_decision",
        advance_times(SESSION)["decision"],
        market_snapshot=market_ref(client, SESSION),
        decisionId=result["decisionId"],
        action=result["proposal"]["action"],
        targetWeights=result["proposal"]["targetWeights"],
    )
    proposal = post_json(client, TRANSITIONS, submit).json()
    assert proposal["policyEvaluation"]["passed"] is True, proposal["policyEvaluation"]
    assert proposal["ordersCreated"]
    filled = post_json(
        client,
        TRANSITIONS,
        transition_body(
            proposal["newState"], "process_events", advance_times(NEXT_SESSION)["decision"]
        ),
    ).json()
    assert filled["fills"]
    new_state = filled["newState"]
    curve_id = market_ref(client, NEXT_SESSION)["curveSnapshotId"]
    risk = post_json(
        client,
        "/internal/v1/analytics/risk",
        {
            "schemaVersion": "1.0",
            "requestId": "risk-full-cycle",
            "portfolioState": new_state,
            "portfolioStateHash": filled["newStateHash"],
            "curveSnapshotId": curve_id,
            "valuationDate": NEXT_SESSION.isoformat(),
            "scenarioIds": ["parallel_up_100"],
        },
    )
    assert risk.status_code == 200, risk.text
    report = risk.json()["report"]
    assert Decimal(report["totalParallelDv01Usd"]) > 0
    assert [s["scenarioId"] for s in report["scenarios"]] == ["parallel_up_100"]
    tampered = post_json(
        client,
        "/internal/v1/analytics/risk",
        {
            "schemaVersion": "1.0",
            "requestId": "risk-full-cycle-tampered",
            "portfolioState": new_state,
            "portfolioStateHash": "sha256:" + "b" * 64,
            "curveSnapshotId": curve_id,
            "valuationDate": NEXT_SESSION.isoformat(),
            "scenarioIds": [],
        },
    )
    assert tampered.status_code == 409


def test_decision_request_hash_binds_the_exact_body_received(client):
    from research_engine.contracts.common import content_hash
    from research_engine.contracts.decisions import DecisionRequest

    state = funded(client, "cash")
    body = decision_body(client, state, SESSION, "cash", decisionId="dec:binding:1")
    first = post_json(client, PATH, body)
    second = post_json(client, PATH, body)
    assert first.status_code == second.status_code == 200, first.text
    expected = content_hash(body)
    assert first.json()["requestHash"] == second.json()["requestHash"] == expected
    verify_signed(first.json(), "resultHash")
    parsed = DecisionRequest.model_validate(body)
    assert first.json()["inputHashes"]["decisionRequest"] == parsed.compute_hash()

    # The optional policy object is part of the body, hence of the binding.
    with_policy = dict(body, riskPolicy=RiskPolicy().to_wire())
    third = post_json(client, PATH, with_policy)
    assert third.status_code == 200, third.text
    assert third.json()["requestHash"] == content_hash(with_policy) != expected
    verify_signed(third.json(), "resultHash")

    changed = dict(body, cycleId="cycle-binding-other")
    fourth = post_json(client, PATH, changed)
    assert fourth.status_code == 200, fourth.text
    assert fourth.json()["requestHash"] == content_hash(changed) != expected
