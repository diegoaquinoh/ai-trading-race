"""Recorded demo experiment and bundle (spec 17.6, 6.5, 15.4; milestone M7).

The demo experiment ``fi-demo-2024q1`` replays 2024-01-02 .. 2024-03-29 in
synthetic-curve mode with seven competitors (``cash``, ``static_ladder``,
``quant_duration``, ``llm_market``, ``llm_rag``, ``llm_graph``, ``llm_team``) on
the budget-matched track, repetition 0. The window covers the 31 January and
20 March 2024 FOMC statements and the minutes released on 3 January and
21 February 2024.

AI strategies use provider ``reference`` (model ``reference-heuristic-v1``), a
deterministic rule-based policy model. It is **not** a hosted LLM; every
artifact says so. Stochastic repetitions do not apply to it (spec 16.2).

:func:`build_demo` writes ``fixtures/demo/<experiment-id>/``:

* ``definition.json`` - registered experiment definition (spec 16.1), hashed;
* ``responses/`` - recorded reference-model responses (recorded-responses-v1);
* ``capture/`` - config + finalized manifest of the capture run
  (``fresh_inference`` of the reference model through a recording provider);
* ``run/`` - the canonical **recorded-response replay** run
  (``recorded_replay`` / ``replay_source=recorded_responses``): config,
  finalized manifest, ``outcomes.jsonl`` (StrategyResults), ``checkpoint.json``
  and ``commits.jsonl.gz`` (the transitions log);
* ``report/`` - ``report.json`` + ``report.md`` (financial, risk, cost, failure,
  evidence, usage and completeness sections, limitations);
* ``evidence/`` - RAG versus Graph RAG delivered passages for each
  policy-document event in the window;
* ``walkthrough.json`` - the spec 17.6 demo script resolved to artifacts;
* ``failure-injection/`` - a separately labelled run with declared fault
  injections (the natural run has no failed, abstained or rejected decision),
  with its own recordings, run artifacts, report and audit trails;
* ``sensitivity/`` - half-spread 0.00 / 0.02 / 0.05 reruns (fresh inference of
  the reference model): manifests and reports;
* ``bundle.json`` - file index with checksums and the expected verification
  values.

:func:`verify_demo` replays the bundle from its recorded responses with every
provider disabled and asserts identical StrategyResults, transitions, state
hashes, report metrics and evidence comparisons. Transitions and results use
the published, non-secret fixture keys of :mod:`research_engine.agents.recording`.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from research_engine.contracts.common import CASH_SECURITY_ID, content_hash, sha256_bytes
from research_engine.contracts.decisions import (
    DecisionBudget,
    DecisionOutcome,
    Proposal,
    StrategyResult,
)
from research_engine.contracts.portfolio import (
    CommandType,
    DecisionAction,
    ExecutionModel,
    RiskPolicy,
    TargetWeight,
    TransitionProposal,
)
from research_engine.simulation.clock import decision_at, ny_date

from .manifest import ExperimentManifest, verify_manifest
from .report import build_run_report, render_markdown
from .runner import ReplayConfig, ReplayRunner, StrategySpec
from .strategy import create_strategy

DEMO_EXPERIMENT_ID = "fi-demo-2024q1"
DEMO_START = date(2024, 1, 2)
DEMO_END = date(2024, 3, 29)
FAULT_START = date(2024, 1, 29)
FAULT_END = date(2024, 2, 23)
REGISTERED_ON = "2026-11-09"
BASELINE_IDS = ("cash", "quant_duration", "static_ladder")
AI_IDS = ("llm_graph", "llm_market", "llm_rag", "llm_team")
DEMO_STRATEGIES = tuple(sorted(BASELINE_IDS + AI_IDS))
DEFINITION_VERSION = "experiment-definition-v1"
BUNDLE_VERSION = "demo-bundle-v1"
DEMO_REPORT_VERSION = "demo-report-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = PROJECT_ROOT / "fixtures" / "demo"
EXCERPT_CHARS = 280
RUN_COPY = ("config.json", "manifest.json", "outcomes.jsonl", "checkpoint.json")
# Manifest fields that legitimately change between a build and a later verify.
VOLATILE_MANIFEST_FIELDS = ("gitCommit", "dependencyLockHashes", "generatedAt", "manifestHash")
VOLATILE_REPORT_FIELDS = ("manifestHash", "manifestVerified")

FAULT_PLAN = [
    {
        "faultId": "F1-provider-outage",
        "kind": "provider_outage",
        "strategyId": "llm_team",
        "session": "2024-01-31",
        "role": "lead",
        "description": "The model provider fails (non-transient) for the team lead on the FOMC "
        "statement day.",
        "expected": "failed_dependency; no order; the portfolio is still processed and valued",
    },
    {
        "faultId": "F2-graph-outage",
        "kind": "graph_outage",
        "strategyId": "llm_graph",
        "session": "2024-01-31",
        "description": "The evidence graph is unavailable for graph_rag_v1 retrieval.",
        "expected": "failed_dependency with no fallback to hybrid_rag_v1 (spec 15.3)",
    },
    {
        "faultId": "F3-evidence-withheld",
        "kind": "evidence_withheld",
        "strategyId": "llm_rag",
        "session": "2024-02-21",
        "description": "Retrieval returns an empty evidence bundle (simulated source gap).",
        "expected": "abstained_insufficient_evidence (configured abstention outcome)",
    },
    {
        "faultId": "F4-policy-breach",
        "kind": "policy_breach",
        "strategyId": "llm_market",
        "session": "2024-02-21",
        "description": "After agent validation, the proposal is overwritten with 70% in one "
        "note and 30% cash, simulating a faulty strategy output that reaches the "
        "authoritative policy gate.",
        "expected": "SUBMIT_DECISION policy evaluation rejects the order set; no order is created",
    },
    {
        "faultId": "F5-specialist-outage",
        "kind": "provider_outage",
        "strategyId": "llm_team",
        "session": "2024-02-21",
        "role": "macro_researcher",
        "description": "The model provider fails (non-transient) for the macro researcher "
        "specialist only.",
        "expected": "specialist task recorded as failed with the provider error; the lead "
        "still synthesizes a decision (non-graph specialist failures are contained by design)",
    },
]

LIMITATIONS = [
    "Synthetic-curve mode: SYN-USD-NOTE-* instruments are hypothetical; marks and fills are "
    "curve-model observations plus a declared half-spread, not market quotes. The run shows "
    "nothing about observed-security relative value or achievable execution.",
    "Same curve for marks and fills: any rich/cheap signal is mechanically neutral.",
    "Retrospective information policy: document availability is reconstructed "
    "(publication time + 120 minutes) and curve availability is 18:00 New York; this is a "
    "historical replay, not a forward paper-trading test.",
    "Pretrained-model hindsight: not applicable to reference-heuristic-v1 (a rule-based "
    "model with no pretrained knowledge), but it applies to any hosted LLM run on this "
    "window; such runs must be labelled retrospective and repeated forward.",
    "AI strategies ran on reference-heuristic-v1, a deterministic rule-based policy model, "
    "not a hosted LLM; the results say nothing about LLM decision quality.",
    "Stochastic repetitions are not applicable to the deterministic reference model; hosted "
    "models need at least three repetitions when affordable (spec 16.2).",
    "Short window (61 sessions, 60 daily returns): no statistical significance; paired "
    "block-bootstrap intervals are descriptive only; Sharpe ratios are unavailable because no "
    "risk-free series is declared.",
    "Exposures differ: equal risk limits did not produce equal duration/DV01; compare the "
    "exposure section before reading return differences.",
    "Cash earns zero (zero_cash_interest_v1); excess returns are not interpreted.",
    "Half-spread assumptions (0.00/0.02/0.05 per 100 face) are illustrative, not measured "
    "Treasury transaction costs.",
    "Evidence pages are 2026 web versions of the FOMC releases (flag "
    "current_web_version_not_archived_original), not archived originals.",
]


# --------------------------------------------------------------------------- #
# Small file helpers
# --------------------------------------------------------------------------- #


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _gzip_copy(source: Path, target: Path) -> None:
    target.write_bytes(gzip.compress(source.read_bytes(), compresslevel=9, mtime=0))


def _jsonl(path: Path) -> list[dict]:
    path = Path(path)
    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]


def _outcomes(path: Path) -> dict[str, StrategyResult]:
    return {r["decisionId"]: StrategyResult.model_validate(r["result"]) for r in _jsonl(Path(path))}


def _proposals(records: Iterable[dict]) -> list[TransitionProposal]:
    return [
        TransitionProposal.model_validate(r["proposal"]) for r in records if r["kind"] == "commit"
    ]


def _num(value: Any) -> Optional[float]:
    return None if value is None else float(value)


# --------------------------------------------------------------------------- #
# Provider and evidence guards / fault injection
# --------------------------------------------------------------------------- #


class ProvidersDisabled(AssertionError):
    """A model provider or network client was contacted during a verified replay."""


@contextlib.contextmanager
def providers_disabled():
    """Make every live provider (reference, Anthropic, OpenAI-compatible, raw HTTP) fail."""
    import httpx

    from research_engine.agents.providers import (
        AnthropicProvider,
        OpenAICompatibleProvider,
        ReferenceHeuristicProvider,
    )

    def refuse(*_args, **_kwargs):
        raise ProvidersDisabled("a model provider was contacted during recorded replay")

    targets = [
        (ReferenceHeuristicProvider, "generate"),
        (AnthropicProvider, "generate"),
        (OpenAICompatibleProvider, "generate"),
        (httpx.Client, "send"),
        (httpx.AsyncClient, "send"),
    ]
    saved = [(cls, name, cls.__dict__.get(name)) for cls, name in targets]
    try:
        for cls, name in targets:
            setattr(cls, name, refuse)
        yield
    finally:
        for cls, name, original in saved:
            if original is None:
                delattr(cls, name)
            else:
                setattr(cls, name, original)


def _session_of(decision_id: str) -> str:
    # dec:<run>:<strategy>:<YYYY-MM-DD>:r<n>
    return decision_id.split(":")[-2]


class FaultInjectingProvider:
    """Raises a declared non-transient provider failure for one decision/role."""

    def __init__(self, inner, faults: list[dict]):
        self.inner = inner
        self.faults = [f for f in faults if f["kind"] == "provider_outage"]
        for name in ("provider", "model", "deterministic", "priced"):
            setattr(self, name, getattr(inner, name))
        self.replay = getattr(inner, "replay", False)
        self.capturing = getattr(inner, "capturing", False)

    def generate(self, request):
        from research_engine.agents.providers import ProviderError

        meta = request.metadata
        for fault in self.faults:
            if (
                meta.decision_id.split(":")[2] == fault["strategyId"]
                and _session_of(meta.decision_id) == fault["session"]
                and meta.role == fault.get("role", meta.role)
            ):
                raise ProviderError(f"injected provider outage ({fault['faultId']})")
        return self.inner.generate(request)


class FaultInjectingEvidence:
    """Evidence port wrapper: graph outage or withheld evidence on one session."""

    def __init__(self, inner, faults: list[dict]):
        self.inner = inner
        self.faults = [f for f in faults if f["kind"] in ("graph_outage", "evidence_withheld")]
        self.index_build_id = inner.index_build_id
        self.evidence_snapshot_id = inner.evidence_snapshot_id

    def _fault(self, decision_as_of: datetime) -> Optional[dict]:
        session = ny_date(decision_as_of).isoformat()
        for fault in self.faults:
            if fault["session"] == session:
                return fault
        return None

    def retrieve(self, *, question, decision_as_of, mode, max_chunks, max_evidence_tokens, **kw):
        from research_engine.agents.ports import GraphUnavailable

        fault = self._fault(decision_as_of)
        if fault and fault["kind"] == "graph_outage":
            raise GraphUnavailable(f"injected graph outage ({fault['faultId']})")
        bundle = self.inner.retrieve(
            question=question,
            decision_as_of=decision_as_of,
            mode=mode,
            max_chunks=max_chunks,
            max_evidence_tokens=max_evidence_tokens,
            **kw,
        )
        if fault and fault["kind"] == "evidence_withheld":
            return bundle.model_copy(
                update={
                    "bundle_id": f"{bundle.bundle_id}-withheld",
                    "chunks": [],
                    "structured_facts": [],
                    "chunk_count": 0,
                    "total_tokens": 0,
                    "truncated_by_budget": [],
                    "empty": True,
                }
            )
        return bundle

    def chunk_text(self, chunk_id: str):
        return self.inner.chunk_text(chunk_id)


class PolicyBreachStrategy:
    """Overwrites one session's proposal after agent validation (labelled fault)."""

    def __init__(self, inner, fault: dict, signing_key: bytes):
        self.inner = inner
        self.fault = fault
        self.key = signing_key
        for name in ("strategy_id", "kind", "invested", "config", "provider"):
            setattr(self, name, getattr(inner, name))

    @property
    def deterministic(self) -> bool:
        return self.inner.deterministic

    def decide(self, ctx):
        from research_engine.agents.result import seal_result

        result = self.inner.decide(ctx)
        if ctx.session_date.isoformat() != self.fault["session"]:
            return result
        longest = max(ctx.universe, key=lambda i: (i.maturity_date, i.security_id))
        proposal = Proposal(
            action=DecisionAction.REBALANCE,
            target_weights=[
                TargetWeight(security_id=longest.security_id, weight=Decimal("0.70")),
                TargetWeight(security_id=CASH_SECURITY_ID, weight=Decimal("0.30")),
            ],
        )
        injected = result.model_copy(
            update={
                "outcome": DecisionOutcome.COMPLETED_PROPOSAL,
                "proposal": proposal,
                "reasons": list(result.reasons)
                + [f"failure_injection:{self.fault['faultId']}:proposal_overwritten"],
            }
        )
        return seal_result(StrategyResult.model_validate(injected.model_dump()), self.key)


