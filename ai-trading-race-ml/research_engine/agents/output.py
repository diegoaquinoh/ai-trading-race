"""Structured model output contract (``agent-output-v1``).

Every model turn returns one JSON object whose ``action`` is one of the actions
the workflow allowed for that turn:

* ``call_tools`` - typed tool calls (tool-selection turns);
* ``final`` - research note, explicit decision (``propose``/``hold``/``abstain``)
  and optional proposal (synthesis turns);
* ``delegate`` / ``decline_delegation`` - lead task assignment (llm_team);
* ``report`` - specialist findings (macro researcher, critical reviewer).

Outputs contain findings, claims, citations, calculations and concise
explanations only: no chain-of-thought is requested or stored. Parsing rejects
NaN/Infinity, unknown fields and actions outside the allowed set; any failure
is a malformed attempt that may be repaired within the decision budget.

:func:`wire_schema` builds the provider-facing JSON schema (objects closed with
``additionalProperties: false``, every property required, numeric/string
constraints removed) rooted at ``{"output": <action object>}``; the parser
accepts both the bare action object and that wrapper.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Iterable, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .tool_schemas import TOOL_ARGS

OUTPUT_CONTRACT_VERSION = "agent-output-v1"


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CitationOut(_Out):
    citation_id: str
    bundle_id: str
    chunk_id: str
    document_version_id: str
    quote: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None


class ClaimOut(_Out):
    claim_id: str
    text: str
    citation_ids: list[str]
    material: bool = True


class FindingOut(_Out):
    finding_id: str
    text: str
    calculation_ids: list[str]
    input_snapshot_ids: list[str] = Field(default_factory=list)


class HypothesisOut(_Out):
    hypothesis_id: str
    text: str
    assumptions: list[str]
    scenario_ids: list[str] = Field(default_factory=list)
    supporting_citation_ids: list[str] = Field(default_factory=list)


class WeightOut(_Out):
    security_id: str
    weight: str

    @field_validator("weight", mode="before")
    @classmethod
    def _weight_text(cls, value):
        if isinstance(value, bool):
            raise ValueError("weight must be a decimal string")
        if isinstance(value, float):
            return repr(value)
        if isinstance(value, int):
            return str(value)
        return value


class ProposalOut(_Out):
    action: Literal["HOLD", "REBALANCE"]
    target_weights: list[WeightOut] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    supporting_calculation_ids: list[str] = Field(default_factory=list)


class _NoteFields(_Out):
    status: Literal["supported", "insufficient_evidence", "contradictory_evidence"]
    claims: list[ClaimOut] = Field(default_factory=list)
    citations: list[CitationOut] = Field(default_factory=list)
    numerical_findings: list[FindingOut] = Field(default_factory=list)
    hypotheses: list[HypothesisOut] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    explanation: str


class FinalOut(_NoteFields):
    action: Literal["final"]
    decision: Literal["propose", "hold", "abstain"]
    proposal: Optional[ProposalOut] = None


class NoteOut(_NoteFields):
    """Research-note synthesis: no decision, no proposal, no order authority."""

    action: Literal["final"]


class ToolCallOut(_Out):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CallToolsOut(_Out):
    action: Literal["call_tools"]
    calls: list[ToolCallOut] = Field(min_length=1, max_length=4)
    reason: str = ""


class TaskOut(_Out):
    role: str
    instruction: str


class DelegateOut(_Out):
    action: Literal["delegate"]
    tasks: list[TaskOut] = Field(min_length=1, max_length=4)
    reason: str = ""


class DeclineOut(_Out):
    action: Literal["decline_delegation"]
    reason: str = ""


class ReportOut(_Out):
    action: Literal["report"]
    findings: list[str]
    claims: list[ClaimOut] = Field(default_factory=list)
    citations: list[CitationOut] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    alternative_scenarios: list[str] = Field(default_factory=list)
    unresolved_assumptions: list[str] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)


AgentOutput = Union[FinalOut, NoteOut, CallToolsOut, DelegateOut, DeclineOut, ReportOut]

ACTION_MODELS: dict[str, type[_Out]] = {
    "final": FinalOut,
    "call_tools": CallToolsOut,
    "delegate": DelegateOut,
    "decline_delegation": DeclineOut,
    "report": ReportOut,
}


class MalformedOutput(ValueError):
    """The model output is not a valid action object for this turn."""


def _reject_constant(name: str):
    raise MalformedOutput(f"non-finite JSON number {name} is not permitted")


_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*)\n\s*```\s*$", re.DOTALL)


def parse_output(
    text: str,
    allowed_actions: Iterable[str],
    *,
    research_note: bool = False,
    allowed_tools: Iterable[str] = (),
) -> AgentOutput:
    """Parse and validate one model response against the turn's allowed actions."""
    allowed = set(allowed_actions)
    body = text.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        data = json.loads(body, parse_constant=_reject_constant)
    except MalformedOutput:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MalformedOutput(f"response is not valid JSON: {exc}") from exc
    if isinstance(data, dict) and set(data) == {"output"} and isinstance(data["output"], dict):
        data = data["output"]
    if not isinstance(data, dict):
        raise MalformedOutput("response must be a JSON object")
    action = data.get("action")
    if action not in allowed:
        raise MalformedOutput(
            f"action {action!r} is not allowed in this turn; allowed: {sorted(allowed)}"
        )
    model = NoteOut if (action == "final" and research_note) else ACTION_MODELS[action]
    try:
        parsed = model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()[:8]
        )
        raise MalformedOutput(f"schema violation: {problems}") from exc
    # Tool names and arguments are checked by the toolbox, which records unknown or
    # disallowed tools as denied_policy traces instead of silently dropping them.
    return parsed


