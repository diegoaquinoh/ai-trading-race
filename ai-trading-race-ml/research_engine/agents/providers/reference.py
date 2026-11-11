"""``reference-heuristic-v1``: a deterministic, offline, rule-based policy model.

This is **not** a language model and is never presented as one. It is reported
as provider ``reference`` everywhere. It exists so demos and tests can run the
full agent workflow (tools, evidence, validation, policy, recording/replay)
end to end without credentials.

It reads only what a hosted model would read - the system prompt and the
messages - and parses the structured ``<platform_json>`` blocks and the
delivered ``<untrusted_document>`` texts. Behaviour (lexicon
``reference-lexicon-v1``):

* tool turns: single/lead agents request two approved scenarios (and, in graph
  mode, one graph expansion from delivered seeds); the macro researcher
  requests one focused retrieval; the critical reviewer requests the opposite
  and curve-shape scenarios;
* stance: sentence-level phrase counts (hawkish / dovish / neutral, with a
  simple negation guard), weighted by document recency; balanced hawkish and
  dovish signals are reported as ``contradictory_evidence``; no signal or no
  evidence is ``insufficient_evidence`` (decision ``abstain``);
* market-only stance: 21-session change of the 2Y par yield (+/-15 bp);
* claims quote exact sentences copied from delivered chunk text with offsets;
  numerical findings cite calculation ids returned by tools;
* targets: hawkish -> 3.0y duration, dovish -> 5.0y, neutral -> HOLD; sells
  only to shorten, buys only with settled cash above the reserve to lengthen,
  within turnover/cap/minimum-change limits; HOLD when no feasible move.

Instructions inside documents are ignored: the rules never read imperative
text, and documents only contribute phrase counts and exact quotes.
"""

from __future__ import annotations

import json
import re
from decimal import ROUND_DOWN, Decimal
from typing import Any, Optional

from ..prompts import parse_blocks, parse_documents
from .base import ModelRequest, ModelResponse, estimate_tokens

REFERENCE_MODEL_ID = "reference-heuristic-v1"
LEXICON_VERSION = "reference-lexicon-v1"
DISCLOSURE = (
    "reference-heuristic-v1 is a deterministic rule-based policy model used for offline demos "
    "and tests. It is not a hosted LLM and its outputs are not model inferences."
)

HAWKISH = (
    "raise the target range",
    "decided to raise",
    "additional policy firming",
    "further policy firming",
    "inflation remains elevated",
    "ongoing increases",
    "upside risks to inflation",
)
DOVISH = (
    "lower the target range",
    "decided to lower",
    "reduce the target range",
    "lowering the target range",
    "cut the target range",
    "inflation has eased",
    "downside risks to employment",
)
NEUTRAL = (
    "maintain the target range",
    "holding the target range steady",
    "hold the target range steady",
    "keep the target range",
)
NEGATIONS = (" not ", " until ", "n't ")
STANCE_TARGET_YEARS = {"hawkish": Decimal("3.0"), "dovish": Decimal("5.0")}
DRIFT_BAND_YEARS = Decimal("0.25")
SAFETY_MARGIN = Decimal("0.01")
MOVE_FLOOR_MARGIN = Decimal("0.005")
W_Q = Decimal("0.000001")
MARKET_MOVE_BP = Decimal("15")

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]")


def _dec(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value)) if value is not None else Decimal(default)
    except Exception:
        return Decimal(default)


class _State:
    """Everything the reference model can read from the conversation."""

    def __init__(self, request: ModelRequest):
        self.context: dict[str, Any] = {}
        self.turn: dict[str, Any] = {}
        self.results: list[dict[str, Any]] = []
        self.index: dict[str, dict[str, Any]] = {}
        self.docs: dict[str, str] = {}
        self.reports: list[dict[str, Any]] = []
        self.draft: Optional[dict[str, Any]] = None
        self.feedback: Optional[dict[str, Any]] = None
        for message in request.messages:
            if message.role != "user":
                continue
            for kind, data in parse_blocks(message.content):
                if kind == "context" and not self.context:
                    self.context = data
                elif kind == "turn":
                    self.turn = data
                elif kind == "tool_results":
                    self.results.extend(data.get("results", []))
                elif kind == "evidence_index":
                    for entry in data:
                        self.index.setdefault(entry["chunkId"], entry)
                elif kind == "specialist_reports":
                    self.reports = data.get("reports", [])
                elif kind == "draft":
                    self.draft = data
                elif kind == "validation_feedback":
                    self.feedback = data
            self.docs.update(parse_documents(message.content))

    @property
    def role(self) -> str:
        return self.turn.get("role", "single")

    def allowed(self, action: str) -> bool:
        return action in self.turn.get("allowedActions", [])

    def tool_allowed(self, tool: str) -> bool:
        return tool in self.turn.get("allowedTools", [])

    def outputs(self, tool: str) -> list[dict[str, Any]]:
        return [
            r["output"] for r in self.results if r.get("tool") == tool and r.get("status") == "ok"
        ]

    def called(self, tool: str) -> bool:
        return any(r.get("tool") == tool for r in self.results)

    def latest(self, tool: str) -> Optional[dict[str, Any]]:
        found = self.outputs(tool)
        if found:
            return found[-1]
        return self.context.get("required", {}).get(tool)