# --------------------------------------------------------------------------- #
# Definition and strategies
# --------------------------------------------------------------------------- #


def demo_definition(index_build_id: str) -> dict:
    """Registered experiment definition (spec 16.1). Content-hashed in ``definitionHash``."""
    from research_engine.agents.providers.reference import DISCLOSURE, REFERENCE_MODEL_ID

    budget = DecisionBudget()
    definition = {
        "definitionVersion": DEFINITION_VERSION,
        "experimentId": DEMO_EXPERIMENT_ID,
        "title": "Recorded demo replay: FOMC Q1 2024, synthetic curve mode",
        "registeredOn": REGISTERED_ON,
        "purpose": "Demonstration bundle for milestone M7 and the spec 17.6 demo script. "
        "Not a held-out evaluation and not evidence of strategy skill.",
        "hypotheses": [
            {
                "id": "H1-retrieval",
                "comparison": ["llm_market", "llm_rag", "llm_graph"],
                "statement": "Document retrieval changes the decisions and exposures of the "
                "matched agent relative to market-only inputs.",
            },
            {
                "id": "H2-graph",
                "comparison": ["llm_rag", "llm_graph"],
                "statement": "Graph-assisted retrieval delivers additional, provenance-backed "
                "passages that change at least one decision.",
            },
            {
                "id": "H3-delegation",
                "comparison": ["llm_graph", "llm_team"],
                "statement": "A lead with two bounded specialists changes decisions relative "
                "to the single graph agent under the same budget.",
            },
        ],
        "evaluationStatus": "demonstration: hypotheses are stated for registration; a "
        "61-session window cannot test them statistically",
        "variants": [
            {"strategyId": "cash", "role": "uninvested reference (zero cash interest)"},
            {"strategyId": "static_ladder", "role": "passive bootstrap, then hold"},
            {"strategyId": "quant_duration", "role": "deterministic 4.0y duration target"},
            {"strategyId": "llm_market", "role": "AI baseline, numerical tools only"},
            {"strategyId": "llm_rag", "role": "AI + hybrid_rag_v1 retrieval"},
            {"strategyId": "llm_graph", "role": "AI + graph_rag_v1 retrieval"},
            {"strategyId": "llm_team", "role": "lead + macro researcher + critical reviewer"},
        ],
        "track": "budget_matched",
        "decisionBudget": budget.to_wire(),
        "monetaryCeiling": "not applicable: provider reference uses the zero-cost price "
        "schedule; priced hosted runs require a versioned price schedule and maxCostUsd",
        "model": {
            "provider": "reference",
            "modelId": REFERENCE_MODEL_ID,
            "isHostedLlm": False,
            "disclosure": DISCLOSURE,
        },
        "repetitions": {
            "ids": [0],
            "stochasticRepetitions": "not applicable: reference-heuristic-v1 is deterministic "
            "(identical output for identical input); hosted models need >= 3 repetitions",
        },
        "responseModes": {
            "capture": "fresh_inference of reference-heuristic-v1 through a recording provider",
            "canonical": "recorded_replay with replay_source=recorded_responses",
            "verification": "recorded_replay with replay_source=recorded_responses and every "
            "provider disabled; plus recorded_replay with replay_source=stored_results",
        },
        "dataMode": "synthetic_curve",
        "universeVersion": "synthetic_universe_v1.0",
        "marketDataset": "usd-treasury-par-2023-2024 (U.S. Treasury daily par yield curves)",
        "evidence": {
            "source": "fed-fomc (Federal Reserve FOMC statements and minutes, public domain)",
            "indexBuildId": index_build_id,
            "includesSynthetic": False,
        },
        "informationPolicy": "reconstructed_publication_plus_lag_v1",
        "window": {"start": DEMO_START.isoformat(), "end": DEMO_END.isoformat()},
        "policyEventsInWindow": [
            "2024-01-03 minutes of the 12-13 Dec 2023 meeting",
            "2024-01-31 statement",
            "2024-02-21 minutes of the 30-31 Jan 2024 meeting",
            "2024-03-20 statement",
        ],
        "primaryMetrics": [
            "netReturn",
            "maxDrawdown",
            "averageDv01Usd",
            "endEffectiveDurationYears",
            "spreadCostUsd",
            "decisionOutcomes",
        ],
        "secondaryMetrics": [
            "graph-added passages and RAG/Graph overlap per event",
            "citation validity and temporal violations of delivered evidence",
            "generation/tool/evidence calls and tokens per decision",
        ],
        "splits": {
            "role": "demonstration window",
            "development": "2023 data used by the agent and evidence workstreams while "
            "building (demo-sample-2023-06, evidence benchmark development run)",
            "heldOut": "none declared; prompts, lexicon and thresholds were not frozen against "
            "a held-out interval, so no result here is a held-out result",
        },
        "costAssumptions": {
            "executionModel": ExecutionModel().to_wire(),
            "sensitivityHalfSpreads": ["0.00", "0.02", "0.05"],
            "cashReturn": "zero_cash_interest_v1",
        },
        "riskPolicy": RiskPolicy().to_wire(),
        "exclusionRules": [
            "a session without a READY curve available by 19:00 New York is skipped for all "
            "competitors (skipped_stale_data) and listed as an exclusion",
            "no decision, session or competitor is excluded after inspecting results",
            "failure-injection and sensitivity runs are reported separately and never ranked "
            "with the canonical run",
        ],
        "faultInjection": {
            "experimentId": f"{DEMO_EXPERIMENT_ID}-faults",
            "window": {"start": FAULT_START.isoformat(), "end": FAULT_END.isoformat()},
            "plan": FAULT_PLAN,
            "reason": "the natural run produced no failed, abstained or rejected decision",
        },
        "limitations": LIMITATIONS,
        "redistribution": "Bundle contains only synthetic instruments, U.S. Treasury par "
        "curve values and Federal Reserve FOMC text excerpts (U.S. government works, public "
        "domain) plus outputs of the reference model.",
    }
    definition["definitionHash"] = content_hash(definition)
    return definition