# --------------------------------------------------------------------------- #
# Provider-facing JSON schema
# --------------------------------------------------------------------------- #

_DROP = {
    "title",
    "default",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "pattern",
    "minItems",
    "maxItems",
    "format",
    "description",
}


def _strict(node: Any) -> Any:
    if isinstance(node, dict):
        out = {k: _strict(v) for k, v in node.items() if k not in _DROP}
        if out.get("type") == "object" or "properties" in out:
            props = out.get("properties", {})
            out["type"] = "object"
            out["properties"] = props
            out["required"] = sorted(props)
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strict(v) for v in node]
    return node


def _collect(schema: dict, defs: dict) -> dict:
    schema = copy.deepcopy(schema)
    for name, value in schema.pop("$defs", {}).items():
        defs[name] = value
    return schema


def _tool_call_schema(tool: str, defs: dict) -> dict:
    args = _collect(TOOL_ARGS[tool].model_json_schema(), defs)
    return {
        "type": "object",
        "properties": {"tool": {"type": "string", "enum": [tool]}, "arguments": args},
    }


def wire_schema(
    allowed_actions: Iterable[str], *, allowed_tools: Iterable[str] = (), research_note=False
) -> dict:
    defs: dict[str, Any] = {}
    variants = []
    for action in sorted(set(allowed_actions)):
        if action == "call_tools":
            calls = [_tool_call_schema(t, defs) for t in sorted(set(allowed_tools))]
            if not calls:
                continue
            variants.append(
                {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["call_tools"]},
                        "calls": {"type": "array", "items": {"anyOf": calls}},
                        "reason": {"type": "string"},
                    },
                }
            )
            continue
        model = NoteOut if (action == "final" and research_note) else ACTION_MODELS[action]
        variants.append(_collect(model.model_json_schema(), defs))
    root: dict[str, Any] = {
        "type": "object",
        "properties": {"output": variants[0] if len(variants) == 1 else {"anyOf": variants}},
    }
    if defs:
        root["$defs"] = defs
    return _strict(root)