class ReferenceHeuristicProvider:
    provider = "reference"
    model = REFERENCE_MODEL_ID
    deterministic = True
    priced = False
    disclosure = DISCLOSURE

    def generate(self, request: ModelRequest) -> ModelResponse:
        state = _State(request)
        output = self._respond(state)
        text = json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return ModelResponse(
            text=text,
            input_tokens=estimate_tokens(request.payload_text()),
            output_tokens=estimate_tokens(text),
            provider=self.provider,
            model=self.model,
            latency_ms=0,
            stop_reason="end_turn",
        )

    # ------------------------------------------------------------------ dispatch

    def _respond(self, s: _State) -> dict[str, Any]:
        if s.allowed("delegate"):
            return self._assign(s)
        if s.role == "macro_researcher":
            return self._macro(s)
        if s.role == "critical_reviewer":
            return self._reviewer(s)
        if s.allowed("call_tools") and s.feedback is None:
            calls = self._tool_calls(s)
            if calls:
                return {"action": "call_tools", "calls": calls, "reason": "reference tool plan"}
        return self._final(s)

    def _tool_calls(self, s: _State) -> list[dict[str, Any]]:
        calls = []
        if s.tool_allowed("run_scenario") and not s.called("run_scenario"):
            for scenario in ("parallel_up_25", "parallel_down_25"):
                calls.append({"tool": "run_scenario", "arguments": {"scenario_id": scenario}})
        if s.tool_allowed("expand_evidence_graph") and not s.called("expand_evidence_graph"):
            seeds = sorted({e["graphSeedId"] for e in s.index.values() if e.get("graphSeedId")})[:4]
            if seeds:
                calls.append(
                    {
                        "tool": "expand_evidence_graph",
                        "arguments": {
                            "seed_ids": seeds,
                            "question": "Policy communications linked to these seeds",
                        },
                    }
                )
        return calls[:4]

    # ------------------------------------------------------------------ team roles

    def _assign(self, s: _State) -> dict[str, Any]:
        if not s.docs and not s.index:
            return {"action": "decline_delegation", "reason": "no delivered evidence to research"}
        return {
            "action": "delegate",
            "tasks": [
                {
                    "role": "macro_researcher",
                    "instruction": (
                        "Compare the delivered policy communications; report supported claims "
                        "with exact quotes, contradictory evidence and coverage gaps."
                    ),
                },
                {
                    "role": "critical_reviewer",
                    "instruction": (
                        "Challenge a duration change using opposite-direction and curve-shape "
                        "scenarios on the current exposures; list objections and assumptions."
                    ),
                },
            ],
            "reason": "evidence available; bounded research and review tasks",
        }

    def _macro(self, s: _State) -> dict[str, Any]:
        if (
            s.allowed("call_tools")
            and s.tool_allowed("retrieve_evidence")
            and not s.called("retrieve_evidence")
            and len(s.docs) < 4
        ):
            return {
                "action": "call_tools",
                "calls": [
                    {
                        "tool": "retrieve_evidence",
                        "arguments": {
                            "question": "FOMC assessment of inflation, employment and the "
                            "balance of risks"
                        },
                    }
                ],
                "reason": "focused retrieval for the assigned comparison",
            }
        analysis = _analyze(s)
        claims, citations = _claims(s, analysis, prefix="mr")
        findings = [analysis.summary()]
        if analysis.latest_title:
            findings.append(f"Most recent communication analysed: {analysis.latest_title}.")
        return {
            "action": "report",
            "findings": findings,
            "claims": claims,
            "citations": citations,
            "counterevidence": analysis.counter[:2],
            "coverage_gaps": _gaps(s),
            "objections": [],
            "alternative_scenarios": [],
            "unresolved_assumptions": [],
            "calculation_ids": [],
        }

    def _reviewer(self, s: _State) -> dict[str, Any]:
        wanted = [x for x in ("parallel_down_25", "steepener_v1") if not _scenario(s, x)]
        if (
            s.allowed("call_tools")
            and s.tool_allowed("run_scenario")
            and wanted
            and not s.called("run_scenario")
        ):
            return {
                "action": "call_tools",
                "calls": [
                    {"tool": "run_scenario", "arguments": {"scenario_id": x}} for x in wanted
                ],
                "reason": "test the candidate against opposite and curve-shape moves",
            }
        objections, alternatives, calc_ids = [], [], []
        for scenario in ("parallel_down_25", "steepener_v1", "parallel_up_25"):
            out = _scenario(s, scenario)
            if out:
                calc_ids.append(out["calculationId"])
                text = f"{scenario} full repricing P&L {out['pnlUsd']} USD on current holdings"
                (objections if scenario == "parallel_down_25" else alternatives).append(text)
        if objections:
            objections = [
                "A move toward easing would make a shorter duration costly: " + objections[0]
            ]
        return {
            "action": "report",
            "findings": ["Reviewed the candidate duration change against approved scenarios."],
            "claims": [],
            "citations": [],
            "counterevidence": [],
            "coverage_gaps": [],
            "objections": objections,
            "alternative_scenarios": alternatives,
            "unresolved_assumptions": [
                "Scenario shocks are hypothetical and instantaneous, not forecasts.",
                "Policy communications may not translate into parallel curve moves.",
            ],
            "calculation_ids": calc_ids,
        }

    # ------------------------------------------------------------------ synthesis

    def _final(self, s: _State) -> dict[str, Any]:
        research_note = s.role == "research_note"
        evidence_mode = s.context.get("retrievalMode", "none") != "none"
        invalid = set((s.feedback or {}).get("invalidIds", []))
        analysis = _analyze(s) if evidence_mode else None
        findings = [f for f in _findings(s) if f["finding_id"] not in invalid]
        findings = [f for f in findings if not set(f["calculation_ids"]) & invalid]
        claims, citations = ([], [])
        if analysis is not None:
            claims, citations = _claims(s, analysis, prefix="ld" if s.role == "lead" else "c")
            claims = [c for c in claims if c["claim_id"] not in invalid]
            kept = {cid for c in claims for cid in c["citation_ids"]}
            citations = [c for c in citations if c["citation_id"] in kept]
        counter = list(analysis.counter[:2]) if analysis else []
        for report in s.reports:
            counter.extend(report.get("objections", [])[:1])
        gaps = _gaps(s)
        if analysis is not None:
            if not s.docs:
                status, stance = "insufficient_evidence", None
            elif analysis.stance == "contradictory":
                status, stance = "contradictory_evidence", None
            elif analysis.stance is None:
                status, stance = "insufficient_evidence", None
            else:
                status, stance = "supported", analysis.stance
            explanation = analysis.summary()
        else:
            stance, explanation = _market_stance(s)
            status = "supported" if stance is not None else "insufficient_evidence"
            gaps.append("Market-only strategy: no documentary evidence by design.")
        hypotheses = _hypotheses(stance, citations)
        note = {
            "action": "final",
            "status": status,
            "claims": claims,
            "citations": citations,
            "numerical_findings": findings,
            "hypotheses": hypotheses,
            "counterevidence": counter,
            "coverage_gaps": gaps,
            "explanation": explanation,
        }
        if research_note:
            return note
        if status != "supported":
            note["decision"] = "abstain"
            note["proposal"] = None
            note["explanation"] = explanation + " Abstaining: evidence does not support a change."
            return note
        policy_rejected = bool((s.feedback or {}).get("policyRejected"))
        targets, why = (None, "previous proposal failed the policy dry run")
        if not policy_rejected:
            targets, why = _targets(s, stance)
        calc_ids = [f["calculation_ids"][0] for f in findings if f["calculation_ids"]]
        claim_ids = [c["claim_id"] for c in claims if c.get("material", True)]
        if targets is None:
            note["decision"] = "hold"
            note["proposal"] = {
                "action": "HOLD",
                "target_weights": [],
                "supporting_claim_ids": claim_ids,
                "supporting_calculation_ids": calc_ids,
            }
            note["explanation"] = f"{explanation} Holding: {why}."
            return note
        note["decision"] = "propose"
        note["proposal"] = {
            "action": "REBALANCE",
            "target_weights": targets,
            "supporting_claim_ids": claim_ids,
            "supporting_calculation_ids": calc_ids,
        }
        note["explanation"] = f"{explanation} {why}."
        return note


