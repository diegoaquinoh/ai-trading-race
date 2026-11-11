# Cost sensitivity — half-spreads 0.00 / 0.02 / 0.05 (`fi-demo-2024q1-cost`)

> The AI strategies ran on **`reference-heuristic-v1`**, a deterministic rule-based model, **not a
> hosted LLM**. Instruments are synthetic and fills are curve-model prices plus the half-spread under
> test. The half-spreads are **illustrative assumptions (spec §9.4), not measured Treasury
> transaction costs**.

Three reruns of the demo experiment (same window, competitors, bootstrap, risk policy and budgets)
differ only in `ExecutionModel.half_spread_per_100`. They ran on 2026-11-10 as `fresh_inference` of
the reference model (no recording; `responseSource: fresh_provider_calls`) inside
`fi-research demo build`. Manifests and reports are in
`ai-trading-race-ml/fixtures/demo/fi-demo-2024q1/sensitivity/half-spread-*/`; the table below is
`sensitivity/summary.json`.

| Run id | Profile |
|---|---|
| `fi-demo-2024q1-cost-hs000-r0` | `synthetic-half-spread-0.00-v1` |
| `fi-demo-2024q1-cost-hs002-r0` | `synthetic-half-spread-0.02-v1` (the demo default) |
| `fi-demo-2024q1-cost-hs005-r0` | `synthetic-half-spread-0.05-v1` |

All three runs completed with the same decision outcomes (413 holds, 14 proposals) and the same
fill counts per strategy.

## Net return and spread cost

| Strategy | Fills | Net @ 0.00 | Net @ 0.02 | Net @ 0.05 | Spread cost @ 0.02 (USD) | Spread cost @ 0.05 (USD) |
|---|---|---|---|---|---|---|
| cash | 0 | 0.000% | 0.000% | 0.000% | 0.00 | 0.00 |
| llm_rag / llm_graph / llm_team | 6 | −0.320% | −0.345% | −0.383% | 249.60 | 624.00 |
| quant_duration | 8 | −0.381% | −0.405% | −0.440% | 234.80 | 587.00 |
| static_ladder | 5 | −0.434% | −0.454% | −0.485% | 205.80 | 514.50 |
| llm_market | 7 | −0.690% | −0.720% | −0.764% | 294.40 | 735.50 |

Exact values (fraction of starting NAV), from `sensitivity/summary.json`:

| Strategy | 0.00 | 0.02 | 0.05 |
|---|---|---|---|
| llm_rag / llm_graph / llm_team | −0.00320309 | −0.00345269 | −0.00382709 |
| quant_duration | −0.00381213 | −0.00404600 | −0.00439820 |
| static_ladder | −0.00433732 | −0.00454312 | −0.00485182 |
| llm_market | −0.00690278 | −0.00719715 | −0.00763821 |

## Observations

- The ranking inside this compatibility group is the same at every half-spread. The differences
  between strategies (about 0.37 percentage points between the evidence agents and `llm_market`)
  are larger than the cost effect of moving from 0.00 to 0.05 (at most 0.074 percentage points, for
  `llm_market`).
- Spread cost scales almost linearly with the half-spread (0.05/0.02 = 2.5; 624.00/249.60 = 2.5),
  because traded face is fixed at submission and decisions did not change.
- Small second-order effects exist: cash balances differ slightly with costs, so sizing differs
  slightly. Average DV01 moved from 387.23 (0.02) to 387.38 (0.00) for `quant_duration`, and from
  368.51 (0.02) to 368.50 (0.05) for `llm_market`.
- **Consistency check:** the 0.02 rerun (fresh inference of the reference model) reproduces the
  canonical recorded-response replay exactly (same net returns, costs and fills).
- Most turnover is the common ~94% bootstrap, so a large share of each invested strategy's cost
  comes from initialization, identical across invested competitors.

## Limitations

Spread assumptions are not observed bid/ask; no depth, impact or capacity is modelled; fills are
next-session close observations on daily data. A short window with few trades cannot separate cost
sensitivity from decision timing. See [demo-experiment.md](demo-experiment.md) §9 for the full list.