def _ports(start: date, end: date):
    from research_engine.agents.recording import default_ports

    return default_ports(start, end)


def _strategies(provider, evidence, faults: Optional[list[dict]] = None) -> dict:
    from research_engine.agents import create_llm_strategy
    from research_engine.agents.recording import FIXTURE_RESULT_KEY

    faults = faults or []
    out: dict[str, Any] = {sid: create_strategy(sid) for sid in BASELINE_IDS}
    for sid in AI_IDS:
        own = [f for f in faults if f["strategyId"] == sid]
        sid_provider = FaultInjectingProvider(provider, own) if own else provider
        sid_evidence = evidence
        if sid != "llm_market" and own:
            sid_evidence = FaultInjectingEvidence(evidence, own)
        strategy: Any = create_llm_strategy(
            sid,
            {},
            provider=sid_provider,
            evidence=sid_evidence if sid != "llm_market" else None,
            signing_key=FIXTURE_RESULT_KEY,
        )
        breach = [f for f in own if f["kind"] == "policy_breach"]
        if breach:
            strategy = PolicyBreachStrategy(strategy, breach[0], FIXTURE_RESULT_KEY)
        out[sid] = strategy
    return out


def _config(
    experiment_id: str,
    start: date,
    end: date,
    strategies: dict,
    *,
    execution_model: Optional[ExecutionModel] = None,
    run_suffix: str = "r0",
    splits: Optional[dict] = None,
) -> ReplayConfig:
    return ReplayConfig(
        experiment_id=experiment_id,
        run_id=f"{experiment_id}-{run_suffix}",
        start_date=start,
        end_date=end,
        strategies=[
            StrategySpec(strategy_id=s, config=strategies[s].config) for s in sorted(strategies)
        ],
        execution_model=execution_model or ExecutionModel(),
        response_mode="fresh_inference",
        repetition=0,
        seed=0,
        splits=splits or {},
        resource_limits={"track": "budget_matched", "decisionBudget": DecisionBudget().to_wire()},
    )


def _replay_config(config: ReplayConfig) -> ReplayConfig:
    from research_engine.agents.recording import recorded_response_config

    return recorded_response_config(config)


def _run(config, strategies, ports, run_dir: Path, **kwargs):
    from research_engine.agents.recording import FIXTURE_TRANSITION_KEY

    pricing, market = ports
    return ReplayRunner(
        config, pricing, market, run_dir, FIXTURE_TRANSITION_KEY, strategies=strategies, **kwargs
    ).run()


# --------------------------------------------------------------------------- #
# Evidence comparison
# --------------------------------------------------------------------------- #


def policy_events(store, start: date, end: date) -> list[dict]:
    """FOMC statements/minutes whose reconstructed availability falls in the window."""
    events = []
    for version in store.list_versions():
        if version.synthetic or version.source_id != "fed-fomc":
            continue
        session = ny_date(version.available_at)
        if not (start <= session <= end) or version.available_at > decision_at(session):
            continue
        events.append(
            {
                "session": session.isoformat(),
                "documentType": version.document_type.value,
                "documentId": version.document_id,
                "versionId": version.version_id,
                "title": version.title,
                "sourceUrl": version.source_url,
                "publishedAt": version.published_at.isoformat(),
                "availableAt": version.available_at.isoformat(),
            }
        )
    return sorted(events, key=lambda e: (e["session"], e["documentType"], e["documentId"]))


def _chunk_row(chunk) -> dict:
    prov = chunk.provenance
    graph = None
    if prov.graph is not None:
        graph = {
            "seedId": prov.graph.seed_id,
            "addedByGraph": prov.graph.added_by_graph,
            "pathLength": prov.graph.path_length,
            "pathAssertionIds": list(prov.graph.path_assertion_ids),
            "graphScore": str(prov.graph.graph_score),
            "supportSpans": [s.to_wire() for s in prov.graph.support_spans],
        }
    return {
        "chunkId": chunk.chunk_id,
        "documentId": chunk.document_id,
        "versionId": chunk.version_id,
        "documentType": chunk.document_type.value,
        "title": chunk.title,
        "sourceUrl": chunk.source_url,
        "publishedAt": chunk.published_at.isoformat(),
        "availableAt": chunk.available_at.isoformat(),
        "headingPath": list(chunk.heading_path),
        "offsets": [chunk.start_offset, chunk.end_offset],
        "finalRank": prov.final_rank,
        "channels": [c.value for c in prov.channels],
        "lexicalRank": prov.lexical_rank,
        "vectorRank": prov.vector_rank,
        "graphRank": prov.graph_rank,
        "graph": graph,
        "excerpt": chunk.text[:EXCERPT_CHARS] + ("..." if len(chunk.text) > EXCERPT_CHARS else ""),
    }


def _delivered(result: StrategyResult, store) -> tuple[list[dict], list[dict]]:
    chunks: dict[str, dict] = {}
    bundles = []
    for bundle_id in result.evidence_bundle_ids:
        bundle = store.get_bundle(bundle_id)
        if bundle is None:
            bundles.append({"bundleId": bundle_id, "persisted": False})
            continue
        bundles.append(
            {
                "bundleId": bundle_id,
                "mode": bundle.mode.value,
                "decisionAsOf": bundle.decision_as_of.isoformat(),
                "chunkCount": bundle.chunk_count,
                "totalTokens": bundle.total_tokens,
                "structuredFacts": [
                    {
                        "relation": f.relation.value,
                        "subject": f.subject_label,
                        "object": f.object_label,
                        "availableAt": f.available_at.isoformat(),
                    }
                    for f in bundle.structured_facts
                ],
            }
        )
        for chunk in bundle.chunks:
            row = _chunk_row(chunk)
            row["bundleId"] = bundle_id
            row["temporalViolation"] = chunk.available_at > bundle.decision_as_of
            previous = chunks.get(chunk.chunk_id)
            if previous is None or (row["graph"] or {}).get("addedByGraph"):
                chunks[chunk.chunk_id] = row
    return bundles, sorted(chunks.values(), key=lambda r: (r["bundleId"], r["finalRank"]))


def _cited(result: StrategyResult) -> list[dict]:
    note = result.research_note
    if note is None:
        return []
    by_id = {c.citation_id: c for c in note.citations}
    rows = []
    for claim in note.claims:
        for cid in claim.citation_ids:
            citation = by_id.get(cid)
            rows.append(
                {
                    "claimId": claim.claim_id,
                    "claim": claim.text[:EXCERPT_CHARS],
                    "validationStatus": claim.validation_status,
                    "citationId": cid,
                    "chunkId": citation.chunk_id if citation else None,
                    "quote": (citation.quote or "")[:EXCERPT_CHARS] if citation else None,
                }
            )
    return rows


def _decision_view(result: Optional[StrategyResult], store) -> Optional[dict]:
    if result is None:
        return None
    bundles, chunks = _delivered(result, store)
    return {
        "decisionId": result.decision_id,
        "outcome": result.outcome.value,
        "reasons": list(result.reasons),
        "action": result.proposal.action.value if result.proposal else None,
        "noteStatus": result.research_note.status.value if result.research_note else None,
        "bundles": bundles,
        "deliveredChunks": chunks,
        "citedClaims": _cited(result),
    }


