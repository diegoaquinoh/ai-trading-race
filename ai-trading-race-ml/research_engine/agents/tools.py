"""Typed, allowlisted agent tools bound to one frozen decision snapshot (spec 10.5).

:class:`ToolBinding` freezes what a decision may see: the decision cutoff, the
common curve snapshot of the session, the strategy's *own* portfolio state at
the decision version, the eligible universe, and the read-only pricing/market
ports. Tools never read today's mutable state, another competitor's portfolio
or a later curve/index: none of those references is a tool argument.

:class:`DecisionToolbox` enforces, for every call:

1. allowlist - the tool exists and is permitted for the agent role and the
   strategy (``llm_market`` has no evidence tools; specialists and research
   notes cannot call ``propose_targets``); otherwise ``denied_policy``;
2. typed arguments (Pydantic, extra fields forbidden);
3. budget - ``tool_calls`` (and ``evidence_calls`` for evidence tools) are
   reserved atomically on the decision-wide ledger before execution; a denial
   raises :class:`BudgetExceeded` (the decision ends ``failed_budget``);
4. execution against the frozen snapshot; numerical outputs are registered as
   signed calculations in the CalculationStore and returned by calculation id;
5. a :class:`ToolTrace` with float-free request and response summaries.

Retrieved passages are returned as structured records; the workflow renders
their text inside ``<untrusted_document>`` blocks, and instructions inside
documents never change tool permissions, limits or targets (permissions are
enforced here, targets by validation and the policy dry run).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Protocol, Sequence

from pydantic import ValidationError

from research_engine import ENGINE_VERSION
from research_engine.contracts.calculations import (
    CalculatedValue,
    CalculationResult,
    CalculationType,
    Completeness,
    EngineProvenance,
    ValueBasis,
)
from research_engine.contracts.common import (
    DataMode,
    Unit,
    content_hash,
    short_id,
)
from research_engine.contracts.decisions import RetrievalMode, ToolTrace
from research_engine.contracts.evidence import DeliveredChunk, EvidenceBundle
from research_engine.contracts.portfolio import (
    DecisionAction,
    ExecutionModel,
    PortfolioState,
    RiskPolicy,
    TargetWeight,
)
from research_engine.pricing.calc_store import CalculationStore
from research_engine.risk.scenarios import SCENARIO_LIBRARY_V1, SCENARIO_LIBRARY_VERSION
from research_engine.simulation.clock import make_id

from .budget import BudgetExceeded, BudgetLedger, TaskAllowance
from .ports import EvidencePort, EvidenceUnavailable, GraphUnavailable
from .tool_schemas import (
    EVIDENCE_TOOLS,
    PROPOSAL_TOOLS,
    TOOL_ARGS,
    TOOL_SCHEMA_VERSION,
    ExpandEvidenceGraphArgs,
    InstrumentTermsArgs,
    PortfolioRiskArgs,
    ProposeTargetsArgs,
    RetrieveEvidenceArgs,
    RunScenarioArgs,
    ValuationArgs,
)

KEY_TENORS = ("2Y", "5Y", "10Y", "30Y")
FEATURE_LAGS = (1, 5, 21)  # supported sessions back
MARKET_FEATURES_VERSION = "market-features-v1"
PORTFOLIO_RISK_VERSION = "agent-portfolio-risk-v1"
TEN_THOUSAND = Decimal(10000)
RATIO_Q = Decimal("0.00000001")

ROLE_RANK = {
    "single": 0,
    "lead": 0,
    "research_note": 0,
    "macro_researcher": 1,
    "critical_reviewer": 2,
}

ROLE_TOOLS: dict[str, frozenset[str]] = {
    "single": frozenset(TOOL_ARGS),
    "lead": frozenset(TOOL_ARGS),
    "macro_researcher": frozenset(
        {
            "get_market_features",
            "get_instrument_terms",
            "retrieve_evidence",
            "expand_evidence_graph",
        }
    ),
    "critical_reviewer": frozenset(
        {
            "get_portfolio_risk",
            "run_scenario",
            "get_valuation",
            "retrieve_evidence",
            "expand_evidence_graph",
        }
    ),
    "research_note": frozenset(TOOL_ARGS) - PROPOSAL_TOOLS,
}


class ToolPolicyError(ValueError):
    """A typed request that the frozen-snapshot policy refuses (denied_policy)."""


class MacroFeatureSource(Protocol):
    def series(self) -> list[tuple[str, list]]:
        """[(series_id, [MacroObservation...])]; selection is vintage-aware here."""
        ...


@dataclass
class ToolBinding:
    decision_id: str
    strategy_id: str
    decision_as_of: datetime
    pricing: Any
    market: Any
    risk_policy: RiskPolicy
    execution_model: ExecutionModel
    session_date: Optional[date] = None
    curve_snapshot_id: Optional[str] = None
    curve_content_hash: Optional[str] = None
    curve_available_at: Optional[datetime] = None
    market_snapshot_id: Optional[str] = None
    data_mode: DataMode = DataMode.SYNTHETIC_CURVE
    portfolio_state: Optional[PortfolioState] = None
    portfolio_snapshot_id: Optional[str] = None
    universe: tuple[str, ...] = ()
    snapshot_fn: Optional[Callable[[], Any]] = None  # -> DecisionSnapshot
    macro_source: Optional[MacroFeatureSource] = None

    @classmethod
    def from_context(cls, ctx, *, macro_source: Optional[MacroFeatureSource] = None):
        curve_id = ctx.market_snapshot.curve_snapshot_id
        info = ctx.market.curve_for_session(ctx.market_snapshot.session_date)
        if info is not None and info.curve_snapshot_id != curve_id:
            info = None
        return cls(
            decision_id=ctx.request.decision_id,
            strategy_id=ctx.request.strategy_id,
            decision_as_of=ctx.request.decision_as_of,
            pricing=ctx.pricing,
            market=ctx.market,
            risk_policy=ctx.risk_policy,
            execution_model=ctx.execution_model,
            session_date=ctx.market_snapshot.session_date,
            curve_snapshot_id=curve_id,
            curve_content_hash=info.content_hash if info else None,
            curve_available_at=info.available_at if info else None,
            market_snapshot_id=ctx.market_snapshot.market_snapshot_id,
            data_mode=ctx.market_snapshot.data_mode,
            portfolio_state=ctx.portfolio_state,
            portfolio_snapshot_id=ctx.request.portfolio_snapshot.id,
            universe=tuple(sorted(i.security_id for i in ctx.universe)),
            snapshot_fn=lambda: ctx.snapshot,
            macro_source=macro_source,
        )

    def holdings(self) -> list[tuple[str, Decimal]]:
        if self.portfolio_state is None:
            return []
        return [
            (p.security_id, p.economic_face)
            for p in sorted(self.portfolio_state.positions, key=lambda p: p.security_id)
            if p.economic_face > 0
        ]


@dataclass
class ToolOutcome:
    name: str
    status: str
    payload: dict[str, Any]
    trace: ToolTrace
    documents: list[DeliveredChunk] = field(default_factory=list)
    bundle_id: Optional[str] = None


def float_free(value: Any) -> Any:
    """JSON-safe, canonical-hash-safe copy (floats become repr strings)."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): float_free(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [float_free(v) for v in value]
    return str(value)


