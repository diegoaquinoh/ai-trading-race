# Replay report — fi-demo-2024q1-faults-r0

**Data mode:** SYNTHETIC CURVE SIMULATION (model prices, not market quotes)  
**Status:** completed · **Response mode:** recorded_replay (recorded_provider_responses)  
**Window:** 2024-01-29 → 2024-02-23 (19 sessions)  
**Execution model:** synthetic-half-spread-0.02-v1 · **Risk policy:** treasury-long-only-v1  
**Manifest:** `sha256:1697731678077e63e3dd5dbcf486af285b256cb07605c67aa9574b4540e5429c` (verified: True)

## Results (ranked within this compatibility group only)

| Strategy | Net return | Gross return | Max drawdown | Fills | Expiries | Rejections | Avg DV01 | End duration | Costs (USD) |
|---|---|---|---|---|---|---|---|---|---|
| cash | 0.000% | 0.000% | 0.000% | 0 | 0 | 0 | 0.0000 | 0.0000 | 0 spread + 0 fees |
| llm_graph | -0.525% | -0.500% | -1.360% | 6 | 0 | 0 | 298.8863 | 3.0527 | 250.00 spread + 0.00 fees |
| llm_rag | -0.525% | -0.500% | -1.360% | 6 | 0 | 0 | 298.8863 | 3.0527 | 250.00 spread + 0.00 fees |
| llm_team | -0.525% | -0.500% | -1.360% | 6 | 0 | 0 | 298.8863 | 3.0527 | 250.00 spread + 0.00 fees |
| quant_duration | -0.748% | -0.726% | -1.748% | 6 | 0 | 0 | 376.4442 | 3.9243 | 222.40 spread + 0.00 fees |
| static_ladder | -0.883% | -0.862% | -1.981% | 5 | 0 | 0 | 423.0916 | 4.4504 | 205.80 spread + 0.00 fees |
| llm_market | -0.977% | -0.952% | -1.979% | 6 | 0 | 1 | 365.2621 | 3.0667 | 250.00 spread + 0.00 fees |

## Decisions, failures and exclusions

- **cash**: 19 decisions {'completed_hold': 19}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 0.00, price 0.00, costs 0, residual 0.00 (total 0.00)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_graph**: 19 decisions {'completed_proposal': 2, 'failed_dependency': 1, 'completed_hold': 16}; 1 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 1368.82, price -6368.78, costs -250.00, residual 0.00 (total -5249.96)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_rag**: 19 decisions {'completed_proposal': 2, 'completed_hold': 16, 'abstained_insufficient_evidence': 1}; 1 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 1368.82, price -6368.78, costs -250.00, residual 0.00 (total -5249.96)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_team**: 19 decisions {'completed_proposal': 2, 'failed_dependency': 1, 'completed_hold': 16}; 1 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 1368.82, price -6368.78, costs -250.00, residual 0.00 (total -5249.96)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **quant_duration**: 19 decisions {'completed_proposal': 2, 'completed_hold': 17}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 1547.81, price -8808.05, costs -222.40, residual 0.00 (total -7482.64)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **static_ladder**: 19 decisions {'completed_proposal': 1, 'completed_hold': 18}; 0 failed/skipped; 0 rejected proposals; 0 missing.
  - Attribution: carry 1655.46, price -10275.14, costs -205.80, residual 0.00 (total -8825.48)
  - Sharpe: n/a (unavailable: missing_risk_free_series)
- **llm_market**: 19 decisions {'completed_proposal': 3, 'completed_hold': 16}; 0 failed/skipped; 1 rejected proposals; 0 missing.
  - Attribution: carry 1517.16, price -11032.89, costs -250.00, residual 0.00 (total -9765.73)
  - Sharpe: n/a (unavailable: missing_risk_free_series)

## Paired comparisons (block bootstrap; not significance claims)

- llm_graph vs cash: mean daily diff -0.000289 [-0.001180, 0.000055] (block 5)
- llm_market vs cash: mean daily diff -0.000539 [-0.001758, 0.000006] (block 5)
- llm_rag vs cash: mean daily diff -0.000289 [-0.001180, 0.000055] (block 5)
- llm_team vs cash: mean daily diff -0.000289 [-0.001180, 0.000055] (block 5)
- quant_duration vs cash: mean daily diff -0.000412 [-0.001522, 0.000013] (block 5)
- static_ladder vs cash: mean daily diff -0.000486 [-0.001737, -0.000010] (block 5)

## Limitations

- Synthetic instruments priced from curve inputs; execution prices are model observations plus declared half-spread, not market quotes.
- Same-curve marks and fills: any rich/cheap signal is mechanically neutral.
- Spread assumptions (0.00/0.02/0.05 per 100 face) are illustrative, not measured costs.
- Daily-only data: fills are labelled next-session close observations.
- Short replays do not support statistical significance claims.
- Retrospective LLM runs may reflect pretrained knowledge of later events.
- Cash earns the configured cash return only (fixture: zero).

## Demo extension (FAILURE INJECTION run (declared faults; not comparable with the canonical run))

AI strategies ran on provider reference / reference-heuristic-v1, a deterministic rule-based policy model. It is not a hosted LLM.

| Strategy | Response source | Proposals | Generation calls | Tool calls | Evidence calls | Input tokens | Output tokens | Model cost (USD) |
|---|---|---|---|---|---|---|---|---|
| cash | deterministic_code | - | 0 | 0 | 0 | 0 | 0 | n/a |
| llm_graph | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 1} | 34 | 105 | 35 | 411912 | 22486 | 0.000000 |
| llm_market | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 2} | 36 | 72 | 0 | 103557 | 8833 | 0.000000 |
| llm_rag | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 1} | 34 | 88 | 18 | 307281 | 21418 | 0.000000 |
| llm_team | recorded_responses:reference/reference-heuristic-v1 | {'BOOTSTRAP': 1, 'REBALANCE': 1} | 86 | 88 | 18 | 433875 | 42296 | 0.000000 |
| quant_duration | deterministic_code | {'BOOTSTRAP': 1, 'REBALANCE': 1} | 0 | 0 | 0 | 0 | 0 | n/a |
| static_ladder | deterministic_code | {'BOOTSTRAP': 1} | 0 | 0 | 0 | 0 | 0 | n/a |

### Evidence

- **llm_graph**: 34 bundles, 306 delivered passages (0 added by graph traversal) from 10 documents; temporal violations 0; claims {'valid': 51}; note statuses {'supported': 17}.
- **llm_rag**: 18 bundles, 102 delivered passages (0 added by graph traversal) from 7 documents; temporal violations 0; claims {'valid': 51}; note statuses {'insufficient_evidence': 1, 'supported': 17}.
- **llm_team**: 18 bundles, 108 delivered passages (0 added by graph traversal) from 5 documents; temporal violations 0; claims {'valid': 51}; note statuses {'supported': 17}.

RAG vs Graph RAG passages: 18 sessions compared, 0 identical, mean Jaccard 0.1813.

### Completeness

133/133 decisions recorded; outcomes {'abstained_insufficient_evidence': 1, 'completed_hold': 118, 'completed_proposal': 12, 'failed_dependency': 2}; data gaps none; exclusions none; incomplete valuations 0.

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
