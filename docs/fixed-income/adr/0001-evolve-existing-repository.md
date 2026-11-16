# ADR 0001 — Evolve the existing repository

- **Status:** Accepted
- **Date:** 2026-11-05
- **Spec:** §1.1 (application foundation), §4 (migration boundaries)

## Context

The repository already contained a working .NET 8 API, an Azure Functions worker, a FastAPI service,
a React dashboard, SQL Server/Azurite/Redis local infrastructure and CI. The fixed income lab needs
the same operational surfaces (authentication, orchestration, persistence, dashboard) but a new
financial domain.

## Decision

Build the Fixed Income Research Lab inside this repository, additively:

- new .NET tables live in SQL schema `fi` (migrations `AddFixedIncomeSchema`,
  `AddFixedIncomeRunCheckpoints`); legacy crypto tables, `/predict`, and the five-minute market
  cycle stay readable and working;
- the Python service keeps its FastAPI shell (`ai-trading-race-ml/app`) and gains an importable
  package (`research_engine`) and `/internal/v1` endpoints;
- the dashboard gains a separate `src/fi` area instead of reinterpreting crypto views.

## Consequences

- One deployment path and one CI pipeline; no microservice per stage.
- Legacy and new code coexist; BTC/ETH quantities are never reinterpreted as bond face.
- The crypto race is documented as legacy in the README; removing it is a separate decision.
