"""Agent workflows: single agent (spec 10.3), bounded team (10.4), research note.

Single agent:

1. required numerical tools on the frozen snapshot (own portfolio risk, market
   features) - recorded tool calls, no model call;
2. mandatory retrieval with the strategy's fixed query template when the
   strategy uses evidence (graph failure -> ``failed_dependency``, never a
   silent RAG fallback; an empty bundle -> configured abstention/review);
3. up to ``max_tool_turns`` tool-selection turns (scenarios, valuation,
   further evidence), then a forced synthesis turn;
4. validation (``validation.py``); blocking failures and malformed replies may
   be repaired while the repair allowance and the decision budget last.

Team (``llm_team``): the lead runs steps 1-2, assigns at most
``max_specialist_invocations`` tasks to registered roles (depth one;
specialists cannot delegate), reserves its synthesis capacity, splits the rest
of the decision budget into per-task allowances, runs the specialists
(``parallel_v1``: concurrently; ``sequential_on_draft_v1``: macro researcher,
lead draft, reviewer on the draft) and synthesizes one note and decision.

Every provider call - assignment, tool selection, specialist turns, synthesis,
malformed replies and repairs - is a generation attempt on the shared ledger.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from research_engine.contracts.decisions import (
    DecisionAttempt,
    DecisionOutcome,
    Proposal,
    ResearchNote,
    ResearchStatus,
    RetrievalMode,
    SpecialistTask,
    ValidationResult,
)
from research_engine.contracts.common import canonical_json
from research_engine.contracts.portfolio import DecisionAction, PolicyEvaluation
from research_engine.risk.scenarios import SCENARIO_LIBRARY_V1
from research_engine.simulation.clock import make_id

from .budget import BudgetExceeded, BudgetLedger, TaskAllowance
from .output import (
    OUTPUT_CONTRACT_VERSION,
    CallToolsOut,
    DelegateOut,
    FinalOut,
    MalformedOutput,
    ReportOut,
    parse_output,
    wire_schema,
)
from .ports import EvidencePort, EvidenceUnavailable, GraphUnavailable
from .prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPTS,
    TURN_INSTRUCTIONS,
    evidence_index_entry,
    platform_block,
    render_documents,
)
from .providers.base import (
    ChatMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderError,
    RequestMetadata,
    worst_case_tokens,
)
from .tool_schemas import TOOL_SCHEMA_VERSION
from .tools import ROLE_RANK, DecisionToolbox, float_free
from .validation import ValidationInputs, ValidationReport, validate_output

SPECIALIST_ROLES = ("macro_researcher", "critical_reviewer")
REVIEWER_WORKFLOWS = ("parallel_v1", "sequential_on_draft_v1")


@dataclass(frozen=True)
class AgentSettings:
    strategy_id: str
    retrieval_mode: RetrievalMode
    strategy_tools: frozenset[str]
    team: bool = False
    mandatory_retrieval: bool = True
    initial_query: str = ""
    initial_max_chunks: int = 6
    initial_max_tokens: int = 4000
    max_tool_turns: int = 2
    specialist_tool_turns: int = 1
    max_repairs: int = 2
    max_provider_retries: int = 1
    max_output_tokens_per_call: int = 2048
    min_output_tokens_per_call: int = 256
    lead_synthesis_input_reserve: int = 2000
    on_insufficient_evidence: str = "abstain"  # abstain | review
    on_contradictory_evidence: str = "review"  # review | abstain
    support_threshold: Decimal = Decimal("0.5")
    require_quotes: bool = True
    timing: str = "logical"  # logical | wall
    reviewer_workflow: str = "parallel_v1"
    retry_backoff_seconds: float = 1.0


class DecisionFailure(Exception):
    def __init__(self, outcome: DecisionOutcome, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.outcome = outcome
        self.reasons = reasons


class TaskFailure(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass
class DecisionRun:
    outcome: DecisionOutcome
    reasons: list[str]
    note: Optional[ResearchNote]
    proposal: Optional[Proposal]
    policy_evaluation: Optional[PolicyEvaluation]
    attempts: list[DecisionAttempt]
    validation: list[ValidationResult]
    specialist_tasks: list[SpecialistTask]
    latency_ms: int
    raw_outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class _Ask:
    parsed: Any
    error: Optional[str]
    attempt_id: str
    response: ModelResponse


@dataclass
class _Conversation:
    role: str
    system: str
    messages: list[ChatMessage] = field(default_factory=list)
    shown: set[str] = field(default_factory=set)
    allowance: Optional[TaskAllowance] = None
    repairs_left: int = 0


class DecisionSession:
    """Runtime state of one decision (thread-safe where specialists share it)."""

    def __init__(
        self,
        settings: AgentSettings,
        provider: ModelProvider,
        toolbox: DecisionToolbox,
        ledger: BudgetLedger,
        *,
        evidence: Optional[EvidencePort] = None,
        sleep=time.sleep,
    ):
        import threading

        self.settings = settings
        self.provider = provider
        self.toolbox = toolbox
        self.ledger = ledger
        self.evidence = evidence
        self.binding = toolbox.binding
        self._sleep = sleep
        self._lock = threading.RLock()
        self._attempts: list[tuple[tuple, DecisionAttempt]] = []
        self._seq: dict[str, int] = {}
        self.validation: list[ValidationResult] = []
        self.specialist_tasks: list[SpecialistTask] = []
        self.raw_outputs: dict[str, str] = {}
        self.latency_ms = 0
        self.required: dict[str, dict] = {}
        self.last_report: Optional[ValidationReport] = None
        self.phase = 0
        self.parallel = False  # concurrent specialists: order by role, not by time
        self._clock = 0

    # ------------------------------------------------------------------ attempts

    def _attempt_id(self, role: str) -> tuple[str, int]:
        with self._lock:
            seq = self._seq.get(role, 0) + 1
            self._seq[role] = seq
        return make_id("att", self.binding.decision_id, role, f"{seq:02d}"), seq

    def _record_attempt(self, role, seq, attempt, raw: Optional[str]) -> None:
        with self._lock:
            self._clock += 1
            if self.parallel:
                key = (self.phase, ROLE_RANK.get(role, 9), role, seq)
            else:
                key = (self.phase, 0, "", self._clock)
            self._attempts.append((key, attempt))
            if raw is not None:
                self.raw_outputs[attempt.attempt_id] = raw
            self.latency_ms += attempt.duration_ms

    def attempts(self) -> list[DecisionAttempt]:
        with self._lock:
            ordered = [a for _, a in sorted(self._attempts, key=lambda item: item[0])]
        return [a.model_copy(update={"attempt_number": n}) for n, a in enumerate(ordered, 1)]

    def _started(self) -> datetime:
        if self.settings.timing == "wall":
            return datetime.now(timezone.utc)
        return self.binding.decision_as_of

    def ask(
        self,
        conv: _Conversation,
        purpose: str,
        allowed_actions: list[str],
        allowed_tools: list[str],
        *,
        research_note: bool = False,
    ) -> _Ask:
        """One provider call (with bounded retries for transient provider errors)."""
        role = conv.role
        retries = 0
        while True:
            attempt_id, seq = self._attempt_id(role)
            remaining_out = self.ledger.remaining()["output_tokens"]
            if conv.allowance is not None:
                cap = conv.allowance.caps.get("output_tokens")
                if cap is not None:
                    remaining_out = min(remaining_out, cap - conv.allowance.used["output_tokens"])
            out_tokens = min(self.settings.max_output_tokens_per_call, remaining_out)
            request = ModelRequest(
                system=conv.system,
                messages=tuple(conv.messages),
                metadata=RequestMetadata(
                    self.binding.decision_id, role, purpose, PROMPT_VERSION, seq
                ),
                json_schema=wire_schema(
                    allowed_actions, allowed_tools=allowed_tools, research_note=research_note
                ),
                max_output_tokens=max(out_tokens, 1),
            )
            started = self._started()
            if out_tokens < self.settings.min_output_tokens_per_call:
                self._denied(role, seq, attempt_id, purpose, started, "output_tokens")
                raise BudgetExceeded("output_tokens", f"{role}:{purpose}: output token budget left")
            estimate = worst_case_tokens(request.payload_text())
            cost = self.ledger.estimate_cost(
                self.provider.provider, self.provider.model, estimate, out_tokens
            )
            try:
                reservation = self.ledger.reserve(
                    f"{role}:{purpose}",
                    allowance=conv.allowance,
                    cost=cost or Decimal("0"),
                    generation_calls=1,
                    input_tokens=estimate,
                    output_tokens=out_tokens,
                )
            except BudgetExceeded as exc:
                self._denied(role, seq, attempt_id, purpose, started, exc.resource)
                raise
            # Every reservation is settled exactly once: committed with the actual
            # (reported) usage, or - for an unexpected exception - committed as one
            # attempted call with no reported usage, in the ``finally`` below.
            try:
                response = self.provider.generate(request)
            except ProviderError as exc:
                used_in = exc.input_tokens or 0
                used_out = exc.output_tokens or 0
                model = exc.model or self.provider.model
                self.ledger.commit(
                    reservation,
                    cost=(
                        self.ledger.estimate_cost(self.provider.provider, model, used_in, used_out)
                        if exc.reported_usage
                        else None
                    ),
                    generation_calls=1,
                    input_tokens=used_in,
                    output_tokens=used_out,
                )
                status = "timeout" if exc.kind == "timeout" else "provider_error"
                self._record_attempt(
                    role,
                    seq,
                    DecisionAttempt(
                        attempt_id=attempt_id,
                        attempt_number=seq,
                        agent_role=role,
                        purpose=purpose,
                        provider=self.provider.provider,
                        model=model,
                        input_tokens=used_in,
                        output_tokens=used_out,
                        started_at=started,
                        duration_ms=0,
                        status=status,
                        error=f"{exc.kind}: {str(exc)[:300]}",
                    ),
                    None,
                )
                if self.ledger.exhausted:
                    raise BudgetExceeded(
                        self.ledger.exhausted, "provider usage exceeded a ceiling"
                    ) from exc
                if exc.transient and retries < self.settings.max_provider_retries:
                    retries += 1
                    if self.settings.timing == "wall":
                        delay = min(
                            self.settings.retry_backoff_seconds * retries,
                            max(0.0, self.ledger.seconds_left()),
                        )
                        self._sleep(delay)
                    continue
                raise DecisionFailure(
                    DecisionOutcome.FAILED_DEPENDENCY,
                    [f"{exc.kind}:{role}:{purpose}", str(exc)[:300]],
                ) from exc
            else:
                actual_cost = self.ledger.estimate_cost(
                    response.provider,
                    response.model,
                    response.input_tokens,
                    response.output_tokens,
                )
                self.ledger.commit(
                    reservation,
                    cost=actual_cost,
                    generation_calls=1,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
            finally:
                if not reservation.settled:  # unexpected exception from the provider
                    self.ledger.commit(reservation, generation_calls=1)
            parsed, error = None, None
            try:
                parsed = parse_output(response.text, allowed_actions, research_note=research_note)
            except MalformedOutput as exc:
                error = str(exc)[:500]
            duration = response.latency_ms
            self._record_attempt(
                role,
                seq,
                DecisionAttempt(
                    attempt_id=attempt_id,
                    attempt_number=seq,
                    agent_role=role,
                    purpose=purpose,
                    provider=response.provider,
                    model=response.model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    started_at=started,
                    duration_ms=duration,
                    status="ok" if error is None else "malformed",
                    recorded_response_id=response.recorded_response_id,
                    error=error,
                ),
                response.text,
            )
            if self.ledger.exhausted:
                raise BudgetExceeded(self.ledger.exhausted, "provider usage exceeded a ceiling")
            return _Ask(parsed, error, attempt_id, response)

    def _denied(self, role, seq, attempt_id, purpose, started, resource) -> None:
        self._record_attempt(
            role,
            seq,
            DecisionAttempt(
                attempt_id=attempt_id,
                attempt_number=seq,
                agent_role=role,
                purpose=purpose,
                provider=self.provider.provider,
                model=self.provider.model,
                input_tokens=0,
                output_tokens=0,
                started_at=started,
                duration_ms=0,
                status="denied_budget",
                error=f"budget:{resource}",
            ),
            None,
        )

    # ------------------------------------------------------------------ messages

    ROLE_REQUIRED = {
        "macro_researcher": ("get_market_features",),
        "critical_reviewer": ("get_portfolio_risk",),
    }

    def context(self, role: str, **extra: Any) -> dict[str, Any]:
        b = self.binding
        keep = self.ROLE_REQUIRED.get(role)
        required = {k: v for k, v in self.required.items() if keep is None or k in keep}
        data = {
            "decisionId": b.decision_id,
            "strategyId": b.strategy_id,
            "role": role,
            "decisionAsOf": b.decision_as_of.isoformat(),
            "sessionDate": b.session_date.isoformat() if b.session_date else None,
            "retrievalMode": self.settings.retrieval_mode.value,
            "curveSnapshotId": b.curve_snapshot_id,
            "portfolioSnapshotId": b.portfolio_snapshot_id,
            "marketSnapshotId": b.market_snapshot_id,
            "outputContract": OUTPUT_CONTRACT_VERSION,
            "toolSchemaVersion": TOOL_SCHEMA_VERSION,
            "allowedScenarioIds": sorted(SCENARIO_LIBRARY_V1),
            "required": required,
        }
        data.update(extra)
        return data

    def turn(self, conv, purpose, actions, tools) -> str:
        if conv.allowance is not None:
            caps, used = conv.allowance.caps, conv.allowance.used
            remaining = {k: caps[k] - used[k] for k in sorted(caps)}
        else:
            remaining = self.ledger.remaining()
        return platform_block(
            "turn",
            {
                "role": conv.role,
                "purpose": purpose,
                "allowedActions": actions,
                "allowedTools": tools,
                "instruction": TURN_INSTRUCTIONS.get(purpose, ""),
                "remainingBudget": remaining,
            },
        )

    def new_documents(self, conv: _Conversation, documents) -> list[str]:
        delivered = self.toolbox.delivered_chunks()
        items = []
        for chunk in documents:
            if chunk.chunk_id in conv.shown or chunk.chunk_id not in delivered:
                continue
            conv.shown.add(chunk.chunk_id)
            items.append((delivered[chunk.chunk_id][0], chunk))
        return render_documents(items)

    def all_unseen_documents(self, conv: _Conversation) -> list[str]:
        delivered = self.toolbox.delivered_chunks()
        return self.new_documents(
            conv, [c for _, c in sorted(delivered.values(), key=lambda x: (x[0], x[1].chunk_id))]
        )

    # ------------------------------------------------------------------ helpers

    def converse(
        self,
        conv: _Conversation,
        purpose: str,
        actions: list[str],
        tools: list[str],
        *,
        research_note: bool = False,
        task: bool = False,
    ):
        while True:
            result = self.ask(conv, purpose, actions, tools, research_note=research_note)
            conv.messages.append(ChatMessage("assistant", result.response.text))
            if result.parsed is not None:
                return result.parsed
            if conv.repairs_left <= 0:
                reason = f"malformed_output_after_repairs:{conv.role}:{result.error}"
                if task:
                    raise TaskFailure("failed", reason)
                raise DecisionFailure(DecisionOutcome.FAILED_INVALID_OUTPUT, [reason])
            conv.repairs_left -= 1
            purpose = "repair"
            conv.messages.append(
                ChatMessage(
                    "user",
                    "\n\n".join(
                        [
                            platform_block("validation_feedback", {"errors": [result.error]}),
                            self.turn(conv, purpose, actions, tools),
                        ]
                    ),
                )
            )

    def run_tools(self, conv: _Conversation, calls: CallToolsOut, *, retrieval_limits=None):
        results, documents = [], []
        for call in calls.calls:
            outcome = self.toolbox.call(
                conv.role,
                call.tool,
                call.arguments,
                allowance=conv.allowance,
                retrieval_limits=retrieval_limits,
            )
            results.append(
                {
                    "tool": call.tool,
                    "status": outcome.status,
                    "arguments": float_free(call.arguments),
                    "output": outcome.payload,
                }
            )
            documents.extend(outcome.documents)
        return results, documents

    def required_tools(self, role: str) -> None:
        for tool in ("get_portfolio_risk", "get_market_features"):
            if tool in self.toolbox.allowed_tools(role):
                outcome = self.toolbox.call(role, tool, {})
                if outcome.status == "ok":
                    self.required[tool] = outcome.payload

    def mandatory_retrieval(self, role: str, question: str):
        """Returns delivered documents; raises DecisionFailure for dependency failures."""
        s = self.settings
        try:
            outcome = self.toolbox.call(
                role,
                "retrieve_evidence",
                {"question": question},
                retrieval_limits=(s.initial_max_chunks, s.initial_max_tokens),
            )
        except GraphUnavailable as exc:
            raise DecisionFailure(
                DecisionOutcome.FAILED_DEPENDENCY,
                [
                    "graph_retrieval_unavailable",
                    f"retrieval_mode:{s.retrieval_mode.value}",
                    "no_fallback_to_hybrid_rag_v1",
                    str(exc)[:300],
                ],
            ) from exc
        except EvidenceUnavailable as exc:
            raise DecisionFailure(
                DecisionOutcome.FAILED_DEPENDENCY,
                [
                    "evidence_unavailable",
                    f"retrieval_mode:{s.retrieval_mode.value}",
                    str(exc)[:300],
                ],
            ) from exc
        if outcome.status != "ok":
            raise DecisionFailure(
                DecisionOutcome.FAILED_DEPENDENCY,
                [f"mandatory_retrieval_{outcome.status}", str(outcome.payload.get("error"))[:300]],
            )
        return outcome.documents

    def validate(self, out, attempt_label: str, *, research_note=False) -> ValidationReport:
        vin = ValidationInputs(
            toolbox=self.toolbox,
            retrieval_mode=self.settings.retrieval_mode,
            evidence=self.evidence,
            require_quotes=self.settings.require_quotes,
            support_threshold=self.settings.support_threshold,
            research_note=research_note,
        )
        report = validate_output(out, vin, attempt_label)
        with self._lock:
            proposal = getattr(out, "proposal", None)
            if proposal is not None:
                self.validation.append(
                    ValidationResult(
                        step="original_proposal",
                        passed=True,
                        severity="info",
                        details=[f"attempt:{attempt_label}", canonical_json(proposal.model_dump())],
                    )
                )
            self.validation.extend(report.results)
        self.last_report = report
        return report

    def last_attempt_id(self, role: str) -> str:
        with self._lock:
            return make_id("att", self.binding.decision_id, role, f"{self._seq.get(role, 0):02d}")

    # ------------------------------------------------------------------ synthesis loop

    def synthesize(
        self,
        conv: _Conversation,
        first_message: list[str],
        *,
        tool_turns: int,
        research_note: bool = False,
    ):
        """Tool-selection turns, forced synthesis, validation and repairs."""
        role = conv.role
        tools_all = self.toolbox.allowed_tools(role)
        turns = 0
        purpose_override: Optional[str] = None
        pending = first_message
        while True:
            tools = tools_all if turns < tool_turns and purpose_override is None else []
            actions = ["call_tools", "final"] if tools else ["final"]
            purpose = purpose_override or ("tool_selection" if tools else "synthesis")
            conv.messages.append(
                ChatMessage(
                    "user", "\n\n".join(pending + [self.turn(conv, purpose, actions, tools)])
                )
            )
            parsed = self.converse(conv, purpose, actions, tools, research_note=research_note)
            if isinstance(parsed, CallToolsOut):
                turns += 1
                results, documents = self.run_tools(conv, parsed)
                pending = [platform_block("tool_results", {"results": results})]
                pending += self.new_documents(conv, documents)
                purpose_override = None
                continue
            report = self.validate(parsed, self.last_attempt_id(role), research_note=research_note)
            if report.blocking and conv.repairs_left > 0:
                conv.repairs_left -= 1
                purpose_override = "repair"
                pending = [
                    platform_block(
                        "validation_feedback",
                        {
                            "errors": report.blocking,
                            "invalidIds": report.invalid_ids,
                            "policyRejected": report.policy_rejected,
                        },
                    )
                ]
                continue
            return parsed, report


# --------------------------------------------------------------------------- #
# Outcome mapping
# --------------------------------------------------------------------------- #


def _evidence_outcome(kind: str, settings: AgentSettings) -> DecisionOutcome:
    choice = (
        settings.on_contradictory_evidence
        if kind == "contradictory"
        else (settings.on_insufficient_evidence)
    )
    return (
        DecisionOutcome.REVIEW_REQUIRED
        if choice == "review"
        else DecisionOutcome.ABSTAINED_INSUFFICIENT_EVIDENCE
    )


def map_outcome(parsed: FinalOut, report: ValidationReport, session: DecisionSession):
    settings = session.settings
    if report.blocking:
        return DecisionOutcome.FAILED_INVALID_OUTPUT, list(report.blocking), None, None
    if parsed.status == "contradictory_evidence":
        return _evidence_outcome("contradictory", settings), ["contradictory_evidence"], None, None
    if parsed.status == "insufficient_evidence" or parsed.decision == "abstain":
        return (
            _evidence_outcome("insufficient", settings),
            [f"model_abstained:{parsed.status}"],
            None,
            None,
        )
    if parsed.decision == "hold":
        proposal = report.proposal or Proposal(action=DecisionAction.HOLD)
        evaluation = report.policy_evaluation or session.toolbox.policy_dry_run(
            DecisionAction.HOLD, []
        )
        return DecisionOutcome.COMPLETED_HOLD, ["explicit_hold"], proposal, evaluation
    if report.review_flags:
        return (
            DecisionOutcome.REVIEW_REQUIRED,
            list(report.review_flags),
            report.proposal,
            report.policy_evaluation,
        )
    return (
        DecisionOutcome.COMPLETED_PROPOSAL,
        ["validated_proposal"],
        report.proposal,
        report.policy_evaluation,
    )


def _empty_note(gap: str, run_ids: list[str]) -> ResearchNote:
    return ResearchNote(
        status=ResearchStatus.INSUFFICIENT_EVIDENCE,
        coverage_gaps=[gap],
        retrieval_run_ids=run_ids,
        explanation="Mandatory retrieval delivered no eligible passages; no model call was made.",
    )


# --------------------------------------------------------------------------- #
# Single agent
# --------------------------------------------------------------------------- #


def run_single(session: DecisionSession) -> DecisionRun:
    s = session.settings
    role = "single"
    conv = _Conversation(role, SYSTEM_PROMPTS["single"], repairs_left=s.max_repairs)

    def body():
        session.required_tools(role)
        first = [platform_block("context", session.context(role))]
        if s.retrieval_mode != RetrievalMode.NONE and s.mandatory_retrieval:
            documents = session.mandatory_retrieval(role, s.initial_query)
            if not documents:
                return (
                    _evidence_outcome("insufficient", s),
                    ["mandatory_retrieval_empty"],
                    _empty_note(
                        "mandatory retrieval returned no eligible passages",
                        list(session.toolbox.retrieval_run_ids),
                    ),
                    None,
                    None,
                )
            first += session.new_documents(conv, documents)
        parsed, report = session.synthesize(conv, first, tool_turns=s.max_tool_turns)
        outcome, reasons, proposal, evaluation = map_outcome(parsed, report, session)
        return outcome, reasons, report.note, proposal, evaluation

    return _guard(session, body)


def _guard(session: DecisionSession, body) -> DecisionRun:
    note = proposal = evaluation = None
    try:
        outcome, reasons, note, proposal, evaluation = body()
    except BudgetExceeded as exc:
        session.ledger.mark_exhausted(exc.resource)
        outcome, reasons = DecisionOutcome.FAILED_BUDGET, [
            f"budget_exhausted:{exc.resource}",
            str(exc),
        ]
    except DecisionFailure as failure:
        outcome, reasons = failure.outcome, failure.reasons
    except GraphUnavailable as exc:
        outcome = DecisionOutcome.FAILED_DEPENDENCY
        reasons = ["graph_retrieval_unavailable", "no_fallback_to_hybrid_rag_v1", str(exc)[:300]]
    except EvidenceUnavailable as exc:
        outcome, reasons = DecisionOutcome.FAILED_DEPENDENCY, [
            "evidence_unavailable",
            str(exc)[:300],
        ]
    if note is None and session.last_report is not None:
        note = session.last_report.note
    return DecisionRun(
        outcome=outcome,
        reasons=reasons,
        note=note,
        proposal=proposal,
        policy_evaluation=evaluation,
        attempts=session.attempts(),
        validation=list(session.validation),
        specialist_tasks=sorted(
            session.specialist_tasks, key=lambda t: SPECIALIST_ROLES.index(t.role)
        ),
        latency_ms=session.latency_ms,
        raw_outputs=dict(session.raw_outputs),
    )


# --------------------------------------------------------------------------- #
# Team
# --------------------------------------------------------------------------- #


TOKEN_SHARES = {"macro_researcher": Decimal("0.6"), "critical_reviewer": Decimal("0.4")}
SHARED_BY_WEIGHT = (
    "input_tokens",
    "output_tokens",
    "evidence_calls",
    "unique_evidence_chunks",
    "evidence_tokens",
)


def _split_allowances(session: DecisionSession, roles: list[str]) -> dict[str, TaskAllowance]:
    """Deterministic per-task blocks whose sum never exceeds the remaining budget.

    Call counts are split evenly; token and evidence resources by role weight
    (``TOKEN_SHARES``, renormalized over the accepted roles) because the macro
    researcher reads passages while the reviewer works from exposures.
    """
    remaining = session.ledger.remaining()
    n = max(1, len(roles))
    total = sum((TOKEN_SHARES[r] for r in roles), Decimal(0))
    ordered = sorted(roles, key=lambda r: (-TOKEN_SHARES[r], r))
    caps: dict[str, dict[str, int]] = {r: {} for r in roles}
    for name, value in remaining.items():
        if name in SHARED_BY_WEIGHT:
            parts = {r: int(Decimal(value) * TOKEN_SHARES[r] / total) for r in roles}
        else:
            parts = {r: value // n for r in roles}
        parts[ordered[0]] += value - sum(parts.values())  # remainder to the largest share
        for role in roles:
            caps[role][name] = parts[role]
    out = {role: TaskAllowance(label=f"task:{role}", caps=caps[role]) for role in roles}
    return out


def _report_payload(role: str, status: str, report: Optional[ReportOut], scenarios) -> dict:
    data = {"role": role, "status": status, "scenarios": scenarios}
    if report is not None:
        data.update(
            {
                "findings": report.findings,
                "claims": [c.model_dump() for c in report.claims],
                "citations": [c.model_dump() for c in report.citations],
                "counterevidence": report.counterevidence,
                "coverageGaps": report.coverage_gaps,
                "objections": report.objections,
                "alternativeScenarios": report.alternative_scenarios,
                "unresolvedAssumptions": report.unresolved_assumptions,
                "calculationIds": report.calculation_ids,
            }
        )
    return data


def _run_specialist(
    session: DecisionSession,
    role: str,
    instruction: str,
    allowance: TaskAllowance,
    draft: Optional[dict] = None,
) -> tuple[SpecialistTask, dict]:
    s = session.settings
    tb = session.toolbox
    conv = _Conversation(role, SYSTEM_PROMPTS[role], allowance=allowance, repairs_left=1)
    task_id = make_id("task", session.binding.decision_id, role)
    handoff = sorted({b for b, _ in tb.delivered_chunks().values()})
    status, report, error = "completed", None, None
    scenarios: list[dict] = []
    try:
        parts = [
            platform_block("context", session.context(role)),
            platform_block("task", {"role": role, "instruction": instruction[:800]}),
        ]
        if draft is not None:
            parts.append(platform_block("draft", draft))
        if role == "macro_researcher":
            parts += session.all_unseen_documents(conv)
        else:  # the reviewer works from exposures and the evidence index, not passage text
            delivered = tb.delivered_chunks()
            index = [
                evidence_index_entry(b, c)
                for b, c in sorted(delivered.values(), key=lambda x: (x[0], x[1].chunk_id))
            ]
            if index:
                parts.append(platform_block("evidence_index", index))
        tools_all = tb.allowed_tools(role)
        turns = 0
        pending = parts
        while True:
            tools = tools_all if turns < s.specialist_tool_turns else []
            actions = ["call_tools", "report"] if tools else ["report"]
            conv.messages.append(
                ChatMessage(
                    "user",
                    "\n\n".join(pending + [session.turn(conv, "specialist", actions, tools)]),
                )
            )
            parsed = session.converse(conv, "specialist", actions, tools, task=True)
            if isinstance(parsed, CallToolsOut):
                turns += 1
                results, documents = session.run_tools(conv, parsed)
                scenarios += [
                    r["output"]
                    for r in results
                    if r["tool"] == "run_scenario" and r["status"] == "ok"
                ]
                pending = [platform_block("tool_results", {"results": results})]
                pending += session.new_documents(conv, documents)
                continue
            report = parsed
            break
    except BudgetExceeded as exc:
        status, error = "denied_budget", f"budget:{exc.resource}"
    except TaskFailure as exc:
        status, error = exc.status, exc.reason
    except DecisionFailure as exc:
        if exc.outcome == DecisionOutcome.FAILED_DEPENDENCY and any(
            "graph" in r for r in exc.reasons
        ):
            raise
        status, error = "failed", "; ".join(exc.reasons)[:300]
    findings = [f[:300] for f in (report.findings if report else [])][:6]
    if error:
        findings.append(f"task_error:{error[:200]}")
    usage = allowance.usage()
    task = SpecialistTask(
        task_id=task_id,
        role=role,
        instruction=instruction[:800],
        input_snapshot_ids=[
            x
            for x in [session.binding.portfolio_snapshot_id, session.binding.curve_snapshot_id]
            + handoff
            if x
        ],
        expected_output_schema=f"{OUTPUT_CONTRACT_VERSION}:report",
        budget_reserved=dict(allowance.caps),
        status=status,
        findings=findings,
        claim_ids=[c.claim_id for c in report.claims] if report else [],
        usage=usage,
    )
    return task, _report_payload(role, status, report, scenarios)


def run_team(session: DecisionSession, budget) -> DecisionRun:
    s = session.settings
    role = "lead"
    conv = _Conversation(role, SYSTEM_PROMPTS["lead"], repairs_left=s.max_repairs)
    tb = session.toolbox

    def body():
        session.required_tools(role)
        first = [platform_block("context", session.context(role))]
        documents = session.mandatory_retrieval(role, s.initial_query)
        if not documents:
            return (
                _evidence_outcome("insufficient", s),
                ["mandatory_retrieval_empty"],
                _empty_note(
                    "mandatory retrieval returned no eligible passages", list(tb.retrieval_run_ids)
                ),
                None,
                None,
            )
        # The lead assigns tasks from the evidence index; passage text reaches the lead
        # once, at synthesis, together with anything the specialists retrieved.
        first.append(
            platform_block(
                "evidence_index",
                [
                    evidence_index_entry(b, c)
                    for b, c in sorted(
                        tb.delivered_chunks().values(), key=lambda x: (x[0], x[1].chunk_id)
                    )
                ],
            )
        )
        actions = ["delegate", "decline_delegation"]
        conv.messages.append(
            ChatMessage(
                "user", "\n\n".join(first + [session.turn(conv, "task_assignment", actions, [])])
            )
        )
        assignment = session.converse(conv, "task_assignment", actions, [])
        accepted: list[tuple[str, str]] = []
        if isinstance(assignment, DelegateOut):
            for index, task in enumerate(assignment.tasks):
                reason = None
                if budget.max_delegation_depth < 1:
                    reason = "delegation_depth_limit"
                elif task.role not in SPECIALIST_ROLES:
                    reason = "unregistered_role"
                elif task.role in {r for r, _ in accepted}:
                    reason = "duplicate_role"
                elif len(accepted) >= budget.max_specialist_invocations:
                    reason = "invocation_limit"
                if reason is None:
                    accepted.append((task.role, task.instruction))
                    continue
                session.specialist_tasks.append(
                    SpecialistTask(
                        task_id=make_id("task", session.binding.decision_id, f"skipped{index}"),
                        role=task.role if task.role in SPECIALIST_ROLES else "macro_researcher",
                        instruction=f"[{task.role}] {task.instruction}"[:800],
                        input_snapshot_ids=[],
                        expected_output_schema=f"{OUTPUT_CONTRACT_VERSION}:report",
                        budget_reserved={},
                        status="skipped",
                        findings=[f"skipped:{reason}"],
                    )
                )
        reports: list[dict] = []
        if accepted:
            reports = _delegate(session, conv, accepted)
        tb.phase = session.phase = 2
        pending = [platform_block("specialist_reports", {"reports": reports})]
        pending += session.all_unseen_documents(conv)
        parsed, report = session.synthesize(conv, pending, tool_turns=0)
        outcome, reasons, proposal, evaluation = map_outcome(parsed, report, session)
        return outcome, reasons, report.note, proposal, evaluation

    return _guard(session, body)


def _delegate(session: DecisionSession, conv: _Conversation, accepted) -> list[dict]:
    s = session.settings
    tb = session.toolbox
    # Reserve the lead's final synthesis capacity before any specialist work.
    unseen = render_documents(
        sorted(tb.delivered_chunks().values(), key=lambda x: (x[0], x[1].chunk_id))
    )
    estimate = (
        worst_case_tokens("\n".join([m.content for m in conv.messages] + unseen))
        + s.lead_synthesis_input_reserve
    )
    hold = session.ledger.reserve(
        "lead:synthesis_reserve",
        generation_calls=1,
        input_tokens=estimate,
        output_tokens=s.max_output_tokens_per_call,
    )
    roles = [r for r, _ in accepted]
    instructions = dict(accepted)
    tb.phase = session.phase = 1
    results: dict[str, tuple[SpecialistTask, dict]] = {}
    try:
        if s.reviewer_workflow == "parallel_v1":
            allowances = _split_allowances(session, roles)
            tb.parallel = session.parallel = True
            try:
                with ThreadPoolExecutor(max_workers=len(roles)) as pool:
                    futures = {
                        role: pool.submit(
                            _run_specialist, session, role, instructions[role], allowances[role]
                        )
                        for role in roles
                    }
                    for role in roles:
                        results[role] = futures[role].result()
            finally:
                tb.parallel = session.parallel = False
        else:  # sequential_on_draft_v1: allowances are computed just before each task
            if "macro_researcher" in instructions:
                allowance = _split_allowances(session, roles)["macro_researcher"]
                results["macro_researcher"] = _run_specialist(
                    session, "macro_researcher", instructions["macro_researcher"], allowance
                )
            if "critical_reviewer" in instructions:
                draft = _lead_draft(session, conv, results)
                allowance = _split_allowances(session, ["critical_reviewer"])["critical_reviewer"]
                results["critical_reviewer"] = _run_specialist(
                    session,
                    "critical_reviewer",
                    instructions["critical_reviewer"],
                    allowance,
                    draft=draft,
                )
    finally:
        session.ledger.release(hold)
    reports = []
    for role in SPECIALIST_ROLES:
        if role in results:
            task, payload = results[role]
            session.specialist_tasks.append(task)
            reports.append(payload)
    return reports


def _lead_draft(session: DecisionSession, conv: _Conversation, results) -> dict:
    """Sequential variant: the lead drafts a candidate the reviewer challenges."""
    reports = [results[r][1] for r in SPECIALIST_ROLES if r in results]
    pending = [platform_block("specialist_reports", {"reports": reports})]
    pending += session.all_unseen_documents(conv)
    conv.messages.append(
        ChatMessage("user", "\n\n".join(pending + [session.turn(conv, "synthesis", ["final"], [])]))
    )
    draft = session.converse(conv, "synthesis", ["final"], [])
    return {"draft": draft.model_dump(), "note": "candidate for review; not final"}


# --------------------------------------------------------------------------- #
# Research note (no order authority)
# --------------------------------------------------------------------------- #


def run_research_note(session: DecisionSession, question: str) -> DecisionRun:
    s = session.settings
    role = "research_note"
    conv = _Conversation(role, SYSTEM_PROMPTS["research_note"], repairs_left=s.max_repairs)

    def body():
        session.required_tools(role)
        first = [platform_block("context", session.context(role, question=question))]
        documents = session.mandatory_retrieval(role, question)
        if not documents:
            return (
                DecisionOutcome.ABSTAINED_INSUFFICIENT_EVIDENCE,
                ["mandatory_retrieval_empty"],
                _empty_note(
                    "retrieval returned no eligible passages",
                    list(session.toolbox.retrieval_run_ids),
                ),
                None,
                None,
            )
        first += session.new_documents(conv, documents)
        parsed, report = session.synthesize(
            conv, first, tool_turns=min(1, s.max_tool_turns), research_note=True
        )
        if report.blocking:
            return (
                DecisionOutcome.FAILED_INVALID_OUTPUT,
                list(report.blocking),
                report.note,
                None,
                None,
            )
        outcome = {
            "supported": DecisionOutcome.COMPLETED_HOLD,
            "insufficient_evidence": DecisionOutcome.ABSTAINED_INSUFFICIENT_EVIDENCE,
            "contradictory_evidence": DecisionOutcome.REVIEW_REQUIRED,
        }[parsed.status]
        return outcome, [f"research_note:{parsed.status}"], report.note, None, None

    return _guard(session, body)
