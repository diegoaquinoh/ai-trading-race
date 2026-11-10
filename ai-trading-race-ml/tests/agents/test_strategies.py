"""LLM strategies end to end (spec 10, 13.3, 15.2, 16.6) on real offline numerical ports."""

from __future__ import annotations

import json
import threading
from datetime import date

import pytest

from research_engine.agents import create_llm_strategy, verify_result
from research_engine.agents.providers import ReferenceHeuristicProvider
from research_engine.contracts.decisions import DecisionOutcome, RetrievalMode, StrategyKind
from research_engine.contracts.portfolio import CommandType, DecisionAction
from research_engine.experiments.strategy import create_strategy

from .conftest import KEY, RESULT_KEY
from .fakes import (
    DOVISH_TEXT,
    HAWKISH_TEXT,
    INJECTION_TEXT,
    FakeDoc,
    FakeEvidencePort,
    ScriptedProvider,
    SpyProvider,
    hawkish_docs,
    utc,
)


def _strategy(sid, provider=None, evidence=None, config=None):
    return create_llm_strategy(
        sid,
        config or {},
        provider=provider or ReferenceHeuristicProvider(),
        evidence=evidence,
        signing_key=RESULT_KEY,
    )


def _reference_after(n_scripted, scripted):
    """Script the first responses, then defer to the reference model."""
    reference = ReferenceHeuristicProvider()

    def script(request, n):
        if n <= n_scripted:
            return scripted(request, n)
        return reference.generate(request)

    return script


def test_registry_and_bootstrap_without_model_calls(contexts, ctx_for):
    import research_engine.agents  # noqa: F401  (registers llm_*)

    strategy = create_strategy("llm_market", {})
    assert strategy.kind == StrategyKind.SINGLE_AGENT and strategy.config["provider"] == "reference"
    spy = SpyProvider(ReferenceHeuristicProvider())
    first = ctx_for("llm_market", date(2023, 6, 12))
    result = _strategy("llm_market", spy).decide(first)
    assert result.outcome == DecisionOutcome.COMPLETED_PROPOSAL
    assert result.proposal.action == DecisionAction.BOOTSTRAP and not spy.requests
    assert verify_result(result, RESULT_KEY)


def test_market_only_strategy_never_receives_document_text(ctx_for):
    ctx = ctx_for("llm_market")
    evidence = FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of))
    spy = SpyProvider(ReferenceHeuristicProvider())
    strategy = _strategy("llm_market", spy, evidence)
    result = strategy.decide(ctx)
    assert spy.requests and not evidence.calls
    for request in spy.requests:
        text = "".join(m.content for m in request.messages)
        assert "<untrusted_document chunk_id=" not in text and "evidence_index" not in text
        assert "Inflation remains elevated" not in text
    assert result.versions.retrieval_mode == RetrievalMode.NONE
    assert not result.evidence_bundle_ids and result.usage.evidence_calls == 0
    assert result.outcome in (DecisionOutcome.COMPLETED_PROPOSAL, DecisionOutcome.COMPLETED_HOLD)
    assert all(
        not f.calculation_ids or f.validation_status == "valid"
        for f in result.research_note.numerical_findings
    )


