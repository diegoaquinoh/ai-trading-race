# ADR 0006 — Reference heuristic provider and recorded responses (no live LLM credentials)

- **Status:** Accepted
- **Date:** 2026-11-07
- **Spec:** §6.5, §10, §15.4, §16.2, §17.6

## Context

No hosted LLM credentials are available to this project. The agent workflow (tools, retrieval,
budgets, validation, policy, audit) still has to run end to end, and the demo must replay without
provider access.

## Decision

- Provider `reference` (model `reference-heuristic-v1`) is a deterministic, rule-based policy model:
  lexicon stance counts over delivered passages, a market-only rule on the 2Y yield change, exact
  quotes, calculation ids from tools. It is reported as provider `reference` everywhere and is never
  presented as a hosted LLM.
- Hosted clients (`anthropic`, `openai`/OpenAI-compatible) exist and are tested only against mocked
  transports. Priced runs require a versioned price schedule and a monetary ceiling.
- Recorded responses (`recorded-responses-v1`) are keyed by a fingerprint of decision id, role,
  purpose, prompt version and the exact messages; a changed request fails with `RecordingMissing`.
- Response modes are separate (spec §6.5): `fresh_inference`; `recorded_replay` with
  `replay_source=recorded_responses` (strategies re-run on replay-only providers); and
  `recorded_replay` with `replay_source=stored_results` (persisted StrategyResults reused). The
  runner refuses a replay provider in `fresh_inference` and a live provider in provider-level
  replay, and manifests carry `responseSource` per run and per strategy.

## Consequences

- Strategy comparisons in this delivery measure plumbing, evidence access and policy behaviour, not
  LLM reasoning. Every report says so.
- Stochastic repetitions do not apply to the reference model; hosted runs need ≥ 3 repetitions.
- Pretrained-model hindsight does not apply to the reference model but applies to any hosted run on
  historical windows.
