"""Strategy decision request/result envelopes (spec 13, 14.4, 14.5, 15.2).

A strategy produces a *proposal*; it never executes. The result envelope is
persisted by .NET (Decision, DecisionAttempt, PolicyEvaluation, ToolTrace,
UsageRecord) for every outcome, including HOLD, abstention and failure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import Field, model_validator

from .common import (
    SCHEMA_VERSION,
    ContentHash,
    ContractModel,
    DataMode,
    DecimalStr,
    OpaqueId,
    StrategyId,
    UtcDatetime,
)
from .portfolio import DecisionAction, PolicyEvaluation, TargetWeight


class DecisionOutcome(str, Enum):
    COMPLETED_HOLD = "completed_hold"
    COMPLETED_PROPOSAL = "completed_proposal"
    ABSTAINED_INSUFFICIENT_EVIDENCE = "abstained_insufficient_evidence"
    REVIEW_REQUIRED = "review_required"
    FAILED_INVALID_OUTPUT = "failed_invalid_output"
    FAILED_DEPENDENCY = "failed_dependency"
    FAILED_BUDGET = "failed_budget"
    SKIPPED_STALE_DATA = "skipped_stale_data"
    CANCELLED = "cancelled"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StrategyKind(str, Enum):
    CASH_REFERENCE = "cash_reference"
    QUANT_POLICY = "quant_policy"
    SINGLE_AGENT = "single_agent"
    SPECIALIST_TEAM = "specialist_team"


class RetrievalMode(str, Enum):
    NONE = "none"
    HYBRID_RAG = "hybrid_rag_v1"
    GRAPH_RAG = "graph_rag_v1"


class ResearchStatus(str, Enum):
    SUPPORTED = "supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"


class SnapshotRef(ContractModel):
    id: OpaqueId
    content_hash: ContentHash
    version: Optional[int] = None


class MarketSnapshotPointer(ContractModel):
    id: OpaqueId
    content_hash: ContentHash
    curve_snapshot_id: OpaqueId


class DecisionBudget(ContractModel):
    """Decision-wide ceilings shared by a lead and all specialists (spec 10.4)."""

    max_generation_calls: int = 6
    max_tool_calls: int = 12
    max_evidence_calls: int = 3
    max_unique_evidence_chunks: int = 12
    max_evidence_tokens: int = 8000
    max_input_tokens: int = 32000
    max_output_tokens: int = 12000
    deadline_seconds: int = 90
    max_cost_usd: Optional[DecimalStr] = None
    price_schedule_id: Optional[OpaqueId] = None
    max_delegation_depth: int = 1
    max_specialist_invocations: int = 2


class DecisionSessionContext(ContractModel):
    """Run calendar context supplied by the platform with a decision request.

    When present it is authoritative: ``previous_session_date`` is the run's
    previous decision session (``None`` for the run's first session), exactly the
    value offline replay takes from its session list. When the whole object is
    absent (older callers) the engine derives the previous session from the
    market calendar.
    """

    previous_session_date: Optional[date] = None


class DecisionRequest(ContractModel):
    schema_version: str = SCHEMA_VERSION
    experiment_id: OpaqueId
    run_id: OpaqueId
    cycle_id: OpaqueId
    decision_id: OpaqueId
    strategy_id: StrategyId
    repetition: int = 0
    decision_as_of: UtcDatetime
    market_session_date: date
    availability_policy: str
    data_mode: DataMode
    portfolio_snapshot: SnapshotRef
    market_snapshot: MarketSnapshotPointer
    instrument_universe_version: OpaqueId
    evidence_snapshot_id: Optional[OpaqueId] = None
    index_build_id: Optional[OpaqueId] = None
    strategy_config_id: OpaqueId
    risk_policy_id: OpaqueId
    response_mode: Literal["fresh_inference", "recorded_replay"] = "recorded_replay"
    budget: DecisionBudget = Field(default_factory=DecisionBudget)
    # Inline immutable artifacts (hash-verified by the receiver).
    portfolio_state: Optional[dict[str, Any]] = None
    # Additive and omitted from the wire/hash when absent, so existing request hashes
    # (recorded responses, fixtures) are unchanged.
    session_context: Optional[DecisionSessionContext] = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def _session_context_precedes_session(self) -> "DecisionRequest":
        context = self.session_context
        if context is not None and context.previous_session_date is not None:
            if context.previous_session_date >= self.market_session_date:
                raise ValueError(
                    "sessionContext.previousSessionDate must precede marketSessionDate"
                )
        return self


# --------------------------------------------------------------------------- #
# Research note components
# --------------------------------------------------------------------------- #


class Citation(ContractModel):
    citation_id: OpaqueId
    bundle_id: OpaqueId
    chunk_id: OpaqueId
    document_version_id: OpaqueId
    quote: Optional[str] = None  # exact substring of stored normalized chunk text
    start_offset: Optional[int] = None  # offsets into the chunk's normalized text
    end_offset: Optional[int] = None


class DocumentaryClaim(ContractModel):
    claim_id: OpaqueId
    text: str
    citation_ids: list[OpaqueId]
    material: bool = True
    validation_status: Literal["unvalidated", "valid", "invalid", "review_required"] = "unvalidated"
    validation_notes: list[str] = Field(default_factory=list)


class NumericalFinding(ContractModel):
    finding_id: OpaqueId
    text: str
    calculation_ids: list[OpaqueId]  # must resolve to signed engine outputs
    input_snapshot_ids: list[OpaqueId] = Field(default_factory=list)
    validation_status: Literal["unvalidated", "valid", "invalid"] = "unvalidated"


class Hypothesis(ContractModel):
    hypothesis_id: OpaqueId
    text: str
    assumptions: list[str]
    scenario_ids: list[str] = Field(default_factory=list)
    supporting_citation_ids: list[OpaqueId] = Field(default_factory=list)


class ResearchNote(ContractModel):
    status: ResearchStatus
    claims: list[DocumentaryClaim] = Field(default_factory=list)
    numerical_findings: list[NumericalFinding] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    retrieval_run_ids: list[OpaqueId] = Field(default_factory=list)
    explanation: str = ""


class Proposal(ContractModel):
    action: DecisionAction
    target_weights: list[TargetWeight] = Field(default_factory=list)
    supporting_claim_ids: list[OpaqueId] = Field(default_factory=list)
    supporting_calculation_ids: list[OpaqueId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _weights(self) -> "Proposal":
        if self.action == DecisionAction.HOLD:
            return self
        if not self.target_weights:
            raise ValueError("REBALANCE/BOOTSTRAP proposals require target weights")
        seen: set[str] = set()
        for weight in self.target_weights:
            if weight.weight < 0:
                raise ValueError("target weights must be nonnegative")
            if weight.security_id in seen:
                raise ValueError(f"duplicate target for {weight.security_id}")
            seen.add(weight.security_id)
        total = sum((w.weight for w in self.target_weights), Decimal("0"))
        if abs(total - Decimal("1")) > Decimal("0.000001"):
            raise ValueError(f"target weights must sum to 1 within 1e-6 (got {total})")
        return self


# --------------------------------------------------------------------------- #
# Audit records
# --------------------------------------------------------------------------- #


class ToolTrace(ContractModel):
    trace_id: OpaqueId
    agent_role: str  # "single", "lead", "macro_researcher", "critical_reviewer"
    tool_name: str
    request: dict[str, Any]
    response_summary: dict[str, Any]
    output_ref: Optional[OpaqueId] = None  # calculation/retrieval/bundle id
    started_at: UtcDatetime
    duration_ms: int
    status: Literal["ok", "error", "denied_budget", "denied_policy"]
    error: Optional[str] = None


class DecisionAttempt(ContractModel):
    attempt_id: OpaqueId
    attempt_number: int
    agent_role: str
    purpose: Literal[
        "task_assignment", "tool_selection", "specialist", "synthesis", "repair", "single"
    ]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    started_at: UtcDatetime
    duration_ms: int
    status: Literal["ok", "malformed", "provider_error", "timeout", "denied_budget"]
    recorded_response_id: Optional[OpaqueId] = None
    error: Optional[str] = None


class SpecialistTask(ContractModel):
    task_id: OpaqueId
    role: Literal["macro_researcher", "critical_reviewer"]
    instruction: str
    input_snapshot_ids: list[OpaqueId]
    expected_output_schema: str
    budget_reserved: dict[str, int]
    status: Literal["completed", "failed", "denied_budget", "skipped"]
    findings: list[str] = Field(default_factory=list)
    claim_ids: list[OpaqueId] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class UsageSummary(ContractModel):
    generation_calls: int = 0
    tool_calls: int = 0
    evidence_calls: int = 0
    unique_evidence_chunks: int = 0
    evidence_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    estimated_cost_usd: Optional[DecimalStr] = None
    price_schedule_id: Optional[OpaqueId] = None
    budget_exhausted: Optional[str] = None


class ValidationResult(ContractModel):
    step: str  # schema, citation_membership, temporal, quote_offsets, calc_refs, support, policy
    passed: bool
    severity: Literal["info", "warning", "blocking"] = "blocking"
    details: list[str] = Field(default_factory=list)


class VersionInfo(ContractModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    tool_schema_version: Optional[str] = None
    engine_version: str
    evidence_snapshot_id: Optional[OpaqueId] = None
    index_build_id: Optional[OpaqueId] = None
    retrieval_mode: RetrievalMode = RetrievalMode.NONE
    strategy_config_hash: Optional[ContentHash] = None


class StrategyResult(ContractModel):
    schema_version: str = SCHEMA_VERSION
    run_id: OpaqueId
    cycle_id: OpaqueId
    decision_id: OpaqueId
    strategy_id: StrategyId
    strategy_kind: StrategyKind
    repetition: int = 0
    request_hash: ContentHash
    input_hashes: dict[str, str]
    outcome: DecisionOutcome
    completed_at: UtcDatetime
    reasons: list[str] = Field(default_factory=list)  # error/abstention/skip reasons
    proposal: Optional[Proposal] = None
    research_note: Optional[ResearchNote] = None
    validation: list[ValidationResult] = Field(default_factory=list)
    policy_evaluation: Optional[PolicyEvaluation] = None
    attempts: list[DecisionAttempt] = Field(default_factory=list)
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    specialist_tasks: list[SpecialistTask] = Field(default_factory=list)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    versions: VersionInfo
    evidence_bundle_ids: list[OpaqueId] = Field(default_factory=list)
    result_hash: Optional[ContentHash] = None
    signature: Optional[str] = None

    def hash_payload(self) -> dict:
        wire = self.to_wire()
        wire.pop("resultHash", None)
        wire.pop("signature", None)
        return wire