def test_every_call_repair_and_tool_turn_consumes_the_ceiling(ctx_for):
    ctx = ctx_for("llm_rag")
    evidence = FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of))

    def scripted(request, n):
        if n == 1:
            return "this is not json"
        return {
            "action": "call_tools",
            "calls": [{"tool": "run_scenario", "arguments": {"scenario_id": "parallel_up_25"}}],
        }

    provider = ScriptedProvider(_reference_after(2, scripted))
    result = _strategy("llm_rag", provider, evidence).decide(ctx)
    purposes = [(a.purpose, a.status) for a in result.attempts]
    assert purposes[:3] == [
        ("tool_selection", "malformed"),
        ("repair", "ok"),
        ("tool_selection", "ok"),
    ]
    assert result.usage.generation_calls == len(provider.requests) == len(result.attempts)
    assert result.usage.input_tokens == sum(a.input_tokens for a in result.attempts)
    assert result.outcome == DecisionOutcome.COMPLETED_PROPOSAL

    tight = ctx_for("llm_rag", max_generation_calls=2)
    provider2 = ScriptedProvider(_reference_after(2, scripted))
    failed = _strategy("llm_rag", provider2, evidence).decide(tight)
    assert failed.outcome == DecisionOutcome.FAILED_BUDGET and failed.proposal is None
    assert (
        failed.usage.generation_calls == 2 and failed.usage.budget_exhausted == "generation_calls"
    )
    assert failed.attempts[-1].status == "denied_budget"
    assert len(provider2.requests) == 2


@pytest.mark.parametrize("sid", ["llm_graph", "llm_team"])
def test_failed_mandatory_graph_never_masquerades_as_rag(ctx_for, sid):
    ctx = ctx_for(sid)
    evidence = FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of), fail_graph=True)
    spy = SpyProvider(ReferenceHeuristicProvider())
    result = _strategy(sid, spy, evidence).decide(ctx)
    assert result.outcome == DecisionOutcome.FAILED_DEPENDENCY
    assert "graph_retrieval_unavailable" in result.reasons
    assert "no_fallback_to_hybrid_rag_v1" in result.reasons
    assert result.versions.retrieval_mode == RetrievalMode.GRAPH_RAG
    assert [c["mode"] for c in evidence.calls] == [RetrievalMode.GRAPH_RAG]
    assert not spy.requests and result.proposal is None
    assert result.strategy_id == sid


@pytest.mark.parametrize(
    "config,expected",
    [
        ({}, DecisionOutcome.ABSTAINED_INSUFFICIENT_EVIDENCE),
        ({"onInsufficientEvidence": "review"}, DecisionOutcome.REVIEW_REQUIRED),
    ],
)
def test_empty_mandatory_retrieval_yields_configured_outcome(ctx_for, config, expected):
    ctx = ctx_for("llm_rag")
    spy = SpyProvider(ReferenceHeuristicProvider())
    result = _strategy("llm_rag", spy, FakeEvidencePort([]), config).decide(ctx)
    assert result.outcome == expected and "mandatory_retrieval_empty" in result.reasons
    assert result.research_note.status.value == "insufficient_evidence"
    assert not spy.requests and result.proposal is None


@pytest.mark.parametrize(
    "config,expected",
    [
        ({}, DecisionOutcome.REVIEW_REQUIRED),
        ({"onContradictoryEvidence": "abstain"}, DecisionOutcome.ABSTAINED_INSUFFICIENT_EVIDENCE),
    ],
)
def test_contradictory_evidence_yields_configured_outcome(ctx_for, config, expected):
    ctx = ctx_for("llm_rag")
    docs = [
        FakeDoc("chk-h", HAWKISH_TEXT, utc(2023, 5, 3, 20), title="Statement A"),
        FakeDoc("chk-d", DOVISH_TEXT, utc(2023, 5, 3, 20), title="Statement B"),
    ]
    result = _strategy("llm_rag", evidence=FakeEvidencePort(docs), config=config).decide(ctx)
    assert result.outcome == expected and result.proposal is None
    assert result.research_note.status.value == "contradictory_evidence"
    assert "contradictory_evidence" in result.reasons


