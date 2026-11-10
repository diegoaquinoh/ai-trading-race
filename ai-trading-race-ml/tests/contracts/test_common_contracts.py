"""Contract primitive tests: decimals, instants, canonical JSON, transition invariants."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from research_engine.contracts.common import (
    canonical_json,
    check_schema_version,
    content_hash,
    money,
    sign_hash,
    verify_signature,
)
from research_engine.contracts.portfolio import (
    AccountCode,
    EventType,
    Journal,
    JournalLine,
    PortfolioState,
    TargetWeight,
)
from research_engine.contracts.decisions import Proposal

VECTORS = Path(__file__).resolve().parents[3] / "contracts" / "test-vectors" / "canonical-json.json"


def _state(**overrides):
    base = dict(
        portfolio_id="pf-1",
        strategy_id="cash",
        run_id="run-1",
        version=0,
        as_of="2024-01-02T00:00:00Z",
        cash_usd="1000000.00",
    )
    base.update(overrides)
    return PortfolioState(**base)


def test_decimal_fields_reject_floats_and_nan():
    with pytest.raises(ValidationError):
        _state(cash_usd=1000.5)
    with pytest.raises(ValidationError):
        _state(cash_usd="NaN")
    with pytest.raises(ValidationError):
        _state(cash_usd="Infinity")


def test_wire_format_is_camel_case_with_decimal_strings():
    wire = _state().to_wire()
    assert wire["cashUsd"] == "1000000.00"
    assert wire["asOf"] == "2024-01-02T00:00:00Z"
    assert "cash_usd" not in wire


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        _state(as_of=datetime(2024, 1, 2))


def test_negative_cash_rejected():
    with pytest.raises(ValidationError):
        _state(cash_usd="-0.01")


def test_hash_is_stable_across_construction_paths():
    a = _state()
    b = PortfolioState.model_validate(json.loads(json.dumps(a.to_wire())))
    assert a.compute_hash() == b.compute_hash() == content_hash(a.to_wire())


def test_canonical_json_rejects_floats():
    with pytest.raises(TypeError):
        canonical_json({"x": 1.5})


def test_canonical_vectors_match_current_implementation():
    payload = json.loads(VECTORS.read_text())
    key = payload["signingKeyUtf8"].encode()
    for vector in payload["vectors"]:
        assert canonical_json(vector["input"]) == vector["canonical"]
        assert content_hash(vector["input"]) == vector["sha256"]
        assert sign_hash(vector["sha256"], key) == vector["signature"]
        assert verify_signature(vector["sha256"], vector["signature"], key)


def test_unbalanced_journal_rejected():
    with pytest.raises(ValidationError):
        Journal(
            journal_id="j1",
            event_id="e1",
            event_type=EventType.CAPITAL_FLOW,
            effective_at="2024-01-02T00:00:00Z",
            template="capital_flow_v1",
            lines=[
                JournalLine(line_id="l1", account=AccountCode.CASH, debit_usd="100.00"),
                JournalLine(line_id="l2", account=AccountCode.CAPITAL, credit_usd="99.99"),
            ],
        )


def test_journal_line_requires_cents():
    with pytest.raises(ValidationError):
        JournalLine(line_id="l1", account=AccountCode.CASH, debit_usd="1.001")


def test_proposal_weights_must_sum_to_one():
    with pytest.raises(ValidationError):
        Proposal(
            action="REBALANCE",
            target_weights=[
                TargetWeight(security_id="SYN-USD-NOTE-001", weight="0.5"),
                TargetWeight(security_id="CASH-USD", weight="0.4"),
            ],
        )
    ok = Proposal(
        action="REBALANCE",
        target_weights=[
            TargetWeight(security_id="SYN-USD-NOTE-001", weight="0.6"),
            TargetWeight(security_id="CASH-USD", weight="0.4"),
        ],
    )
    assert ok.action.value == "REBALANCE"


def test_money_rounds_half_up_to_cents():
    assert money(Decimal("1.005")) == Decimal("1.01")
    assert money("2.344") == Decimal("2.34")


def test_schema_major_version_check():
    check_schema_version("1.3")
    with pytest.raises(ValueError):
        check_schema_version("2.0")


def test_date_fields_serialize_as_dates():
    state = _state(cash_flows_processed_through=date(2024, 1, 2))
    assert state.to_wire()["cashFlowsProcessedThrough"] == "2024-01-02"
    assert datetime.now(timezone.utc)
