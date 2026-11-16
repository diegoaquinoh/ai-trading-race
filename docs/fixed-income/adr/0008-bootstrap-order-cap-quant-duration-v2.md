# ADR 0008 — Common bootstrap capped by max orders per decision; quant-duration-v2 two-step rotation

- **Status:** Accepted
- **Date:** 2026-11-08
- **Spec:** §9.3 (maximum orders per decision: 6), §9.4 (funding rule), §10.1

## Context

The passive bootstrap (30% short / 34% intermediate / 30% longer / 6% cash) originally bought every
eligible note in a bucket, which could exceed the six-orders-per-decision control. The turnover
exemption for initialization covers turnover only, not order count. Separately, the settled-cash
funding rule means sale proceeds cannot fund same-decision purchases, so a duration-lengthening
rotation could never complete in one decision.

## Decision

- Bootstrap `bootstrap-30-34-30-6-v2`: each bucket holds at most `max_orders_per_decision // 3`
  instruments (minimum one), chosen by remaining maturity closest to the bucket's representative
  tenor (2y/5y/10y) with a security-id tie break; weights floored to 6 decimals, remainder to cash.
  It is identical for every invested competitor; an empty bucket fails initialization for all.
- `quant-duration-v2`: one decision either sells (longest duration first) or buys with settled cash,
  never both. When duration is below target and no cash-funded purchase is possible, it performs
  stage 1 of a two-step rotation (sell shortest-duration holdings to cash); a later drift-band
  decision buys once proceeds have settled.

## Consequences

- In the demo window the bootstrap holds five notes plus 6% cash (see
  `fixtures/demo/fi-demo-2024q1/run/manifest.json`, `bootstrapAllocation`).
- Changing either rule is a new strategy/config version and a new trial.
