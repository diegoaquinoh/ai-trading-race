"""Proposal validation pipeline ``proposal-validation-v1`` (spec 13.2, 15.2).

Steps, in order, each recorded as a :class:`ValidationResult` (first detail
line ``attempt:<attempt id>``):

1. ``schema`` - identifiers, cross-references, decision/proposal consistency,
   finite decimal weights in [0, 1] over the frozen universe plus cash, and the
   :class:`Proposal` contract (sum to 1, no duplicates);
2. ``citation_membership`` - every citation resolves to a chunk actually
   delivered to this decision in that exact bundle, with the same document
   version;
3. ``temporal`` - the chunk was available at the cutoff, the bundle carries the
   decision cutoff, and it came from the permitted index build and retrieval mode;
4. ``quote_offsets`` - exact quote/offset check against the delivered normalized
   text, which must equal the stored chunk text (hash and store lookup);
5. ``calc_refs`` - calculation ids exist in the signed CalculationStore, verify
   under the store key, were issued to this decision by a tool and are not
   later than the cutoff (a model cannot mint a trusted id);
6. ``support`` - ``support-lexical-v1`` review aid: share of a material claim's
   content tokens found in its cited quotes/titles; below the threshold the
   claim is flagged ``review_required``. A flag, never proof of entailment;
7. ``policy`` - target weights, sizing, funding and risk through the
   simulation policy dry run (no order intents are kept).

Outcome rules applied by the workflow: invalid dependent claims or calculations
invalidate the proposal (blocking); a flagged material dependency yields
``review_required``; a policy rejection is blocking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

from pydantic import ValidationError

from research_engine.contracts.common import CASH_SECURITY_ID, sha256_text
from research_engine.contracts.decisions import (
    Citation,
    DocumentaryClaim,
    Hypothesis,
    NumericalFinding,
    Proposal,
    ResearchNote,
    ResearchStatus,
    RetrievalMode,
    ValidationResult,
)
from research_engine.contracts.portfolio import DecisionAction, PolicyEvaluation, TargetWeight
from research_engine.retrieval.citations import validate_quote

from .output import FinalOut, NoteOut
from .ports import EvidencePort
from .tools import DecisionToolbox

VALIDATION_PIPELINE_VERSION = "proposal-validation-v1"
SUPPORT_CLASSIFIER_VERSION = "support-lexical-v1"
DEFAULT_SUPPORT_THRESHOLD = Decimal("0.5")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-\.:]{0,159}$")
_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have in into is it its of on or that the
    their this to was were will with which said states says stated statement noted would could
    should may might than then there these those also over under about after before""".split()
)


def content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1}


def support_score(claim_text: str, cited_texts: list[str]) -> Decimal:
    """``support-lexical-v1``: |claim tokens in cited text| / |claim tokens|."""
    claim = content_tokens(claim_text)
    if not claim:
        return Decimal(0)
    cited: set[str] = set()
    for text in cited_texts:
        cited |= content_tokens(text)
    return (Decimal(len(claim & cited)) / Decimal(len(claim))).quantize(Decimal("0.0001"))


@dataclass
class ValidationInputs:
    toolbox: DecisionToolbox
    retrieval_mode: RetrievalMode
    evidence: Optional[EvidencePort] = None
    require_quotes: bool = True
    support_threshold: Decimal = DEFAULT_SUPPORT_THRESHOLD
    research_note: bool = False

    @property
    def decision_as_of(self) -> datetime:
        return self.toolbox.binding.decision_as_of


@dataclass
class ValidationReport:
    results: list[ValidationResult]
    note: Optional[ResearchNote]
    proposal: Optional[Proposal]
    policy_evaluation: Optional[PolicyEvaluation]
    blocking: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    invalid_ids: list[str] = field(default_factory=list)
    policy_rejected: bool = False

    @property
    def ok(self) -> bool:
        return not self.blocking


def _result(attempt_id, step, passed, details, severity="blocking") -> ValidationResult:
    return ValidationResult(
        step=step,
        passed=passed,
        severity="info" if passed and severity == "blocking" else severity,
        details=[f"attempt:{attempt_id}"] + details,
    )


