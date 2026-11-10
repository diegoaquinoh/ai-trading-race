# Demo experiment report — `fi-demo-2024q1`

> **Read this first.** Every number below comes from the recorded run in
> `ai-trading-race-ml/fixtures/demo/fi-demo-2024q1/` (built 2026-11-10, verified with
> `fi-research demo verify`: 28/28 checks passed). The AI strategies (`llm_market`, `llm_rag`,
> `llm_graph`, `llm_team`) ran on provider **`reference`**, model **`reference-heuristic-v1`**: a
> deterministic, rule-based policy model. **It is not a hosted LLM.** No hosted model produced any
> result in this report. Instruments are **synthetic** and prices are **curve-model observations**, not
> market quotes. The window is short; nothing here is statistically significant.

| Item | Value |
|---|---|
| Experiment / run | `fi-demo-2024q1` / `fi-demo-2024q1-r0` (repetition 0) |
| Definition | `definition.json`, hash `sha256:39230373…8b36` (registered 2026-11-09) |
| Window | 2024-01-02 → 2024-03-28: 61 supported sessions (29 Mar 2024 is not a session on `us-gov-calendar-v1`) |
| Data mode | `synthetic_curve`: universe `synthetic-universe-v1` priced from U.S. Treasury daily par curves (`usd-treasury-par-2023-2024`) |
| Information policy | `reconstructed_publication_plus_lag_v1` (FOMC text available at publication + 120 min; curves at 18:00 New York; decision 19:00) |
| Execution | `synthetic-half-spread-0.02-v1`: next-session 15:30 observation, T+1 settlement, 0.02 per 100 face half-spread, no fees, zero cash interest |
| Risk policy | `treasury-long-only-v1` (spec §9.3 defaults) |
| Track | budget-matched: every AI decision has the same `DecisionBudget` (6 generation calls, 12 tool calls, 3 evidence calls, 12 chunks / 8,000 evidence tokens, 32k input / 12k output tokens, 90 s) |
| Response modes | capture = `fresh_inference` of the reference model through a recording provider; **canonical run = `recorded_replay` with `replay_source=recorded_responses`** (manifest `responseSource: recorded_provider_responses`) |
| Manifest | `run/manifest.json`, hash `sha256:15f6c1a1…46c1`, git `ded71fcb` at build time |
| Repetitions | 0 only. Stochastic repetitions are not applicable: the reference model returns identical output for identical input. Hosted models need ≥ 3 repetitions (spec §16.2). |

Reproduce: `cd ai-trading-race-ml && .venv/bin/python -m research_engine demo verify` (offline,
about 20 s). Rebuild: `demo build --overwrite` (about 70 s, includes the sensitivity reruns).

## 1. Competitors and common start

Seven isolated portfolios of USD 1,000,000. All invested competitors received the identical
`bootstrap-30-34-30-6-v2` allocation on 2024-01-02 (filled 2024-01-03 at the 15:30 observation):
SYN-USD-NOTE-003 15%, NOTE-006 15%, NOTE-007 17%, NOTE-008 17%, NOTE-009 30%, cash 6%. `cash` never
invests.

| Strategy | Kind | Response source |
|---|---|---|
| `cash` | cash reference | deterministic code |
| `static_ladder` | quant policy | deterministic code |
| `quant_duration` | quant policy (`quant-duration-v2`, 4.0y target) | deterministic code |
| `llm_market` | single agent, numerical tools only | recorded responses: reference/reference-heuristic-v1 |
| `llm_rag` | single agent + `hybrid_rag_v1` | recorded responses: reference/reference-heuristic-v1 |
| `llm_graph` | single agent + `graph_rag_v1` | recorded responses: reference/reference-heuristic-v1 |
| `llm_team` | lead + macro researcher + critical reviewer, `graph_rag_v1` | recorded responses: reference/reference-heuristic-v1 |

## 2. Financial results (ranked within this compatibility group only)

Net return includes all execution costs; gross adds back the analytic spread cost. Market context
from the same Treasury fixture: between 2024-01-02 and 2024-03-28 the 2Y par yield moved 4.33% →
4.59%, the 5Y 3.93% → 4.21% and the 10Y 3.95% → 4.20%, so every long-duration portfolio lost value.