def evidence_comparison(event: dict, results: dict[str, Optional[StrategyResult]], store) -> dict:
    """RAG versus Graph RAG (and team) delivered passages for one policy-document event."""
    views = {
        sid: _decision_view(results.get(sid), store) for sid in ("llm_rag", "llm_graph", "llm_team")
    }
    rag = {c["chunkId"] for c in (views["llm_rag"] or {}).get("deliveredChunks", [])}
    graph_rows = (views["llm_graph"] or {}).get("deliveredChunks", [])
    graph = {c["chunkId"] for c in graph_rows}
    added = [c for c in graph_rows if (c["graph"] or {}).get("addedByGraph")]
    delivered_event = {
        sid: any(c["documentId"] == event["documentId"] for c in view["deliveredChunks"])
        for sid, view in views.items()
        if view is not None
    }
    return {
        "event": event,
        "strategies": views,
        "comparison": {
            "eventDocumentDelivered": delivered_event,
            "ragChunks": len(rag),
            "graphChunks": len(graph),
            "common": sorted(rag & graph),
            "ragOnly": sorted(rag - graph),
            "graphOnly": sorted(graph - rag),
            "graphAddedByTraversal": [
                {
                    "chunkId": c["chunkId"],
                    "documentId": c["documentId"],
                    "headingPath": c["headingPath"],
                    "seedId": c["graph"]["seedId"],
                    "pathAssertionIds": c["graph"]["pathAssertionIds"],
                    "supportSpans": c["graph"]["supportSpans"],
                }
                for c in added
            ],
            "sameDecision": (views["llm_rag"] or {}).get("action")
            == (views["llm_graph"] or {}).get("action")
            and (views["llm_rag"] or {}).get("outcome")
            == (views["llm_graph"] or {}).get("outcome"),
        },
    }


def render_comparison_markdown(comparison: dict) -> str:
    event = comparison["event"]
    comp = comparison["comparison"]
    lines = [
        f"# Evidence comparison - {event['session']} {event['documentType']}",
        "",
        f"Event: [{event['title']}]({event['sourceUrl']}) - published {event['publishedAt']}, "
        f"available {event['availableAt']} (reconstructed: publication + 120 min).",
        "",
        "AI strategies ran on `reference-heuristic-v1` (deterministic rule-based model, not a "
        "hosted LLM).",
        "",
        f"- RAG delivered {comp['ragChunks']} passages; Graph RAG delivered {comp['graphChunks']}.",
        f"- Common: {len(comp['common'])}; RAG only: {len(comp['ragOnly'])}; Graph only: "
        f"{len(comp['graphOnly'])}; added by graph traversal: "
        f"{len(comp['graphAddedByTraversal'])}.",
        f"- Same decision for RAG and Graph RAG: {comp['sameDecision']}.",
        f"- Event document ({event['documentId']}) among delivered passages: "
        + ", ".join(f"{k}={v}" for k, v in sorted(comp["eventDocumentDelivered"].items()))
        + ".",
        "",
        '"Graph only" passages reached llm_graph through its graph-mode retrieval and '
        '`expand_evidence_graph` call; "added by graph traversal" counts passages whose '
        "provenance says they were not among the hybrid lexical/vector candidates "
        "(`addedByGraph=true`).",
        "",
    ]
    for sid in ("llm_rag", "llm_graph", "llm_team"):
        view = comparison["strategies"].get(sid)
        if view is None:
            continue
        lines += [
            f"## {sid}: {view['outcome']} ({view['action'] or 'no proposal'})",
            "",
            "| Rank | Chunk | Document | Section | Channels | Graph |",
            "|---|---|---|---|---|---|",
        ]
        for c in view["deliveredChunks"]:
            graph = ""
            if c["graph"]:
                graph = (
                    f"seed `{c['graph']['seedId']}`, added={c['graph']['addedByGraph']}, "
                    f"{len(c['graph']['pathAssertionIds'])} assertion(s)"
                )
            section = " > ".join(c["headingPath"])[-60:]
            lines.append(
                f"| {c['finalRank']} | `{c['chunkId']}` | {c['documentId']} | {section} | "
                f"{', '.join(c['channels'])} | {graph} |"
            )
        if view["citedClaims"]:
            lines += ["", "Cited claims:", ""]
            for claim in view["citedClaims"]:
                lines.append(
                    f"- [{claim['validationStatus']}] {claim['claim']} (`{claim['chunkId']}`)"
                )
        lines.append("")
    if comp["graphAddedByTraversal"]:
        lines += ["## Graph-added passages and provenance", ""]
        for item in comp["graphAddedByTraversal"]:
            lines.append(
                f"- `{item['chunkId']}` ({item['documentId']}): seed `{item['seedId']}`, "
                f"assertions {', '.join(f'`{a}`' for a in item['pathAssertionIds'])}"
            )
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Report extension
# --------------------------------------------------------------------------- #


def _sum_usage(results: list[StrategyResult]) -> dict:
    keys = (
        "generation_calls",
        "tool_calls",
        "evidence_calls",
        "unique_evidence_chunks",
        "evidence_tokens",
        "input_tokens",
        "output_tokens",
    )
    totals = {k: sum(getattr(r.usage, k) for r in results) for k in keys}
    costs = [r.usage.estimated_cost_usd for r in results if r.usage.estimated_cost_usd is not None]
    schedules = sorted({r.usage.price_schedule_id for r in results if r.usage.price_schedule_id})
    exhausted = sorted({r.usage.budget_exhausted for r in results if r.usage.budget_exhausted})
    modelled = [r for r in results if r.attempts]
    camel = {
        "generation_calls": "generationCalls",
        "tool_calls": "toolCalls",
        "evidence_calls": "evidenceCalls",
        "unique_evidence_chunks": "uniqueEvidenceChunks",
        "evidence_tokens": "evidenceTokens",
        "input_tokens": "inputTokens",
        "output_tokens": "outputTokens",
    }
    out = {camel[k]: v for k, v in totals.items()}
    out.update(
        {
            "decisionsWithModelCalls": len(modelled),
            "maxGenerationCallsPerDecision": max(
                (r.usage.generation_calls for r in results), default=0
            ),
            "maxToolCallsPerDecision": max((r.usage.tool_calls for r in results), default=0),
            "estimatedModelCostUsd": format(sum(costs, Decimal("0")), "f") if costs else None,
            "priceSchedules": schedules,
            "budgetExhausted": exhausted,
            "attemptStatuses": _count(a.status for r in results for a in r.attempts),
            "providers": sorted({f"{a.provider}/{a.model}" for r in results for a in r.attempts}),
            "recordedResponseIds": sum(
                1 for r in results for a in r.attempts if a.recorded_response_id
            ),
        }
    )
    return out


