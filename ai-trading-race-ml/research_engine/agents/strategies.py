"""LLM strategies ``llm_market``, ``llm_rag``, ``llm_graph`` and ``llm_team`` (spec 10.1).

All four share the base prompt set, output contract, validation pipeline,
risk policy and provider/model, so the retrieval and delegation comparisons
are controlled (spec 10.2):

==============  ==========  ===============  =========================================
strategy        kind        retrieval        tools
==============  ==========  ===============  =========================================
llm_market      single      none             numerical tools only (no document text)
llm_rag         single      hybrid_rag_v1    + retrieve_evidence (mandatory first call)
llm_graph       single      graph_rag_v1     + expand_evidence_graph
llm_team        team        graph_rag_v1     lead + macro_researcher + critical_reviewer
==============  ==========  ===============  =========================================

Construct with :func:`create_llm_strategy` (provider/evidence injection) or
through the experiment registry (``create_strategy("llm_rag", config)``) after
``import research_engine.agents``; registry construction resolves the provider
from ``config["provider"]`` (default ``reference``) and opens the default
offline evidence index for evidence strategies.

The strategy config records provider label, pinned model id, prompt version,
tool schema version, retrieval mode, index build and workflow limits; its hash
is the strategy config hash. The response *source* (live provider, recording
capture or recorded replay) is a runtime injection and not part of the config,
so a recorded replay reproduces the captured StrategyResults exactly.
"""

from __future__ import annotations

import json
import os
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from research_engine import ENGINE_VERSION
from research_engine.contracts.common import content_hash
from research_engine.contracts.decisions import (
    DecisionBudget,
    DecisionOutcome,
    RetrievalMode,
    StrategyKind,
    StrategyResult,
    VersionInfo,
)
from research_engine.contracts.portfolio import DecisionAction
from research_engine.experiments.strategy import (
    StrategyContext,
    config_hash,
    make_result,
    register_strategy,
)
from research_engine.pricing.calc_store import CalculationStore

from .budget import REFERENCE_ZERO_COST, BudgetLedger, PriceSchedule
from .output import OUTPUT_CONTRACT_VERSION
from .ports import EvidencePort, open_default_evidence_port
from .prompts import INITIAL_QUERY_TEMPLATES, PROMPT_SET_HASH, PROMPT_VERSION
from .providers import ModelProvider, build_provider
from .result import completion_time, result_signing_key, seal_result
from .tool_schemas import EVIDENCE_TOOLS, TOOL_ARGS, TOOL_SCHEMA_VERSION, tool_schema_hash
from .tools import DecisionToolbox, MacroFeatureSource, ToolBinding
from .validation import SUPPORT_CLASSIFIER_VERSION, VALIDATION_PIPELINE_VERSION
from .workflow import (
    REVIEWER_WORKFLOWS,
    SPECIALIST_ROLES,
    AgentSettings,
    DecisionRun,
    DecisionSession,
    run_single,
    run_team,
)

LLM_STRATEGY_IDS = ("llm_graph", "llm_market", "llm_rag", "llm_team")
STRATEGY_VERSIONS = {
    "llm_market": ("llm-market-v1", RetrievalMode.NONE, False),
    "llm_rag": ("llm-rag-v1", RetrievalMode.HYBRID_RAG, False),
    "llm_graph": ("llm-graph-v1", RetrievalMode.GRAPH_RAG, False),
    "llm_team": ("llm-team-v1", RetrievalMode.GRAPH_RAG, True),
}
EVIDENCE_HOME_ENV = "FI_RESEARCH_HOME"

_evidence_cache: dict[str, EvidencePort] = {}
_evidence_lock = threading.Lock()


def default_evidence_port(home: Optional[str] = None) -> EvidencePort:
    key = home or os.environ.get(EVIDENCE_HOME_ENV) or ""
    with _evidence_lock:
        if key not in _evidence_cache:
            _evidence_cache[key] = open_default_evidence_port(key or None)
        return _evidence_cache[key]


