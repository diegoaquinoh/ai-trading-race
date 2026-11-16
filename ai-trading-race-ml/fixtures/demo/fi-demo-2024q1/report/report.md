# Replay report — fi-demo-2024q1-r0

**Data mode:** SYNTHETIC CURVE SIMULATION (model prices, not market quotes)  
**Status:** completed · **Response mode:** recorded_replay (recorded_provider_responses)  
**Window:** 2024-01-02 → 2024-03-29 (61 sessions)  
**Execution model:** synthetic-half-spread-0.02-v1 · **Risk policy:** treasury-long-only-v1  
**Manifest:** `sha256:ace347a44774018261cca1c54b9a4c82e17cbb4272fc84dff1f9abb005964641` (verified: True)

## Results (ranked within this compatibility group only)

| Strategy | Net return | Gross return | Max drawdown | Fills | Expiries | Rejections | Avg DV01 | End duration | Costs (USD) |
|---|---|---|---|---|---|---|---|---|---|
| cash | 0.000% | 0.000% | 0.000% | 0 | 0 | 0 | 0.0000 | 0.0000 | 0 spread + 0 fees |
| llm_graph | -0.345% | -0.320% | -1.368% | 6 | 0 | 0 | 305.1928 | 3.0084 | 249.60 spread + 0.00 fees |
| llm_rag | -0.345% | -0.320% | -1.368% | 6 | 0 | 0 | 305.1928 | 3.0084 | 249.60 spread + 0.00 fees |
| llm_team | -0.345% | -0.320% | -1.368% | 6 | 0 | 0 | 305.1928 | 3.0084 | 249.60 spread + 0.00 fees |
| quant_duration | -0.405% | -0.381% | -1.733% | 8 | 0 | 0 | 387.2293 | 3.9320 | 234.80 spread + 0.00 fees |
| static_ladder | -0.454% | -0.434% | -1.983% | 5 | 0 | 0 | 438.2720 | 4.3751 | 205.80 spread + 0.00 fees |
| llm_market | -0.720% | -0.690% | -1.980% | 7 | 0 | 0 | 368.5095 | 4.3931 | 294.40 spread + 0.00 fees |

## Decisions, failures and exclusions

- **cash**: 61 decisions {'completed_hold': 61}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 0.00, price 0.00, costs 0, residual 0.00 (total 0.00)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_graph**: 61 decisions {'completed_proposal': 2, 'completed_hold': 59}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 4619.77, price -7822.86, costs -249.60, residual 0.00 (total -3452.69)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_rag**: 61 decisions {'completed_proposal': 2, 'completed_hold': 59}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 4619.77, price -7822.86, costs -249.60, residual 0.00 (total -3452.69)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_team**: 61 decisions {'completed_proposal': 2, 'completed_hold': 59}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 4619.77, price -7822.86, costs -249.60, residual 0.00 (total -3452.69)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **quant_duration**: 61 decisions {'completed_proposal': 4, 'completed_hold': 57}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 5294.81, price -9106.01, costs -234.80, residual 0.00 (total -4046.00)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **static_ladder**: 61 decisions {'completed_proposal': 1, 'completed_hold': 60}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 5609.20, price -9946.52, costs -205.80, residual 0.00 (total -4543.12)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_market**: 61 decisions {'completed_proposal': 3, 'completed_hold': 58}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 5067.15, price -11969.90, costs -294.40, residual 0.00 (total -7197.15)
  - Sharpe: n/a (unavailable: missing_risk_free_series)

## Paired comparisons (block bootstrap; not significance claims)

- llm_graph vs cash: mean daily diff -0.000056 [-0.000496, 0.000373] (block 5)
- llm_market vs cash: mean daily diff -0.000117 [-0.000699, 0.000413] (block 5)
- llm_rag vs cash: mean daily diff -0.000056 [-0.000496, 0.000373] (block 5)
- llm_team vs cash: mean daily diff -0.000056 [-0.000496, 0.000373] (block 5)
- quant_duration vs cash: mean daily diff -0.000065 [-0.000637, 0.000467] (block 5)
- static_ladder vs cash: mean daily diff -0.000072 [-0.000731, 0.000527] (block 5)