def _count(items: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


def _evidence_metrics(results: list[StrategyResult], store) -> dict:
    delivered = 0
    graph_added = 0
    violations = 0
    documents: set[str] = set()
    for result in results:
        _, chunks = _delivered(result, store)
        delivered += len(chunks)
        graph_added += sum(1 for c in chunks if (c["graph"] or {}).get("addedByGraph"))
        violations += sum(1 for c in chunks if c["temporalViolation"])
        documents.update(c["documentId"] for c in chunks)
    claims = [c for r in results if r.research_note for c in r.research_note.claims]
    citations = [c for r in results if r.research_note for c in r.research_note.citations]
    steps: dict[str, dict[str, int]] = {}
    for result in results:
        for check in result.validation:
            if check.step == "original_proposal":
                continue
            entry = steps.setdefault(check.step, {"passed": 0, "failed": 0})
            entry["passed" if check.passed else "failed"] += 1
    return {
        "decisionsWithEvidence": sum(1 for r in results if r.evidence_bundle_ids),
        "bundles": sum(len(r.evidence_bundle_ids) for r in results),
        "deliveredPassages": delivered,
        "graphAddedPassages": graph_added,
        "distinctDocuments": len(documents),
        "temporalViolations": violations,
        "claims": len(claims),
        "claimValidation": _count(c.validation_status for c in claims),
        "citations": len(citations),
        "noteStatuses": _count(r.research_note.status.value for r in results if r.research_note),
        "validationSteps": dict(sorted(steps.items())),
    }


def _exposure(proposals: list[TransitionProposal]) -> dict:
    series = []
    for p in proposals:
        if p.command_type != CommandType.VALUE_PORTFOLIO or p.valuation is None:
            continue
        v = p.valuation
        series.append(
            {
                "session": ny_date(v.valuation_at).isoformat(),
                "complete": v.complete,
                "equityUsd": _num(v.equity_usd),
                "cashUsd": _num(v.cash_usd),
                "dv01Usd": _num(v.parallel_dv01_usd),
                "durationYears": _num(v.effective_duration_years),
            }
        )
    return {"daily": series}


def _overlap(results: dict[str, StrategyResult], store, sessions: list[str], run_id: str) -> dict:
    rows: list[dict[str, Any]] = []
    for session in sessions:
        sets = {}
        for sid in ("llm_rag", "llm_graph"):
            result = results.get(f"dec:{run_id}:{sid}:{session}:r0")
            if result is None:
                continue
            _, chunks = _delivered(result, store)
            sets[sid] = {c["chunkId"] for c in chunks}
        if len(sets) == 2 and (sets["llm_rag"] or sets["llm_graph"]):
            union = sets["llm_rag"] | sets["llm_graph"]
            rows.append(
                {
                    "session": session,
                    "rag": len(sets["llm_rag"]),
                    "graph": len(sets["llm_graph"]),
                    "common": len(sets["llm_rag"] & sets["llm_graph"]),
                    "jaccard": round(len(sets["llm_rag"] & sets["llm_graph"]) / len(union), 4),
                }
            )
    identical = sum(1 for r in rows if r["jaccard"] == 1.0)
    return {
        "sessionsCompared": len(rows),
        "sessionsWithIdenticalPassages": identical,
        "meanJaccard": round(sum(r["jaccard"] for r in rows) / len(rows), 4) if rows else None,
        "perSession": rows,
    }


def demo_report(
    manifest: ExperimentManifest,
    records: list[dict],
    outcomes: dict[str, StrategyResult],
    store,
    *,
    data_gaps: Optional[list] = None,
    label: str = "canonical recorded-response replay",
) -> dict:
    proposals = _proposals(records)
    results = list(outcomes.values())
    report = build_run_report(manifest, proposals, results)
    sessions = [d.isoformat() for d in manifest.decision_sessions]
    strategies = {}
    for entry in manifest.strategies:
        sid = entry.strategy_id
        own = sorted((r for r in results if r.strategy_id == sid), key=lambda r: r.decision_id)
        own_props = [p for p in proposals if p.strategy_id == sid]
        actions = _count(
            r.proposal.action.value
            for r in own
            if r.outcome == DecisionOutcome.COMPLETED_PROPOSAL and r.proposal
        )
        strategies[sid] = {
            "responseSource": entry.response_source,
            "proposalActions": actions,
            "usage": _sum_usage(own),
            "evidence": _evidence_metrics(own, store) if entry.retrieval_mode != "none" else None,
            "exposure": _exposure(own_props),
        }
    report["demo"] = {
        "demoReportVersion": DEMO_REPORT_VERSION,
        "label": label,
        "modelDisclosure": "AI strategies ran on provider reference / reference-heuristic-v1, "
        "a deterministic rule-based policy model. It is not a hosted LLM.",
        "strategies": strategies,
        "ragGraphOverlap": _overlap(outcomes, store, sessions, manifest.run_id),
        "completeness": {
            "sessions": len(sessions),
            "decisionsExpected": len(sessions) * len(manifest.strategies),
            "decisionsRecorded": len(results),
            "outcomes": _count(r.outcome.value for r in results),
            "dataGaps": [f"{d.isoformat()}:{reason}" for d, reason in (data_gaps or [])],
            "exclusions": list(manifest.exclusions),
            "runFailures": list(manifest.failures),
            "incompleteValuations": sum(
                1
                for p in proposals
                if p.command_type == CommandType.VALUE_PORTFOLIO
                and p.valuation is not None
                and not p.valuation.complete
            ),
        },
        "limitations": LIMITATIONS,
    }
    return report


def render_demo_markdown(report: dict) -> str:
    demo = report["demo"]
    lines = [render_markdown(report).rstrip(), "", f"## Demo extension ({demo['label']})", ""]
    lines += [demo["modelDisclosure"], ""]
    lines += [
        "| Strategy | Response source | Proposals | Generation calls | Tool calls | "
        "Evidence calls | Input tokens | Output tokens | Model cost (USD) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for sid, entry in sorted(demo["strategies"].items()):
        u = entry["usage"]
        lines.append(
            f"| {sid} | {entry['responseSource']} | {entry['proposalActions'] or '-'} | "
            f"{u['generationCalls']} | {u['toolCalls']} | {u['evidenceCalls']} | "
            f"{u['inputTokens']} | {u['outputTokens']} | {u['estimatedModelCostUsd'] or 'n/a'} |"
        )
    lines += ["", "### Evidence", ""]
    for sid, entry in sorted(demo["strategies"].items()):
        ev = entry["evidence"]
        if not ev:
            continue
        lines.append(
            f"- **{sid}**: {ev['bundles']} bundles, {ev['deliveredPassages']} delivered "
            f"passages ({ev['graphAddedPassages']} added by graph traversal) from "
            f"{ev['distinctDocuments']} documents; temporal violations "
            f"{ev['temporalViolations']}; claims {ev['claimValidation']}; note statuses "
            f"{ev['noteStatuses']}."
        )
    overlap = demo["ragGraphOverlap"]
    lines += [
        "",
        f"RAG vs Graph RAG passages: {overlap['sessionsCompared']} sessions compared, "
        f"{overlap['sessionsWithIdenticalPassages']} identical, mean Jaccard "
        f"{overlap['meanJaccard']}.",
        "",
        "### Completeness",
        "",
    ]
    comp = demo["completeness"]
    lines.append(
        f"{comp['decisionsRecorded']}/{comp['decisionsExpected']} decisions recorded; outcomes "
        f"{comp['outcomes']}; data gaps {comp['dataGaps'] or 'none'}; exclusions "
        f"{comp['exclusions'] or 'none'}; incomplete valuations {comp['incompleteValuations']}."
    )
    lines += ["", "### Demo limitations", ""] + [f"- {item}" for item in demo["limitations"]]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Walkthrough and audit trails
# --------------------------------------------------------------------------- #


def _commands_for(records: list[dict], strategy_id: str, sessions: Iterable[str]) -> list[dict]:
    wanted = set(sessions)
    out = []
    for p in _proposals(records):
        if p.strategy_id != strategy_id:
            continue
        step = p.command_id.split(":")
        if len(step) >= 4 and step[3] in wanted:
            out.append(_proposal_view(p))
    return out


def _proposal_view(p: TransitionProposal) -> dict:
    wire = p.to_wire()
    valuation = wire.get("valuation") or None
    return {
        "commandId": wire["commandId"],
        "commandType": wire["commandType"],
        "newVersion": wire["newVersion"],
        "newStateHash": wire["newStateHash"],
        "events": [
            {"type": e.get("type"), "effectiveAt": e.get("effectiveAt")}
            for e in wire.get("events", [])
        ],
        "policyEvaluation": wire.get("policyEvaluation"),
        "ordersCreated": wire.get("ordersCreated", []),
        "orderStatusChanges": wire.get("orderStatusChanges", []),
        "fills": wire.get("fills", []),
        "settlementsCreated": wire.get("settlementsCreated", []),
        "settlementsCompleted": wire.get("settlementsCompleted", []),
        "cashFlows": wire.get("cashFlows", []),
        "valuation": (
            {
                k: valuation.get(k)
                for k in (
                    "complete",
                    "equityUsd",
                    "cashUsd",
                    "parallelDv01Usd",
                    "effectiveDurationYears",
                )
            }
            if valuation
            else None
        ),
        "reconciliationOk": (wire.get("reconciliation") or {}).get("ok"),
    }


def _result_summary(result: StrategyResult) -> dict:
    wire = result.to_wire()
    return {
        "decisionId": result.decision_id,
        "strategyId": result.strategy_id,
        "outcome": result.outcome.value,
        "reasons": list(result.reasons),
        "proposal": wire.get("proposal"),
        "agentPolicyCheck": wire.get("policyEvaluation"),
        "noteStatus": result.research_note.status.value if result.research_note else None,
        "explanation": (result.research_note.explanation if result.research_note else "")[:600],
        "counterevidence": (
            list(result.research_note.counterevidence) if result.research_note else []
        ),
        "coverageGaps": list(result.research_note.coverage_gaps) if result.research_note else [],
        "attempts": [a.to_wire() for a in result.attempts],
        "toolTraces": [
            {
                "agentRole": t.agent_role,
                "tool": t.tool_name,
                "status": t.status,
                "outputRef": t.output_ref,
                "error": t.error,
            }
            for t in result.tool_traces
        ],
        "specialistTasks": [t.to_wire() for t in result.specialist_tasks],
        "validation": [v.to_wire() for v in result.validation if v.step != "original_proposal"],
        "usage": result.usage.to_wire(),
        "evidenceBundleIds": list(result.evidence_bundle_ids),
        "resultHash": result.result_hash,
    }


def _bond_view(pricing, market, session: date) -> dict:
    universe = sorted(pricing.universe(session), key=lambda i: i.maturity_date)
    target = min(
        universe, key=lambda i: (abs((i.maturity_date - session).days - 5 * 365), i.security_id)
    )
    curve = market.curve_for_session(session)
    settle = pricing.settlement_date(target.security_id, session)
    price = pricing.price(target.security_id, curve.curve_snapshot_id, settle)
    risk = pricing.position_risk(
        target.security_id, curve.curve_snapshot_id, session, Decimal("1000000")
    )
    flows = [
        f.to_wire() for f in pricing.cash_flows(target.security_id) if f.payment_date > session
    ]
    return {
        "securityId": target.security_id,
        "synthetic": target.synthetic,
        "label": "SYNTHETIC instrument; curve-model price, not a market quote",
        "terms": target.to_wire(),
        "curveSnapshotId": curve.curve_snapshot_id,
        "settlementDate": settle.isoformat(),
        "modelPrice": price.to_wire(),
        "riskFor1mmFace": risk.to_wire(),
        "upcomingCashFlows": flows,
    }


def build_walkthrough(
    pricing,
    market,
    records: list[dict],
    outcomes: dict[str, StrategyResult],
    run_id: str,
    event: dict,
    comparison_file: str,
    report: dict,
    fault_audits: list[str],
) -> dict:
    session = date.fromisoformat(event["session"])
    sessions = market.sessions(session, DEMO_END)
    next_session = sessions[1].isoformat() if len(sessions) > 1 else None
    settle_session = sessions[2].isoformat() if len(sessions) > 2 else None
    proposals = {}
    for sid in DEMO_STRATEGIES:
        result = outcomes.get(f"dec:{run_id}:{sid}:{event['session']}:r0")
        proposals[sid] = {
            "decision": _result_summary(result) if result else None,
            "commands": _commands_for(
                records, sid, [s for s in (event["session"], next_session, settle_session) if s]
            ),
        }
    exposure = {
        s["strategyId"]: {
            "netReturn": s["metrics"].get("netReturn"),
            "averageDv01Usd": s["metrics"].get("averageDv01Usd"),
            "endEffectiveDurationYears": s["metrics"].get("endEffectiveDurationYears"),
            "averageCashProportion": s["metrics"].get("averageCashProportion"),
            "spreadCostUsd": s["metrics"].get("spreadCostUsd"),
        }
        for s in report["strategies"]
    }
    return {
        "walkthroughVersion": "demo-walkthrough-v1",
        "experimentId": DEMO_EXPERIMENT_ID,
        "runId": run_id,
        "modelDisclosure": report["demo"]["modelDisclosure"],
        "steps": {
            "1_openRecordedExperiment": {
                "manifest": "run/manifest.json",
                "report": "report/report.md",
                "responseMode": report["responseMode"],
                "responseSource": report.get("responseSource"),
            },
            "2_inspectBond": _bond_view(pricing, market, session),
            "3_policyDocumentEvent": event,
            "4_compareEvidence": comparison_file,
            "5_proposalsAndPolicy": {k: v["decision"] for k, v in proposals.items()},
            "6_executionAndSettlement": {
                "decisionSession": event["session"],
                "fillSession": next_session,
                "settlementSession": settle_session,
                "note": "orders fill only at the next session's 15:30 New York curve "
                "observation (next-session close, daily data) and settle T+1",
                "commands": {k: v["commands"] for k, v in proposals.items()},
            },
            "7_compareExposureAndOutcomes": exposure,
            "8_failureAuditTrail": fault_audits
            or ["natural run had no failed, abstained or rejected decision"],
            "9_specialistTeam": proposals["llm_team"]["decision"],
        },
    }


def _walkthrough_event(events: list[dict], outcomes: dict, run_id: str) -> dict:
    """First policy-document event on which an evidence agent proposed a rebalance."""
    for event in events:
        for sid in ("llm_rag", "llm_graph", "llm_team"):
            result = outcomes.get(f"dec:{run_id}:{sid}:{event['session']}:r0")
            if (
                result is not None
                and result.outcome == DecisionOutcome.COMPLETED_PROPOSAL
                and result.proposal is not None
                and result.proposal.action == DecisionAction.REBALANCE
            ):
                return event
    return next(e for e in events if "statement" in e["documentType"])


def _fault_audit(fault: dict, outcomes: dict, records: list[dict], run_id: str) -> dict:
    sid, session = fault["strategyId"], fault["session"]
    result = outcomes.get(f"dec:{run_id}:{sid}:{session}:r0")
    commands = _commands_for(records, sid, [session])
    others = {
        o.strategy_id: o.outcome.value
        for o in outcomes.values()
        if _session_of(o.decision_id) == session and o.strategy_id != sid
    }
    submitted = [c for c in commands if c["commandType"] == CommandType.SUBMIT_DECISION.value]
    return {
        "auditVersion": "demo-audit-v1",
        "label": "FAILURE INJECTION (declared fault; not a natural outcome)",
        "fault": fault,
        "decision": _result_summary(result) if result else None,
        "financialCommands": commands,
        "policyGate": submitted[0]["policyEvaluation"] if submitted else None,
        "ordersCreated": sum(len(c["ordersCreated"]) for c in commands),
        "otherCompetitorsSameSession": others,
        "portfolioStillProcessed": any(
            c["commandType"] == CommandType.VALUE_PORTFOLIO.value for c in commands
        ),
    }


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


@dataclass
class RunArtifacts:
    run_dir: Path
    manifest: ExperimentManifest
    records: list[dict]
    outcomes: dict[str, StrategyResult]
    status: str


def _collect(run_dir: Path, status: str) -> RunArtifacts:
    manifest = ExperimentManifest.model_validate_json((run_dir / "manifest.json").read_text())
    return RunArtifacts(
        run_dir,
        manifest,
        _jsonl(run_dir / "commits.jsonl"),
        _outcomes(run_dir / "outcomes.jsonl"),
        status,
    )


def _capture_and_replay(
    experiment_id: str,
    start: date,
    end: date,
    target: Path,
    evidence,
    ports,
    work: Path,
    faults: Optional[list[dict]] = None,
) -> tuple[RunArtifacts, RunArtifacts, list[str]]:
    from research_engine.agents.providers import (
        RecordedResponseProvider,
        RecordingProvider,
        ReferenceHeuristicProvider,
    )
    from research_engine.agents.providers.reference import DISCLOSURE
    from research_engine.agents.recording import compare_capture_and_replay

    recorder = RecordingProvider(
        ReferenceHeuristicProvider(), target / "responses", disclosure=DISCLOSURE
    )
    strategies = _strategies(recorder, evidence, faults)
    splits = {"role": "demonstration", "heldOut": None}
    config = _config(experiment_id, start, end, strategies, splits=splits)
    capture = _run(config, strategies, ports, work / "capture")
    replayer = RecordedResponseProvider(target / "responses")
    replay = _run(
        _replay_config(config), _strategies(replayer, evidence, faults), ports, work / "run"
    )
    cap = _collect(work / "capture", capture.status)
    run = _collect(work / "run", replay.status)
    problems = compare_capture_and_replay(cap.outcomes, run.outcomes)
    cap_commits = [r for r in cap.records if r["kind"] == "commit"]
    run_commits = [r for r in run.records if r["kind"] == "commit"]
    if cap_commits != run_commits:
        problems.append("capture_and_replay_transitions_differ")
    return cap, run, problems


def _write_run(artifacts: RunArtifacts, capture: RunArtifacts, target: Path) -> None:
    (target / "capture").mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "manifest.json"):
        shutil.copy2(capture.run_dir / name, target / "capture" / name)
    (target / "run").mkdir(parents=True, exist_ok=True)
    for name in RUN_COPY:
        shutil.copy2(artifacts.run_dir / name, target / "run" / name)
    _gzip_copy(artifacts.run_dir / "commits.jsonl", target / "run" / "commits.jsonl.gz")


def _final_states(records: list[dict]) -> dict[str, str]:
    states: dict[str, str] = {}
    for record in records:
        if record["kind"] == "commit":
            states[record["proposal"]["portfolioId"]] = record["proposal"]["newStateHash"]
    return dict(sorted(states.items()))


def _expected(artifacts: RunArtifacts, report: dict) -> dict:
    commits = [r for r in artifacts.records if r["kind"] == "commit"]
    return {
        "status": artifacts.status,
        "decisions": len(artifacts.outcomes),
        "outcomeHashes": content_hash(
            {k: v.result_hash for k, v in sorted(artifacts.outcomes.items())}
        ),
        "transitions": len(commits),
        "transitionsHash": content_hash([r["proposal"]["proposalHash"] for r in commits]),
        "finalStateHashes": _final_states(artifacts.records),
        "reportMetricsHash": content_hash(_comparable_report(report), allow_floats=True),
    }


def _comparable_report(report: dict) -> dict:
    return {k: v for k, v in report.items() if k not in VOLATILE_REPORT_FIELDS}


def _sensitivity(evidence, ports, work: Path, target: Path, log) -> list[dict]:
    from research_engine.agents.providers import ReferenceHeuristicProvider
    from research_engine.simulation.fills import cost_profiles

    rows = []
    for profile in cost_profiles(ExecutionModel()):
        label = f"half-spread-{profile.half_spread_per_100}"
        log(f"sensitivity run {label} (fresh inference, reference model)")
        strategies = _strategies(ReferenceHeuristicProvider(), evidence)
        config = _config(
            f"{DEMO_EXPERIMENT_ID}-cost",
            DEMO_START,
            DEMO_END,
            strategies,
            execution_model=profile,
            run_suffix=f"hs{str(profile.half_spread_per_100).replace('.', '')}-r0",
        )
        result = _run(config, strategies, ports, work / label)
        artifacts = _collect(work / label, result.status)
        report = build_run_report(
            artifacts.manifest, _proposals(artifacts.records), list(artifacts.outcomes.values())
        )
        out = target / "sensitivity" / label
        _dump(out / "report.json", report)
        shutil.copy2(work / label / "manifest.json", out / "manifest.json")
        rows.append(
            {
                "profile": profile.execution_model_id,
                "halfSpreadPer100": str(profile.half_spread_per_100),
                "runId": config.run_id,
                "status": result.status,
                "decisionOutcomes": _count(o.outcome.value for o in artifacts.outcomes.values()),
                "strategies": {
                    s["strategyId"]: {
                        "netReturn": s["metrics"].get("netReturn"),
                        "grossReturn": s["metrics"].get("grossReturn"),
                        "spreadCostUsd": s["metrics"].get("spreadCostUsd"),
                        "fillCount": s["metrics"].get("fillCount"),
                        "proposalCount": s["metrics"].get("proposalCount"),
                        "averageDv01Usd": s["metrics"].get("averageDv01Usd"),
                    }
                    for s in report["strategies"]
                },
            }
        )
    return rows


def _file_index(root: Path) -> list[dict]:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "bundle.json"):
        raw = path.read_bytes()
        row = {
            "path": path.relative_to(root).as_posix(),
            "bytes": len(raw),
            "sha256": sha256_bytes(raw),
        }
        if path.suffix == ".gz":
            row["contentSha256"] = sha256_bytes(gzip.decompress(raw))
        rows.append(row)
    return rows


