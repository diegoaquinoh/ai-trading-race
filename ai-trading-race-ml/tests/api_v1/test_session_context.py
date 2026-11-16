"""``DecisionRequest.sessionContext``: application mode uses the run's previous session.

Offline replay gives strategies ``previous_session = sessions[index - 1]`` (``None``
on the run's first session). The platform sends the same value explicitly; when it is
absent the engine falls back to the market calendar. The field is omitted from the
wire form when absent, so existing model hashes do not change. ``requestHash`` binds
the exact body sent (``content_hash`` of the parsed JSON body).
"""

from __future__ import annotations

from datetime import date

import research_engine.experiments.strategy as strategy_module
from research_engine.contracts.common import content_hash
from research_engine.contracts.decisions import DecisionRequest

from .conftest import SESSION
from .helpers import decision_body, post_json
from .test_decisions import PATH, funded


def _capture(monkeypatch) -> list:
    seen: list = []
    original = strategy_module.StrategyContext

    def recording(*args, **kwargs):
        seen.append(kwargs.get("previous_session"))
        return original(*args, **kwargs)

    monkeypatch.setattr(strategy_module, "StrategyContext", recording)
    return seen


def test_absent_context_keeps_the_request_hash(client):
    state = funded(client, "cash")
    body = decision_body(client, state, SESSION, "cash")
    parsed = DecisionRequest.model_validate(body)
    assert "sessionContext" not in parsed.to_wire()
    assert parsed.compute_hash() == content_hash(DecisionRequest.model_validate(body).to_wire())
    response = post_json(client, PATH, body)
    assert response.status_code == 200, response.text
    assert response.json()["requestHash"] == content_hash(body)
    assert response.json()["inputHashes"]["decisionRequest"] == parsed.compute_hash()


def test_explicit_context_is_authoritative(client, monkeypatch):
    state = funded(client, "cash")
    seen = _capture(monkeypatch)

    first = decision_body(
        client, state, SESSION, "cash", decisionId="dec:ctx:first", sessionContext={}
    )
    response = post_json(client, PATH, first)
    assert response.status_code == 200, response.text
    explicit = DecisionRequest.model_validate(first)
    assert explicit.to_wire()["sessionContext"] == {"previousSessionDate": None}
    assert response.json()["requestHash"] == content_hash(first)
    assert response.json()["inputHashes"]["decisionRequest"] == explicit.compute_hash()

    later = decision_body(
        client,
        state,
        SESSION,
        "cash",
        decisionId="dec:ctx:later",
        sessionContext={"previousSessionDate": "2024-02-27"},
    )
    assert post_json(client, PATH, later).status_code == 200

    fallback = decision_body(client, state, SESSION, "cash", decisionId="dec:ctx:calendar")
    assert post_json(client, PATH, fallback).status_code == 200

    assert seen[0] is None  # first session of the run, as offline replay
    assert seen[1] == date(2024, 2, 27)
    assert seen[2] == date(2024, 2, 29)  # market calendar fallback


def test_context_must_precede_the_session(client):
    state = funded(client, "cash")
    body = decision_body(
        client,
        state,
        SESSION,
        "cash",
        decisionId="dec:ctx:bad",
        sessionContext={"previousSessionDate": SESSION.isoformat()},
    )
    response = post_json(client, PATH, body)
    assert response.status_code == 422
