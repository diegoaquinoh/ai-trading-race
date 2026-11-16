# Methodology card — Fixed Income Research Lab (status 2026-11-10)

This card follows spec §16.1–16.2. It covers the registered demo experiment `fi-demo-2024q1`, its
labelled companion runs and the evidence benchmark. **No result in this repository is a held-out
evaluation, and no hosted LLM has been run.** AI strategies use `reference-heuristic-v1`, a
deterministic rule-based model.

## 1. Questions and hypotheses

| Id | Comparison | Hypothesis (registered in `definition.json`) | Status after the demo run |
|---|---|---|---|
| H1-retrieval | llm_market vs llm_rag vs llm_graph | Document retrieval changes the matched agent's decisions and exposures relative to market-only inputs | Decisions and exposures differ (2024-01-03 shorten vs 2024-02-12/03-27); one window, one repetition, no significance |
| H2-graph | llm_rag vs llm_graph | Graph-assisted retrieval delivers additional, provenance-backed passages that change at least one decision | Different passages on all 60 retrieval days (mean Jaccard 0.227); 0 strictly graph-added passages; **no decision changed** |
| H3-delegation | llm_graph vs llm_team | A lead with two bounded specialists changes decisions relative to the single graph agent under the same budget | **No decision changed**; the team used 2.5× the generation calls |
| Benchmark | hybrid_rag_v1 vs graph_rag_v1 | Graph expansion improves evidence recall on multi-document/relationship questions without temporal violations | Recall@K 0.7073 → 0.7667, 7 helped / 0 harmed, 0 violations; held-out contaminated |

Profitability, graph superiority and delegation superiority are hypotheses, not acceptance criteria
(spec §1). Under the reference model, H2 and H3 test plumbing and evidence access, not reasoning.

## 2. Variants (competitors)

| Strategy | Version / config | Notes |
|---|---|---|
| cash | `cash` | uninvested reference, zero cash interest |
| static_ladder | `bootstrap-30-34-30-6-v2`, then hold | coupons stay cash |
| quant_duration | `quant-duration-v2`, 4.0y target, 0.25y band, monthly | two-step rotation (ADR 0008) |
| llm_market | `llm-market-v1`, retrieval `none` | numerical tools only |
| llm_rag | `llm-rag-v1`, `hybrid_rag_v1`, mandatory first retrieval | |
| llm_graph | `llm-graph-v1`, `graph_rag_v1` + `expand_evidence_graph` | |
| llm_team | `llm-team-v1`, lead + macro researcher + critical reviewer, `parallel_v1` | same evidence access as llm_graph |

Shared by all AI variants: provider `reference` / `reference-heuristic-v1`, prompts
`fi-agent-prompts-v1@d9bc062da834e51c`, tools `fi-agent-tools-v1`, output contract, validation pipeline, support
threshold 0.5, initial query template `policy-outlook-v1`, and the budget-matched `DecisionBudget`
(6 generation calls, 12 tool calls, 3 evidence calls, 12 chunks / 8,000 evidence tokens, 32k input /
12k output tokens, 90 s). Strategy config hashes are in `run/manifest.json`.

## 3. Metrics

- **Primary (financial):** net return, max drawdown, average DV01, end effective duration, spread
  cost, decision outcome counts.
- **Reported alongside:** gross return, daily volatility, turnover, cash share, coupons,
  realized/unrealized PnL, reconciled attribution, fills/expiries/rejections, completeness.
- **Evidence:** delivered passages, graph-added passages, RAG/Graph overlap per session, event
  document delivered, temporal violations, claim validation; benchmark recall/precision@K and @5,
  version recall, citation validity, helped/harmed, latency.
- **Usage:** generation/tool/evidence calls, estimated tokens, model cost (zero schedule), kept
  separate from execution costs.
- **Conventions:** `metrics-v1` (complete valuations only; Sharpe needs a declared risk-free series
  and ≥ 60 returns; annualization needs ≥ 252; moving-block bootstrap, block 5, 1,000 resamples,
  seed 0, descriptive only).

## 4. Data, splits and time policy

| Item | Value |
|---|---|
| Market data | U.S. Treasury daily par yield curves 2023–2024 (fixture checksums in `fixtures/market/treasury/manifest.json`), curve `usd-tsy-par-bootstrap-v1` |
| Instruments | `synthetic-universe-v1` (hypothetical SYN-USD-NOTE-*) |
| Evidence | FOMC statements and minutes 2023–2024 (2026 web versions, flagged), `hash-embed-v1` |
| Development period | 2023 (agent sample `demo-sample-2023-06`, evidence benchmark development, numerical fixtures) |
| Demo window | 2024-01-02 → 2024-03-28 (61 sessions). A demonstration window, not a validation or held-out interval |
| Held-out | **None declared.** Prompts, lexicon, thresholds and retrieval settings were not frozen against a held-out interval |
| Information policy | `reconstructed_publication_plus_lag_v1` (retrospective); no forward paper run |
| Purging | Not applicable: no fitted model or label horizon; nothing is trained on the window |