def build_demo(
    out_root: Optional[Path] = None,
    *,
    home: Optional[Path] = None,
    overwrite: bool = False,
    sensitivity: bool = True,
    log: Callable[[str], None] = lambda _msg: None,
) -> dict:
    """Register, capture, replay and package the demo bundle. Returns ``bundle.json``."""
    from research_engine.agents.ports import open_default_evidence_port

    target = Path(out_root or DEMO_ROOT) / DEMO_EXPERIMENT_ID
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"{target} exists; pass overwrite=True")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        evidence = open_default_evidence_port(home or work / "evidence-home")
        definition = demo_definition(evidence.index_build_id)
        _dump(target / "definition.json", definition)
        log(f"registered {DEMO_EXPERIMENT_ID} ({definition['definitionHash']})")
        ports = _ports(DEMO_START, DEMO_END)
        log("capture run (fresh inference of reference-heuristic-v1, recorded)")
        capture, run, problems = _capture_and_replay(
            DEMO_EXPERIMENT_ID, DEMO_START, DEMO_END, target, evidence, ports, work / "main"
        )
        if problems:
            raise RuntimeError(f"capture and recorded replay disagree: {problems[:5]}")
        _write_run(run, capture, target)
        store = evidence.store
        report = demo_report(
            run.manifest,
            run.records,
            run.outcomes,
            store,
            data_gaps=ports[1].data_gaps(DEMO_START, DEMO_END),
        )
        _dump(target / "report" / "report.json", report)
        (target / "report" / "report.md").write_text(render_demo_markdown(report))
        events = policy_events(store, DEMO_START, DEMO_END)
        comparisons = {}
        for event in events:
            results = {
                sid: run.outcomes.get(f"dec:{run.manifest.run_id}:{sid}:{event['session']}:r0")
                for sid in ("llm_rag", "llm_graph", "llm_team")
            }
            comparison = evidence_comparison(event, results, store)
            name = f"{event['session']}-{event['documentType']}"
            _dump(target / "evidence" / f"{name}.json", comparison)
            (target / "evidence" / f"{name}.md").write_text(render_comparison_markdown(comparison))
            comparisons[name] = comparison
        log("failure-injection run (declared faults, separately labelled)")
        faults_dir = target / "failure-injection"
        fcap, frun, fproblems = _capture_and_replay(
            f"{DEMO_EXPERIMENT_ID}-faults",
            FAULT_START,
            FAULT_END,
            faults_dir,
            evidence,
            _ports(FAULT_START, FAULT_END),
            work / "faults",
            faults=FAULT_PLAN,
        )
        if fproblems:
            raise RuntimeError(f"failure-injection capture and replay disagree: {fproblems[:5]}")
        _write_run(frun, fcap, faults_dir)
        _dump(faults_dir / "fault-plan.json", {"label": "FAILURE INJECTION", "faults": FAULT_PLAN})
        freport = demo_report(
            frun.manifest,
            frun.records,
            frun.outcomes,
            store,
            label="FAILURE INJECTION run (declared faults; not comparable with the canonical run)",
        )
        _dump(faults_dir / "report" / "report.json", freport)
        (faults_dir / "report" / "report.md").write_text(render_demo_markdown(freport))
        audits = []
        for fault in FAULT_PLAN:
            audit = _fault_audit(fault, frun.outcomes, frun.records, frun.manifest.run_id)
            path = f"failure-injection/audit/{fault['faultId']}.json"
            _dump(target / path, audit)
            audits.append(path)
        statement = _walkthrough_event(events, run.outcomes, run.manifest.run_id)
        comparison_name = f"{statement['session']}-{statement['documentType']}"
        walkthrough = build_walkthrough(
            ports[0],
            ports[1],
            run.records,
            run.outcomes,
            run.manifest.run_id,
            statement,
            f"evidence/{comparison_name}.json",
            report,
            audits,
        )
        _dump(target / "walkthrough.json", walkthrough)
        sensitivity_rows = (
            _sensitivity(evidence, ports, work / "sensitivity", target, log) if sensitivity else []
        )
        if sensitivity_rows:
            _dump(target / "sensitivity" / "summary.json", {"profiles": sensitivity_rows})
    bundle = {
        "bundleVersion": BUNDLE_VERSION,
        "experimentId": DEMO_EXPERIMENT_ID,
        "definitionHash": definition["definitionHash"],
        "builtFromGitCommit": run.manifest.git_commit,
        "modelDisclosure": report["demo"]["modelDisclosure"],
        "runs": {
            "canonical": {
                "runId": run.manifest.run_id,
                "responseMode": run.manifest.response_mode,
                "responseSource": run.manifest.response_source,
                "manifestHash": run.manifest.manifest_hash,
                "captureManifestHash": capture.manifest.manifest_hash,
                "expected": _expected(run, report),
            },
            "failureInjection": {
                "runId": frun.manifest.run_id,
                "label": "FAILURE INJECTION (declared faults)",
                "responseMode": frun.manifest.response_mode,
                "responseSource": frun.manifest.response_source,
                "manifestHash": frun.manifest.manifest_hash,
                "expected": _expected(frun, freport),
            },
        },
        "evidenceComparisons": {
            name: content_hash(c, allow_floats=True) for name, c in sorted(comparisons.items())
        },
        "sensitivity": [r["profile"] for r in sensitivity_rows],
        "files": _file_index(target),
    }
    _dump(target / "bundle.json", bundle)
    return bundle


