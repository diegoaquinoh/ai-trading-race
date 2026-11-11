# ADR 0003 — Contract-first canonical JSON with HMAC-signed proposals and results

- **Status:** Accepted
- **Date:** 2026-11-05
- **Spec:** §14.1, §14.5, §5.3

## Context

Two runtimes exchange financial state. Results must be bound to the exact inputs that produced them
and must not be forgeable by anything that can only produce text (for example a model).

## Decision

- Pydantic models in `research_engine/contracts/` are the source of truth. JSON Schemas and canonical
  JSON test vectors are exported to `contracts/schemas/v1/` and `contracts/test-vectors/`
  (`python -m research_engine.contracts.export`) and consumed by .NET contract tests.
- Wire format: camelCase, decimal strings, UTC `Z` instants, ISO dates; floats rejected in hashed
  payloads.
- Hash: `sha256:` over canonical JSON (sorted keys, compact separators, ASCII escaping).
  Signature: HMAC-SHA256 over the hash string. `TransitionProposal` and `StrategyResult` are signed
  with the key shared between `ML_SERVICE_SIGNING_KEY` and `ResearchEngine__SigningKey`; calculation
  results with the Python-only `RESEARCH_SIGNING_KEY`.
- Fixtures (parity, recorded demo) use published, non-secret fixture keys so anyone can reproduce
  them; those keys are never valid in application mode.

## Consequences

- Additive schema changes keep `schema_version` major `1`; unknown majors are rejected.
- Adding `CalculationType.MARKET_FEATURES` (2026-11) did not change any exported schema.
- Key rotation re-signs nothing retroactively; committed rows keep their verified hashes.
