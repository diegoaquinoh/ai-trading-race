"""Agent strategies through the decision endpoint (reference provider, loaded index)."""

from __future__ import annotations

import pytest

from .conftest import NEXT_SESSION, SESSION, make_engine, make_settings
from .helpers import (
    advance_times,
    decision_body,
    market_ref,
    post_json,
    transition_body,
    verify_signed,
)
from .test_decisions import PATH, TRANSITIONS, funded

agents = pytest.importorskip("research_engine.agents")


def bootstrapped(client, strategy_id: str) -> dict:
    state = funded(client, strategy_id)
    result = post_json(client, PATH, decision_body(client, state, SESSION, strategy_id)).json()
    assert result["outcome"] == "completed_proposal", result
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
    filled = post_json(
        client,
        TRANSITIONS,
        transition_body(
            proposal["newState"], "process_events", advance_times(NEXT_SESSION)["decision"]
        ),
    ).json()
    return filled["newState"]


@pytest.mark.parametrize("strategy_id", ["llm_market", "llm_rag"])
def test_agent_decision_is_signed_and_replayable(client, engine, strategy_id):
    state = bootstrapped(client, strategy_id)
    body = decision_body(client, state, NEXT_SESSION, strategy_id)
    first = post_json(client, PATH, body)
    assert first.status_code == 200, first.text
    result = first.json()
    verify_signed(result, "resultHash")
    assert result["versions"]["provider"] == "reference"
    assert result["strategyKind"] == "single_agent"
    if strategy_id == "llm_rag":
        assert result["versions"]["indexBuildId"] in engine.evidence.indexes
        assert result["evidenceBundleIds"]
    second = post_json(client, PATH, body)
    assert second.content == first.content


def test_evidence_strategy_without_index_is_503(ports, client_for):
    pricing, market = ports
    bare = make_engine(pricing, market)
    client = client_for(bare)
    state = funded(client, "llm_rag")
    response = post_json(client, PATH, decision_body(client, state, SESSION, "llm_rag"))
    assert response.status_code == 503
    assert response.json()["code"] == "evidence_index_unavailable"
    bare.shutdown()


def test_provider_comes_from_configuration(ports, evidence, client_for):
    pricing, market = ports
    recorded = make_engine(pricing, market, make_settings(strategy_provider="recorded"))
    recorded.evidence.attach(*evidence)
    client = client_for(recorded)
    state = funded(client, "llm_market")
    body = decision_body(client, state, SESSION, "llm_market", responseMode="fresh_inference")
    response = post_json(client, PATH, body)
    assert response.status_code == 503
    assert response.json()["code"] == "provider_mode_unavailable"
    body = decision_body(client, state, SESSION, "llm_market")
    response = post_json(client, PATH, body)
    assert response.status_code == 503
    assert response.json()["code"] == "model_provider_unavailable"
    recorded.shutdown()
