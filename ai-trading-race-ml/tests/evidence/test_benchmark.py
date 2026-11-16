"""Evidence benchmark structure and structural release gates (spec 16.4)."""

from __future__ import annotations

from collections import Counter

from research_engine.retrieval import benchmark


def test_questions_are_versioned_balanced_and_split():
    data = benchmark.load_questions()
    assert data["benchmark"] == "evidence-benchmark-v1"
    questions = data["questions"]
    assert len(questions) == 60
    assert Counter(q["category"] for q in questions) == {
        "direct_document": 20,
        "multi_document": 20,
        "relationship_temporal": 20,
    }
    split = Counter((q["category"], q["split"]) for q in questions)
    assert set(split.values()) == {10}
    for q in questions:
        assert q["adjudication"]["status"].startswith("auto-annotated")
        if q["requiresAbstention"]:
            assert q["acceptableAbstention"] and not q["expectedChunkIds"]
        else:
            assert q["expectedChunkIds"]


def test_expected_evidence_resolves_and_was_available(home, synthetic_index):
    for q in benchmark.load_questions()["questions"]:
        from datetime import datetime

        as_of = datetime.fromisoformat(q["decisionAsOf"].replace("Z", "+00:00"))
        for chunk_id in q["expectedChunkIds"]:
            chunk = home.store.get_chunk(chunk_id)
            assert chunk is not None, (q["id"], chunk_id)
            assert chunk.available_at <= as_of


def test_generation_is_reproducible(synthetic_index):
    regenerated = benchmark.generate(synthetic_index)
    stored = benchmark.load_questions()
    assert [q["expectedChunkIds"] for q in regenerated["questions"]] == [
        q["expectedChunkIds"] for q in stored["questions"]
    ]


def test_dev_split_structural_gates(home, synthetic_index):
    report = benchmark.evaluate(home.store, synthetic_index, split="dev")
    summary = report["summary"]["all"]
    assert summary["questions"] == 30
    for mode in ("hybrid_rag_v1", "graph_rag_v1"):
        assert summary[mode]["temporal_violations"] == 0
        assert summary[mode]["citation_validity"] == 1.0
    assert report["summary"]["manual_factual_support"].startswith("not computed")
    assert "trial_note" in report
