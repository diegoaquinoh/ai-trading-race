"""Research question -> cited research note, with no order authority (spec 2.2, 13.1).

:func:`research_note` answers a question scoped to an information cutoff and,
optionally, a frozen portfolio snapshot. It retrieves eligible passages
(``graph_rag_v1`` by default) with the question as the query, may run one
tool-selection turn (evidence, market features and, with a portfolio,
exposures and approved scenarios) and returns a validated, cited
:class:`ResearchNote`. ``propose_targets`` is never available, the output
contract has no proposal field and the envelope carries
``orderAuthority: false``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from research_engine import ENGINE_VERSION
from research_engine.contracts.common import (
    SCHEMA_VERSION,
    ContractModel,
    OpaqueId,
    UtcDatetime,
    content_hash,
    short_id,
)
from research_engine.contracts.decisions import (
    DecisionAttempt,
    DecisionBudget,
    DecisionOutcome,
    ResearchNote,
    RetrievalMode,
    ToolTrace,
    UsageSummary,
    ValidationResult,
    VersionInfo,
)
from research_engine.contracts.portfolio import ExecutionModel, PortfolioState, RiskPolicy
from research_engine.simulation.clock import make_id

from .budget import REFERENCE_ZERO_COST, BudgetLedger, PriceSchedule
from .ports import EvidencePort
from .prompts import PROMPT_VERSION
from .providers import ModelProvider, ReferenceHeuristicProvider
from .result import completion_time, result_signing_key
from .tool_schemas import PROPOSAL_TOOLS, TOOL_ARGS, TOOL_SCHEMA_VERSION
from .tools import DecisionToolbox, ToolBinding
from .workflow import AgentSettings, DecisionSession, run_research_note

NoteStatus = Literal[
    "completed",
    "insufficient_evidence",
    "contradictory_evidence",
    "failed_invalid_output",
    "failed_dependency",
    "failed_budget",
]
_STATUS = {
    DecisionOutcome.COMPLETED_HOLD: "completed",
    DecisionOutcome.ABSTAINED_INSUFFICIENT_EVIDENCE: "insufficient_evidence",
    DecisionOutcome.REVIEW_REQUIRED: "contradictory_evidence",
    DecisionOutcome.FAILED_INVALID_OUTPUT: "failed_invalid_output",
    DecisionOutcome.FAILED_DEPENDENCY: "failed_dependency",
    DecisionOutcome.FAILED_BUDGET: "failed_budget",
}


class ResearchNoteResult(ContractModel):
    schema_version: str = SCHEMA_VERSION
    note_id: OpaqueId
    question: str
    cutoff: UtcDatetime
    portfolio_snapshot_id: Optional[OpaqueId] = None
    order_authority: Literal[False] = False
    status: NoteStatus
    reasons: list[str] = Field(default_factory=list)
    research_note: Optional[ResearchNote] = None
    validation: list[ValidationResult] = Field(default_factory=list)
    attempts: list[DecisionAttempt] = Field(default_factory=list)
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    versions: VersionInfo
    evidence_bundle_ids: list[OpaqueId] = Field(default_factory=list)
    completed_at: UtcDatetime
    result_hash: Optional[str] = None
    signature: Optional[str] = None

    def hash_payload(self) -> dict:
        wire = self.to_wire()
        wire.pop("resultHash", None)
        wire.pop("signature", None)
        return wire


def research_note(
    question: str,
    as_of: datetime,
    *,
    evidence: EvidencePort,
    provider: Optional[ModelProvider] = None,
    mode: RetrievalMode = RetrievalMode.GRAPH_RAG,
    pricing=None,
    market=None,
    portfolio_state: Optional[PortfolioState] = None,
    risk_policy: Optional[RiskPolicy] = None,
    budget: Optional[DecisionBudget] = None,
    price_schedule: Optional[PriceSchedule] = None,
    signing_key: Optional[bytes] = None,
    timing: str = "logical",
) -> ResearchNoteResult:
    if mode == RetrievalMode.NONE:
        raise ValueError("research notes need an evidence retrieval mode")
    provider = provider or ReferenceHeuristicProvider()
    if price_schedule is None and provider.provider == "reference":
        price_schedule = REFERENCE_ZERO_COST
    budget = budget or DecisionBudget()
    risk_policy = risk_policy or RiskPolicy()
    binding = _binding(question, as_of, pricing, market, portfolio_state, risk_policy)
    ledger = BudgetLedger(budget, price_schedule=price_schedule)
    toolbox = DecisionToolbox(
        binding,
        ledger,
        strategy_tools=frozenset(TOOL_ARGS) - PROPOSAL_TOOLS,
        evidence=evidence,
        retrieval_mode=mode,
        timing=timing,
    )
    settings = AgentSettings(
        strategy_id="research_note",
        retrieval_mode=mode,
        strategy_tools=toolbox.strategy_tools,
        initial_query=question,
        max_tool_turns=1,
        timing=timing,
    )
    session = DecisionSession(settings, provider, toolbox, ledger, evidence=evidence)
    run = run_research_note(session, question)
    traces = toolbox.traces()
    duration = run.latency_ms + sum(t.duration_ms for t in traces)
    result = ResearchNoteResult(
        note_id=binding.decision_id,
        question=question,
        cutoff=as_of,
        portfolio_snapshot_id=binding.portfolio_snapshot_id,
        status=_STATUS.get(run.outcome, "failed_dependency"),
        reasons=run.reasons,
        research_note=run.note,
        validation=run.validation,
        attempts=run.attempts,
        tool_traces=traces,
        usage=ledger.usage(duration_ms=duration),
        versions=VersionInfo(
            provider=provider.provider,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            tool_schema_version=TOOL_SCHEMA_VERSION,
            engine_version=ENGINE_VERSION,
            evidence_snapshot_id=evidence.evidence_snapshot_id,
            index_build_id=evidence.index_build_id,
            retrieval_mode=mode,
        ),
        evidence_bundle_ids=sorted(toolbox.bundles),
        completed_at=completion_time(as_of, duration, timing),
    )
    from research_engine.contracts.common import sign_hash

    digest = content_hash(result.hash_payload())
    return result.model_copy(
        update={
            "result_hash": digest,
            "signature": sign_hash(digest, signing_key or result_signing_key()),
        }
    )


def _binding(question, as_of, pricing, market, state, risk_policy) -> ToolBinding:
    note_id = short_id(
        "rn",
        {
            "question": question,
            "cutoff": as_of,
            "portfolio": state.compute_hash() if state else None,
        },
        20,
    )
    binding = ToolBinding(
        decision_id=note_id,
        strategy_id="research_note",
        decision_as_of=as_of,
        pricing=pricing,
        market=market,
        risk_policy=risk_policy,
        execution_model=ExecutionModel(),
    )
    if pricing is None or market is None:
        return binding
    curve = market.latest_available_curve(as_of)
    if curve is None:
        return binding
    binding.session_date = curve.session_date
    binding.curve_snapshot_id = curve.curve_snapshot_id
    binding.curve_content_hash = curve.content_hash
    binding.curve_available_at = curve.available_at
    binding.data_mode = curve.data_mode
    binding.universe = tuple(sorted(i.security_id for i in pricing.universe(curve.session_date)))
    if state is not None:
        from research_engine.simulation.ledger import Book
        from research_engine.simulation.policy import build_decision_snapshot
        from research_engine.simulation.valuation import CurveRef

        binding.portfolio_state = state
        binding.portfolio_snapshot_id = make_id("pfs", state.portfolio_id, f"v{state.version}")
        cache: dict = {}

        def snapshot():
            if "snap" not in cache:
                cache["snap"] = build_decision_snapshot(
                    Book.from_state(state),
                    pricing,
                    curve=CurveRef(curve.curve_snapshot_id, curve.session_date, curve.observed_at),
                    decision_time=as_of,
                    data_mode=curve.data_mode,
                    policy=risk_policy,
                )
            return cache["snap"]

        binding.snapshot_fn = snapshot
    return binding