def test_malformed_proposal_cannot_write_financial_state(ports, tmp_path):
    from research_engine.experiments.runner import ReplayConfig, ReplayRunner, StrategySpec

    pricing, market = ports
    evidence = FakeEvidencePort(hawkish_docs(utc(2023, 6, 13)))
    provider = ScriptedProvider(lambda request, n: '{"action": "final", "status": "supported"')
    strategy = _strategy("llm_rag", provider, evidence)
    config = ReplayConfig(
        experiment_id="malformed",
        run_id="malformed-r0",
        start_date=date(2023, 6, 12),
        end_date=date(2023, 6, 13),
        strategies=[StrategySpec(strategy_id="llm_rag", config=strategy.config)],
        response_mode="fresh_inference",
    )
    runner = ReplayRunner(
        config, pricing, market, tmp_path / "run", KEY, strategies={"llm_rag": strategy}
    )
    runner.run()
    outcomes = [
        json.loads(ln)["result"]
        for ln in (tmp_path / "run" / "outcomes.jsonl").read_text().splitlines()
    ]
    final = outcomes[-1]
    assert final["outcome"] == "failed_invalid_output" and final["proposal"] is None
    assert any(r.startswith("malformed_output_after_repairs") for r in final["reasons"])
    assert len(final["attempts"]) == 3  # original + two repairs, all recorded
    decisions = [
        p
        for p in runner.store.committed()
        if p.command_type == CommandType.SUBMIT_DECISION and p.request_hash
    ]
    assert len(decisions) == 1  # only the 2023-06-12 bootstrap; no transition for 06-13
    state = runner.store.state(runner._pid("llm_rag"))
    assert not any(o.decision_id == final["decisionId"] for o in state.open_orders)


def test_prompt_injection_does_not_change_permissions_or_targets(ctx_for):
    ctx = ctx_for("llm_rag")
    clean = hawkish_docs(ctx.request.decision_as_of)
    injected = clean + [FakeDoc("chk-inject", INJECTION_TEXT, utc(2023, 5, 4, 20), title="Note")]
    base = _strategy("llm_rag", evidence=FakeEvidencePort(clean)).decide(ctx)
    attacked = _strategy("llm_rag", evidence=FakeEvidencePort(injected)).decide(ctx)
    assert attacked.outcome == base.outcome
    assert attacked.proposal.target_weights == base.proposal.target_weights
    assert {t.tool_name for t in attacked.tool_traces} == {t.tool_name for t in base.tool_traces}

    # A model that obeys the injected text is still bounded by the toolbox and the policy.
    def obedient(request, n):
        if n == 1:
            return {
                "action": "call_tools",
                "calls": [
                    {"tool": "execute_trade", "arguments": {"buy": "everything"}},
                    {
                        "tool": "propose_targets",
                        "arguments": {
                            "action": "REBALANCE",
                            "target_weights": [{"security_id": "SYN-USD-NOTE-009", "weight": "1"}],
                        },
                    },
                ],
            }
        out = json.loads(ReferenceHeuristicProvider().generate(request).text)
        if out.get("action") == "final" and out.get("proposal"):
            out["decision"] = "propose"
            out["proposal"]["action"] = "REBALANCE"
            out["proposal"]["target_weights"] = [{"security_id": "SYN-USD-NOTE-009", "weight": "1"}]
        return out

    result = _strategy(
        "llm_rag", ScriptedProvider(obedient), FakeEvidencePort(injected), {"maxRepairs": 0}
    ).decide(ctx)
    statuses = {t.tool_name: t.status for t in result.tool_traces}
    assert statuses["execute_trade"] == "denied_policy"
    dry_run = next(t for t in result.tool_traces if t.tool_name == "propose_targets")
    assert dry_run.status == "ok" and dry_run.response_summary["passed"] is False
    assert result.outcome == DecisionOutcome.FAILED_INVALID_OUTPUT and result.proposal is None
    assert any(r.startswith("policy_rejected") for r in result.reasons)