def validate_output(
    out: Union[FinalOut, NoteOut], vin: ValidationInputs, attempt_id: str
) -> ValidationReport:
    tb = vin.toolbox
    results: list[ValidationResult] = []
    blocking: list[str] = []
    review: list[str] = []
    invalid: set[str] = set()
    proposal_out = getattr(out, "proposal", None)
    decision = getattr(out, "decision", None)

    # 1. schema ---------------------------------------------------------------
    problems: list[str] = []
    ids = (
        [c.claim_id for c in out.claims]
        + [c.citation_id for c in out.citations]
        + [f.finding_id for f in out.numerical_findings]
        + [h.hypothesis_id for h in out.hypotheses]
    )
    referenced = (
        [i for c in out.claims for i in c.citation_ids]
        + [i for f in out.numerical_findings for i in f.calculation_ids + f.input_snapshot_ids]
        + [i for h in out.hypotheses for i in h.supporting_citation_ids]
        + [c.bundle_id for c in out.citations]
        + [c.chunk_id for c in out.citations]
        + [c.document_version_id for c in out.citations]
    )
    if proposal_out is not None:
        referenced += proposal_out.supporting_claim_ids + proposal_out.supporting_calculation_ids
    bad_ids = sorted({i for i in ids + referenced if not _ID.match(i)})
    if bad_ids:
        problems.append(f"invalid_identifier:{','.join(bad_ids[:5])}")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate_id:{','.join(duplicates)}")
    citation_ids = {c.citation_id for c in out.citations}
    claim_ids = {c.claim_id for c in out.claims}
    for claim in out.claims:
        missing = [i for i in claim.citation_ids if i not in citation_ids]
        if not claim.citation_ids or missing:
            invalid.add(claim.claim_id)
            problems.append(f"claim_citation_unresolved:{claim.claim_id}")
    for c in out.citations:
        if (c.start_offset is not None and c.start_offset < 0) or (
            c.end_offset is not None and c.end_offset < 0
        ):
            invalid.add(c.citation_id)
            problems.append(f"negative_offset:{c.citation_id}")
    proposal: Optional[Proposal] = None
    proposal_problems: list[str] = []
    if not vin.research_note:
        if decision == "propose" and (proposal_out is None or proposal_out.action != "REBALANCE"):
            proposal_problems.append("decision_propose_requires_rebalance_proposal")
        if (
            decision != "propose"
            and proposal_out is not None
            and proposal_out.action == "REBALANCE"
        ):
            proposal_problems.append(f"rebalance_proposal_with_decision_{decision}")
        if decision == "propose" and out.status != "supported":
            proposal_problems.append(f"proposal_with_status_{out.status}")
        if proposal_out is not None and decision in ("propose", "hold"):
            targets: list[TargetWeight] = []
            allowed = set(tb.binding.universe) | {CASH_SECURITY_ID}
            for item in proposal_out.target_weights:
                try:
                    weight = Decimal(str(item.weight).strip())
                except InvalidOperation:
                    proposal_problems.append(f"invalid_weight:{item.security_id}")
                    continue
                if not weight.is_finite() or weight < 0 or weight > 1:
                    proposal_problems.append(f"weight_out_of_range:{item.security_id}")
                    continue
                if item.security_id not in allowed:
                    proposal_problems.append(f"security_not_in_frozen_universe:{item.security_id}")
                    continue
                try:
                    targets.append(TargetWeight(security_id=item.security_id, weight=weight))
                except ValidationError:
                    proposal_problems.append(f"invalid_security_id:{item.security_id}")
            for claim_id in proposal_out.supporting_claim_ids:
                if claim_id not in claim_ids:
                    proposal_problems.append(f"supporting_claim_unknown:{claim_id}")
            if not proposal_problems:
                try:
                    proposal = Proposal(
                        action=DecisionAction(proposal_out.action),
                        target_weights=targets,
                        supporting_claim_ids=proposal_out.supporting_claim_ids,
                        supporting_calculation_ids=proposal_out.supporting_calculation_ids,
                    )
                except (ValidationError, ValueError) as exc:
                    message = (
                        exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
                    )
                    proposal_problems.append(f"proposal_contract:{message}")
    problems += proposal_problems
    if bad_ids or duplicates or proposal_problems:
        blocking += [p for p in problems if not p.startswith(("claim_citation", "negative_offset"))]
    results.append(
        _result(
            attempt_id,
            "schema",
            not problems,
            problems,
            severity="blocking" if blocking else "warning",
        )
    )

    # 2-4. citations -------------------------------------------------------------
    membership, temporal, quotes = [], [], []
    delivered = tb.delivered
    for c in out.citations:
        bundle = tb.bundles.get(c.bundle_id)
        chunk = None
        if bundle is not None and c.chunk_id in delivered.get(c.bundle_id, []):
            chunk = bundle.chunk(c.chunk_id)
        if chunk is None:
            membership.append(f"{c.citation_id}:{c.chunk_id}_not_delivered_in_{c.bundle_id}")
            invalid.add(c.citation_id)
            continue
        if chunk.version_id != c.document_version_id:
            membership.append(f"{c.citation_id}:document_version_mismatch")
            invalid.add(c.citation_id)
            continue
        problems_t = []
        if chunk.available_at > vin.decision_as_of:
            problems_t.append(
                f"{c.citation_id}:future_source_available_{chunk.available_at.isoformat()}"
            )
        if bundle.decision_as_of != vin.decision_as_of:
            problems_t.append(f"{c.citation_id}:bundle_cutoff_mismatch")
        if vin.evidence is not None and bundle.index_build_id != vin.evidence.index_build_id:
            problems_t.append(f"{c.citation_id}:index_not_permitted:{bundle.index_build_id}")
        permitted = {vin.retrieval_mode}
        if bundle.mode not in permitted:
            problems_t.append(f"{c.citation_id}:retrieval_mode_not_permitted:{bundle.mode.value}")
        if problems_t:
            temporal += problems_t
            invalid.add(c.citation_id)
            continue
        problems_q = []
        if vin.require_quotes and not c.quote:
            problems_q.append(f"{c.citation_id}:quote_required")
        check = validate_quote(chunk.text, c.quote, c.start_offset, c.end_offset)
        if not check.valid:
            problems_q.append(f"{c.citation_id}:" + ";".join(check.reasons))
        stored = vin.evidence.chunk_text(c.chunk_id) if vin.evidence is not None else chunk.text
        if sha256_text(chunk.text) != chunk.text_hash or stored != chunk.text:
            problems_q.append(f"{c.citation_id}:delivered_text_differs_from_stored_text")
        if problems_q:
            quotes += problems_q
            invalid.add(c.citation_id)
    results.append(_result(attempt_id, "citation_membership", not membership, membership))
    results.append(_result(attempt_id, "temporal", not temporal, temporal))
    results.append(_result(attempt_id, "quote_offsets", not quotes, quotes))
    for claim in out.claims:
        if any(i in invalid for i in claim.citation_ids):
            invalid.add(claim.claim_id)

    # 5. calculation references -------------------------------------------------
    calc_problems = []
    calc_ids = {i for f in out.numerical_findings for i in f.calculation_ids}
    if proposal_out is not None:
        calc_ids |= set(proposal_out.supporting_calculation_ids)
    bad_calcs: set[str] = set()
    for calc_id in sorted(calc_ids):
        calc = tb.calc_store.get(calc_id)
        if calc is None:
            calc_problems.append(f"{calc_id}:unknown_calculation")
        elif not tb.calc_store.verify(calc_id):
            calc_problems.append(f"{calc_id}:signature_invalid")
        elif calc_id not in tb.issued_calc_ids:
            calc_problems.append(f"{calc_id}:not_issued_to_this_decision")
        elif calc.as_of > vin.decision_as_of:
            calc_problems.append(f"{calc_id}:calculation_after_cutoff")
        else:
            continue
        bad_calcs.add(calc_id)
    invalid |= bad_calcs
    for finding in out.numerical_findings:
        if not finding.calculation_ids or set(finding.calculation_ids) & bad_calcs:
            invalid.add(finding.finding_id)
    results.append(_result(attempt_id, "calc_refs", not calc_problems, calc_problems))

    # 6. semantic support review aid ---------------------------------------------
    flagged: set[str] = set()
    support_details = []
    by_citation = {c.citation_id: c for c in out.citations}
    for claim in out.claims:
        if claim.claim_id in invalid or not claim.material:
            continue
        texts = []
        for cid in claim.citation_ids:
            citation = by_citation[cid]
            chunk = tb.bundles[citation.bundle_id].chunk(citation.chunk_id)
            texts.append(citation.quote or chunk.text)
            texts.append(chunk.title + " " + " ".join(chunk.heading_path))
        score = support_score(claim.text, texts)
        if score < vin.support_threshold:
            flagged.add(claim.claim_id)
            support_details.append(
                f"{claim.claim_id}:lexical_support_{score}_below_{vin.support_threshold}"
            )
    results.append(
        _result(
            attempt_id,
            "support",
            not flagged,
            [f"classifier:{SUPPORT_CLASSIFIER_VERSION}"] + support_details,
            severity="warning",
        )
    )

    # dependencies ----------------------------------------------------------------
    if proposal_out is not None and decision in ("propose", "hold"):
        for claim_id in proposal_out.supporting_claim_ids:
            if claim_id in invalid:
                blocking.append(f"dependent_claim_invalid:{claim_id}")
            elif claim_id in flagged:
                review.append(f"flagged_material_dependency:{claim_id}")
        for calc_id in proposal_out.supporting_calculation_ids:
            if calc_id in bad_calcs:
                blocking.append(f"dependent_calculation_invalid:{calc_id}")
        if proposal_out.action == "REBALANCE":
            valid_claims = [i for i in proposal_out.supporting_claim_ids if i not in invalid]
            valid_calcs = [i for i in proposal_out.supporting_calculation_ids if i not in bad_calcs]
            if vin.retrieval_mode != RetrievalMode.NONE and not valid_claims:
                blocking.append("evidence_dependent_proposal_without_valid_claims")
            if vin.retrieval_mode == RetrievalMode.NONE and not valid_calcs:
                blocking.append("market_proposal_without_valid_calculations")

    # 7. policy dry run -------------------------------------------------------------
    evaluation: Optional[PolicyEvaluation] = None
    policy_rejected = False
    if proposal is not None and not blocking:
        evaluation = tb.policy_dry_run(proposal.action, list(proposal.target_weights))
        if not evaluation.passed:
            policy_rejected = True
            blocking.append("policy_rejected:" + ";".join(evaluation.rejected_reasons[:6]))
        results.append(
            _result(attempt_id, "policy", evaluation.passed, list(evaluation.rejected_reasons))
        )
    else:
        reason = "no_proposal" if proposal is None else "skipped_after_blocking_failures"
        results.append(_result(attempt_id, "policy", proposal is None, [reason], severity="info"))

    note = _note(out, invalid, flagged, tb)
    return ValidationReport(
        results=results,
        note=note,
        proposal=proposal,
        policy_evaluation=evaluation,
        blocking=blocking,
        review_flags=review,
        invalid_ids=sorted(invalid),
        policy_rejected=policy_rejected,
    )


