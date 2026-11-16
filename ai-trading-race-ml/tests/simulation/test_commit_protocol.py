"""Commit protocol: idempotency, stale versions, integrity, malformed proposals (spec 9.5, 16.6)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from research_engine.contracts.common import content_hash, sign_hash, verify_signature
from research_engine.contracts.portfolio import (
    AccountCode,
    CommandType,
    DecisionAction,
    EventType,
    Journal,
    JournalLine,
)
from research_engine.simulation.clock import decision_at, valuation_at
from research_engine.simulation.engine import (
    ClockMovedBackward,
    InvalidTransitionRequest,
    PortfolioBlocked,
    StateHashMismatch,
    sign_proposal,
)
from research_engine.simulation.store import (
    IdempotencyConflict,
    InvalidProposal,
    OfflineStateStore,
    PortfolioBlockedError,
    ReconciliationFailed,
    StaleStateVersion,
)

from .harness import KEY, Harness, weights

D2 = date(2024, 1, 2)


def _bootstrapped():
    h = Harness()
    h.capital()
    h.decide(D2, weights(n3="0.30", n5="0.30", cash="0.40"), action=DecisionAction.BOOTSTRAP)
    return h


def test_proposal_is_hashed_signed_and_deterministic():
    h = Harness()
    request = h.request(CommandType.CAPITAL_FLOW, valuation_at(D2), capital_amount_usd=Decimal("5"))
    first = h.propose(request)
    second = h.propose(request)
    assert first.to_wire() == second.to_wire()
    assert first.proposal_hash == content_hash(first.hash_payload())
    assert verify_signature(first.proposal_hash, first.signature, KEY)
    assert set(first.input_hashes) == {
        "portfolioState",
        "marketSnapshot",
        "riskPolicy",
        "executionModel",
    }
    assert first.request_hash == request.compute_hash()
    assert first.new_state_hash == first.new_state.compute_hash()
    assert first.new_version == first.expected_version + 1


def test_repeated_command_has_no_second_financial_effect():
    h = Harness()
    request = h.request(
        CommandType.CAPITAL_FLOW,
        valuation_at(D2),
        command_id="cap-1",
        capital_amount_usd=Decimal("1000000"),
    )
    proposal = h.propose(request)
    first = h.store.commit(proposal, request)
    retry = h.store.commit(h.propose(request), request)
    assert retry.duplicate and retry.proposal.proposal_hash == first.proposal.proposal_hash
    assert h.state.cash_usd == Decimal("1000000.00") and h.state.version == 1
    # Same logical command id with a different payload is a conflict (HTTP 409).
    other = h.request(
        CommandType.CAPITAL_FLOW,
        valuation_at(D2),
        command_id="cap-1",
        capital_amount_usd=Decimal("7"),
    )
    with pytest.raises(IdempotencyConflict):
        h.store.commit(h.propose(other), other)
    assert h.state.cash_usd == Decimal("1000000.00")


def test_competing_state_versions_reject_the_stale_transition():
    h = _bootstrapped()
    base = h.state
    a = h.request(CommandType.PROCESS_EVENTS, decision_at(date(2024, 1, 3)), state=base)
    b = h.request(CommandType.VALUE_PORTFOLIO, valuation_at(D2), state=base, market_snapshot=None)
    pa, pb = h.propose(a), h.propose(b)
    h.store.commit(pa, a)
    with pytest.raises(StaleStateVersion):
        h.store.commit(pb, b)
    assert h.state.version == pa.new_version


def test_no_op_keeps_version_and_state():
    h = _bootstrapped()
    proposal = h.process(D2)  # nothing due before the eligible session
    assert proposal.no_op and proposal.new_version == proposal.expected_version
    assert proposal.new_state_hash == proposal.input_hashes["portfolioState"]


def test_tampered_proposals_cannot_write_state():
    h = _bootstrapped()
    request = h.request(CommandType.PROCESS_EVENTS, decision_at(date(2024, 1, 3)))
    proposal = h.propose(request)
    richer = proposal.new_state.model_copy(update={"cash_usd": Decimal("9999999")})
    tampered = proposal.model_copy(update={"new_state": richer})
    with pytest.raises(InvalidProposal):
        h.store.commit(tampered)
    rehashed = proposal.model_copy(
        update={"new_state": richer, "new_state_hash": richer.compute_hash()}
    )
    rehashed = rehashed.model_copy(update={"proposal_hash": content_hash(rehashed.hash_payload())})
    with pytest.raises(InvalidProposal):  # signature no longer matches
        h.store.commit(rehashed)
    forged = sign_proposal(proposal, b"some-other-key")
    with pytest.raises(InvalidProposal):
        h.store.commit(forged)
    assert h.state.version == proposal.expected_version


def test_unbalanced_journal_is_unrepresentable():
    with pytest.raises(ValidationError):
        Journal(
            journal_id="jnl:x",
            event_id="evt:x",
            event_type=EventType.CAPITAL_FLOW,
            effective_at="2024-01-02T00:00:00Z",
            template="capital_flow_v1",
            lines=[
                JournalLine(line_id="l1", account=AccountCode.CASH, debit_usd=Decimal("10.00")),
                JournalLine(line_id="l2", account=AccountCode.CAPITAL, credit_usd=Decimal("9.00")),
            ],
        )


def test_reconciliation_failure_blocks_portfolio():
    h = _bootstrapped()
    request = h.request(CommandType.PROCESS_EVENTS, decision_at(date(2024, 1, 3)))
    proposal = h.propose(request)
    broken = proposal.reconciliation.model_copy(update={"ok": False, "messages": ["injected"]})
    bad = sign_proposal(proposal.model_copy(update={"reconciliation": broken}), KEY)
    with pytest.raises(ReconciliationFailed):
        h.store.commit(bad)
    assert h.store.blocked_reason(h.pid).startswith("reconciliation_failed")
    with pytest.raises(PortfolioBlockedError):
        h.store.commit(proposal, request)


def test_invalid_requests_are_rejected_before_computation():
    h = _bootstrapped()
    state = h.state
    request = h.request(CommandType.PROCESS_EVENTS, decision_at(date(2024, 1, 3)))
    with pytest.raises(StateHashMismatch):
        h.propose(request.model_copy(update={"portfolio_state_hash": "sha256:" + "0" * 64}))
    with pytest.raises(ClockMovedBackward):
        h.propose(h.request(CommandType.PROCESS_EVENTS, valuation_at(date(2023, 12, 29))))
    with pytest.raises(InvalidTransitionRequest):
        h.propose(h.request(CommandType.CAPITAL_FLOW, decision_at(date(2024, 1, 3))))
    blocked = state.model_copy(update={"blocked_reason": "reconciliation_failed"})
    with pytest.raises(PortfolioBlocked):
        h.propose(
            h.request(CommandType.PROCESS_EVENTS, decision_at(date(2024, 1, 3)), state=blocked)
        )
    with pytest.raises(InvalidTransitionRequest):
        h.propose(request.model_copy(update={"schema_version": "2.0"}))


def test_jsonl_store_replays_to_identical_state(tmp_path):
    path = tmp_path / "commits.jsonl"
    h = Harness()
    h.store = OfflineStateStore(KEY, path)
    h.store.register(Harness().state)
    h.capital()
    h.decide(D2, weights(n3="0.30", cash="0.70"), action=DecisionAction.BOOTSTRAP)
    h.process(date(2024, 1, 3))
    reloaded = OfflineStateStore(KEY, path)
    assert reloaded.state(h.pid).compute_hash() == h.state.compute_hash()
    assert len(reloaded.committed()) == len(h.store.committed())
    assert sign_hash("sha256:" + "a" * 64, KEY).startswith("hmac-sha256:")