def test_team_obeys_bounds_and_records_task_tree(ctx_for):
    ctx = ctx_for("llm_team")
    evidence = FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of))
    reference = ReferenceHeuristicProvider()

    def script(request, n):
        role, purpose = request.metadata.role, request.metadata.purpose
        if role == "lead" and purpose == "task_assignment":
            return {
                "action": "delegate",
                "tasks": [
                    {"role": "macro_researcher", "instruction": "compare communications"},
                    {"role": "risk_quant", "instruction": "unregistered role"},
                    {"role": "critical_reviewer", "instruction": "challenge the hypothesis"},
                    {"role": "macro_researcher", "instruction": "duplicate"},
                ],
            }
        if role == "critical_reviewer":  # specialists cannot delegate further
            return {
                "action": "delegate",
                "tasks": [{"role": "macro_researcher", "instruction": "x"}],
            }
        return reference.generate(request)

    result = _strategy("llm_team", ScriptedProvider(script), evidence).decide(ctx)
    tasks = {(t.role, t.status) for t in result.specialist_tasks}
    executed = [t for t in result.specialist_tasks if t.status != "skipped"]
    assert len(executed) == 2  # max two specialist invocations
    skipped = [t for t in result.specialist_tasks if t.status == "skipped"]
    assert sorted(f for t in skipped for f in t.findings) == [
        "skipped:duplicate_role",
        "skipped:unregistered_role",
    ]
    assert ("macro_researcher", "completed") in tasks
    reviewer = next(t for t in executed if t.role == "critical_reviewer")
    assert reviewer.status == "failed" and "malformed_output_after_repairs" in reviewer.findings[-1]
    for task in executed:
        assert task.budget_reserved["generation_calls"] >= 1 and task.input_snapshot_ids
    roles = {a.agent_role for a in result.attempts}
    assert roles == {"lead", "macro_researcher", "critical_reviewer"}
    assert result.usage.generation_calls <= 6 == ctx.request.budget.max_generation_calls
    assert result.strategy_kind == StrategyKind.SPECIALIST_TEAM

    no_depth = ctx_for("llm_team", max_delegation_depth=0)
    depthless = _strategy("llm_team", evidence=evidence).decide(no_depth)
    assert all(t.status == "skipped" for t in depthless.specialist_tasks)
    assert {f for t in depthless.specialist_tasks for f in t.findings} == {
        "skipped:delegation_depth_limit"
    }


def test_simultaneous_specialists_cannot_overspend(ctx_for):
    ctx = ctx_for(
        "llm_team", max_evidence_calls=2, max_unique_evidence_chunks=3, max_input_tokens=26000
    )
    docs = hawkish_docs(ctx.request.decision_as_of) + [
        FakeDoc(
            f"chk-x{i}", HAWKISH_TEXT + f" Extra {i}.", utc(2023, 4, 1 + i, 20), title=f"Doc {i}"
        )
        for i in range(4)
    ]
    evidence = FakeEvidencePort(docs)
    reference = ReferenceHeuristicProvider()
    barrier = threading.Barrier(2, timeout=10)

    def script(request, n):
        role = request.metadata.role
        if (
            role in ("macro_researcher", "critical_reviewer")
            and request.metadata.purpose == "specialist"
        ):
            if not any("tool_results" in m.content for m in request.messages):
                barrier.wait()  # both specialists act at the same instant
                return {
                    "action": "call_tools",
                    "calls": [
                        {
                            "tool": "retrieve_evidence",
                            "arguments": {"question": f"{role} evidence"},
                        },
                        {"tool": "retrieve_evidence", "arguments": {"question": f"{role} more"}},
                    ],
                }
        return reference.generate(request)

    result = _strategy(
        "llm_team", ScriptedProvider(script), evidence, {"initialMaxChunks": 2}
    ).decide(ctx)
    budget = ctx.request.budget
    usage = result.usage
    assert usage.evidence_calls <= budget.max_evidence_calls
    assert usage.unique_evidence_chunks <= budget.max_unique_evidence_chunks
    assert usage.input_tokens <= budget.max_input_tokens
    assert usage.generation_calls <= budget.max_generation_calls
    statuses = [t.status for t in result.tool_traces if t.tool_name == "retrieve_evidence"]
    assert statuses.count("ok") == usage.evidence_calls == 2  # lead + one specialist
    assert statuses.count("denied_budget") >= 2  # the simultaneous excess is refused
    by_role = {t.role: t for t in result.specialist_tasks}
    assert by_role["critical_reviewer"].status == "denied_budget"
    caps = [t.budget_reserved["evidence_calls"] for t in by_role.values()]
    assert sum(caps) <= budget.max_evidence_calls - 1  # blocks never exceed what was left


