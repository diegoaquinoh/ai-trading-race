# ADR 0004 — Synthetic-curve mode first; observed-security mode gated

- **Status:** Accepted
- **Date:** 2026-11-05
- **Spec:** §1.1, §3.2–3.3, §7.3, §8.4, §21

## Context

No licensed or otherwise permitted source of security-level historical Treasury quotes has been
selected. The U.S. Treasury daily par yield curve is public but is derived from indicative bid-side
quotations and is not an execution feed.

## Decision

- Initial data mode is `synthetic_curve`: hypothetical instruments `SYN-USD-NOTE-001…` (universe
  `synthetic-universe-v1`) priced from curves bootstrapped from Treasury par yields
  (`usd-treasury-par-2023-2024`). Execution prices are curve-model prices plus a declared
  half-spread; they are labelled as model observations, never market quotes.
- Relative-value output in this mode is `mechanically_neutral`; no rich/cheap signal is
  manufactured from the same-curve identity.
- `observed_security` mode exists as contracts, quote validation and a data-admission gate
  (`market/admission.py`) but no quote adapter is admitted. M8 is not delivered.
- Reports, manifests and compatibility keys carry the data mode; runs of different modes are never
  ranked together.

## Consequences

- The platform can test pipeline correctness, risk management, evidence quality and exposure
  decisions, but it cannot support claims about actual mispricing or achievable execution.
- Selecting a quote provider (rights, coverage, timestamps) is the precondition for M8.