## 5. Assumptions

Synthetic-curve execution at next-session 15:30 observation, half-spread 0.02 per 100 face
(sensitivity 0.00/0.05), no fees, no slippage, T+1 settlement, settled-cash funding, zero cash
interest, risk policy `treasury-long-only-v1`, common bootstrap with an initialization-only
turnover exemption, FIFO lots, cents posting precision. The reference model is deterministic, so
stochastic repetitions are not applicable (repetition 0 only).

## 6. Exclusion rules

- A session without a READY curve available by 19:00 New York is skipped for every competitor
  (`skipped_stale_data`) and listed. None occurred in the demo window.
- No decision, session or competitor is excluded after inspecting results.
- Failure-injection and sensitivity runs are reported separately and never ranked with the canonical
  run.
- Benchmark questions requiring abstention (C16–C20) are excluded from recall averages and from
  helped/harmed counts; abstention quality is not computed.

## 7. Trial registry (everything run so far that produced or informed reported results)

| # | Date | Trial / run id | Kind | Saved at | What changed afterwards |
|---|---|---|---|---|---|
| T1 | 2026-11-09 | `demo-sample-2023-06-r0` (2023-06-13 → 06-16, 4 AI strategies) | agent recorded-replay fixture (agents workstream) | `fixtures/recorded/demo-sample-2023-06/` | Re-recorded 2026-11-09 under the two-mode protocol after market features became `CalculationType.MARKET_FEATURES` (content-addressed calculation ids changed, so the recordings had to be recaptured) |
| T2 | 2026-11-06 | evidence benchmark v1 development run (all 60) | retrieval benchmark (evidence workstream) | `benchmarks/evidence/results/v1-all.json` | Co-support materialization and `graph_reserved_slots=4` finalized **after** inspecting all 60 questions, which contaminates held-out |
| T3 | 2026-11-10 | evidence benchmark v1 (all, dev, held-out) | retrieval benchmark, same settings as T2 | `benchmarks/evidence/results/v1-{all,dev,heldout}-2026-11-10.json` | None (reproduces T2) |
| T4 | 2026-11-09 | `explore-r0` (demo window, 7 competitors, fresh inference) | exploratory sizing/runtime run | not saved (scratch) | Bundle format chosen (gzip transitions log); no strategy or parameter change. Its numbers are not reported |
| T5 | 2026-11-10 | `fi-demo-2024q1-r0` trial build | bundle build without sensitivity | not saved (scratch) | Fault plan revised: F1 targeted a specialist and showed the designed containment (HOLD), so F1 became a lead outage and the specialist case became F5. The walkthrough event was moved to the first policy-document event with an evidence-agent proposal (2024-01-03). No strategy parameter changed |
| T6 | 2026-11-10 | `fi-demo-2024q1-r0` (capture + recorded-response replay) | **canonical demo run** | `fixtures/demo/fi-demo-2024q1/run/` | Rebuilt once to correct a limitation sentence about Sharpe; runs and metrics identical |
| T7 | 2026-11-10 | `fi-demo-2024q1-faults-r0` | labelled failure-injection run (5 declared faults) | `fixtures/demo/fi-demo-2024q1/failure-injection/` | — |
| T8 | 2026-11-10 | `fi-demo-2024q1-cost-hs000-r0`, `-hs002-r0`, `-hs005-r0` | cost sensitivity (fresh inference, reference model) | `fixtures/demo/fi-demo-2024q1/sensitivity/` | — |

Not trials: unit/integration test replays, parity fixtures (`contracts/fixtures/parity/`, numerical
parity of baselines), and other workstreams' development runs that produced no reported result.

## 8. What a real evaluation still needs

1. Freeze prompts, lexicon/retrieval settings, signal mappings and strategy parameters; register a
   new trial.
2. Choose development/validation/held-out intervals after the data admission report (24–48 months
   of supported data proposed).
3. Run a hosted model with a pinned identifier, a versioned price schedule and a monetary ceiling,
   with ≥ 3 repetitions, labelled retrospective; then a forward paper run.
4. Declare a risk-free/cash series before interpreting excess returns.
5. Complete manual factual-support review of generated answers and an entity/edge error audit.
6. Report paired differences with a time-series bootstrap only when the sample supports it.

## 9. Limitations

See [demo-experiment.md](demo-experiment.md) §9 (synthetic vs observed, retrospective policy,
pretrained-model hindsight, data gaps, exposure differences, no significance) and
[evidence-benchmark.md](evidence-benchmark.md) (contamination, pending manual review).
