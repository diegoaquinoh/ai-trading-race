"""Research notes: cited, validated, no order authority."""

from __future__ import annotations

import pytest

from research_engine.agents.output import MalformedOutput, parse_output
from research_engine.agents.providers import ReferenceHeuristicProvider
from research_engine.agents.research_note import research_note
from research_engine.contracts.common import content_hash, verify_signature
from research_engine.contracts.decisions import RetrievalMode

from .conftest import RESULT_KEY
from .fakes import FakeEvidencePort, ScriptedProvider, hawkish_docs, utc

AS_OF = utc(2023, 6, 13, 23)


def test_research_note_is_cited_and_has_no_order_authority(ports, contexts):
    pricing, market = ports
    evidence = FakeEvidencePort(hawkish_docs(AS_OF))
    state = contexts[max(contexts)].portfolio_state
    result = research_note(
        "What did the FOMC say about inflation?",
        AS_OF,
        evidence=evidence,
        pricing=pricing,
        market=market,
        portfolio_state=state,
        signing_key=RESULT_KEY,
    )
    assert result.status == "completed" and result.order_authority is False
    assert "proposal" not in result.to_wire()
    note = result.research_note
    assert note.claims and all(c.validation_status == "valid" for c in note.claims)
    assert note.citations and note.retrieval_run_ids
    assert evidence.calls[0]["question"] == "What did the FOMC say about inflation?"
    assert evidence.calls[0]["mode"] == RetrievalMode.GRAPH_RAG
    assert "propose_targets" not in {t.tool_name for t in result.tool_traces}
    assert result.portfolio_snapshot_id and result.versions.provider == "reference"
    assert verify_signature(content_hash(result.hash_payload()), result.signature, RESULT_KEY)


def test_research_note_cannot_propose(ports):
    pricing, market = ports
    reference = ReferenceHeuristicProvider()

    def script(request, n):
        if n == 1:
            return {
                "action": "call_tools",
                "calls": [{"tool": "propose_targets", "arguments": {"action": "HOLD"}}],
            }
        if n == 2:  # a note carrying a decision/proposal violates the note contract
            return {
                "action": "final",
                "status": "supported",
                "decision": "propose",
                "explanation": "x",
                "proposal": {"action": "HOLD"},
            }
        return reference.generate(request)

    result = research_note(
        "Policy outlook?",
        AS_OF,
        evidence=FakeEvidencePort(hawkish_docs(AS_OF)),
        provider=ScriptedProvider(script),
        pricing=pricing,
        market=market,
        mode=RetrievalMode.HYBRID_RAG,
    )
    denied = [t for t in result.tool_traces if t.tool_name == "propose_targets"]
    assert denied and denied[0].status == "denied_policy"
    assert [a.status for a in result.attempts][:2] == ["ok", "malformed"]
    assert result.status == "completed"
    with pytest.raises(MalformedOutput):
        parse_output(
            '{"action":"final","status":"supported","explanation":"","decision":"hold"}',
            ["final"],
            research_note=True,
        )


def test_research_note_without_evidence_reports_insufficiency():
    result = research_note("Anything?", AS_OF, evidence=FakeEvidencePort([]))
    assert result.status == "insufficient_evidence" and not result.attempts