| Strategy | Net return | Gross return | Max drawdown | Daily vol | End equity (USD) | Total PnL (USD) |
|---|---|---|---|---|---|---|
| cash | 0.000% | 0.000% | 0.000% | 0.0000 | 1,000,000.00 | 0.00 |
| llm_rag | −0.345% | −0.320% | −1.368% | 0.0019 | 996,547.31 | −3,452.69 |
| llm_graph | −0.345% | −0.320% | −1.368% | 0.0019 | 996,547.31 | −3,452.69 |
| llm_team | −0.345% | −0.320% | −1.368% | 0.0019 | 996,547.31 | −3,452.69 |
| quant_duration | −0.405% | −0.381% | −1.733% | 0.0024 | 995,954.00 | −4,046.00 |
| static_ladder | −0.454% | −0.434% | −1.983% | 0.0027 | 995,456.88 | −4,543.12 |
| llm_market | −0.720% | −0.690% | −1.980% | 0.0025 | 992,802.85 | −7,197.15 |

Every invested strategy's drawdown peaked at observation 21 and troughed at observation 35, with no
recovery by the end of the window. Annualized return is not reported (fewer than 252 returns). Sharpe is unavailable:
no risk-free series is declared (60 daily returns exist). Paired moving-block bootstrap intervals
(block 5, 1,000 resamples, seed 0) of the mean daily difference against `cash` all include zero, for
example `llm_rag` −0.000056 [−0.000496, 0.000373]; they are descriptive, not significance tests.

### Attribution and income (USD)

| Strategy | Carry | Price | Costs | Residual | Coupons | Realized | Unrealized |
|---|---|---|---|---|---|---|---|
| llm_rag / llm_graph / llm_team | 4,619.77 | −7,822.86 | −249.60 | 0.00 | 7,955.50 | −1,092.10 | −4,724.84 |
| quant_duration | 5,294.81 | −9,106.01 | −234.80 | 0.00 | 9,627.25 | −473.74 | −6,226.13 |
| static_ladder | 5,609.20 | −9,946.52 | −205.80 | 0.00 | 10,036.00 | 0.00 | −7,370.96 |
| llm_market | 5,067.15 | −11,969.90 | −294.40 | 0.00 | 7,936.50 | −5,268.54 | −4,745.04 |

Attribution reconciles to total PnL for every strategy (residual 0.00). No redemptions occurred.

## 3. Risk and exposure (actual, not assumed equal)

Equal limits did not produce equal risk. Read return differences against these exposures.

| Strategy | Avg DV01 (USD/bp) | Max DV01 | Avg eff. duration (y) | End duration (y) | Avg cash share | Turnover / avg NAV |
|---|---|---|---|---|---|---|
| cash | 0.00 | 0.00 | 0.00 | 0.00 | 100.0% | 0.00 |
| llm_rag / llm_graph / llm_team | 305.19 | 460.92 | 3.07 | 3.01 | 27.5% | 1.13 |
| llm_market | 368.51 | 460.92 | 3.71 | 4.39 | 19.1% | 1.32 |
| quant_duration | 387.23 | 460.92 | 3.89 | 3.93 | 15.2% | 1.08 |
| static_ladder | 438.27 | 460.92 | 4.41 | 4.38 | 9.6% | 0.95 |

Turnover includes the ~94% bootstrap purchase (initialization-only turnover exemption). Max DV01 is
the post-bootstrap level shared by all invested competitors (cap 600 USD per 1,000,000 NAV). Among
invested strategies, lower average DV01 coincided with smaller losses in this rising-rate window,
except `llm_market`: it shortened on 2024-02-12 and lengthened again on 2024-03-27, realizing
−5,268.54 USD. Lower losses here reflect lower rate exposure, not skill.

## 4. Decisions, costs and execution

| Strategy | Decisions | Proposals (excl. bootstrap) | Fills | Expiries | Policy rejections | Spread cost (USD) |
|---|---|---|---|---|---|---|
| cash | 61 hold | 0 | 0 | 0 | 0 | 0.00 |
| static_ladder | 60 hold, 1 bootstrap | 0 | 5 | 0 | 0 | 205.80 |
| quant_duration | 57 hold, 4 proposals | 3 (2024-01-03, 02-01, 03-01) | 8 | 0 | 0 | 234.80 |
| llm_market | 58 hold, 3 proposals | 2 (2024-02-12 shorten, 03-27 lengthen) | 7 | 0 | 0 | 294.40 |
| llm_rag | 59 hold, 2 proposals | 1 (2024-01-03 shorten) | 6 | 0 | 0 | 249.60 |
| llm_graph | 59 hold, 2 proposals | 1 (2024-01-03 shorten) | 6 | 0 | 0 | 249.60 |
| llm_team | 59 hold, 2 proposals | 1 (2024-01-03 shorten) | 6 | 0 | 0 | 249.60 |

No fees (0.00 USD), no expiries, no rejected orders, no incomplete valuations, no data gaps and no
excluded sessions. Execution costs are reported separately from model costs (§7).

