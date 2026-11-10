# ADR 0002 — Canonical Python numerical/simulation engine; .NET transactional authority

- **Status:** Accepted
- **Date:** 2026-11-05
- **Spec:** §1.1, §5.1–5.3, §9.5

## Context

Pricing, accrual, curve building, risk and ledger transitions must be identical in notebooks,
offline replay and the application. Maintaining two numerical implementations (C# and Python) would
drift. At the same time, portfolio state must be committed with authorization, optimistic concurrency
and audit in SQL.

## Decision

- `research_engine` (Python, QuantLib 1.44 behind an application wrapper) is the only implementation of
  schedules, curves, pricing, risk, scenarios, fills, posting templates and state transitions.
- It returns signed `TransitionProposal`s (inputs hashed, journals balanced, next state hashed). It
  never writes application-owned portfolio, order or ledger rows.
- .NET verifies schema, identity, hashes, engine version, signature and policy, checks the expected
  portfolio version and commits in one SQL transaction with a unique logical command id. It never
  prices, accrues or computes risk.
- Offline research applies the same proposals through `OfflineStateStore`, which mirrors the .NET
  checks. Parity fixtures (`contracts/fixtures/parity/`) prove the two paths produce the same
  transitions.

## Consequences

- A Python outage blocks new transitions in application mode; committed state stays authoritative.
- QuantLib's global evaluation date is isolated per calculation (serialized access); see
  `docs/fixed-income/numerical-methods.md`.
- Any numerical change is a Python change plus re-exported parity fixtures.
