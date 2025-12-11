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

## Phase 2 Progress (model & SQL)
- EF Core data model built with constraints/seeds (Agents, MarketAssets, MarketCandles, Portfolios, Positions, Trades, EquitySnapshots) and design-time factory with SQL Server env var fallback to SQLite.
- Migration `20251207123426_InitialCreate` + snapshot added; DI updated to pick SQL Server when `ConnectionStrings:TradingDb` is set, otherwise in-memory for dev.
- Services persistants EF : `EfMarketDataProvider` (lecture bougies) et `EfPortfolioService` (création portefeuille, trades buy/sell/hold, snapshots equity) enregistrés en DI (Web + Functions).
- Config examples renseignés : `AiTradingRace.Web/appsettings.Development.json` et `AiTradingRace.Functions/local.settings.json.example` contiennent la chaîne SQL Server locale; README mentionne les commandes EF (`migrations add`, `database update`).
- Restant Phase 2 : régénérer la migration avec SQL Server actif (la version commise est issue du fallback SQLite), ajouter ingestion de vraies données de marché, tests d’intégration EF (seed/ingestion/PNL), et documenter/automatiser la gestion des secrets + logs ingestion/trades.