**Execution walk-through (spec §17.6 steps 5–6).** On 2024-01-03 (Dec 2023 minutes released 14:00,
available 16:00 New York) `llm_rag`, `llm_graph` and `llm_team` each proposed shortening to the
reference model's hawkish 3.0-year target. The policy gate passed (turnover 0.190 of NAV); sizing
produced one order: SELL 219,000 face of SYN-USD-NOTE-009. It filled at the 2024-01-04 15:30
observation at a clean price of 85.6473 (model mid minus 0.02), consideration 189,184.51 USD, and
settled on 2024-01-05. `quant_duration` sold 95,000 face of the same note on the same schedule
(drift trigger, duration 4.61y). Details: `walkthrough.json` steps 5–6.

## 5. Failures, abstentions and rejections

**The canonical run has none:** all 427 decisions are `completed_hold` (413) or
`completed_proposal` (14). No failure was forced into it. To show the audit path (spec §17.6 step 8),
the bundle contains a **separately labelled failure-injection run** (`fi-demo-2024q1-faults-r0`,
2024-01-29 → 2024-02-23, 19 sessions, same protocol: capture, then recorded-response replay) with
five declared faults. It is never ranked with the canonical run.

| Fault | Strategy / session | Recorded outcome | Financial consequence |
|---|---|---|---|
| F1 provider outage (team lead) | llm_team, 2024-01-31 | `failed_dependency` (`provider_error:lead:task_assignment`) | no order; portfolio still processed and valued |
| F2 graph outage | llm_graph, 2024-01-31 | `failed_dependency` (`graph_retrieval_unavailable`, `no_fallback_to_hybrid_rag_v1`) | no order; no silent fallback to plain RAG |
| F3 evidence withheld (empty bundle) | llm_rag, 2024-02-21 | `abstained_insufficient_evidence` (`mandatory_retrieval_empty`) | no order |
| F4 policy breach (70% in NOTE-009 after agent validation) | llm_market, 2024-02-21 | `completed_proposal`, then **rejected by the policy gate**: single-security limit, daily turnover cap, unfundable purchases | no order created |
| F5 specialist outage (macro researcher) | llm_team, 2024-02-21 | `completed_hold`; specialist task `failed` with the provider error | contained by design: the lead synthesized without it |

All other competitors on those sessions completed normally. Audit trails (decision, attempts, tool
traces, specialist tasks, validation, policy gate, financial commands of the session) are in
`failure-injection/audit/F*.json`; the run's own report is `failure-injection/report/report.md`.

## 6. Evidence

Retrieval used the default offline index `ib-c5ff36b8d6d057e4ab95` (FOMC statements and minutes,
synthetic correction excluded) with the fixed query template `policy-outlook-v1`.

| Strategy | Bundles | Delivered passages | Graph-added (not hybrid candidates) | Distinct documents | Temporal violations | Claims (valid) |
|---|---|---|---|---|---|---|
| llm_rag | 60 | 360 | 0 | 7 | 0 | 180 (180) |
| llm_graph | 120 | 1,080 | 0 | 10 | 0 | 180 (180) |
| llm_team | 60 | 360 | 0 | 5 | 0 | 180 (180) |

All 60 research notes per evidence strategy were `supported`, and every validation step (schema,
citation membership, quote offsets, temporal, calculation references, support, policy) passed on all
60 decisions with model calls; all 180 cited claims per strategy were valid. Across the 60 decision days with retrieval, RAG and Graph RAG
never delivered identical passage sets (mean Jaccard 0.227).

### Policy-document events (spec §17.6 steps 3–4)

| Event (available, New York) | RAG passages | Graph passages | Common | Graph only | Event document delivered (rag / graph / team) | Same decision |
|---|---|---|---|---|---|---|
| 2024-01-03 Dec 2023 minutes | 6 | 18 | 5 | 13 | yes / yes / yes | yes (all REBALANCE) |
| 2024-01-31 statement | 6 | 18 | 4 | 14 | no / no / no | yes (HOLD) |
| 2024-02-21 Jan 2024 minutes | 6 | 18 | 4 | 14 | no / **yes** / no | yes (HOLD) |
| 2024-03-20 statement | 6 | 18 | 5 | 13 | no / no / no | yes (HOLD) |

"Graph only" passages reached `llm_graph` through its graph-mode retrieval and its
`expand_evidence_graph` call. Their provenance shows they were also among the hybrid candidates
(`addedByGraph=false`), so the strict graph-added count is 0 for every event. Per-passage seeds,
assertion paths and support spans are in `evidence/<event>.json` and `.md`.

