"""Validation pipeline (spec 13.2): citations, chronology, quotes, signed calculations, policy."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from research_engine.agents.budget import BudgetLedger
from research_engine.agents.output import FinalOut
from research_engine.agents.tool_schemas import TOOL_ARGS
from research_engine.agents.tools import DecisionToolbox, ToolBinding
from research_engine.agents.validation import ValidationInputs, support_score, validate_output
from research_engine.contracts.calculations import (
    CalculatedValue,
    CalculationResult,
    CalculationType,
    Completeness,
    EngineProvenance,
    ValueBasis,
)
from research_engine.contracts.common import Unit
from research_engine.contracts.decisions import DecisionBudget, RetrievalMode

from .fakes import HAWKISH_TEXT, FakeDoc, FakeEvidencePort, utc

QUOTE = "Inflation remains elevated."


def _setup(ctx, docs, tampered=None):
    evidence = FakeEvidencePort(docs, tampered=tampered)
    tb = DecisionToolbox(
        ToolBinding.from_context(ctx),
        BudgetLedger(DecisionBudget()),
        strategy_tools=frozenset(TOOL_ARGS),
        evidence=evidence,
        retrieval_mode=RetrievalMode.HYBRID_RAG,
    )
    delivered = tb.call("single", "retrieve_evidence", {"question": "policy outlook"})
    risk = tb.call("single", "get_portfolio_risk", {"scenario_ids": []})
    return tb, evidence, delivered.payload["bundleId"], risk.payload


def _output(bundle_id, chunk_id, version_id, calc_id, *, quote=QUOTE, claim=None, weights=None):
    start = HAWKISH_TEXT.find(quote) if quote in HAWKISH_TEXT else 0
    return FinalOut.model_validate(
        {
            "action": "final",
            "status": "supported",
            "decision": "propose" if weights else "hold",
            "claims": [
                {
                    "claim_id": "clm-1",
                    "text": claim or f"FOMC statement May 2023 states: {QUOTE}",
                    "citation_ids": ["cit-1"],
                }
            ],
            "citations": [
                {
                    "citation_id": "cit-1",
                    "bundle_id": bundle_id,
                    "chunk_id": chunk_id,
                    "document_version_id": version_id,
                    "quote": quote,
                    "start_offset": start,
                    "end_offset": start + len(quote),
                }
            ],
            "numerical_findings": [
                {"finding_id": "f-1", "text": "duration", "calculation_ids": [calc_id]}
            ],
            "explanation": "test",
            "proposal": {
                "action": "REBALANCE" if weights else "HOLD",
                "target_weights": weights or [],
                "supporting_claim_ids": ["clm-1"],
                "supporting_calculation_ids": [calc_id],
            },
        }
    )


def _validate(tb, evidence, out):
    vin = ValidationInputs(toolbox=tb, retrieval_mode=RetrievalMode.HYBRID_RAG, evidence=evidence)
    return validate_output(out, vin, "att-test")


def _step(report, name):
    return next(r for r in report.results if r.step == name)


def _sell_some(risk, amount="0.03"):
    weights = {
        u["securityId"]: Decimal(u["weight"]) for u in risk["universe"] if Decimal(u["weight"]) > 0
    }
    longest = max(weights)
    weights[longest] -= Decimal(amount)
    out = [
        {"security_id": k, "weight": format(v.quantize(Decimal("0.000001")), "f")}
        for k, v in sorted(weights.items())
    ]
    total = sum(Decimal(w["weight"]) for w in out)
    out.append({"security_id": "CASH-USD", "weight": format(Decimal(1) - total, "f")})
    return out


def test_valid_output_passes_every_step(ctx_for):
    ctx = ctx_for("llm_rag")
    tb, ev, bundle, risk = _setup(ctx, [FakeDoc("chk-a", HAWKISH_TEXT, utc(2023, 5, 3, 20))])
    report = _validate(
        tb,
        ev,
        _output(bundle, "chk-a", "ver-chk-a", risk["calculationId"], weights=_sell_some(risk)),
    )
    assert report.ok, report.blocking
    assert [r.step for r in report.results] == [
        "schema",
        "citation_membership",
        "temporal",
        "quote_offsets",
        "calc_refs",
        "support",
        "policy",
    ]
    assert all(r.passed for r in report.results)
    assert report.policy_evaluation is not None and report.policy_evaluation.passed
    assert report.note.claims[0].validation_status == "valid"


def test_future_dated_citation_is_rejected(ctx_for):
    ctx = ctx_for("llm_rag")
    future = ctx.request.decision_as_of + timedelta(days=1)
    tb, ev, bundle, risk = _setup(ctx, [FakeDoc("chk-f", HAWKISH_TEXT, future)])
    report = _validate(
        tb,
        ev,
        _output(bundle, "chk-f", "ver-chk-f", risk["calculationId"], weights=_sell_some(risk)),
    )
    temporal = _step(report, "temporal")
    assert not temporal.passed and "future_source" in temporal.details[1]
    assert "dependent_claim_invalid:clm-1" in report.blocking
    assert report.note.claims[0].validation_status == "invalid"
    assert report.policy_evaluation is None  # blocked before the policy step


def test_fabricated_and_foreign_calculation_ids_are_rejected(ctx_for):
    ctx = ctx_for("llm_rag")
    tb, ev, bundle, risk = _setup(ctx, [FakeDoc("chk-a", HAWKISH_TEXT, utc(2023, 5, 3, 20))])
    fabricated = _validate(tb, ev, _output(bundle, "chk-a", "ver-chk-a", "calc-0123456789abcdef"))
    calc = _step(fabricated, "calc_refs")
    assert not calc.passed and "unknown_calculation" in calc.details[1]
    assert "dependent_calculation_invalid:calc-0123456789abcdef" in fabricated.blocking
    # A genuinely signed calculation that was never issued to this decision is also rejected.
    foreign = tb.calc_store.register(
        CalculationResult(
            calculation_type=CalculationType.RISK,
            calculation_version="foreign-v1",
            input_hashes={},
            as_of=ctx.request.decision_as_of,
            outputs=[
                CalculatedValue(
                    name="x", value=Decimal("1"), unit=Unit.YEARS, basis=ValueBasis.UNSCALED
                )
            ],
            completeness=Completeness.COMPLETE,
            engine=EngineProvenance(engine_version="t", library="t", conventions_version="t"),
        )
    )
    report = _validate(tb, ev, _output(bundle, "chk-a", "ver-chk-a", foreign.calculation_id))
    assert "not_issued_to_this_decision" in _step(report, "calc_refs").details[1]


def test_quote_not_in_chunk_and_tampered_store_are_rejected(ctx_for):
    ctx = ctx_for("llm_rag")
    tb, ev, bundle, risk = _setup(ctx, [FakeDoc("chk-a", HAWKISH_TEXT, utc(2023, 5, 3, 20))])
    bad_quote = "Inflation has fallen sharply."
    report = _validate(
        tb, ev, _output(bundle, "chk-a", "ver-chk-a", risk["calculationId"], quote=bad_quote)
    )
    assert not _step(report, "quote_offsets").passed
    assert report.note.claims[0].validation_status == "invalid"
    assert "dependent_claim_invalid:clm-1" in report.blocking
    tb2, ev2, bundle2, risk2 = _setup(
        ctx,
        [FakeDoc("chk-b", HAWKISH_TEXT, utc(2023, 5, 3, 20))],
        tampered={"chk-b": "edited text"},
    )
    report2 = _validate(tb2, ev2, _output(bundle2, "chk-b", "ver-chk-b", risk2["calculationId"]))
    assert "delivered_text_differs_from_stored_text" in " ".join(
        _step(report2, "quote_offsets").details
    )


def test_citation_outside_the_delivered_bundle_is_rejected(ctx_for):
    ctx = ctx_for("llm_rag")
    tb, ev, bundle, risk = _setup(ctx, [FakeDoc("chk-a", HAWKISH_TEXT, utc(2023, 5, 3, 20))])
    report = _validate(
        tb, ev, _output("eb-not-delivered", "chk-a", "ver-chk-a", risk["calculationId"])
    )
    assert not _step(report, "citation_membership").passed
    wrong_version = _validate(tb, ev, _output(bundle, "chk-a", "ver-other", risk["calculationId"]))
    assert "document_version_mismatch" in _step(wrong_version, "citation_membership").details[1]


def test_support_classifier_flags_unsupported_material_claims(ctx_for):
    ctx = ctx_for("llm_rag")
    tb, ev, bundle, risk = _setup(ctx, [FakeDoc("chk-a", HAWKISH_TEXT, utc(2023, 5, 3, 20))])
    report = _validate(
        tb,
        ev,
        _output(
            bundle,
            "chk-a",
            "ver-chk-a",
            risk["calculationId"],
            claim="Unemployment will collapse and equities rally next quarter",
            weights=_sell_some(risk),
        ),
    )
    support = _step(report, "support")
    assert not support.passed and support.severity == "warning"
    assert report.review_flags == ["flagged_material_dependency:clm-1"]
    assert report.ok  # a flag, not a blocking failure
    assert support_score("Inflation remains elevated", [QUOTE]) == Decimal("1.0000")


def test_policy_dry_run_rejects_infeasible_targets(ctx_for):
    ctx = ctx_for("llm_rag")
    tb, ev, bundle, risk = _setup(ctx, [FakeDoc("chk-a", HAWKISH_TEXT, utc(2023, 5, 3, 20))])
    everything = [{"security_id": "SYN-USD-NOTE-009", "weight": "1"}]
    report = _validate(
        tb, ev, _output(bundle, "chk-a", "ver-chk-a", risk["calculationId"], weights=everything)
    )
    assert report.policy_rejected and any(b.startswith("policy_rejected") for b in report.blocking)
    assert not _step(report, "policy").passed
    bad_sum = [{"security_id": "SYN-USD-NOTE-009", "weight": "0.5"}]
    report2 = _validate(
        tb, ev, _output(bundle, "chk-a", "ver-chk-a", risk["calculationId"], weights=bad_sum)
    )
    assert any("proposal_contract" in b for b in report2.blocking)
    nan = [
        {"security_id": "SYN-USD-NOTE-009", "weight": "NaN"},
        {"security_id": "CASH-USD", "weight": "1"},
    ]
    report3 = _validate(
        tb, ev, _output(bundle, "chk-a", "ver-chk-a", risk["calculationId"], weights=nan)
    )
    assert any("weight_out_of_range" in b or "invalid_weight" in b for b in report3.blocking)