## Limitations

- Synthetic instruments priced from curve inputs; execution prices are model observations plus declared half-spread, not market quotes.
- Same-curve marks and fills: any rich/cheap signal is mechanically neutral.
- Spread assumptions (0.00/0.02/0.05 per 100 face) are illustrative, not measured costs.
- Daily-only data: fills are labelled next-session close observations.
- Short replays do not support statistical significance claims.
- Retrospective LLM runs may reflect pretrained knowledge of later events.
- Cash earns the configured cash return only (fixture: zero).

## Demo extension (canonical recorded-response replay)

AI strategies ran on provider reference / reference-heuristic-v1, a deterministic rule-based policy model. It is not a hosted LLM.

| Strategy | Response source | Proposals | Generation calls | Tool calls | Evidence calls | Input tokens | Output tokens | Model cost (USD) |
|---|---|---|---|---|---|---|---|---|
| cash | deterministic_code | - | 0 | 0 | 0 | 0 | 0 | n/a |
| llm_graph | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 1} | 120 | 360 | 120 | 1459477 | 78740 | 0.000000 |
| llm_market | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 2} | 120 | 240 | 0 | 344582 | 28714 | 0.000000 |
| llm_rag | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 1} | 120 | 300 | 60 | 1084781 | 75452 | 0.000000 |
| llm_team | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 1} | 300 | 300 | 60 | 1560587 | 151805 | 0.000000 |
| quant_duration | deterministic_code | {'BOOTSTRAP': 1, 'REBALANCE': 3} | 0 | 0 | 0 | 0 | 0 | n/a |
| static_ladder | deterministic_code | {'BOOTSTRAP': 1} | 0 | 0 | 0 | 0 | 0 | n/a |

### Evidence

- **llm_graph**: 120 bundles, 1080 delivered passages (0 added by graph traversal) from 10 documents; temporal violations 0; claims {'valid': 180}; note statuses {'supported': 60}.
- **llm_rag**: 60 bundles, 360 delivered passages (0 added by graph traversal) from 7 documents; temporal violations 0; claims {'valid': 180}; note statuses {'supported': 60}.
- **llm_team**: 60 bundles, 360 delivered passages (0 added by graph traversal) from 5 documents; temporal violations 0; claims {'valid': 180}; note statuses {'supported': 60}.

RAG vs Graph RAG passages: 60 sessions compared, 0 identical, mean Jaccard 0.2274.

### Completeness

427/427 decisions recorded; outcomes {'completed_hold': 413, 'completed_proposal': 14}; data gaps none; exclusions none; incomplete valuations 0.

### Demo limitations

- Synthetic-curve mode: SYN-USD-NOTE-* instruments are hypothetical; marks and fills are curve-model observations plus a declared half-spread, not market quotes. The run shows nothing about observed-security relative value or achievable execution.
- Same curve for marks and fills: any rich/cheap signal is mechanically neutral.
- Retrospective information policy: document availability is reconstructed (publication time + 120 minutes) and curve availability is 18:00 New York; this is a historical replay, not a forward paper-trading test.
- Pretrained-model hindsight: not applicable to reference-heuristic-v1 (a rule-based model with no pretrained knowledge), but it applies to any hosted LLM run on this window; such runs must be labelled retrospective and repeated forward.
- AI strategies ran on reference-heuristic-v1, a deterministic rule-based policy model, not a hosted LLM; the results say nothing about LLM decision quality.
- Stochastic repetitions are not applicable to the deterministic reference model; hosted models need at least three repetitions when affordable (spec 16.2).
- Short window (61 sessions, 60 daily returns): no statistical significance; paired block-bootstrap intervals are descriptive only; Sharpe ratios are unavailable because no risk-free series is declared.
- Exposures differ: equal risk limits did not produce equal duration/DV01; compare the exposure section before reading return differences.
- Cash earns zero (zero_cash_interest_v1); excess returns are not interpreted.
- Half-spread assumptions (0.00/0.02/0.05 per 100 face) are illustrative, not measured Treasury transaction costs.
- Evidence pages are 2026 web versions of the FOMC releases (flag current_web_version_not_archived_original), not archived originals.
