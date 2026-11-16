# Evidence benchmark report — `evidence-benchmark-v1` (hybrid vs graph retrieval)

Run on 2026-11-10 with `fi-research benchmark run --split {all,dev,heldout}` on a fresh offline
evidence home. Results are saved in
`ai-trading-race-ml/benchmarks/evidence/results/v1-{all,dev,heldout}-2026-11-10.json`. This is a
**retrieval** benchmark: no model, hosted or reference, generated answers here.

| Item | Value |
|---|---|
| Questions | 60 (`benchmarks/evidence/questions_v1.json`): 20 direct-document, 20 multi-document/event, 20 relationship/revision/temporal/insufficient-evidence |
| Split | fixed before tuning: alternating dev/held-out within each category (30/30) |
| Corpus | 16 FOMC statements + 16 minutes (2023-02 → 2024-12) + 1 labelled synthetic correction; index `ib-9c6e806d754e5317c6ab` (benchmark index includes the synthetic correction; the agent/demo index `ib-c5ff36b8d6d057e4ab95` excludes it) |
| Modes | `hybrid_rag_v1` (BM25 + exact `hash-embed-v1` vector + RRF on the eligible snapshot) vs `graph_rag_v1` (hybrid + bounded graph expansion, `graph-expand-v1`) |
| Annotation | expected evidence auto-annotated by recorded rules (document + heading + regex on the version eligible at the cutoff) |

## Contamination note (read before using held-out numbers)

The evidence workstream recorded in every result file (`trial_note`) that the graph-expansion
co-support materialization and the `graph_reserved_slots=4` selection quota were **finalized during
development after inspecting results on all 60 questions**. The held-out numbers below are therefore
**not untouched held-out results** (spec §16.1). Freeze the settings and register a new trial before a
final held-out evaluation.

**Manual factual-support review is pending.** The benchmark measures evidence retrieval and citation
resolvability. Answer completeness, manually reviewed factual support (the ≥ 95% project target),
abstention quality and reviewer disagreement are **not computed**; they need offline manual review
of generated answers, and none has been done.

## Results — all 60 questions

| Metric | hybrid_rag_v1 | graph_rag_v1 |
|---|---|---|
| Evidence recall@K (K = all delivered) | 0.7073 | 0.7667 |
| Evidence recall@5 | 0.5585 | 0.6034 |
| Precision@K | 0.1350 | 0.1471 |
| Precision@5 | 0.1855 | 0.2109 |
| Version recall | 0.9000 | 0.9455 |
| Temporal violations (future evidence delivered) | **0** | **0** |
| Citation id/span validity | **100%** | **100%** |
| Graph-added passages (not among hybrid candidates) | — | 2 |
| Graph-added passages that were expected evidence | — | 0 |
| CPI release-fact hits (structured facts) | 0 | 3 |
| Mean retrieval latency (ms, wall clock) | 4.98 | 7.65 |

Graph effect on recall (55 questions with expected evidence; the 5 insufficient-evidence questions
C16–C20 have none): **7 helped, 0 harmed, 48 neutral**.

## By split

| Split | Mode | Recall@K | Recall@5 | Precision@K | Precision@5 | Temporal violations | Citation validity | Latency (ms) | Helped / harmed |
|---|---|---|---|---|---|---|---|---|---|
| dev (30) | hybrid | 0.7125 | 0.5833 | 0.1729 | 0.2143 | 0 | 100% | 3.86 | — |
| dev (30) | graph | 0.7732 | 0.5905 | 0.1818 | 0.2214 | 0 | 100% | 6.02 | 3 / 0 |
| held-out (30)\* | hybrid | 0.7019 | 0.5328 | 0.0957 | 0.1556 | 0 | 100% | 4.18 | — |
| held-out (30)\* | graph | 0.7600 | 0.6168 | 0.1111 | 0.2000 | 0 | 100% | 6.50 | 4 / 0 |

\* Contaminated: see the note above.

## By category (all splits)

| Category | Hybrid recall@K | Graph recall@K | Hybrid P@K | Graph P@K | Helped / harmed | Latency hybrid / graph (ms) |
|---|---|---|---|---|---|---|
| Direct document (20) | 0.9800 | 0.9800 | 0.147 | 0.147 | 0 / 0 | 4.93 / 7.13 |
| Multi-document/event (20) | 0.4651 | 0.5785 | 0.124 | 0.153 | 6 / 0 | 5.27 / 8.41 |
| Relationship/temporal (20) | 0.6667 | 0.7333 | 0.133 | 0.139 | 1 / 0 | 4.74 / 7.40 |

Graph-assisted retrieval matters on multi-document and relationship questions, not on simple
lookups. That is the expected pattern (spec §16.4).

## Graph-specific reporting (spec §16.4)

- **Additional passages because of graph traversal.** Two passages in the whole benchmark were
  strictly graph-added (outside the hybrid candidate pool): questions A18 and A20 (held-out,
  minutes-section lookups). Neither was expected evidence, and neither changed recall (neutral).
- **Questions helped.** B03, B06, B08 (statement-vs-minutes), B14, B15, B16 (decision vs previous
  meeting) and C05 (minutes not yet available). In all seven the expected passages were hybrid
  candidates that graph-assisted ranking and the reserved graph slots moved into the delivered set
  (`addedByGraph=false`). **Harmed:** none.
- **Added latency and resources.** Graph mode adds about 2.7 ms per query (4.98 → 7.65 ms mean, all
  questions) and delivers slightly more evidence tokens on average (5,548 vs 5,252 per question) for
  the same mean passage count (10.8). Latency is wall clock on a development laptop and varies
  between runs.
- **Relationship/entity-resolution errors.** Not measured automatically. The rule lexicon routes
  ambiguous aliases to review and never traverses them (`tests/evidence/test_knowledge.py`); a
  manual error audit of graph edges is pending.
- **Persistent failure.** C06–C09 (previous-meeting labor-market discussion in minutes) score 0
  recall in both modes: the lexical baseline ranks generic minutes sections above the targeted
  participants' discussion, and graph expansion does not recover them.

## Structural release gates (test fixtures)

| Gate | Status |
|---|---|
| Zero accepted future-evidence citations | Met: 0 temporal violations in both modes, all splits; also enforced by `tests/evidence/test_temporal.py` and `tests/agents/test_validation.py::test_future_dated_citation_is_rejected` |
| 100% resolvable citation ids/spans | Met: citation validity 1.0 in both modes, all splits (`tests/evidence/test_benchmark.py::test_dev_split_structural_gates`) |
| ≥ 95% manually supported factual claims (project target) | **Not assessed:** manual review pending |

## Consistency with the development run

`results/v1-all.json` (evidence workstream development run, 2026-11-06, same index) reported hybrid
recall@K 0.71 vs graph 0.77 with 7 helped and 0 harmed. This run reproduces those values (0.7073 /
0.7667; 7 / 0).

## Interpretation and default

Graph RAG is a completed experiment: it passes the structural gates and improves recall on
multi-document and relationship questions at about 2.7 ms extra latency. It does not reach the
persistent C06–C09 failures, and its strict graph-added passages contributed no expected evidence.
In the demo replay ([demo-experiment.md](demo-experiment.md) §6) the extra evidence never changed a
decision of the reference model. An operational default should weigh these measured benefits
against cost once a semantic embedding provider and a hosted model are evaluated as new trials.