def test_results_are_signed_and_carry_versions(ctx_for):
    ctx = ctx_for("llm_graph")
    result = _strategy(
        "llm_graph", evidence=FakeEvidencePort(hawkish_docs(ctx.request.decision_as_of))
    ).decide(ctx)
    assert verify_result(result, RESULT_KEY)
    tampered = result.model_copy(update={"reasons": ["edited"]})
    assert not verify_result(tampered, RESULT_KEY)
    v = result.versions
    assert (v.provider, v.model, v.retrieval_mode) == (
        "reference",
        "reference-heuristic-v1",
        RetrievalMode.GRAPH_RAG,
    )
    assert (
        v.prompt_version.startswith("fi-agent-prompts-v1@")
        and v.tool_schema_version == "fi-agent-tools-v1"
    )
    assert {
        "strategyConfig",
        "promptSet",
        "toolSchema",
        "evidenceBundles",
        "decisionRequest",
    } <= set(result.input_hashes)
    assert any(
        t.tool_name == "expand_evidence_graph" and t.status == "ok" for t in result.tool_traces
    )
    assert (
        result.usage.estimated_cost_usd == 0
        and result.usage.price_schedule_id == "reference-zero-cost-v1"
    )
    assert any(v.step == "original_proposal" for v in result.validation)


def test_hosted_priced_runs_require_a_price_schedule(ctx_for):
    class Hosted(ScriptedProvider):
        pass

    hosted = Hosted(lambda r, n: "{}", provider="anthropic", model="claude-sonnet-5-5", priced=True)
    result = _strategy("llm_market", hosted).decide(ctx_for("llm_market"))
    assert result.outcome == DecisionOutcome.FAILED_DEPENDENCY and not hosted.requests
    assert result.reasons == ["price_schedule_and_monetary_ceiling_required_for_priced_runs"]


def test_refused_call_records_reported_usage(ctx_for):
    from research_engine.agents.providers.base import ProviderRefusal

    def refuse(request, n):
        raise ProviderRefusal("model declined", input_tokens=1234, output_tokens=17)

    provider = ScriptedProvider(refuse)
    result = _strategy("llm_market", provider).decide(ctx_for("llm_market"))
    assert result.outcome == DecisionOutcome.FAILED_DEPENDENCY
    assert len(provider.requests) == 1
    (attempt,) = result.attempts
    assert attempt.status == "provider_error" and "provider_refusal" in attempt.error
    assert (attempt.input_tokens, attempt.output_tokens) == (1234, 17)
    usage = result.usage
    assert usage.generation_calls == 1
    assert (usage.input_tokens, usage.output_tokens) == (1234, 17)


def test_unexpected_provider_exception_settles_the_reservation(ctx_for, monkeypatch):
    import research_engine.agents.strategies as strategies_module
    from research_engine.agents.budget import BudgetLedger

    ledgers: list[BudgetLedger] = []

    class RecordingLedger(BudgetLedger):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            ledgers.append(self)

    monkeypatch.setattr(strategies_module, "BudgetLedger", RecordingLedger)

    def broken(request, n):
        raise KeyError("provider bug")

    with pytest.raises(KeyError):
        _strategy("llm_market", ScriptedProvider(broken)).decide(ctx_for("llm_market"))
    (ledger,) = ledgers
    assert ledger._outstanding == {}  # no reservation left holding budget
    assert ledger.usage().generation_calls == 1  # the attempted call is counted
