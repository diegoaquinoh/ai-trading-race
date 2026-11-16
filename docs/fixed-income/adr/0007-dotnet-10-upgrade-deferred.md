# ADR 0007 — .NET 8 → .NET 10 upgrade deferred to a separate migration

- **Status:** Proposed — action required
- **Date:** 2026-11-10
- **Spec:** §4.1

## Context

`AiTradingRace.Web` and `AiTradingRace.Functions` target `net8.0`. Microsoft's .NET support policy
lists .NET 8 (LTS) support ending on **10 November 2026**
([policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)). After that date it
receives no security fixes. .NET 10 is the current LTS and the spec's proposed target, subject to a
compatibility check of the Functions isolated worker, EF Core provider and other packages.

## Decision

Do not mix the runtime upgrade into the fixed income feature work. Perform it as one reviewable
migration:

1. retarget all projects to `net10.0` and update the Functions isolated worker, EF Core and ASP.NET
   packages to versions supporting .NET 10;
2. run `make test-backend`, the parity and commit-protocol tests, and a local end-to-end replay;
3. update Dockerfiles, CI images and Azure runtime settings.

## Consequences

- Until the migration lands, the repository runs on an out-of-support runtime and must not be used
  for a new public deployment.
- The fixed income contracts are runtime-independent (canonical JSON, exported schemas), so the
  upgrade does not change wire behaviour.