**Findings.** (1) Graph RAG delivered more and different evidence but never changed a decision:
`llm_rag`, `llm_graph` and `llm_team` produced identical decisions on all 61 sessions. Hypotheses H2
(graph) and H3 (delegation) are therefore not supported in this window under the reference model; H1
(retrieval vs market-only) shows different decisions (dates, direction) and exposures. (2) The two 2024
statements were never among the delivered passages on their release days. This comes from the
strategies' fixed research-question template, not from temporal filtering: the template asks a
general rates/inflation question, and lexical ranking then favours long 2023 minutes sections. A
statement-specific question at the same cutoff (2024-01-31 19:00 America/New_York) retrieves the
31 January 2024 statement as the top passage in both `hybrid_rag_v1` and `graph_rag_v1`. Because
spec §12.3 forbids LLM query expansion in initial experiments, a hosted-model run with the same
template would inherit this limitation; an event-aware question template is a separately
registered retrieval experiment.

## 7. Usage and model cost (separate from execution costs)

Token counts are the reference provider's estimates (`estimate_tokens`), not provider-billed tokens.
Model cost is 0.000000 USD under the zero-cost price schedule for provider `reference`. The bootstrap
day uses no model call.

| Strategy | Generation calls | Tool calls | Evidence calls | Input tokens | Output tokens | Max calls / decision | Budget exhausted |
|---|---|---|---|---|---|---|---|
| llm_market | 120 | 240 | 0 | 344,582 | 28,714 | 2 | never |
| llm_rag | 120 | 300 | 60 | 1,084,781 | 75,452 | 2 | never |
| llm_graph | 120 | 360 | 120 | 1,459,477 | 78,740 | 2 | never |
| llm_team | 300 | 300 | 60 | 1,560,587 | 151,805 | 5 | never |

Equal ceilings did not mean equal realized compute: `llm_team` used 2.5× the generation calls of the
single agents, and `llm_graph` twice the evidence calls of `llm_rag`.

## 8. Completeness

427/427 decisions recorded (61 sessions × 7 competitors); 875 committed transitions; 0 data gaps;
0 exclusions; 0 run failures; 0 incomplete valuations. Verification replays the run with every
provider disabled and reproduces all StrategyResults, all transitions, the final state hashes, the
checkpoint, this report's metrics and the four evidence comparisons; a stored-results replay
reproduces the same transitions without calling any strategy.

## 9. Limitations (spec §16.2, §21)

- **Synthetic, not observed.** SYN-USD-NOTE-* instruments are hypothetical; marks and fills come
  from the same curve model plus a declared half-spread. Relative value is mechanically neutral.
  Nothing here supports claims about real Treasury mispricing or achievable execution.
- **Retrospective information policy.** Availability is reconstructed (publication + 120 min for
  FOMC text, 18:00 for curves). This is a historical replay, not a forward paper test. FOMC pages
  are 2026 web versions (`current_web_version_not_archived_original`), not archived originals.
- **Pretrained-model hindsight.** Not applicable to `reference-heuristic-v1` (a rule-based model
  with no pretrained knowledge). It does apply to any hosted LLM run on this window. Such runs must
  be labelled retrospective and repeated forward.
- **Not an LLM result.** The AI strategies measure plumbing, evidence access, validation and policy
  behaviour, not LLM reasoning. Model aliases, pinned identifiers and provider drift do not apply.
- **Data gaps.** None in the window. 29 March 2024 is a calendar holiday, not a gap.
- **Actual exposure differences.** Average DV01 ranged from 305 to 438 USD/bp across invested
  strategies (§3). Return differences mostly reflect rate exposure in a rising-rate quarter.
- **No statistical significance.** 61 sessions, one repetition, overlapping holdings. Intervals are
  descriptive; Sharpe is unavailable (no risk-free series).
- **Costs are assumptions.** Half-spreads are illustrative, not measured; see
  [cost-sensitivity.md](cost-sensitivity.md).
- **Not a held-out result.** See the [methodology card](methodology-card.md) and trial registry.

## 10. Bundle contents

`definition.json`, `bundle.json` (checksums, expected hashes), `responses/` (660 recorded
responses), `capture/`, `run/` (`outcomes.jsonl`, `commits.jsonl.gz`, `checkpoint.json`,
`manifest.json`, `config.json`), `report/`, `evidence/` (4 events), `walkthrough.json`,
`failure-injection/`, `sensitivity/`. Size about 8.6 MB. Only synthetic instruments, U.S. Treasury
par yields and Federal Reserve FOMC text excerpts (U.S. government works) plus reference-model
outputs are included.