def _note(out, invalid: set[str], flagged: set[str], tb: DecisionToolbox) -> Optional[ResearchNote]:
    try:
        return ResearchNote(
            status=ResearchStatus(out.status),
            claims=[
                DocumentaryClaim(
                    claim_id=c.claim_id,
                    text=c.text,
                    citation_ids=c.citation_ids,
                    material=c.material,
                    validation_status=(
                        "invalid"
                        if c.claim_id in invalid
                        else "review_required" if c.claim_id in flagged else "valid"
                    ),
                )
                for c in out.claims
            ],
            numerical_findings=[
                NumericalFinding(
                    finding_id=f.finding_id,
                    text=f.text,
                    calculation_ids=f.calculation_ids,
                    input_snapshot_ids=f.input_snapshot_ids,
                    validation_status="invalid" if f.finding_id in invalid else "valid",
                )
                for f in out.numerical_findings
            ],
            hypotheses=[
                Hypothesis(
                    hypothesis_id=h.hypothesis_id,
                    text=h.text,
                    assumptions=h.assumptions,
                    scenario_ids=h.scenario_ids,
                    supporting_citation_ids=h.supporting_citation_ids,
                )
                for h in out.hypotheses
            ],
            counterevidence=out.counterevidence,
            coverage_gaps=out.coverage_gaps,
            citations=[
                Citation(
                    citation_id=c.citation_id,
                    bundle_id=c.bundle_id,
                    chunk_id=c.chunk_id,
                    document_version_id=c.document_version_id,
                    quote=c.quote,
                    start_offset=c.start_offset,
                    end_offset=c.end_offset,
                )
                for c in out.citations
            ],
            retrieval_run_ids=list(tb.retrieval_run_ids),
            explanation=out.explanation,
        )
    except ValidationError:
        return None