def _s(value: Optional[Decimal], places: Optional[str] = None) -> Optional[str]:
    if value is None:
        return None
    value = Decimal(value)
    if places:
        value = value.quantize(Decimal(places))
    return format(value, "f")


class DecisionToolbox:
    def __init__(
        self,
        binding: ToolBinding,
        ledger: BudgetLedger,
        *,
        strategy_tools: frozenset[str],
        evidence: Optional[EvidencePort] = None,
        retrieval_mode: RetrievalMode = RetrievalMode.NONE,
        calc_store: Optional[CalculationStore] = None,
        timing: str = "logical",
        retrieval_max_chunks: int = 12,
        retrieval_max_tokens: int = 8000,
        permission_scope: str = "public",
    ):
        self.binding = binding
        self.ledger = ledger
        self.evidence = evidence
        self.retrieval_mode = retrieval_mode
        tools = set(strategy_tools)
        if retrieval_mode == RetrievalMode.NONE or evidence is None:
            tools -= EVIDENCE_TOOLS
        if retrieval_mode != RetrievalMode.GRAPH_RAG:
            tools.discard("expand_evidence_graph")
        if binding.portfolio_state is None:
            tools -= {"get_portfolio_risk", "run_scenario", "propose_targets"}
        if binding.curve_snapshot_id is None:
            tools -= {"get_market_features", "get_valuation", "get_portfolio_risk", "run_scenario"}
        self.strategy_tools = frozenset(tools)
        self.calc_store = (
            calc_store or getattr(binding.pricing, "calc_store", None) or CalculationStore()
        )
        self.timing = timing
        self.retrieval_max_chunks = retrieval_max_chunks
        self.retrieval_max_tokens = retrieval_max_tokens
        self.permission_scope = permission_scope
        self.phase = 0
        self.parallel = False
        self._clock = 0
        self._lock = threading.RLock()
        self._seq: dict[str, int] = {}
        self._traces: list[tuple[tuple, ToolTrace]] = []
        self.issued_calc_ids: set[str] = set()
        self.bundles: dict[str, EvidenceBundle] = {}
        self.delivered: dict[str, list[str]] = {}  # bundle id -> admitted chunk ids
        self.retrieval_run_ids: list[str] = []

    # ------------------------------------------------------------------ permissions

    def allowed_tools(self, role: str) -> list[str]:
        return sorted(ROLE_TOOLS.get(role, frozenset()) & self.strategy_tools)

    # ------------------------------------------------------------------ bookkeeping

    def traces(self) -> list[ToolTrace]:
        with self._lock:
            return [t for _, t in sorted(self._traces, key=lambda item: item[0])]

    def _next_seq(self, role: str) -> int:
        with self._lock:
            value = self._seq.get(role, 0) + 1
            self._seq[role] = value
            return value

    def _issue(self, *calc_ids: Optional[str]) -> None:
        with self._lock:
            self.issued_calc_ids.update(c for c in calc_ids if c)

    def delivered_chunks(self) -> dict[str, tuple[str, DeliveredChunk]]:
        with self._lock:
            out: dict[str, tuple[str, DeliveredChunk]] = {}
            for bundle_id, ids in self.delivered.items():
                bundle = self.bundles[bundle_id]
                for chunk_id in ids:
                    chunk = bundle.chunk(chunk_id)
                    if chunk is not None and chunk_id not in out:
                        out[chunk_id] = (bundle_id, chunk)
            return out

    def allowed_seeds(self) -> set[str]:
        seeds: set[str] = set()
        with self._lock:
            for bundle_id, ids in self.delivered.items():
                bundle = self.bundles[bundle_id]
                for chunk_id in ids:
                    chunk = bundle.chunk(chunk_id)
                    if chunk is None:
                        continue
                    seeds.add(chunk.version_id)
                    seeds.add(chunk.document_id)
                    graph = chunk.provenance.graph
                    if graph is not None:
                        seeds.add(graph.seed_id)
                for fact in bundle.structured_facts:
                    seeds.add(fact.subject_id)
                    seeds.add(fact.object_id)
        return seeds

    def _record(self, role, seq, name, request, summary, status, error, started, duration, ref):
        trace = ToolTrace(
            trace_id=make_id("tt", self.binding.decision_id, role, f"{seq:02d}"),
            agent_role=role,
            tool_name=name,
            request=float_free(request),
            response_summary=float_free(summary),
            output_ref=ref,
            started_at=started,
            duration_ms=duration,
            status=status,
            error=error,
        )
        with self._lock:
            self._clock += 1
            if self.parallel:
                key = (self.phase, ROLE_RANK.get(role, 9), role, seq)
            else:
                key = (self.phase, 0, "", self._clock)
            self._traces.append((key, trace))
        return trace

    def _times(self) -> tuple[datetime, float]:
        if self.timing == "wall":
            return datetime.now(timezone.utc), time.perf_counter()
        return self.binding.decision_as_of, 0.0

    def _duration(self, start: float) -> int:
        if self.timing == "wall":
            return int((time.perf_counter() - start) * 1000)
        return 0

    # ------------------------------------------------------------------ entry point

    def call(
        self,
        role: str,
        name: str,
        arguments: Optional[dict[str, Any]] = None,
        *,
        allowance: Optional[TaskAllowance] = None,
        retrieval_limits: Optional[tuple[int, int]] = None,
    ) -> ToolOutcome:
        arguments = arguments or {}
        seq = self._next_seq(role)
        started, clock = self._times()

        def outcome(status, payload, error=None, ref=None, documents=(), bundle_id=None):
            summary = {k: v for k, v in payload.items() if k in _SUMMARY_KEYS}
            summary["status"] = status
            trace = self._record(
                role,
                seq,
                name,
                arguments,
                summary,
                status,
                error,
                started,
                self._duration(clock),
                ref,
            )
            return ToolOutcome(name, status, payload, trace, list(documents), bundle_id)

        if name not in TOOL_ARGS:
            return outcome("denied_policy", {"error": "unknown_tool"}, "unknown_tool")
        if name not in self.allowed_tools(role):
            return outcome(
                "denied_policy",
                {"error": "tool_not_permitted"},
                f"tool_not_permitted_for_role:{role}",
            )
        try:
            args = TOOL_ARGS[name].model_validate(arguments)
        except ValidationError as exc:
            message = "; ".join(e["msg"] for e in exc.errors()[:4])
            return outcome("error", {"error": f"invalid_arguments: {message}"}, "invalid_arguments")
        amounts = {"tool_calls": 1}
        if name in EVIDENCE_TOOLS:
            amounts["evidence_calls"] = 1
        try:
            reservation = self.ledger.reserve(f"{role}:tool:{name}", allowance=allowance, **amounts)
        except BudgetExceeded as exc:
            outcome("denied_budget", {"error": str(exc)}, f"budget:{exc.resource}")
            raise
        try:
            payload, ref, documents, bundle_id = getattr(self, f"_{name}")(
                args, _Opts(allowance, retrieval_limits)
            )
        except ToolPolicyError as exc:
            self.ledger.release(reservation)
            return outcome("denied_policy", {"error": str(exc)}, str(exc))
        except (GraphUnavailable, EvidenceUnavailable) as exc:
            self.ledger.commit(reservation, **amounts)
            outcome("error", {"error": type(exc).__name__}, f"{type(exc).__name__}: {exc}")
            raise
        except Exception as exc:  # deterministic tool failure: visible, not fatal
            self.ledger.commit(reservation, **amounts)
            return outcome("error", {"error": type(exc).__name__}, f"{type(exc).__name__}: {exc}")
        self.ledger.commit(reservation, **amounts)
        return outcome("ok", payload, None, ref, documents, bundle_id)

    # ------------------------------------------------------------------ helpers

    def _check_securities(self, security_ids: Sequence[str]) -> list[str]:
        held = {sid for sid, _ in self.binding.holdings()}
        allowed = set(self.binding.universe) | held
        bad = [sid for sid in security_ids if sid not in allowed]
        if bad:
            raise ToolPolicyError(f"security_not_in_frozen_universe:{','.join(sorted(bad))}")
        return list(dict.fromkeys(security_ids))

    def _curve_snapshot(self, curve_id: str):
        for owner in (self.binding.pricing, self.binding.market):
            for attr in ("curve_snapshot", "get_curve_snapshot"):
                getter = getattr(owner, attr, None)
                if callable(getter):
                    try:
                        return getter(curve_id)
                    except Exception:
                        continue
        return None

    def _provenance(self) -> EngineProvenance:
        return EngineProvenance(
            engine_name="research_engine.agents.tools",
            engine_version=ENGINE_VERSION,
            library="research_engine",
            conventions_version=TOOL_SCHEMA_VERSION,
        )

    def _register(self, calc: CalculationResult) -> str:
        sealed = self.calc_store.register(calc)
        self._issue(sealed.calculation_id)
        return sealed.calculation_id

    # ------------------------------------------------------------------ numerical tools

    def _get_instrument_terms(self, args: InstrumentTermsArgs, allowance):
        ids = self._check_securities(args.security_ids)
        terms = []
        for sid in ids:
            info = self.binding.pricing.instrument(sid)
            terms.append(
                {
                    "securityId": sid,
                    "couponRate": _s(info.coupon_rate),
                    "couponFrequency": info.coupon_frequency,
                    "issueDate": info.issue_date.isoformat(),
                    "maturityDate": info.maturity_date.isoformat(),
                    "dayCount": info.day_count,
                    "minFaceUsd": _s(info.min_face_usd),
                    "faceIncrementUsd": _s(info.face_increment_usd),
                    "termsVersion": info.terms_version,
                    "synthetic": info.synthetic,
                }
            )
        ref = short_id("terms", terms)
        return {"terms": terms, "termsRef": ref}, ref, [], None

    def _par_yields(self, snapshot) -> dict[str, Decimal]:
        return {r.tenor: Decimal(r.input_quote) for r in getattr(snapshot, "residuals", [])}

    def _get_market_features(self, args, allowance):
        b = self.binding
        snapshot = self._curve_snapshot(b.curve_snapshot_id)
        if snapshot is None:
            raise RuntimeError("curve snapshot unavailable for market features")
        levels = self._par_yields(snapshot)
        zeros = {n.source_tenor: Decimal(n.zero_rate) for n in snapshot.nodes if n.source_tenor}
        sessions = b.market.sessions(b.session_date - timedelta(days=45), b.session_date)
        earlier = [d for d in sessions if d < b.session_date]
        outputs: list[CalculatedValue] = []
        changes: dict[str, dict[str, str]] = {}
        lagged: dict[str, str] = {}
        lag_ids = []
        for tenor in KEY_TENORS:
            if tenor in levels:
                outputs.append(_value(f"par_yield:{tenor}", levels[tenor], Unit.DECIMAL_RATE))
            if tenor in zeros:
                outputs.append(_value(f"zero_rate:{tenor}", zeros[tenor], Unit.DECIMAL_RATE))
        for lag in FEATURE_LAGS:
            if len(earlier) < lag:
                continue
            day = earlier[-lag]
            info = b.market.curve_for_session(day)
            if info is None or str(info.status).upper() != "READY":
                continue
            if info.available_at > b.decision_as_of:  # never later data
                continue
            then = self._curve_snapshot(info.curve_snapshot_id)
            if then is None:
                continue
            old = self._par_yields(then)
            lagged[f"{lag}s"] = day.isoformat()
            lag_ids.append(info.curve_snapshot_id)
            per = {}
            for tenor in KEY_TENORS:
                if tenor in levels and tenor in old:
                    bp = ((levels[tenor] - old[tenor]) * TEN_THOUSAND).quantize(Decimal("0.01"))
                    per[tenor] = format(bp, "f")
                    outputs.append(
                        _value(f"par_yield_change_bp:{tenor}:{lag}s", bp, Unit.BASIS_POINTS)
                    )
            changes[f"{lag}s"] = per
        slope = None
        if "2Y" in levels and "10Y" in levels:
            slope = ((levels["10Y"] - levels["2Y"]) * TEN_THOUSAND).quantize(Decimal("0.01"))
            outputs.append(_value("slope_2s10s_bp", slope, Unit.BASIS_POINTS))
        macro = self._macro_features(outputs)
        calc = CalculationResult(
            calculation_type=CalculationType.MARKET_FEATURES,
            calculation_version=MARKET_FEATURES_VERSION,
            data_mode=b.data_mode,
            curve_snapshot_id=b.curve_snapshot_id,
            input_hashes={
                "curveSnapshot": snapshot.content_hash or "",
                "laggedCurves": content_hash(sorted(lag_ids)),
                "macro": content_hash(macro),
            },
            as_of=snapshot.available_at,
            valuation_date=b.session_date,
            outputs=outputs,
            completeness=Completeness.COMPLETE if changes else Completeness.PARTIAL,
            diagnostics=[
                "market features: curve levels/changes and numerical macro values only; "
                "no document text, summaries or graph content",
                "par yields are the session's published inputs; changes vs earlier READY "
                "curves available at the decision cutoff",
            ],
            engine=self._provenance(),
        )
        calc_id = self._register(calc)
        payload = {
            "calculationId": calc_id,
            "curveSnapshotId": b.curve_snapshot_id,
            "sessionDate": b.session_date.isoformat(),
            "parYields": {t: format(levels[t], "f") for t in KEY_TENORS if t in levels},
            "zeroRates": {t: _s(zeros[t], "0.000001") for t in KEY_TENORS if t in zeros},
            "changesBp": changes,
            "laggedSessions": lagged,
            "slope2s10sBp": _s(slope),
            "macro": macro,
            "units": {"parYields": "DECIMAL_ANNUAL_RATE", "changesBp": "BASIS_POINTS"},
        }
        return payload, calc_id, [], None

    def _macro_features(self, outputs: list[CalculatedValue]) -> list[dict[str, Any]]:
        source = self.binding.macro_source
        if source is None:
            return []
        from research_engine.market.fred import vintage_as_of

        rows = []
        for series_id, observations in source.series():
            vintage = vintage_as_of(observations, self.binding.decision_as_of)
            values = [o for o in vintage.observations if o.value is not None]
            if not values:
                continue
            last = values[-1]
            row = {
                "seriesId": series_id,
                "referencePeriod": last.reference_period.isoformat(),
                "value": _s(last.value),
                "units": last.units,
                "availableAt": last.available_at.isoformat(),
                "vintageHash": vintage.content_hash,
            }
            if len(values) > 1:
                row["previousValue"] = _s(values[-2].value)
            rows.append(row)
            outputs.append(_value(f"macro:{series_id}", last.value, Unit.RATIO))
        return rows

    def _get_valuation(self, args: ValuationArgs, allowance):
        b = self.binding
        ids = self._check_securities(args.security_ids)
        rows = []
        for sid in ids:
            settle = b.pricing.settlement_date(sid, b.session_date)
            price = b.pricing.price(sid, b.curve_snapshot_id, settle)
            row = {
                "securityId": sid,
                "settlementDate": settle.isoformat(),
                "cleanPricePer100": _s(price.clean_price_per_100),
                "accruedPer100": _s(price.accrued_per_100),
                "dirtyPricePer100": _s(price.dirty_price_per_100),
                "priceCalculationId": price.calculation_id,
            }
            ids_issued = [price.calculation_id]
            risk_fn = getattr(b.pricing, "position_risk", None)
            if callable(risk_fn):
                risk = risk_fn(sid, b.curve_snapshot_id, b.session_date)
                row.update(
                    {
                        "effectiveDurationYears": _s(risk.effective_duration_years),
                        "parallelDv01UsdPer100Face": _s(risk.parallel_dv01_usd),
                        "ytm": _s(risk.ytm),
                        "riskCalculationId": risk.calculation_id,
                    }
                )
                ids_issued.append(risk.calculation_id)
            self._issue(*ids_issued)
            rows.append(row)
        return {"valuations": rows, "curveSnapshotId": b.curve_snapshot_id}, None, [], None

    def _get_portfolio_risk(self, args: PortfolioRiskArgs, allowance):
        b = self.binding
        bad = [s for s in args.scenario_ids if s not in SCENARIO_LIBRARY_V1]
        if bad:
            raise ToolPolicyError(f"scenario_not_approved:{','.join(bad)}")
        snap = b.snapshot_fn() if b.snapshot_fn else None
        if snap is None or snap.nav is None or not snap.nav:
            raise RuntimeError("decision snapshot has no NAV")
        nav = Decimal(snap.nav)
        holdings = b.holdings()
        component_ids = sorted(set(snap.valuation.calculation_ids))
        dv01 = Decimal(snap.detail.total_dv01)
        duration = snap.portfolio_duration()
        scenarios = []
        report_fn = getattr(b.pricing, "portfolio_risk", None)
        if callable(report_fn) and holdings:
            report = report_fn(
                holdings,
                b.curve_snapshot_id,
                b.session_date,
                portfolio_snapshot_id=b.portfolio_snapshot_id,
                cash_usd=snap.contractual_cash,
                scenario_ids=list(args.scenario_ids),
            )
            component_ids = sorted(set(component_ids) | set(report.calculation_ids))
            for item in report.scenarios:
                scenarios.append(
                    {
                        "scenarioId": item.scenario_id,
                        "pnlUsd": _s(item.pnl_usd),
                        "calculationId": item.calculation_id,
                    }
                )
        positions = []
        universe = []
        outputs = [
            _value("nav_usd", nav, Unit.USD, ValueBasis.FACE_SCALED),
            _value("parallel_dv01_usd", dv01, Unit.USD_PER_BP, ValueBasis.FACE_SCALED),
        ]
        cash_ratio = (snap.contractual_cash / nav).quantize(RATIO_Q)
        funding_ratio = ((snap.cash_settled - snap.payables) / nav).quantize(RATIO_Q)
        dv01_per_million = (dv01 * Decimal(1_000_000) / nav).quantize(Decimal("0.01"))
        outputs += [
            _value("contractual_cash_ratio", cash_ratio, Unit.RATIO),
            _value("settled_funding_ratio", funding_ratio, Unit.RATIO),
            _value("parallel_dv01_usd_per_million_nav", dv01_per_million, Unit.USD_PER_BP),
        ]
        if duration is not None:
            outputs.append(_value("effective_duration_years", duration, Unit.YEARS))
        weights = {sid: snap.weight(sid) for sid in snap.detail.pv}
        for sid in sorted(set(snap.universe) | set(weights)):
            info = snap.instruments.get(sid)
            entry = {
                "securityId": sid,
                "weight": _s(Decimal(weights.get(sid, 0)).quantize(RATIO_Q)),
                "effectiveDurationYears": _s(snap.durations.get(sid), "0.0001"),
                "tradable": bool(snap.tradable.get(sid, False)),
                "maturityDate": info.maturity_date.isoformat() if info is not None else None,
            }
            universe.append(entry)
            if sid in weights:
                positions.append(entry)
                outputs.append(_value(f"weight:{sid}", weights[sid].quantize(RATIO_Q), Unit.WEIGHT))
        state_hash = b.portfolio_state.compute_hash() if b.portfolio_state else ""
        calc = CalculationResult(
            calculation_type=CalculationType.PORTFOLIO_RISK,
            calculation_version=PORTFOLIO_RISK_VERSION,
            data_mode=b.data_mode,
            curve_snapshot_id=b.curve_snapshot_id,
            input_hashes={
                "curveSnapshot": b.curve_content_hash or "",
                "portfolioState": state_hash,
                "components": content_hash(component_ids),
            },
            as_of=b.curve_available_at or b.decision_as_of,
            valuation_date=b.session_date,
            outputs=outputs,
            completeness=Completeness.COMPLETE if snap.complete else Completeness.PARTIAL,
            diagnostics=["own frozen portfolio at the decision version; weights = PV / NAV"]
            + list(snap.reasons),
            engine=self._provenance(),
        )
        calc_id = self._register(calc)
        self._issue(*component_ids)
        policy = b.risk_policy
        payload = {
            "calculationId": calc_id,
            "componentCalculationIds": component_ids,
            "portfolioSnapshotId": b.portfolio_snapshot_id,
            "navUsd": _s(nav, "0.01"),
            "effectiveDurationYears": _s(duration, "0.0001"),
            "parallelDv01Usd": _s(dv01, "0.01"),
            "parallelDv01UsdPerMillionNav": _s(dv01_per_million),
            "contractualCashRatio": _s(cash_ratio),
            "settledFundingRatio": _s(funding_ratio),
            "universe": universe,
            "scenarios": scenarios,
            "policyLimits": {
                "policyId": policy.policy_id,
                "minCashRatio": _s(policy.min_cash_ratio),
                "maxSingleSecurityRatio": _s(policy.max_single_security_ratio),
                "maxParallelDv01UsdPerMillionNav": _s(policy.max_parallel_dv01_usd_per_million_nav),
                "maxDailyTurnoverRatio": _s(policy.max_daily_turnover_ratio),
                "maxOrdersPerDecision": policy.max_orders_per_decision,
                "minWeightChange": _s(policy.min_weight_change),
                "fundingRule": "unsettled sale proceeds never fund purchases",
            },
        }
        return payload, calc_id, [], None

    def _run_scenario(self, args: RunScenarioArgs, allowance):
        b = self.binding
        if args.scenario_id not in SCENARIO_LIBRARY_V1:
            raise ToolPolicyError(f"scenario_not_approved:{args.scenario_id}")
        holdings = b.holdings()
        if not holdings:
            raise ToolPolicyError("no_holdings_to_reprice")
        result = b.pricing.portfolio_scenario(
            holdings, b.curve_snapshot_id, b.session_date, args.scenario_id
        )
        self._issue(result.calculation_id)
        payload = {
            "scenarioId": args.scenario_id,
            "libraryVersion": SCENARIO_LIBRARY_VERSION,
            "basePvUsd": _s(result.base_pv_usd),
            "scenarioPvUsd": _s(result.scenario_pv_usd),
            "pnlUsd": _s(result.pnl_usd),
            "dv01ApproxPnlUsd": _s(result.dv01_approx_pnl_usd),
            "calculationId": result.calculation_id,
            "hypothetical": True,
        }
        return payload, result.calculation_id, [], None

    # ------------------------------------------------------------------ evidence tools

    def _deliver(self, bundle: EvidenceBundle, allowance) -> tuple[dict, list[DeliveredChunk]]:
        if bundle.decision_as_of != self.binding.decision_as_of:
            raise EvidenceUnavailable("evidence bundle cutoff differs from the decision cutoff")
        admitted, rejected = self.ledger.register_chunks(
            [(c.chunk_id, c.token_count) for c in bundle.chunks], allowance=allowance
        )
        with self._lock:
            self.bundles[bundle.bundle_id] = bundle
            current = self.delivered.setdefault(bundle.bundle_id, [])
            for chunk_id in admitted:
                if chunk_id not in current:
                    current.append(chunk_id)
            if bundle.retrieval_run_id not in self.retrieval_run_ids:
                self.retrieval_run_ids.append(bundle.retrieval_run_id)
        documents = [c for c in bundle.chunks if c.chunk_id in set(admitted)]
        payload = {
            "bundleId": bundle.bundle_id,
            "retrievalRunId": bundle.retrieval_run_id,
            "mode": bundle.mode.value,
            "indexBuildId": bundle.index_build_id,
            "deliveredChunkIds": admitted,
            "rejectedForEvidenceBudget": rejected,
            "empty": not admitted,
            "structuredFacts": [
                {
                    "assertionId": f.assertion_id,
                    "relation": f.relation.value,
                    "subjectId": f.subject_id,
                    "subjectLabel": f.subject_label,
                    "objectId": f.object_id,
                    "objectLabel": f.object_label,
                    "availableAt": f.available_at.isoformat(),
                }
                for f in bundle.structured_facts
            ],
        }
        return payload, documents

    def _retrieve(self, question: str, explicit: Sequence[str], mode: RetrievalMode, opts):
        if self.evidence is None:
            raise EvidenceUnavailable("no evidence port configured")
        allowance = opts.allowance
        registered = self.ledger.registered_chunks()
        if allowance is not None:  # deterministic under parallel specialists
            free_chunks = (
                allowance.caps.get("unique_evidence_chunks", 0)
                - allowance.used["unique_evidence_chunks"]
            )
            free_tokens = (
                allowance.caps.get("evidence_tokens", 0) - allowance.used["evidence_tokens"]
            )
        else:
            remaining = self.ledger.remaining()
            free_chunks = remaining["unique_evidence_chunks"]
            free_tokens = remaining["evidence_tokens"]
        limit_chunks, limit_tokens = opts.retrieval_limits or (
            self.retrieval_max_chunks,
            self.retrieval_max_tokens,
        )
        max_chunks = min(limit_chunks, max(0, free_chunks) + len(registered))
        max_tokens = min(limit_tokens, max(0, free_tokens) + sum(registered.values()))
        bundle = self.evidence.retrieve(
            question=question,
            decision_as_of=self.binding.decision_as_of,
            mode=mode,
            max_chunks=max_chunks,
            max_evidence_tokens=max_tokens,
            explicit_identifiers=list(explicit),
            permission_scope=self.permission_scope,
        )
        payload, documents = self._deliver(bundle, allowance)
        return payload, bundle.bundle_id, documents, bundle.bundle_id

    def _retrieve_evidence(self, args: RetrieveEvidenceArgs, opts):
        return self._retrieve(args.question, (), self.retrieval_mode, opts)

    def _expand_evidence_graph(self, args: ExpandEvidenceGraphArgs, opts):
        allowed = self.allowed_seeds()
        seeds = [s for s in dict.fromkeys(args.seed_ids) if s in allowed]
        if not seeds:
            raise ToolPolicyError("no_seed_ids_delivered_to_this_decision")
        question = args.question or "Evidence linked to the selected graph seeds"
        return self._retrieve(question, seeds, RetrievalMode.GRAPH_RAG, opts)

    # ------------------------------------------------------------------ proposal tool

    def parse_targets(self, weights) -> list[TargetWeight]:
        targets = []
        for item in weights:
            try:
                value = Decimal(str(item.weight).strip())
            except InvalidOperation as exc:
                raise ToolPolicyError(f"invalid_weight:{item.security_id}") from exc
            if not value.is_finite():
                raise ToolPolicyError(f"non_finite_weight:{item.security_id}")
            targets.append(TargetWeight(security_id=item.security_id, weight=value))
        return targets

    def policy_dry_run(self, action: DecisionAction, targets: list[TargetWeight]):
        from research_engine.simulation.ledger import Book
        from research_engine.simulation.policy import evaluate_decision

        b = self.binding
        snap = b.snapshot_fn()
        evaluation, _orders = evaluate_decision(
            Book.from_state(b.portfolio_state),
            snap,
            decision_id=b.decision_id,
            action=action,
            targets=targets,
            policy=b.risk_policy,
            execution=b.execution_model,
            pricing=b.pricing,
            submitted_at=b.decision_as_of,
        )
        return evaluation  # orders are discarded: a dry run never creates intents

    def _propose_targets(self, args: ProposeTargetsArgs, allowance):
        try:
            targets = self.parse_targets(args.target_weights)
        except Exception as exc:
            raise ToolPolicyError(str(exc)) from exc
        evaluation = self.policy_dry_run(DecisionAction(args.action), targets)
        payload = {
            "dryRun": True,
            "passed": evaluation.passed,
            "rejectedReasons": evaluation.rejected_reasons,
            "failedChecks": [c.check_id for c in evaluation.checks if not c.passed],
            "orderCount": evaluation.order_count,
            "turnoverRatio": _s(evaluation.turnover_ratio),
            "postTradeCashRatio": _s(evaluation.post_trade_cash_ratio),
            "postTradeParallelDv01Usd": _s(evaluation.post_trade_parallel_dv01_usd),
            "normalizationNotes": evaluation.normalization_notes,
        }
        return payload, None, [], None


@dataclass(frozen=True)
class _Opts:
    allowance: Optional[TaskAllowance] = None
    retrieval_limits: Optional[tuple[int, int]] = None


_SUMMARY_KEYS = {
    "calculationId",
    "bundleId",
    "retrievalRunId",
    "deliveredChunkIds",
    "rejectedForEvidenceBudget",
    "empty",
    "scenarioId",
    "pnlUsd",
    "passed",
    "rejectedReasons",
    "error",
    "termsRef",
    "effectiveDurationYears",
    "navUsd",
}


def _value(
    name: str, value, unit: Unit, basis: ValueBasis = ValueBasis.UNSCALED
) -> CalculatedValue:
    return CalculatedValue(name=name, value=Decimal(value), unit=unit, basis=basis)