def _flag(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


class LlmStrategy:
    invested = True

    def __init__(
        self,
        strategy_id: str,
        config: Optional[dict] = None,
        *,
        provider: Optional[ModelProvider] = None,
        evidence: Optional[EvidencePort] = None,
        price_schedule: Optional[PriceSchedule] = None,
        calc_store: Optional[CalculationStore] = None,
        macro_source: Optional[MacroFeatureSource] = None,
        signing_key: Optional[bytes] = None,
        audit_dir: Optional[Path] = None,
    ):
        if strategy_id not in STRATEGY_VERSIONS:
            raise KeyError(f"unknown LLM strategy {strategy_id!r}")
        version, mode, team = STRATEGY_VERSIONS[strategy_id]
        cfg = dict(config or {})
        self.strategy_id = strategy_id
        self.kind = StrategyKind.SPECIALIST_TEAM if team else StrategyKind.SINGLE_AGENT
        if provider is None:
            provider = build_provider(
                cfg.get("provider", "reference"),
                model=cfg.get("modelId"),
                recordings=cfg.get("recordingsDir"),
                base_url=cfg.get("baseUrl"),
            )
        self.provider = provider
        if mode != RetrievalMode.NONE and evidence is None:
            evidence = default_evidence_port(cfg.get("evidenceHome"))
        self.evidence = evidence if mode != RetrievalMode.NONE else None
        self.price_schedule = price_schedule
        if self.price_schedule is None and provider.provider == "reference":
            self.price_schedule = REFERENCE_ZERO_COST
        self.calc_store = calc_store
        self.macro_source = macro_source
        self.signing_key = signing_key
        self.audit_dir = Path(audit_dir) if audit_dir else None
        workflow = cfg.get("reviewerWorkflow", "parallel_v1")
        if workflow not in REVIEWER_WORKFLOWS:
            raise ValueError(f"reviewerWorkflow must be one of {REVIEWER_WORKFLOWS}")
        tools = frozenset(TOOL_ARGS) - (
            EVIDENCE_TOOLS if mode == RetrievalMode.NONE else frozenset()
        )
        template_id = cfg.get("initialQueryTemplate", "policy-outlook-v1")
        self.settings = AgentSettings(
            strategy_id=strategy_id,
            retrieval_mode=mode,
            strategy_tools=tools,
            team=team,
            mandatory_retrieval=_flag(cfg.get("mandatoryRetrieval"), True),
            initial_query=INITIAL_QUERY_TEMPLATES[template_id],
            initial_max_chunks=int(cfg.get("initialMaxChunks", 6)),
            initial_max_tokens=int(cfg.get("initialMaxEvidenceTokens", 4000)),
            max_tool_turns=int(cfg.get("maxToolTurns", 2)),
            specialist_tool_turns=int(cfg.get("specialistToolTurns", 1)),
            max_repairs=int(cfg.get("maxRepairs", 2)),
            max_provider_retries=int(cfg.get("maxProviderRetries", 1)),
            max_output_tokens_per_call=int(cfg.get("maxOutputTokensPerCall", 2048)),
            on_insufficient_evidence=cfg.get("onInsufficientEvidence", "abstain"),
            on_contradictory_evidence=cfg.get("onContradictoryEvidence", "review"),
            support_threshold=Decimal(str(cfg.get("supportThreshold", "0.5"))),
            require_quotes=_flag(cfg.get("requireQuotes"), True),
            timing=cfg.get("timing", "logical"),
            reviewer_workflow=workflow,
        )
        s = self.settings
        self.config: dict[str, Any] = {
            "version": version,
            "strategyKind": self.kind.value,
            "provider": provider.provider,
            "modelId": provider.model,
            "promptVersion": PROMPT_VERSION,
            "toolSchemaVersion": TOOL_SCHEMA_VERSION,
            "outputContract": OUTPUT_CONTRACT_VERSION,
            "validationPipeline": VALIDATION_PIPELINE_VERSION,
            "supportClassifier": SUPPORT_CLASSIFIER_VERSION,
            "supportThreshold": str(s.support_threshold),
            "requireQuotes": s.require_quotes,
            "retrievalMode": mode.value,
            "mandatoryRetrieval": s.mandatory_retrieval and mode != RetrievalMode.NONE,
            "initialQueryTemplate": template_id,
            "initialMaxChunks": s.initial_max_chunks,
            "initialMaxEvidenceTokens": s.initial_max_tokens,
            "maxToolTurns": s.max_tool_turns,
            "maxRepairs": s.max_repairs,
            "maxProviderRetries": s.max_provider_retries,
            "maxOutputTokensPerCall": s.max_output_tokens_per_call,
            "onInsufficientEvidence": s.on_insufficient_evidence,
            "onContradictoryEvidence": s.on_contradictory_evidence,
            "timing": s.timing,
            "indexBuildId": self.evidence.index_build_id if self.evidence else None,
            "evidenceSnapshotId": self.evidence.evidence_snapshot_id if self.evidence else None,
        }
        if team:
            self.config.update(
                {
                    "reviewerWorkflow": workflow,
                    "specialistRoles": list(SPECIALIST_ROLES),
                    "specialistToolTurns": s.specialist_tool_turns,
                }
            )
        for key in ("maxCostUsd", "priceScheduleId"):
            if key in cfg:
                self.config[key] = str(cfg[key])
        if self.price_schedule is not None:
            self.config["priceScheduleId"] = self.price_schedule.schedule_id

    @property
    def deterministic(self) -> bool:
        return bool(self.provider.deterministic)

    # ------------------------------------------------------------------ helpers

    def versions(self) -> VersionInfo:
        return VersionInfo(
            provider=self.provider.provider,
            model=self.provider.model,
            prompt_version=PROMPT_VERSION,
            tool_schema_version=TOOL_SCHEMA_VERSION,
            engine_version=ENGINE_VERSION,
            evidence_snapshot_id=self.config.get("evidenceSnapshotId"),
            index_build_id=self.config.get("indexBuildId"),
            retrieval_mode=self.settings.retrieval_mode,
            strategy_config_hash=config_hash(self.config),
        )

    def budget(self, request_budget: DecisionBudget) -> DecisionBudget:
        update = {}
        if request_budget.max_cost_usd is None and "maxCostUsd" in self.config:
            update["max_cost_usd"] = Decimal(self.config["maxCostUsd"])
        if request_budget.price_schedule_id is None and self.price_schedule is not None:
            update["price_schedule_id"] = self.price_schedule.schedule_id
        return request_budget.model_copy(update=update) if update else request_budget

    def _input_hashes(self, ctx: StrategyContext, bundle_ids: list[str]) -> dict[str, str]:
        hashes = dict(ctx.input_hashes)
        hashes.update(
            {
                "strategyConfig": config_hash(self.config),
                "promptSet": PROMPT_SET_HASH,
                "toolSchema": tool_schema_hash(),
                "evidenceBundles": content_hash(sorted(bundle_ids)),
            }
        )
        return hashes

    def _seal(self, result: StrategyResult) -> StrategyResult:
        return seal_result(result, self.signing_key or result_signing_key())

    def _simple(self, ctx, outcome, reasons, *, action=None, targets=None) -> StrategyResult:
        result = make_result(
            ctx,
            self,
            outcome,
            action=action,
            targets=targets,
            reasons=reasons,
            versions=self.versions(),
        )
        result = result.model_copy(update={"input_hashes": self._input_hashes(ctx, [])})
        return self._seal(result)

    # ------------------------------------------------------------------ decide

    def decide(self, ctx: StrategyContext) -> StrategyResult:
        if not ctx.initialized():
            if not ctx.bootstrap_targets:
                return self._simple(
                    ctx, DecisionOutcome.FAILED_DEPENDENCY, ["bootstrap_allocation_unavailable"]
                )
            from research_engine.experiments.baselines import BOOTSTRAP_ALLOCATION_VERSION

            return self._simple(
                ctx,
                DecisionOutcome.COMPLETED_PROPOSAL,
                [BOOTSTRAP_ALLOCATION_VERSION, "common_bootstrap_no_model_call"],
                action=DecisionAction.BOOTSTRAP,
                targets=list(ctx.bootstrap_targets),
            )
        budget = self.budget(ctx.request.budget)
        live_priced = self.provider.priced and not getattr(self.provider, "replay", False)
        if live_priced and (
            budget.max_cost_usd is None
            or self.price_schedule is None
            or self.price_schedule.price(self.provider.provider, self.provider.model) is None
        ):
            return self._simple(
                ctx,
                DecisionOutcome.FAILED_DEPENDENCY,
                ["price_schedule_and_monetary_ceiling_required_for_priced_runs"],
            )
        snapshot = ctx.snapshot
        if not snapshot.complete:
            return self._simple(
                ctx,
                DecisionOutcome.FAILED_DEPENDENCY,
                ["decision_snapshot_incomplete"] + list(snapshot.reasons),
            )
        ledger = BudgetLedger(budget, price_schedule=self.price_schedule)
        binding = ToolBinding.from_context(ctx, macro_source=self.macro_source)
        toolbox = DecisionToolbox(
            binding,
            ledger,
            strategy_tools=self.settings.strategy_tools,
            evidence=self.evidence,
            retrieval_mode=self.settings.retrieval_mode,
            calc_store=self.calc_store,
            timing=self.settings.timing,
        )
        session = DecisionSession(
            self.settings, self.provider, toolbox, ledger, evidence=self.evidence
        )
        run = run_team(session, budget) if self.settings.team else run_single(session)
        result = self.assemble(ctx, run, toolbox, ledger)
        if self.audit_dir is not None:
            self._write_audit(result, run)
        return result

    def assemble(self, ctx, run: DecisionRun, toolbox: DecisionToolbox, ledger) -> StrategyResult:
        bundle_ids = sorted(toolbox.bundles)
        traces = toolbox.traces()
        tool_ms = sum(t.duration_ms for t in traces)
        result = StrategyResult(
            run_id=ctx.request.run_id,
            cycle_id=ctx.request.cycle_id,
            decision_id=ctx.request.decision_id,
            strategy_id=self.strategy_id,
            strategy_kind=self.kind,
            repetition=ctx.request.repetition,
            request_hash=ctx.request_hash,
            input_hashes=self._input_hashes(ctx, bundle_ids),
            outcome=run.outcome,
            completed_at=completion_time(
                ctx.request.decision_as_of, run.latency_ms + tool_ms, self.settings.timing
            ),
            reasons=run.reasons,
            proposal=run.proposal,
            research_note=run.note,
            validation=run.validation,
            policy_evaluation=run.policy_evaluation,
            attempts=run.attempts,
            tool_traces=traces,
            specialist_tasks=run.specialist_tasks,
            usage=ledger.usage(duration_ms=run.latency_ms + tool_ms),
            versions=self.versions(),
            evidence_bundle_ids=bundle_ids,
        )
        return self._seal(result)

    def _write_audit(self, result: StrategyResult, run: DecisionRun) -> None:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        safe = result.decision_id.replace(":", "_")
        payload = {
            "decisionId": result.decision_id,
            "resultHash": result.result_hash,
            "rawOutputs": run.raw_outputs,
            "note": "raw model outputs per attempt (original proposals included); no "
            "chain-of-thought is requested or stored",
        }
        (self.audit_dir / f"{safe}.json").write_text(json.dumps(payload, indent=2, sort_keys=True))


def create_llm_strategy(strategy_id: str, config: Optional[dict] = None, **kwargs) -> LlmStrategy:
    """Build an LLM strategy with an injected provider/evidence port (runner, FastAPI)."""
    return LlmStrategy(strategy_id, config, **kwargs)


def build_llm_strategies(
    strategy_ids=LLM_STRATEGY_IDS, config: Optional[dict] = None, **kwargs
) -> dict[str, LlmStrategy]:
    return {sid: LlmStrategy(sid, config, **kwargs) for sid in strategy_ids}


for _sid in LLM_STRATEGY_IDS:
    register_strategy(_sid, lambda cfg, _sid=_sid: LlmStrategy(_sid, cfg))
