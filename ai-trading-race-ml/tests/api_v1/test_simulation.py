"""Transition proposals over HTTP and the common bootstrap allocation."""

from __future__ import annotations

import json
from decimal import Decimal

from research_engine.contracts.portfolio import RiskPolicy, TransitionProposal

from .conftest import NEXT_SESSION, SESSION, initial_state
from .helpers import (
    advance_times,
    capital_flow_body,
    fund,
    market_ref,
    post_json,
    transition_body,
    verify_signed,
)

PATH = "/internal/v1/simulation/transitions"


def test_transition_proposal_verifies_and_is_replayable(client):
    body = capital_flow_body(initial_state("cash"), SESSION)
    first = post_json(client, PATH, body)
    assert first.status_code == 200, first.text
    proposal = first.json()
    verify_signed(proposal, "proposalHash")
    parsed = TransitionProposal.model_validate(proposal)
    assert parsed.new_version == 1 and parsed.expected_version == 0
    assert Decimal(proposal["newState"]["cashUsd"]) == Decimal("1000000")
    assert proposal["newStateHash"] == parsed.new_state.compute_hash()
    # nulls are included on the wire (TransitionProposal.to_wire()).
    assert "policyEvaluation" in proposal and proposal["policyEvaluation"] is None
    second = post_json(client, PATH, body)
    assert second.status_code == 200
    assert second.content == first.content


def test_transition_with_market_snapshot_values_portfolio(client):
    state = post_json(client, PATH, capital_flow_body(initial_state("cash"), SESSION)).json()[
        "newState"
    ]
    body = transition_body(
        state,
        "value_portfolio",
        advance_times(SESSION)["valuation"],
        market_snapshot=market_ref(client, SESSION),
    )
    response = post_json(client, PATH, body)
    assert response.status_code == 200, response.text
    proposal = response.json()
    verify_signed(proposal, "proposalHash")
    assert proposal["valuation"]["complete"] is True
    assert proposal["inputHashes"]["marketSnapshot"] == body["marketSnapshot"]["contentHash"]


def test_tampered_state_hash_is_409(client):
    body = capital_flow_body(initial_state("cash"), SESSION)
    body["portfolioStateHash"] = "sha256:" + "0" * 64
    response = post_json(client, PATH, body)
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "state_hash_mismatch"


def test_market_snapshot_mismatch_is_409(client):
    state = initial_state("cash")
    ref = market_ref(client, SESSION)
    ref["contentHash"] = "sha256:" + "1" * 64
    body = transition_body(
        state, "process_events", advance_times(SESSION)["decision"], market_snapshot=ref
    )
    response = post_json(client, PATH, body)
    assert response.status_code == 409
    assert response.json()["code"] == "market_snapshot_mismatch"


def test_clock_moving_backward_is_409(client):
    state = initial_state("cash")
    body = transition_body(state, "process_events", "2024-02-01T00:00:00Z")
    response = post_json(client, PATH, body)
    assert response.status_code == 409
    assert response.json()["code"] == "clock_moved_backward"


def test_unknown_schema_major_is_rejected(client):
    body = capital_flow_body(initial_state("cash"), SESSION)
    body["schemaVersion"] = "2.0"
    response = post_json(client, PATH, body)
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_schema_version"
    body = capital_flow_body(initial_state("cash"), SESSION)
    body["portfolioState"]["schemaVersion"] = "3.1"
    assert post_json(client, PATH, body).status_code == 422


def test_float_in_decimal_field_is_rejected(client):
    body = capital_flow_body(initial_state("cash"), SESSION)
    body["capitalAmountUsd"] = 1000000.5
    response = post_json(client, PATH, body)
    assert response.status_code == 422
    assert "float" in json.dumps(response.json()).lower()


