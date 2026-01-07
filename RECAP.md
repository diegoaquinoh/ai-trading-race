# Project Recap

This document tracks completed milestones. 

## Phase 1 Progress (architecture/bootstrap)
- Planning: produced `PLANNING_PHASE1.md` based on `PLANNING_GLOBAL.md`, setting objectives, deliverables, DI strategy, and validation checklist.
- Solution scaffolding: added `.gitignore`, `AiTradingRace.sln`, and five projects (`Web`, `Domain`, `Application`, `Infrastructure`, `Functions`) with proper references.
- Domain & application contracts: defined Entities plus shared models/interfaces (`IMarketDataProvider`, `IPortfolioService`, `IAgentRunner`, `IAgentModelClient`) to lock boundaries early.
- Infrastructure stubs: shipped in-memory providers (market data, portfolio state, agent runner/model client) and DI extensions so everything compiles and can be exercised.
- Blazor Server shell: basic layout, navigation, dashboard page triggering a sample agent run, sample pages/services, and configuration files (`appsettings*`, `launchSettings.json`).
- Azure Functions: isolated worker project with `MarketDataFunction` & `RunAgentsFunction`, program bootstrap, `host.json`, `local.settings.json.example`.
- Documentation: expanded `README.md` with architecture overview, prerequisites, and common commands.
- Tooling fixes: aligned Azure Functions packages (worker/SDK v2.0.0 + timer 4.3.1), added DI package references for Application/Infrastructure, removed WebAssembly import, and validated `dotnet restore`, `dotnet build`, `dotnet run` (only expected dev warnings remain).

## Phase 2 Progress (model & SQL) — Completed 11/12/2025
- EF Core data model built with constraints/seeds (Agents, MarketAssets, MarketCandles, Portfolios, Positions, Trades, EquitySnapshots) and design-time factory with SQL Server env var fallback to SQLite.
- Migration SQL Server `20251211174618_InitialCreate` régénérée avec types natifs (uniqueidentifier, nvarchar, decimal(18,8)) + snapshot; appliquée sur SQL Server local (Docker).
- Services persistants EF : `EfMarketDataProvider` (lecture bougies) et `EfPortfolioService` (création portefeuille, trades buy/sell/hold, snapshots equity) enregistrés en DI (Web + Functions).
- Environnement dev configuré : conteneur Docker SQL Server 2022 avec mot de passe conforme aux règles (8+ caractères, 3 types), chaîne de connexion stockée dans `dotnet user-secrets` (Web) et variable d'environnement pour EF CLI, `appsettings.Development.json` nettoyé (pas de secret committé).
- Config examples fournis : `AiTradingRace.Functions/local.settings.json.example` avec chaîne SQL Server; README documente les commandes EF (`migrations add`, `database update`) et la gestion des secrets.
- **Restant Phase 2 :** ajouter ingestion de vraies données de marché (API externe), tests d'intégration EF (seed/ingestion/PnL +/-), et logs basiques sur l'ingestion/trades.

## Session 07/01/2026 — Architecture Updates

### Planning Updates
- Added **Phase 5b** (Python ML model integration with FastAPI) to `PLANNING_GLOBAL.md`:
  - FastAPI microservice structure (`ai-trading-race-ml/`)
  - API contract for `/predict` endpoint
  - `PyTorchAgentModelClient` integration in .NET
  - `ModelType` enum on `Agent` entity (LLM vs CustomML)

- Switched frontend from **Blazor to React**:
  - Updated Phase 1 & Phase 7 in `PLANNING_GLOBAL.md`
  - Updated `README.md` architecture section

### React Frontend (`ai-trading-race-web/`)
- Scaffolded Vite + React 18 + TypeScript project
- Installed dependencies: `react-router-dom`, `@tanstack/react-query`, `axios`, `recharts`
- Created project structure:
  - `src/types/index.ts` — TypeScript interfaces (Agent, Trade, EquitySnapshot, etc.)
  - `src/services/api.ts` — Axios client for .NET API
  - `src/hooks/useApi.ts` — React Query hooks (useAgents, useEquity, useTrades, useLeaderboard)
  - `src/pages/Dashboard.tsx` — Leaderboard table + equity chart placeholder
  - `src/pages/AgentDetail.tsx` — Agent info, equity curve, trades table
  - `src/App.css` — Dark theme styling
- Verified builds pass (`npm run build`)

### Backend Changes
- Added CORS policy in `AiTradingRace.Web/Program.cs` for React dev server (`http://localhost:5173`)
- Added API Controllers support (`AddControllers()` + `MapControllers()`)
- Blazor files kept for now (to be removed when React is fully ready)

### Remaining
- API controllers (`AgentsController`, `LeaderboardController`, `TradesController`) — left as Phase 7 to-do
