"""Typed tools: allowlists, frozen-snapshot binding, signed calculations, untrusted text."""

from __future__ import annotations

import json

import pytest

from research_engine.agents.budget import BudgetExceeded, BudgetLedger
from research_engine.agents.prompts import document_block, parse_blocks, parse_documents
from research_engine.agents.tool_schemas import EVIDENCE_TOOLS, TOOL_ARGS
from research_engine.agents.tools import DecisionToolbox, ToolBinding
from research_engine.contracts.decisions import DecisionBudget, RetrievalMode

from .fakes import INJECTION_TEXT, FakeDoc, FakeEvidencePort, hawkish_docs, utc


def _toolbox(ctx, mode=RetrievalMode.HYBRID_RAG, evidence=None, **budget):
    tools = frozenset(TOOL_ARGS) - (EVIDENCE_TOOLS if mode == RetrievalMode.NONE else frozenset())
    ledger = BudgetLedger(DecisionBudget(**budget))
    return DecisionToolbox(
        ToolBinding.from_context(ctx),
        ledger,
        strategy_tools=tools,
        evidence=evidence,
        retrieval_mode=mode,
    )


def test_market_strategy_has_no_evidence_tools_and_roles_are_allowlisted(ctx_for):
    ctx = ctx_for("llm_market")
    tb = _toolbox(
        ctx, RetrievalMode.NONE, FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of))
    )
    assert "retrieve_evidence" not in tb.allowed_tools("single")
    denied = tb.call("single", "retrieve_evidence", {"question": "what did the Fed say?"})
    assert denied.status == "denied_policy" and denied.trace.status == "denied_policy"
    assert tb.call("single", "execute_trade", {"all": True}).status == "denied_policy"
    assert tb.call("critical_reviewer", "propose_targets", {"action": "HOLD"}).status == (
        "denied_policy"
    )
    assert tb.call(
        "macro_researcher", "run_scenario", {"scenario_id": "parallel_up_25"}
    ).status == ("denied_policy")
    assert tb.ledger.usage().tool_calls == 0  # denied calls never execute


def test_tools_are_bound_to_the_frozen_snapshot(ctx_for):
    ctx = ctx_for("llm_rag")
    tb = _toolbox(ctx)
    # Snapshot/curve/portfolio references are not arguments: extra fields are rejected.
    sneaky = tb.call("single", "get_portfolio_risk", {"scenario_ids": [], "portfolio_id": "other"})
    assert sneaky.status == "error" and "invalid_arguments" in sneaky.payload["error"]
    risk = tb.call("single", "get_portfolio_risk", {"scenario_ids": ["parallel_up_25"]})
    assert risk.status == "ok"
    snapshot = ctx.snapshot
    assert risk.payload["navUsd"] == format(snapshot.nav.quantize(risk_q()), "f")
    assert risk.payload["portfolioSnapshotId"] == ctx.request.portfolio_snapshot.id
    store = tb.calc_store
    assert store.verify(risk.payload["calculationId"])
    assert risk.payload["calculationId"] in tb.issued_calc_ids
    assert risk.payload["scenarios"][0]["scenarioId"] == "parallel_up_25"
    terms = tb.call("single", "get_instrument_terms", {"security_ids": ["NOT-IN-UNIVERSE"]})
    assert terms.status == "denied_policy"


def risk_q():
    from decimal import Decimal

    return Decimal("0.01")


def test_scenarios_are_allowlisted_and_registered(ctx_for):
    tb = _toolbox(ctx_for("llm_rag"))
    rejected = tb.call("single", "run_scenario", {"scenario_id": "custom_crash_500"})
    assert rejected.status == "denied_policy" and "scenario_not_approved" in rejected.trace.error
    ok = tb.call("single", "run_scenario", {"scenario_id": "steepener_v1"})
    assert ok.status == "ok" and tb.calc_store.verify(ok.payload["calculationId"])
    valuation = tb.call("single", "get_valuation", {"security_ids": ["SYN-USD-NOTE-005"]})
    row = valuation.payload["valuations"][0]
    assert row["priceCalculationId"] in tb.issued_calc_ids