# --------------------------------------------------------------------------- #
# Analysis helpers
# --------------------------------------------------------------------------- #


class _Analysis:
    def __init__(self):
        self.stance: Optional[str] = None
        self.scores = {"hawkish": Decimal(0), "dovish": Decimal(0), "neutral": Decimal(0)}
        self.sentences: list[tuple[Decimal, str, str, int, str]] = (
            []
        )  # weight, label, chunk, pos, text
        self.counter: list[str] = []
        self.latest_title: Optional[str] = None
        self.documents = 0

    def summary(self) -> str:
        h, d, n = (
            self.scores[k].quantize(Decimal("0.01")) for k in ("hawkish", "dovish", "neutral")
        )
        label = self.stance or "no clear"
        return (
            f"Reference lexicon {LEXICON_VERSION}: {label} policy signal across {self.documents} "
            f"delivered documents (weighted hawkish {h}, dovish {d}, neutral {n})."
        )


def _label(sentence: str) -> Optional[str]:
    low = f" {sentence.lower()} "
    negated = any(n in low for n in NEGATIONS)
    counts = {
        "hawkish": sum(p in low for p in HAWKISH),
        "dovish": sum(p in low for p in DOVISH),
        "neutral": sum(p in low for p in NEUTRAL),
    }
    if negated:
        counts["neutral"] += counts["hawkish"] + counts["dovish"]
        counts["hawkish"] = counts["dovish"] = 0
    best = max(counts.values())
    if best == 0:
        return None
    for key in ("hawkish", "dovish", "neutral"):
        if counts[key] == best:
            return key
    return None


