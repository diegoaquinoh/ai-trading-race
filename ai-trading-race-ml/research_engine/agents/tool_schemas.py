"""Typed tool request schemas (``fi-agent-tools-v1``, spec 10.5).

Every tool argument model forbids extra fields. Snapshot, curve, cutoff, index
and portfolio references are *not* arguments: the toolbox binds them to the
frozen decision snapshot, so a model cannot point a tool at today's mutable
state, another portfolio or a later index. No tool accepts SQL, Cypher, Python
or URLs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from research_engine.contracts.common import content_hash

TOOL_SCHEMA_VERSION = "fi-agent-tools-v1"


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InstrumentTermsArgs(_Args):
    security_ids: list[str] = Field(min_length=1, max_length=12)


class MarketFeaturesArgs(_Args):
    pass


class ValuationArgs(_Args):
    security_ids: list[str] = Field(min_length=1, max_length=12)


class PortfolioRiskArgs(_Args):
    scenario_ids: list[str] = Field(default_factory=list, max_length=6)


class RunScenarioArgs(_Args):
    scenario_id: str = Field(min_length=1, max_length=64)


class RetrieveEvidenceArgs(_Args):
    question: str = Field(min_length=3, max_length=400)


class ExpandEvidenceGraphArgs(_Args):
    seed_ids: list[str] = Field(min_length=1, max_length=8)
    question: str = Field(default="", max_length=400)


class WeightArg(_Args):
    security_id: str
    weight: str

    @field_validator("weight", mode="before")
    @classmethod
    def _weight_text(cls, value):
        if isinstance(value, bool):
            raise ValueError("weight must be a decimal string")
        if isinstance(value, (int, float)):
            return repr(value) if isinstance(value, float) else str(value)
        return value


class ProposeTargetsArgs(_Args):
    action: Literal["HOLD", "REBALANCE"]
    target_weights: list[WeightArg] = Field(default_factory=list, max_length=40)
    supporting_claim_ids: list[str] = Field(default_factory=list, max_length=20)
    supporting_calculation_ids: list[str] = Field(default_factory=list, max_length=40)


TOOL_ARGS: dict[str, type[_Args]] = {
    "get_instrument_terms": InstrumentTermsArgs,
    "get_market_features": MarketFeaturesArgs,
    "get_valuation": ValuationArgs,
    "get_portfolio_risk": PortfolioRiskArgs,
    "run_scenario": RunScenarioArgs,
    "retrieve_evidence": RetrieveEvidenceArgs,
    "expand_evidence_graph": ExpandEvidenceGraphArgs,
    "propose_targets": ProposeTargetsArgs,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_instrument_terms": "Versioned contractual terms for admitted security ids.",
    "get_market_features": (
        "Eligible curve levels and changes plus numerical macro features for the frozen "
        "decision snapshot. Never returns document text."
    ),
    "get_valuation": "Engine-verified prices and per-100 risk at the frozen curve.",
    "get_portfolio_risk": "Own frozen portfolio exposure, funding and optional scenario P&L.",
    "run_scenario": "Deterministic full repricing of the own portfolio under an approved scenario.",
    "retrieve_evidence": "Eligible evidence passages (untrusted data) at the decision cutoff.",
    "expand_evidence_graph": (
        "Bounded source-backed graph expansion from seed ids already delivered to this decision."
    ),
    "propose_targets": "Dry-run policy check of target weights. Proposal only; never executes.",
}

EVIDENCE_TOOLS = frozenset({"retrieve_evidence", "expand_evidence_graph"})
PROPOSAL_TOOLS = frozenset({"propose_targets"})
NUMERICAL_TOOLS = frozenset(TOOL_ARGS) - EVIDENCE_TOOLS - PROPOSAL_TOOLS


def tool_schema_hash() -> str:
    return content_hash(
        {name: model.model_json_schema() for name, model in sorted(TOOL_ARGS.items())},
        allow_floats=True,
    )