# --------------------------------------------------------------------------- #
# Verify
# --------------------------------------------------------------------------- #


@dataclass
class DemoVerification:
    ok: bool
    checks: list[dict] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "passed": passed, "detail": detail})
        if not passed:
            self.ok = False
            self.mismatches.append(f"{name}: {detail}" if detail else name)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": self.checks,
            "mismatches": self.mismatches,
            "notes": self.notes,
        }


def _first_difference(expected: Any, actual: Any, path: str = "") -> Optional[str]:
    """Path and values of the first differing leaf of two wire payloads (for diagnostics)."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            found = _first_difference(expected.get(key), actual.get(key), f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path or '.'} length {len(expected)} -> {len(actual)}"
        for index, (a, b) in enumerate(zip(expected, actual)):
            found = _first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
        return None
    if expected != actual:
        return f"{path or '.'} {str(expected)[:80]!r} -> {str(actual)[:80]!r}"
    return None


def _diff_results(expected: dict, actual: dict, limit: int = 5) -> list[str]:
    out = []
    for decision_id in sorted(set(expected) | set(actual)):
        a, b = expected.get(decision_id), actual.get(decision_id)
        if a is None or b is None:
            out.append(f"{decision_id}:missing")
        elif a.to_wire() != b.to_wire():
            where = _first_difference(a.to_wire(), b.to_wire())
            out.append(f"{decision_id}:result_differs at {where}")
        if len(out) >= limit:
            break
    return out


def _diff_commits(expected: list[dict], actual: list[dict]) -> Optional[str]:
    exp = [r for r in expected if r["kind"] == "commit"]
    act = [r for r in actual if r["kind"] == "commit"]
    if len(exp) != len(act):
        return f"transition count {len(act)} != {len(exp)}"
    for index, (a, b) in enumerate(zip(exp, act)):
        if a != b:
            return f"transition {index} ({a['proposal']['commandId']}) differs"
    return None


def _diff_report(expected: dict, actual: dict, path: str = "") -> list[str]:
    """Values present in the bundle report must be reproduced; extra keys are notes."""
    out = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected):
            if not path and key in VOLATILE_REPORT_FIELDS:
                continue
            if key not in actual:
                out.append(f"{path}{key}:missing")
            else:
                out += _diff_report(expected[key], actual[key], f"{path}{key}.")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(f"{path}length {len(actual)} != {len(expected)}")
        else:
            for i, (a, b) in enumerate(zip(expected, actual)):
                out += _diff_report(a, b, f"{path}{i}.")
    elif expected != actual:
        out.append(f"{path.rstrip('.')}: {actual!r} != {expected!r}")
    return out


def _extra_keys(expected: Any, actual: Any, path: str = "") -> list[str]:
    out = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(actual):
            if key not in expected:
                out.append(f"{path}{key}")
            else:
                out += _extra_keys(expected[key], actual[key], f"{path}{key}.")
    elif isinstance(expected, list) and isinstance(actual, list):
        for i, (a, b) in enumerate(zip(expected, actual)):
            out += _extra_keys(a, b, f"{path}{i}.")
    return out


def _manifest_core(manifest: ExperimentManifest) -> dict:
    wire = manifest.to_wire()
    for name in VOLATILE_MANIFEST_FIELDS:
        wire.pop(name, None)
    wire.pop("artifacts", None)  # checksums of files compared directly
    return wire


def _verify_run(
    label: str,
    bundle_dir: Path,
    evidence,
    ports,
    work: Path,
    verification: DemoVerification,
    faults: Optional[list[dict]] = None,
    report_label: str = "canonical recorded-response replay",
    data_gaps: bool = True,
) -> Optional[RunArtifacts]:
    from research_engine.agents.providers import RecordedResponseProvider

    config = ReplayConfig.model_validate_json((bundle_dir / "run" / "config.json").read_text())
    verification.check(
        f"{label}:response_mode",
        config.response_mode == "recorded_replay"
        and config.effective_replay_source == "recorded_responses",
        f"{config.response_mode}/{config.effective_replay_source}",
    )
    expected_manifest = ExperimentManifest.model_validate_json(
        (bundle_dir / "run" / "manifest.json").read_text()
    )
    verification.check(f"{label}:manifest_hash", verify_manifest(expected_manifest))
    strategies = _strategies(RecordedResponseProvider(bundle_dir / "responses"), evidence, faults)
    drift = [
        s.strategy_id for s in config.strategies if strategies[s.strategy_id].config != s.config
    ]
    verification.check(f"{label}:strategy_configs", not drift, ",".join(drift))
    if drift:
        return None
    with providers_disabled():
        result = _run(config, strategies, ports, work / label)
    actual = _collect(work / label, result.status)
    expected_outcomes = _outcomes(bundle_dir / "run" / "outcomes.jsonl")
    diffs = _diff_results(expected_outcomes, actual.outcomes)
    verification.check(
        f"{label}:strategy_results_identical",
        not diffs,
        f"{len(expected_outcomes)} decisions" if not diffs else "; ".join(diffs),
    )
    expected_records = _jsonl(bundle_dir / "run" / "commits.jsonl.gz")
    commit_diff = _diff_commits(expected_records, actual.records)
    verification.check(
        f"{label}:transitions_identical",
        commit_diff is None,
        commit_diff or f"{sum(1 for r in expected_records if r['kind'] == 'commit')} transitions",
    )
    expected_states = _final_states(expected_records)
    actual_states = _final_states(actual.records)
    verification.check(f"{label}:final_state_hashes", expected_states == actual_states)
    checkpoint_expected = _load(bundle_dir / "run" / "checkpoint.json")
    checkpoint_actual = _load(work / label / "checkpoint.json")
    verification.check(
        f"{label}:checkpoint_portfolios",
        checkpoint_expected["portfolios"] == checkpoint_actual["portfolios"]
        and checkpoint_expected["eventPosition"] == checkpoint_actual["eventPosition"],
    )
    core_expected = _manifest_core(expected_manifest)
    core_actual = _manifest_core(actual.manifest)
    differing = sorted(k for k in core_expected if core_expected.get(k) != core_actual.get(k))
    verification.check(f"{label}:manifest_content", not differing, ",".join(differing))
    if expected_manifest.git_commit != actual.manifest.git_commit:
        verification.notes.append(
            f"{label}: built at git {expected_manifest.git_commit}, verified at "
            f"{actual.manifest.git_commit} (informational)"
        )
    if expected_manifest.dependency_lock_hashes != actual.manifest.dependency_lock_hashes:
        verification.notes.append(f"{label}: dependency lock hashes changed since build")
    gaps = ports[1].data_gaps(config.start_date, config.end_date) if data_gaps else None
    report = demo_report(
        actual.manifest,
        actual.records,
        actual.outcomes,
        evidence.store,
        data_gaps=gaps,
        label=report_label,
    )
    expected_report = _load(bundle_dir / "report" / "report.json")
    report_diffs = _diff_report(expected_report, report)
    verification.check(
        f"{label}:report_metrics_identical", not report_diffs, "; ".join(report_diffs[:5])
    )
    extra = _extra_keys(expected_report, report)
    if extra:
        verification.notes.append(
            f"{label}: report now has {len(extra)} additional field(s) not in the bundle "
            f"(e.g. {extra[0]}); bundle values were reproduced"
        )
    return actual


def verify_demo(
    bundle_dir: Optional[Path] = None,
    *,
    home: Optional[Path] = None,
    log: Callable[[str], None] = lambda _msg: None,
) -> DemoVerification:
    """Replay the bundle from recorded responses with every provider disabled."""
    from research_engine.agents.ports import open_default_evidence_port

    bundle_dir = Path(bundle_dir or DEMO_ROOT / DEMO_EXPERIMENT_ID)
    verification = DemoVerification(ok=True)
    bundle = _load(bundle_dir / "bundle.json")
    index = {row["path"]: row for row in bundle["files"]}
    bad = [
        path
        for path, row in index.items()
        if not (bundle_dir / path).exists()
        or sha256_bytes((bundle_dir / path).read_bytes()) != row["sha256"]
    ]
    verification.check("bundle_file_checksums", not bad, ",".join(bad[:5]) or f"{len(index)} files")
    definition = _load(bundle_dir / "definition.json")
    body = {k: v for k, v in definition.items() if k != "definitionHash"}
    verification.check(
        "definition_hash",
        content_hash(body) == definition["definitionHash"] == bundle["definitionHash"],
    )
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        evidence = open_default_evidence_port(home or work / "evidence-home")
        verification.check(
            "evidence_index_build",
            evidence.index_build_id == definition["evidence"]["indexBuildId"],
            evidence.index_build_id,
        )
        ports = _ports(DEMO_START, DEMO_END)
        log("recorded-response replay of the canonical run (providers disabled)")
        actual = _verify_run("canonical", bundle_dir, evidence, ports, work, verification)
        if actual is not None:
            expected = bundle["runs"]["canonical"]["expected"]
            verification.check(
                "canonical:expected_summary",
                _final_states(actual.records) == expected["finalStateHashes"]
                and len(actual.outcomes) == expected["decisions"],
            )
            log("stored-results replay of the canonical run (strategies not called)")
            config = ReplayConfig.model_validate_json(
                (bundle_dir / "run" / "config.json").read_text()
            )
            stored = ReplayConfig.model_validate({**config.to_wire(), "replaySource": None})
            recorded = _outcomes(bundle_dir / "run" / "outcomes.jsonl")
            with providers_disabled():
                result = _run(
                    stored,
                    _strategies(_NoProvider(), evidence),
                    ports,
                    work / "stored",
                    recorded_outcomes=recorded,
                )
            stored_run = _collect(work / "stored", result.status)
            verification.check(
                "stored_results:strategy_results_identical",
                not _diff_results(recorded, stored_run.outcomes),
            )
            verification.check(
                "stored_results:transitions_identical",
                _diff_commits(actual.records, stored_run.records) is None,
            )
            events = policy_events(evidence.store, DEMO_START, DEMO_END)
            for event in events:
                name = f"{event['session']}-{event['documentType']}"
                results = {
                    sid: actual.outcomes.get(
                        f"dec:{actual.manifest.run_id}:{sid}:{event['session']}:r0"
                    )
                    for sid in ("llm_rag", "llm_graph", "llm_team")
                }
                comparison = evidence_comparison(event, results, evidence.store)
                verification.check(
                    f"evidence_comparison:{name}",
                    content_hash(comparison, allow_floats=True)
                    == bundle["evidenceComparisons"].get(name),
                )
        log("recorded-response replay of the failure-injection run (providers disabled)")
        _verify_run(
            "failure_injection",
            bundle_dir / "failure-injection",
            evidence,
            _ports(FAULT_START, FAULT_END),
            work,
            verification,
            faults=FAULT_PLAN,
            report_label="FAILURE INJECTION run (declared faults; not comparable with the "
            "canonical run)",
            data_gaps=False,
        )
    return verification


class _NoProvider:
    """Placeholder provider for result-level replay: strategies are never called."""

    provider = "reference"
    model = "reference-heuristic-v1"
    deterministic = True
    priced = False
    replay = True

    def generate(self, request):  # pragma: no cover - must never run
        raise ProvidersDisabled("stored-results replay must not call a provider")