def _analyze(s: _State) -> _Analysis:
    result = _Analysis()
    versions: dict[str, str] = {}
    for chunk_id, entry in s.index.items():
        if chunk_id in s.docs:
            versions.setdefault(entry["documentVersionId"], entry["availableAt"])
    ranked = sorted(versions, key=lambda v: (versions[v], v), reverse=True)
    instants = sorted(set(versions.values()), reverse=True)  # dense rank: same instant, same weight
    weight_of = {v: Decimal(1) / Decimal(instants.index(versions[v]) + 1) for v in ranked}
    result.documents = len(ranked)
    if ranked:
        latest = ranked[0]
        result.latest_title = next(
            (e["title"] for e in s.index.values() if e["documentVersionId"] == latest), None
        )
    for chunk_id in sorted(s.docs):
        entry = s.index.get(chunk_id)
        if entry is None:
            continue
        text = s.docs[chunk_id]
        weight = weight_of[entry["documentVersionId"]]
        for match in _SENTENCE.finditer(text):
            sentence = match.group(0).strip()
            label = _label(sentence)
            if label is None or len(sentence) < 25:
                continue
            result.scores[label] += weight
            position = text.find(sentence)
            result.sentences.append((weight, label, chunk_id, position, sentence))
    h, d, n = result.scores["hawkish"], result.scores["dovish"], result.scores["neutral"]
    if h == 0 and d == 0 and n == 0:
        result.stance = None
    elif h > 0 and d > 0 and min(h, d) / max(h, d) >= Decimal("0.6"):
        result.stance = "contradictory"
    else:
        result.stance = max(("hawkish", h), ("dovish", d), ("neutral", n), key=lambda x: x[1])[0]
    opposite = {"hawkish": "dovish", "dovish": "hawkish"}.get(result.stance or "")
    for weight, label, chunk_id, _, sentence in sorted(
        result.sentences, key=lambda x: (-x[0], x[2], x[3])
    ):
        if opposite and label == opposite and len(result.counter) < 3:
            result.counter.append(f"{chunk_id}: {sentence}")
    return result