def test_market_features_are_numerical_only(ctx_for):
    ctx = ctx_for("llm_market")
    tb = _toolbox(ctx, RetrievalMode.NONE)
    out = tb.call("single", "get_market_features", {})
    assert out.status == "ok"
    payload = out.payload
    assert set(payload) == {
        "calculationId",
        "curveSnapshotId",
        "sessionDate",
        "parYields",
        "zeroRates",
        "changesBp",
        "laggedSessions",
        "slope2s10sBp",
        "macro",
        "units",
    }
    text = json.dumps(payload)
    for phrase in ("Committee", "inflation", "FOMC", "statement"):
        assert phrase not in text
    assert payload["changesBp"]["21s"]["2Y"]  # 21-session change available at the cutoff
    for day in payload["laggedSessions"].values():
        assert day < ctx.session_date.isoformat()
    calc = tb.calc_store.get(payload["calculationId"])
    assert calc.as_of <= ctx.request.decision_as_of and tb.calc_store.verify(calc.calculation_id)


def test_tool_and_evidence_calls_consume_the_ledger(ctx_for):
    ctx = ctx_for("llm_rag")
    evidence = FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of))
    tb = _toolbox(ctx, evidence=evidence, max_tool_calls=3, max_evidence_calls=1)
    first = tb.call("single", "retrieve_evidence", {"question": "policy outlook"})
    assert first.status == "ok" and len(first.documents) == 2
    with pytest.raises(BudgetExceeded) as info:
        tb.call("single", "retrieve_evidence", {"question": "again"})
    assert info.value.resource == "evidence_calls"
    assert tb.traces()[-1].status == "denied_budget"
    tb.call("single", "run_scenario", {"scenario_id": "parallel_up_25"})
    tb.call("single", "run_scenario", {"scenario_id": "parallel_down_25"})
    with pytest.raises(BudgetExceeded):
        tb.call("single", "run_scenario", {"scenario_id": "flattener_v1"})
    usage = tb.ledger.usage()
    assert (usage.tool_calls, usage.evidence_calls, usage.unique_evidence_chunks) == (3, 1, 2)


def test_graph_expansion_only_from_delivered_seeds(ctx_for):
    ctx = ctx_for("llm_graph")
    evidence = FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of))
    tb = _toolbox(ctx, RetrievalMode.GRAPH_RAG, evidence)
    assert tb.call(
        "single", "expand_evidence_graph", {"seed_ids": ["event-fomc-20230503"]}
    ).status == (
        "denied_policy"
    )  # nothing delivered yet
    tb.call("single", "retrieve_evidence", {"question": "policy outlook"})
    ok = tb.call(
        "single", "expand_evidence_graph", {"seed_ids": ["event-fomc-20230503", "made-up"]}
    )
    assert ok.status == "ok"
    assert evidence.calls[-1]["seeds"] == ["event-fomc-20230503"]
    assert evidence.calls[-1]["mode"] == RetrievalMode.GRAPH_RAG
    hybrid = _toolbox(ctx, RetrievalMode.HYBRID_RAG, evidence)
    assert "expand_evidence_graph" not in hybrid.allowed_tools("single")


def test_retrieved_text_is_wrapped_as_untrusted_data():
    doc = FakeDoc("chk-inject", INJECTION_TEXT, utc(2023, 5, 3, 20)).delivered()
    block = document_block(doc)
    assert block.startswith('<untrusted_document chunk_id="chk-inject">')
    # The forged closing tag and platform block inside the document are neutralized.
    assert parse_blocks(block) == []
    assert list(parse_documents(block)) == ["chk-inject"]
    assert "‹/untrusted_document" in block
