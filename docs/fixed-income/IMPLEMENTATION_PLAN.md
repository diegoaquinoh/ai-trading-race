# Fixed Income Research Lab — Implementation Plan

Implements [`docs/FIXED_INCOME_PLATFORM_SPEC.md`](../FIXED_INCOME_PLATFORM_SPEC.md) (v1.0).
Scope delivered here: milestones **M0–M7** in synthetic-curve mode, plus the
observed-security admission *gates* (M8 data acquisition is out of scope until a
quote provider is selected — spec §21) and forward-cycle scheduling (M9 without
intraday execution).

## Ground rules

- Additive and reversible: legacy crypto tables, endpoints, `/predict` and the
  five-minute market cycle keep working. New .NET tables live in SQL schema `fi`.
- One numerical/accounting implementation: Python `research_engine`. .NET verifies
  and commits; it never prices, accrues or computes risk.
- Contract-first: `research_engine/contracts/` (Pydantic) is the source of truth;
  JSON Schemas and canonical-JSON test vectors are exported to `contracts/` at the
  repo root and consumed by .NET contract tests.
- Wire format: camelCase JSON, decimal strings, UTC `Z` instants, ISO dates.
  Hashes: `sha256:` over canonical JSON. Signatures: HMAC-SHA256 over the hash.
- No live LLM credentials are assumed. Provider clients exist and are tested with
  mocked transports; demo runs use *recorded responses* from a deterministic,
  clearly labelled reference policy model (`reference-heuristic-v1`), never
  presented as a hosted LLM.

## Workstreams and ownership

| WS | Owner area | Paths | Milestone |
|---|---|---|---|
| A | Numerical core: terms, calendars, curves, pricing, risk, scenarios, market adapters, data admission | `research_engine/{instruments,market,pricing,risk}`, `contracts/{instruments,market,calculations}.py`, `tests/numerical` | M1 |
| B | Evidence: source registry, Fed adapters, versions, chunks; knowledge graph; hybrid + graph retrieval; benchmark | `research_engine/{evidence,knowledge,retrieval}`, `contracts/evidence.py`, `tests/evidence`, `fixtures/evidence` | M4, M5 |
| C | Simulation: event ordering, ledger posting templates, fills, settlement, coupons, sizing, policy, valuation, baselines, offline replay, manifests, metrics | `research_engine/{simulation,experiments}`, `tests/simulation` | M2 |
| D | .NET: `fi` schema, commit protocol, idempotency, public `/api/v1`, research-engine client, Functions orchestration, parity test | `AiTradingRace.*` (FixedIncome folders) | M2, M7 |
| E | Agents: providers, budget ledger, typed tools, llm_market/rag/graph/team, validation pipeline, recorded responses | `research_engine/agents`, `tests/agents` | M3, M6 |
| F | Dashboard: experiments, run replay, instrument, portfolio, decision, evidence explorer, health | `ai-trading-race-web/src/fi` | M7 |
| G | Experiments & docs: demo bundle, reports, benchmark evaluation, ADRs, operations guide, README | `research_engine/experiments`, `docs/fixed-income`, `fixtures/demo` | M7 |

Waves: **1** = A, B, C, D (parallel, contract-first) → **2** = E, F, D-integration →
**3** = G, end-to-end verification, review.

## Key interfaces

- `contracts/portfolio.py` — `PortfolioState`, events (priority table
  `event-priority-v1`), `Journal`, `RiskPolicy`, `ExecutionModel`,
  `TransitionRequest`, `TransitionProposal`, `PolicyEvaluation`, `ValuationSnapshot`.
- `contracts/decisions.py` — `DecisionRequest`, `StrategyResult`, research note,
  citations, attempts, tool traces, usage, outcomes.
- `simulation/ports.py` — `PricingPort`, `MarketDataPort` (numerical core implements).
- Internal HTTP (Python, API-key auth): `/internal/v1/{analytics/price, analytics/risk,
  simulation/transitions, strategies/decisions, evidence/retrieve, capabilities}`.
- Public HTTP (.NET): `/api/v1/...` per spec §14.2.

## Daily chronology (proposed platform schedule)

Curve observation 15:30 America/New_York → reconstructed availability 18:00 →
decision 19:00 → orders fill against the **next** session's observation → T+1
settlement on the U.S. government-bond calendar.

## Verification

- Python: `cd ai-trading-race-ml && .venv/bin/python -m pytest` (numerical,
  temporal, simulation, evidence, agent, contract suites).
- .NET: `make test-backend` (includes commit-protocol and parity tests).
- Frontend: `make test-frontend`.
- Demo: `fi-research demo build` then `fi-research demo verify`.
