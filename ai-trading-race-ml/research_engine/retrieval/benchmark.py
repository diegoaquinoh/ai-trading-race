"""Evidence benchmark ``evidence-benchmark-v1`` (spec 16.4).

60 questions: 20 direct-document, 20 multi-document/event, 20
relationship/revision/temporal/insufficient-evidence. Expected evidence is
auto-annotated from the ingested corpus by explicit, recorded rules
(document + heading + regex) evaluated on the version eligible at the question's
``decision_as_of``; the rule is stored with each question as an adjudication
note. Manual adjudication of those annotations, and manual review of factual
support in generated answers, are **offline/manual** and are not computed here.

The development/held-out split is fixed at generation time: within each
category, questions alternate dev/held-out in id order (10/10 per category).

The benchmark corpus includes the clearly labelled synthetic correction
(revision questions need it); default agent indexes do not.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from research_engine.contracts.common import utc_to_str
from research_engine.contracts.decisions import Citation, RetrievalMode
from research_engine.contracts.evidence import RetrievalRequest
from research_engine.evidence import fed
from research_engine.evidence.store import ResearchStore

from .citations import resolve_chunk, validate_citation
from .index import EvidenceIndex
from .service import retrieve
from .snapshot import eligible_snapshot

BENCHMARK_VERSION = "evidence-benchmark-v1"
BENCHMARK_DIR = fed.ML_ROOT / "benchmarks" / "evidence"
QUESTIONS_PATH = BENCHMARK_DIR / "questions_v1.json"
M = fed.PINNED_MEETINGS
PARTICIPANTS = "Participants' Views"
TRIAL_NOTE = (
    "graph-expand-v1 co-support materialization and the graph_reserved_slots=4 selection "
    "quota were finalized during development after inspecting results on all 60 "
    "questions; held-out numbers for this version are not "
    "untouched held-out results. Freeze settings and register a new trial before a final "
    "held-out evaluation (spec 16.1-16.2)."
)


def _month(meeting: fed.FomcMeeting) -> str:
    return f"{meeting.end:%B %Y}"


def statement_evening(meeting: fed.FomcMeeting) -> datetime:
    """23:30 UTC on the statement day: after the 14:00 ET release + 120 min lag."""
    return datetime(
        meeting.end.year, meeting.end.month, meeting.end.day, 23, 30, tzinfo=timezone.utc
    )


def after_minutes(meeting: fed.FomcMeeting) -> datetime:
    day = meeting.minutes_released + timedelta(days=1)
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)


@dataclass
class Rule:
    document_id: str
    regex: str
    heading: Optional[str] = None
    synthetic: Optional[bool] = None  # restrict to synthetic/original versions

    def describe(self) -> str:
        parts = [f"document={self.document_id}", f"regex=/{self.regex}/i"]
        if self.heading:
            parts.append(f"heading contains '{self.heading}'")
        if self.synthetic is not None:
            parts.append("synthetic correction only" if self.synthetic else "original version only")
        return "; ".join(parts)


@dataclass
class QuestionSpec:
    qid: str
    category: str
    subtype: str
    question: str
    as_of: datetime
    rules: list[Rule] = field(default_factory=list)
    acceptable_abstention: bool = False
    requires_abstention: bool = False
    forbidden_document_ids: list[str] = field(default_factory=list)
    expected_fact_release: Optional[str] = None
    note: str = ""


def _st(m: fed.FomcMeeting) -> str:
    return f"doc-fed-fomc-statement-{m.key}"


def _mn(m: fed.FomcMeeting) -> str:
    return f"doc-fed-fomc-minutes-{m.key}"


def question_specs() -> list[QuestionSpec]:
    specs: list[QuestionSpec] = []
    # ---- A: direct document (20)
    for i, m in enumerate(M, start=1):
        specs.append(
            QuestionSpec(
                f"A{i:02d}",
                "direct_document",
                "statement_policy_rate",
                f"What target range for the federal funds rate did the FOMC set at its {_month(m)} meeting?",
                statement_evening(m),
                [Rule(_st(m), r"target range for the federal funds rate")],
                note="Answer is stated directly in the meeting statement.",
            )
        )
    minutes_direct = [
        (
            M[1],
            "What did the minutes of the March 2023 meeting report about recent developments in the banking sector?",
            Rule(_mn(M[1]), r"bank", "Banking"),
        ),
        (
            M[2],
            "In the minutes of the May 2023 meeting, how did participants assess the banking system?",
            Rule(_mn(M[2]), r"banking (?:system|sector)", PARTICIPANTS),
        ),
        (
            M[9],
            "What considerations for slowing balance sheet runoff were discussed in the March 2024 minutes?",
            Rule(_mn(M[9]), r"runoff|balance sheet", "Slowing"),
        ),
        (
            M[10],
            "What did participants say about balance sheet runoff in the minutes of the May 2024 meeting?",
            Rule(_mn(M[10]), r"runoff|redemption cap", PARTICIPANTS),
        ),
    ]
    for j, (m, text, rule) in enumerate(minutes_direct, start=17):
        specs.append(
            QuestionSpec(
                f"A{j:02d}",
                "direct_document",
                "minutes_section",
                text,
                after_minutes(m),
                [rule],
                note="Answer is in one minutes section.",
            )
        )
    # ---- B: multi-document / event (20)
    for n, m in enumerate(M[0::2], start=1):
        specs.append(
            QuestionSpec(
                f"B{n:02d}",
                "multi_document",
                "statement_vs_minutes",
                f"Compare what the FOMC statement and the minutes for the {_month(m)} meeting said about inflation.",
                after_minutes(m),
                [Rule(_st(m), r"inflation"), Rule(_mn(m), r"inflation", PARTICIPANTS)],
                note="Needs the statement and the participants' discussion in the minutes of the same meeting.",
            )
        )
    for n, (prev, cur) in enumerate(list(zip(M, M[1:]))[0::2], start=9):
        specs.append(
            QuestionSpec(
                f"B{n:02d}",
                "multi_document",
                "decision_vs_previous",
                f"How did the policy rate decision at the {_month(cur)} meeting compare with the decision at the previous meeting?",
                statement_evening(cur),
                [
                    Rule(_st(cur), r"target range for the federal funds rate"),
                    Rule(_st(prev), r"target range for the federal funds rate"),
                ],
                note="Needs two consecutive statements.",
            )
        )
    for n, (a, b) in enumerate(
        [(M[0], M[4]), (M[5], M[8]), (M[9], M[12]), (M[13], M[15])], start=17
    ):
        specs.append(
            QuestionSpec(
                f"B{n:02d}",
                "multi_document",
                "statement_language_change",
                f"How did the description of job gains and unemployment change between the {_month(a)} and {_month(b)} FOMC statements?",
                statement_evening(b),
                [Rule(_st(a), r"job gains|unemployment"), Rule(_st(b), r"job gains|unemployment")],
                note="Needs two statements several meetings apart.",
            )
        )
    # ---- C: relationship / revision / temporal / insufficient (20)
    for n, m in enumerate([M[0], M[3], M[6], M[11], M[14]], start=1):
        specs.append(
            QuestionSpec(
                f"C{n:02d}",
                "relationship_temporal",
                "minutes_not_yet_available",
                f"What did the minutes of the {_month(m)} meeting say about inflation?",
                statement_evening(m),
                [Rule(_st(m), r"inflation")],
                acceptable_abstention=True,
                forbidden_document_ids=[_mn(m)],
                note="Minutes are released about three weeks later; only the statement is eligible. Abstaining on the minutes is correct.",
            )
        )
    for n, (prev, cur) in enumerate(
        [(M[1], M[2]), (M[4], M[5]), (M[8], M[9]), (M[12], M[13])], start=6
    ):
        specs.append(
            QuestionSpec(
                f"C{n:02d}",
                "relationship_temporal",
                "previous_meeting_minutes",
                f"What did the minutes of the meeting before the {_month(cur)} meeting say about the labor market?",
                statement_evening(cur),
                [Rule(_mn(prev), r"labor market", PARTICIPANTS)],
                note="Requires resolving PREVIOUS_EVENT, then that meeting's minutes (released before the cutoff).",
            )
        )
    for n, m in enumerate([M[3], M[7], M[11]], start=10):
        specs.append(
            QuestionSpec(
                f"C{n:02d}",
                "relationship_temporal",
                "series_release",
                f"Which CPI release was available before the {_month(m)} FOMC statement, and what did that statement say about inflation?",
                statement_evening(m),
                [Rule(_st(m), r"inflation")],
                expected_fact_release="latest",
                note="Structured fact: latest CPI release available at the cutoff (RELEASE_OF); passage: the statement.",
            )
        )
    march = M[1]
    revision_q = "What did the March 2023 FOMC statement say about the extent of the effects of recent banking developments?"
    specs += [
        QuestionSpec(
            "C13",
            "relationship_temporal",
            "revision_before_correction",
            revision_q,
            statement_evening(march),
            [Rule(_st(march), r"extent of these effects", synthetic=False)],
            note="Before the synthetic correction exists: original text only.",
        ),
        QuestionSpec(
            "C14",
            "relationship_temporal",
            "revision_boundary",
            revision_q,
            datetime(2023, 3, 29, 19, 0, tzinfo=timezone.utc),
            [Rule(_st(march), r"extent of these effects", synthetic=False)],
            note="Correction published 18:00Z but available 20:00Z: original still delivered.",
        ),
        QuestionSpec(
            "C15",
            "relationship_temporal",
            "revision_after_correction",
            revision_q,
            datetime(2023, 4, 5, 12, 0, tzinfo=timezone.utc),
            [Rule(_st(march), r"synthetic correction", synthetic=True)],
            note="After the SYNTHETIC correction is available it supersedes the original (labelled synthetic).",
        ),
    ]
    insufficient = [
        (
            "C16",
            "What did the FOMC decide at its January 2025 meeting?",
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
            "Event after the corpus and the cutoff.",
        ),
        (
            "C17",
            "What was the FOMC's decision on cryptocurrency regulation?",
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
            "Out of the Committee's documented scope; no decision exists.",
        ),
        (
            "C18",
            "What federal funds rate target will the FOMC set in 2026?",
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
            "Forecast; documents cannot establish it.",
        ),
        (
            "C19",
            "What did the December 2024 minutes say about the labor market?",
            datetime(2024, 12, 31, 12, tzinfo=timezone.utc),
            "Minutes released 2025-01-08, after the cutoff.",
        ),
        (
            "C20",
            "What did the March 2023 FOMC statement announce?",
            datetime(2023, 3, 15, 12, tzinfo=timezone.utc),
            "Asked before the meeting; the statement does not exist yet.",
        ),
    ]
    for qid, text, as_of, note in insufficient:
        forbidden = [_st(march)] if qid == "C20" else ([_mn(M[15])] if qid == "C19" else [])
        specs.append(
            QuestionSpec(
                qid,
                "relationship_temporal",
                "insufficient_evidence",
                text,
                as_of,
                [],
                True,
                True,
                forbidden,
                note=note,
            )
        )
    return specs


def _split(specs: list[QuestionSpec]) -> dict[str, str]:
    out: dict[str, str] = {}
    for category in sorted({s.category for s in specs}):
        ids = sorted(s.qid for s in specs if s.category == category)
        for i, qid in enumerate(ids):
            out[qid] = "dev" if i % 2 == 0 else "heldout"
    return out


def _eligible_versions(index: EvidenceIndex, as_of: datetime) -> set[str]:
    return set(eligible_snapshot(index, as_of, ["fed-fomc"]).version_ids)


def generate(index: EvidenceIndex) -> dict[str, Any]:
    specs = question_specs()
    split = _split(specs)
    releases = sorted(
        (e for e in index.entities.values() if e.entity_type.value == "MacroRelease"),
        key=lambda e: e.available_at,
    )
    questions = []
    for spec in specs:
        eligible = _eligible_versions(index, spec.as_of)
        expected_chunks: list[str] = []
        expected_versions: list[str] = []
        for rule in spec.rules:
            versions = [
                v
                for v in index.versions.values()
                if v.document_id == rule.document_id
                and v.version_id in eligible
                and (rule.synthetic is None or v.synthetic == rule.synthetic)
            ]
            for version in versions:
                for chunk_id in index.chunks_by_version[version.version_id]:
                    chunk = index.chunks[chunk_id]
                    if rule.heading and not any(rule.heading in h for h in chunk.heading_path):
                        continue
                    if re.search(rule.regex, chunk.text, re.IGNORECASE):
                        expected_chunks.append(chunk_id)
                        if version.version_id not in expected_versions:
                            expected_versions.append(version.version_id)
        if spec.rules and not expected_chunks:
            raise ValueError(f"{spec.qid}: annotation rules matched no eligible chunk")
        fact = None
        if spec.expected_fact_release:
            visible = [r for r in releases if r.available_at <= spec.as_of]
            fact = visible[-1].entity_id if visible else None
        forbidden_versions = sorted(
            v.version_id
            for v in index.versions.values()
            if v.document_id in spec.forbidden_document_ids
        )
        questions.append(
            {
                "id": spec.qid,
                "category": spec.category,
                "subtype": spec.subtype,
                "split": split[spec.qid],
                "question": spec.question,
                "decisionAsOf": utc_to_str(spec.as_of),
                "expectedChunkIds": expected_chunks,
                "expectedVersionIds": expected_versions,
                "expectedReleaseFact": fact,
                "forbiddenVersionIds": forbidden_versions,
                "acceptableAbstention": spec.acceptable_abstention,
                "requiresAbstention": spec.requires_abstention,
                "supportAnnotation": "auto_rule" if spec.rules else "none_expected",
                "adjudication": {
                    "status": "auto-annotated; manual adjudication pending (offline)",
                    "rules": [r.describe() for r in spec.rules],
                    "note": spec.note,
                },
            }
        )
    return {
        "benchmark": BENCHMARK_VERSION,
        "description": (
            "Evidence retrieval benchmark over Federal Reserve FOMC statements and minutes "
            "(2023-2024) plus one labelled synthetic correction. Expected evidence ids are "
            "content-addressed chunk/version ids from the ingested corpus."
        ),
        "categories": {
            "direct_document": 20,
            "multi_document": 20,
            "relationship_temporal": 20,
        },
        "split_rule": "within each category, alternate dev/heldout in id order (fixed before tuning)",
        "corpus": {
            "index_member_versions": len(index.versions),
            "chunk_set_hash": index.build.member_chunk_set_hash,
            "chunker": index.build.chunker_version,
            "tokenizer": index.build.tokenizer_version,
            "includes_synthetic": index.build.includes_synthetic,
        },
        "manual_review": "Factual-support review of generated answers is offline/manual and not part of this file.",
        "questions": questions,
    }


def load_questions(path: Path = QUESTIONS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text())


def _first_sentence(text: str) -> tuple[str, int, int]:
    match = re.search(r"[^.]{20,}?\.", text)
    if match:
        return match.group(0), match.start(), match.end()
    end = min(len(text), 80)
    return text[:end], 0, end


def _ratio(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def evaluate(
    store: ResearchStore,
    index: EvidenceIndex,
    *,
    split: Optional[str] = None,
    modes: tuple[RetrievalMode, ...] = (RetrievalMode.HYBRID_RAG, RetrievalMode.GRAPH_RAG),
    path: Path = QUESTIONS_PATH,
) -> dict[str, Any]:
    data = load_questions(path)
    questions = [q for q in data["questions"] if split in (None, "all") or q["split"] == split]
    rows = []
    for q in questions:
        as_of = datetime.fromisoformat(q["decisionAsOf"].replace("Z", "+00:00"))
        expected = set(q["expectedChunkIds"])
        expected_versions = set(q["expectedVersionIds"])
        row: dict[str, Any] = {
            "id": q["id"],
            "category": q["category"],
            "split": q["split"],
            "modes": {},
        }
        for mode in modes:
            request = RetrievalRequest(
                question=q["question"],
                decision_as_of=as_of,
                mode=mode,
                index_build_id=index.build_id,
                permission_scope="benchmark",
            )
            started = time.perf_counter()
            run, bundle = retrieve(request, store, index, use_cache=False)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            delivered = [c.chunk_id for c in bundle.chunks]
            top5 = delivered[:5]
            hits = [c for c in delivered if c in expected]
            violations = [
                c.chunk_id
                for c in bundle.chunks
                if c.available_at > as_of or c.version_id in set(q["forbiddenVersionIds"])
            ]
            valid_citations = 0
            for chunk in bundle.chunks:
                quote, start, end = _first_sentence(chunk.text)
                citation = Citation(
                    citation_id=f"cit-{chunk.chunk_id}",
                    bundle_id=bundle.bundle_id,
                    chunk_id=chunk.chunk_id,
                    document_version_id=chunk.version_id,
                    quote=quote,
                    start_offset=start,
                    end_offset=end,
                )
                results = validate_citation(citation, bundle, store)
                if (
                    all(r.passed for r in results)
                    and resolve_chunk(store, chunk.chunk_id).text_hash == chunk.text_hash
                ):
                    valid_citations += 1
            graph_added = [
                c.chunk_id
                for c in bundle.chunks
                if c.provenance.graph and c.provenance.graph.added_by_graph
            ]
            facts = [f.subject_id for f in bundle.structured_facts]
            row["modes"][mode.value] = {
                "delivered": len(delivered),
                "tokens": bundle.total_tokens,
                "recall_at_k": _ratio(len(hits), len(expected)) if expected else None,
                "recall_at_5": (
                    _ratio(len([c for c in top5 if c in expected]), len(expected))
                    if expected
                    else None
                ),
                "precision_at_k": _ratio(len(hits), len(delivered)) if expected else None,
                "precision_at_5": (
                    _ratio(len([c for c in top5 if c in expected]), len(top5)) if expected else None
                ),
                "version_recall": (
                    _ratio(
                        len({c.version_id for c in bundle.chunks} & expected_versions),
                        len(expected_versions),
                    )
                    if expected_versions
                    else None
                ),
                "temporal_violations": len(violations),
                "citation_valid": valid_citations,
                "citation_total": len(delivered),
                "graph_added": len(graph_added),
                "graph_added_expected_hits": len([c for c in graph_added if c in expected]),
                "release_fact_hit": (
                    (q["expectedReleaseFact"] in facts) if q["expectedReleaseFact"] else None
                ),
                "latency_ms": latency_ms,
                "retrieval_run_id": run.retrieval_run_id,
            }
        if "hybrid_rag_v1" in row["modes"] and "graph_rag_v1" in row["modes"] and expected:
            h = row["modes"]["hybrid_rag_v1"]["recall_at_k"] or 0.0
            g = row["modes"]["graph_rag_v1"]["recall_at_k"] or 0.0
            row["graph_effect"] = "helped" if g > h else ("harmed" if g < h else "neutral")
        rows.append(row)
    return {
        "benchmark": data["benchmark"],
        "split": split or "all",
        "index_build_id": index.build_id,
        "trial_note": TRIAL_NOTE,
        "summary": summarize(rows, modes),
        "questions": rows,
    }


def summarize(rows: list[dict[str, Any]], modes: tuple[RetrievalMode, ...]) -> dict[str, Any]:
    def mean(values: list[Optional[float]]) -> Optional[float]:
        vals = [v for v in values if v is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    out: dict[str, Any] = {}
    groups = {"all": rows}
    for category in sorted({r["category"] for r in rows}):
        groups[category] = [r for r in rows if r["category"] == category]
    for name, group in groups.items():
        out[name] = {"questions": len(group)}
        for mode in modes:
            metrics = [r["modes"][mode.value] for r in group]
            out[name][mode.value] = {
                "recall_at_k": mean([m["recall_at_k"] for m in metrics]),
                "recall_at_5": mean([m["recall_at_5"] for m in metrics]),
                "precision_at_k": mean([m["precision_at_k"] for m in metrics]),
                "precision_at_5": mean([m["precision_at_5"] for m in metrics]),
                "version_recall": mean([m["version_recall"] for m in metrics]),
                "temporal_violations": sum(m["temporal_violations"] for m in metrics),
                "citation_validity": _ratio(
                    sum(m["citation_valid"] for m in metrics),
                    sum(m["citation_total"] for m in metrics),
                ),
                "graph_added_passages": sum(m["graph_added"] for m in metrics),
                "graph_added_expected_hits": sum(m["graph_added_expected_hits"] for m in metrics),
                "release_fact_hits": sum(1 for m in metrics if m["release_fact_hit"]),
                "mean_latency_ms": mean([m["latency_ms"] for m in metrics]),
            }
        effects = [r.get("graph_effect") for r in group if r.get("graph_effect")]
        out[name]["graph_effect"] = {e: effects.count(e) for e in ("helped", "harmed", "neutral")}
    out["manual_factual_support"] = "not computed: offline/manual review"
    out["abstention_quality"] = (
        "not computed here: abstention is an answer-level judgement (agents); see requiresAbstention"
    )
    return out