def _claims(s: _State, analysis: _Analysis, *, prefix: str):
    wanted = analysis.stance if analysis.stance in ("hawkish", "dovish", "neutral") else None
    picked = []
    seen_chunks = set()
    for weight, label, chunk_id, position, sentence in sorted(
        analysis.sentences, key=lambda x: (-x[0], x[2], x[3])
    ):
        if wanted and label != wanted and analysis.stance != "contradictory":
            continue
        if chunk_id in seen_chunks:
            continue
        seen_chunks.add(chunk_id)
        picked.append((label, chunk_id, position, sentence))
        if len(picked) >= 3:
            break
    claims, citations = [], []
    for n, (label, chunk_id, position, sentence) in enumerate(picked, start=1):
        entry = s.index[chunk_id]
        cid = f"{prefix}-cit-{n}"
        citations.append(
            {
                "citation_id": cid,
                "bundle_id": entry["bundleId"],
                "chunk_id": chunk_id,
                "document_version_id": entry["documentVersionId"],
                "quote": sentence,
                "start_offset": position,
                "end_offset": position + len(sentence),
            }
        )
        claims.append(
            {
                "claim_id": f"{prefix}-clm-{n}",
                "text": f"{entry['title']} states: {sentence}",
                "citation_ids": [cid],
                "material": True,
            }
        )
    return claims, citations


def _scenario(s: _State, scenario_id: str) -> Optional[dict[str, Any]]:
    for out in s.outputs("run_scenario"):
        if out.get("scenarioId") == scenario_id:
            return out
    for report in s.reports:
        for item in report.get("scenarios", []):
            if item.get("scenarioId") == scenario_id:
                return item
    return None


def _findings(s: _State) -> list[dict[str, Any]]:
    snapshots = [
        x for x in (s.context.get("curveSnapshotId"), s.context.get("portfolioSnapshotId")) if x
    ]
    findings = []
    risk = s.latest("get_portfolio_risk")
    if risk and risk.get("calculationId"):
        findings.append(
            {
                "finding_id": "f-risk",
                "text": (
                    f"Own portfolio effective duration {risk.get('effectiveDurationYears')} years, "
                    f"parallel DV01 {risk.get('parallelDv01Usd')} USD per bp, NAV "
                    f"{risk.get('navUsd')} USD."
                ),
                "calculation_ids": [risk["calculationId"]],
                "input_snapshot_ids": snapshots,
            }
        )
    features = s.latest("get_market_features")
    if features and features.get("calculationId"):
        change = (features.get("changesBp", {}).get("21s") or {}).get("2Y")
        findings.append(
            {
                "finding_id": "f-curve",
                "text": (
                    f"2Y par yield {features.get('parYields', {}).get('2Y')}, 21-session change "
                    f"{change} bp, 2s10s slope {features.get('slope2s10sBp')} bp."
                ),
                "calculation_ids": [features["calculationId"]],
                "input_snapshot_ids": snapshots,
            }
        )
    for n, out in enumerate(s.outputs("run_scenario"), start=1):
        findings.append(
            {
                "finding_id": f"f-scn-{n}",
                "text": f"Hypothetical {out['scenarioId']} full repricing P&L {out['pnlUsd']} USD.",
                "calculation_ids": [out["calculationId"]],
                "input_snapshot_ids": snapshots,
            }
        )
    for report in s.reports:
        for n, calc_id in enumerate(report.get("calculationIds", []), start=1):
            findings.append(
                {
                    "finding_id": f"f-{report.get('role', 'specialist')}-{n}",
                    "text": f"Specialist {report.get('role')} scenario calculation.",
                    "calculation_ids": [calc_id],
                    "input_snapshot_ids": snapshots,
                }
            )
    return findings


def _gaps(s: _State) -> list[str]:
    gaps = []
    types = {e.get("documentType") for cid, e in s.index.items() if cid in s.docs}
    if s.context.get("retrievalMode", "none") != "none":
        if "fomc_minutes" not in types:
            gaps.append("No FOMC minutes among the delivered passages.")
        if not s.docs:
            gaps.append("No eligible passages were delivered.")
    return gaps


def _market_stance(s: _State) -> tuple[Optional[str], str]:
    features = s.latest("get_market_features") or {}
    change = (features.get("changesBp", {}).get("21s") or {}).get("2Y")
    if change is None:
        return None, "Market-only reference rule: no 21-session 2Y change available."
    value = _dec(change)
    if value > MARKET_MOVE_BP:
        return (
            "hawkish",
            f"Market-only reference rule: 2Y par yield rose {value} bp over 21 sessions.",
        )
    if value < -MARKET_MOVE_BP:
        return (
            "dovish",
            f"Market-only reference rule: 2Y par yield fell {value} bp over 21 sessions.",
        )
    return (
        "neutral",
        f"Market-only reference rule: 2Y par yield change {value} bp is within the band.",
    )


