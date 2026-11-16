"""Request builders shared by the API v1 tests."""

from __future__ import annotations

import json
from datetime import date, time
from typing import Any, Optional

from research_engine.contracts.common import content_hash, sign_hash
from research_engine.contracts.portfolio import PortfolioState
from research_engine.simulation.clock import CAPITAL_TIME, decision_at, ny_instant, valuation_at

from .conftest import RUN_ID, SIGNING_KEY

UNIVERSE_VERSION = "synthetic_universe_v1.0"


def verify_signed(body: dict, hash_field: str) -> None:
    """Recompute the content hash from the JSON body and check the HMAC."""
    payload = {k: v for k, v in body.items() if k not in (hash_field, "signature")}
    digest = content_hash(payload)
    assert body[hash_field] == digest
    assert body["signature"] == sign_hash(digest, SIGNING_KEY.encode())


def session_row(client, day: date) -> dict:
    response = client.get(
        "/internal/v1/market/sessions",
        params={"start": day.isoformat(), "end": day.isoformat()},
    )
    assert response.status_code == 200, response.text
    rows = response.json()["sessions"]
    assert rows and rows[0]["sessionDate"] == day.isoformat()
    return rows[0]


def market_ref(client, day: date) -> dict:
    row = session_row(client, day)
    assert not row["gap"], row
    return {
        "marketSnapshotId": row["marketSnapshotId"],
        "contentHash": row["marketSnapshotHash"],
        "curveSnapshotId": row["curveSnapshotId"],
        "sessionDate": day.isoformat(),
        "dataMode": "synthetic_curve",
    }


def transition_body(
    state: PortfolioState | dict,
    command_type: str,
    advance_to,
    *,
    command_id: Optional[str] = None,
    market_snapshot: Optional[dict] = None,
    **extra: Any,
) -> dict:
    state_wire = state.to_wire() if isinstance(state, PortfolioState) else state
    state_hash = PortfolioState.model_validate(state_wire).compute_hash()
    body = {
        "schemaVersion": "1.0",
        "commandId": command_id
        or f"cmd:{state_wire['portfolioId']}:{command_type}:v{state_wire['version']}",
        "commandType": command_type,
        "portfolioState": state_wire,
        "portfolioStateHash": state_hash,
        "advanceTo": advance_to if isinstance(advance_to, str) else _z(advance_to),
        "instrumentUniverseVersion": UNIVERSE_VERSION,
    }
    if market_snapshot is not None:
        body["marketSnapshot"] = market_snapshot
    body.update(extra)
    return body


def _z(instant) -> str:
    from research_engine.contracts.common import utc_to_str

    return utc_to_str(instant)


def capital_flow_body(state: PortfolioState, day: date, amount: str = "1000000") -> dict:
    return transition_body(
        state,
        "capital_flow",
        ny_instant(day, CAPITAL_TIME),
        capitalAmountUsd=amount,
    )


def post_json(client, path: str, body: Any):
    return client.post(path, content=json.dumps(body), headers={"Content-Type": "application/json"})


def fund(client, state: PortfolioState, day: date) -> dict:
    response = post_json(
        client, "/internal/v1/simulation/transitions", capital_flow_body(state, day)
    )
    assert response.status_code == 200, response.text
    return response.json()["newState"]


def decision_body(
    client,
    state_wire: dict,
    day: date,
    strategy_id: str,
    *,
    decision_id: Optional[str] = None,
    **extra: Any,
) -> dict:
    ref = market_ref(client, day)
    state_hash = PortfolioState.model_validate(state_wire).compute_hash()
    body = {
        "schemaVersion": "1.0",
        "experimentId": "exp-api-v1",
        "runId": RUN_ID,
        "cycleId": f"cycle-{day.isoformat()}",
        "decisionId": decision_id or f"dec:{RUN_ID}:{strategy_id}:{day.isoformat()}:r0",
        "strategyId": strategy_id,
        "repetition": 0,
        "decisionAsOf": _z(decision_at(day)),
        "marketSessionDate": day.isoformat(),
        "availabilityPolicy": "reconstructed_publication_plus_lag_v1",
        "dataMode": "synthetic_curve",
        "portfolioSnapshot": {
            "id": f"pfs:{state_wire['portfolioId']}:v{state_wire['version']}",
            "contentHash": state_hash,
            "version": state_wire["version"],
        },
        "marketSnapshot": {
            "id": ref["marketSnapshotId"],
            "contentHash": ref["contentHash"],
            "curveSnapshotId": ref["curveSnapshotId"],
        },
        "instrumentUniverseVersion": UNIVERSE_VERSION,
        "strategyConfigId": f"{strategy_id}-config-v1",
        "riskPolicyId": "treasury-long-only-v1",
        "responseMode": "recorded_replay",
        "portfolioState": state_wire,
    }
    body.update(extra)
    return body


def advance_times(day: date) -> dict:
    return {
        "midnight": ny_instant(day, time(0, 0)),
        "decision": decision_at(day),
        "valuation": valuation_at(day),
    }