def test_nan_is_rejected(client):
    raw = json.dumps(capital_flow_body(initial_state("cash"), SESSION)).replace(
        '"capitalAmountUsd": "1000000"', '"capitalAmountUsd": NaN'
    )
    response = client.post(PATH, content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["code"] == "non_finite_number"


def test_malformed_and_unknown_fields(client):
    response = client.post(PATH, content="{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    body = capital_flow_body(initial_state("cash"), SESSION)
    body["llmChosenPolicy"] = {"maxSingleSecurityRatio": "1"}
    response = post_json(client, PATH, body)
    assert response.status_code == 422


def test_bootstrap_allocation_is_common_and_complete(client):
    request = {
        "schemaVersion": "1.0",
        "sessionDate": SESSION.isoformat(),
        "universeVersion": "synthetic_universe_v1.0",
        "riskPolicy": RiskPolicy().to_wire(),
    }
    first = post_json(client, "/internal/v1/simulation/bootstrap-allocation", request)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["version"] == "bootstrap-30-34-30-6-v2"
    total = sum(Decimal(t["weight"]) for t in body["targets"])
    assert total == Decimal("1")
    assert body["targets"][-1]["securityId"] == "CASH-USD"
    assert set(body["buckets"]) == {"short", "intermediate", "longer"}
    again = post_json(client, "/internal/v1/simulation/bootstrap-allocation", request)
    assert again.content == first.content


def test_bootstrap_allocation_errors(client):
    request = {
        "schemaVersion": "1.0",
        "sessionDate": "2024-03-02",
        "universeVersion": "synthetic_universe_v1.0",
        "riskPolicy": RiskPolicy().to_wire(),
    }
    assert (
        post_json(client, "/internal/v1/simulation/bootstrap-allocation", request).status_code
        == 422
    )
    request["sessionDate"] = NEXT_SESSION.isoformat()
    request["universeVersion"] = "another-universe"
    response = post_json(client, "/internal/v1/simulation/bootstrap-allocation", request)
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Deterministic engine rejections are 422, never 500 (spec 14.6)
# --------------------------------------------------------------------------- #


def test_withdrawal_above_available_cash_is_422_naming_the_portfolio(client):
    from research_engine.simulation.clock import decision_at

    state = fund(client, initial_state("cash"), SESSION)
    body = transition_body(
        state, "capital_flow", decision_at(SESSION), capitalAmountUsd="-1000000.01"
    )
    response = post_json(client, PATH, body)
    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem["code"] == "withdrawal_exceeds_available_cash"
    assert problem["portfolioId"] == state["portfolioId"]
    assert state["portfolioId"] in problem["detail"]


def test_ledger_invariant_violation_is_422_not_500(client):
    """A payable larger than settled cash cannot settle: a deterministic rejection."""
    from datetime import time

    from research_engine.contracts.portfolio import (
        Lot,
        PendingSettlement,
        PortfolioState,
        Position,
        Side,
    )
    from research_engine.simulation.clock import decision_at, ny_instant

    sid = "SYN-USD-NOTE-003"
    lot = Lot(
        lot_id="lot-api-invariant",
        security_id=sid,
        face=Decimal("500000"),
        trade_date=SESSION,
        settlement_date=NEXT_SESSION,
        clean_price_per_100=Decimal("100"),
        principal_cost_usd=Decimal("500000.00"),
        accrued_purchased_usd=Decimal("0"),
    )
    state = PortfolioState(
        portfolio_id="pf-api-invariant",
        strategy_id="cash",
        run_id="run-api-v1",
        version=3,
        as_of=ny_instant(SESSION, time(19, 0)),
        cash_usd=Decimal("100000.00"),
        positions=[
            Position(
                security_id=sid,
                economic_face=Decimal("500000"),
                settled_face=Decimal("0"),
                lots=[lot],
            )
        ],
        pending_settlements=[
            PendingSettlement(
                settlement_id="stl:api-invariant",
                fill_id="fill:api-invariant",
                security_id=sid,
                side=Side.BUY,
                face=Decimal("500000"),
                settlement_date=NEXT_SESSION,
                cash_usd=Decimal("500000.00"),
            )
        ],
        external_capital_usd=Decimal("100000.00"),
    )
    body = transition_body(state, "process_events", decision_at(NEXT_SESSION))
    response = post_json(client, PATH, body)
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["code"] == "ledger_invariant_violation"
    assert problem["portfolioId"] == "pf-api-invariant"


# --------------------------------------------------------------------------- #
# Request binding: requestHash = content_hash(the JSON body exactly as received)
# --------------------------------------------------------------------------- #


def test_request_hash_binds_the_exact_body_received(client):
    from research_engine.contracts.common import content_hash
    from research_engine.contracts.portfolio import TransitionRequest

    body = capital_flow_body(initial_state("cash"), SESSION, amount="250000")
    raw = json.dumps(body)
    headers = {"Content-Type": "application/json"}
    first = client.post(PATH, content=raw, headers=headers)
    # Same JSON, different bytes (whitespace/key order): same canonical body.
    reordered = json.dumps(dict(reversed(list(body.items()))), indent=2)
    second = client.post(PATH, content=reordered, headers=headers)
    assert first.status_code == second.status_code == 200, first.text
    expected = content_hash(json.loads(raw))
    assert first.json()["requestHash"] == second.json()["requestHash"] == expected
    verify_signed(first.json(), "proposalHash")
    # The parsed model fills defaults (riskPolicy, executionModel, nulls): not the binding.
    assert expected != TransitionRequest.model_validate(body).compute_hash()

    changed = dict(body, commandId=body["commandId"] + ":other")
    third = post_json(client, PATH, changed)
    assert third.status_code == 200, third.text
    assert third.json()["requestHash"] == content_hash(changed) != expected

    # An explicit default is a different body: different binding, same economics.
    explicit = dict(body, riskPolicy=RiskPolicy().to_wire())
    fourth = post_json(client, PATH, explicit)
    assert fourth.status_code == 200, fourth.text
    assert fourth.json()["requestHash"] == content_hash(explicit) != expected
    assert fourth.json()["newStateHash"] == first.json()["newStateHash"]
    verify_signed(fourth.json(), "proposalHash")