def _hypotheses(stance: Optional[str], citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    support = [c["citation_id"] for c in citations[:2]]
    if stance == "hawkish":
        return [
            {
                "hypothesis_id": "h-1",
                "text": "Yields may rise further if the restrictive stance persists; a shorter "
                "duration limits mark-to-market losses.",
                "assumptions": [
                    "Recent communications describe the near-term policy path.",
                    "Parallel upward moves dominate curve changes.",
                ],
                "scenario_ids": ["parallel_up_25"],
                "supporting_citation_ids": support,
            }
        ]
    if stance == "dovish":
        return [
            {
                "hypothesis_id": "h-1",
                "text": "Yields may fall as policy eases; a longer duration benefits from lower "
                "rates.",
                "assumptions": [
                    "Recent communications describe the near-term policy path.",
                    "Parallel downward moves dominate curve changes.",
                ],
                "scenario_ids": ["parallel_down_25"],
                "supporting_citation_ids": support,
            }
        ]
    return []


def _targets(s: _State, stance: Optional[str]) -> tuple[Optional[list[dict[str, str]]], str]:
    risk = s.latest("get_portfolio_risk")
    if not risk:
        return None, "no portfolio risk output"
    target = STANCE_TARGET_YEARS.get(stance or "")
    if target is None:
        return None, "neutral signal; no duration change warranted"
    duration = _dec(risk.get("effectiveDurationYears"), "0")
    if abs(duration - target) <= DRIFT_BAND_YEARS:
        return (
            None,
            f"duration {duration} already within {DRIFT_BAND_YEARS}y of the {target}y target",
        )
    limits = risk.get("policyLimits", {})
    min_change = _dec(limits.get("minWeightChange"), "0.02") + MOVE_FLOOR_MARGIN
    budget = _dec(limits.get("maxDailyTurnoverRatio"), "0.20") - SAFETY_MARGIN
    cap = _dec(limits.get("maxSingleSecurityRatio"), "0.40") - SAFETY_MARGIN
    universe = {u["securityId"]: u for u in risk.get("universe", [])}
    weights = {sid: _dec(u["weight"]) for sid, u in universe.items() if _dec(u["weight"]) > 0}
    durations = {sid: _dec(u.get("effectiveDurationYears")) for sid, u in universe.items()}
    error = duration - target
    moved = False
    if error > 0:  # shorten: sell only (sale proceeds stay cash)
        order = sorted(
            (sid for sid in weights if durations.get(sid, 0) > 0 and universe[sid]["tradable"]),
            key=lambda sid: (-durations[sid], sid),
        )
        for sid in order:
            if error <= 0 or budget <= 0:
                break
            delta = min(weights[sid], error / durations[sid], budget)
            if delta < min_change:
                continue
            weights[sid] -= delta
            error -= delta * durations[sid]
            budget -= delta
            moved = True
    else:  # lengthen: buy only with settled cash above the reserve
        room = min(
            _dec(risk.get("settledFundingRatio")), _dec(risk.get("contractualCashRatio"))
        ) - (_dec(limits.get("minCashRatio"), "0.05") + SAFETY_MARGIN)
        need = -error
        order = sorted(
            (sid for sid, u in universe.items() if u["tradable"] and durations.get(sid, 0) > 0),
            key=lambda sid: (-durations[sid], sid),
        )
        for sid in order:
            if need <= 0 or budget <= 0 or room <= 0:
                break
            delta = min(cap - weights.get(sid, Decimal(0)), need / durations[sid], budget, room)
            if delta < min_change:
                continue
            weights[sid] = weights.get(sid, Decimal(0)) + delta
            need -= delta * durations[sid]
            budget -= delta
            room -= delta
            moved = True
    if not moved:
        return None, "no feasible move within turnover, cash and minimum-change limits"
    out = []
    total = Decimal(0)
    for sid in sorted(weights):
        w = weights[sid].quantize(W_Q, rounding=ROUND_DOWN)
        if w > 0:
            out.append({"security_id": sid, "weight": format(w, "f")})
            total += w
    out.append({"security_id": "CASH-USD", "weight": format(Decimal(1) - total, "f")})
    direction = "Shortening" if duration > target else "Lengthening"
    return out, f"{direction} duration from {duration}y toward the {target}y {stance} target"
