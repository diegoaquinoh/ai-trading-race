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

## Phase 3 Progress (Market Data Ingestion) — Completed 16/01/2026 ✅

### Components Implemented

- **`IExternalMarketDataClient`** — Interface for external market data APIs
- **`CoinGeckoMarketDataClient`** — CoinGecko OHLC API integration with:
  - Proper User-Agent header (required by CoinGecko)
  - Rate limit handling (429)
  - JSON parsing for `[[timestamp, O, H, L, C], ...]` format
  - Error logging and empty response handling
- **`IMarketDataIngestionService`** — Orchestration contract
- **`MarketDataIngestionService`** — Full ingestion pipeline with:
  - Duplicate candle prevention (timestamp-based)
  - Multi-asset support
  - Configurable via `CoinGeckoOptions`
- **`AdminController`** — REST endpoints:
  - `POST /api/admin/ingest` — Ingest all enabled assets
  - `POST /api/admin/ingest/{symbol}` — Ingest specific asset

### Database Changes

- Added `MarketAsset.ExternalId` field for API mapping (BTC→`bitcoin`, ETH→`ethereum`)
- Migration `20260109025203_AddMarketAssetExternalId` applied

### Configuration

- `appsettings.json` updated with CoinGecko section:
  ```json
  "CoinGecko": {
    "BaseUrl": "https://api.coingecko.com/api/v3/",
    "TimeoutSeconds": 30,
    "DefaultDays": 1
  }
  ```

### Tests — 16 Unit Tests Added

Created `AiTradingRace.Tests` project (xUnit + Moq):

**CoinGeckoMarketDataClientTests** (8 tests):

- Valid data parsing
- Error status codes (403, 429)
- Empty response handling
- Timestamp parsing
- Argument validation
- User-Agent header verification

**MarketDataIngestionServiceTests** (8 tests):

- New candle insertion
- Duplicate prevention
- Missing/disabled asset handling
- Case-insensitive symbol lookup
- All-assets ingestion

### Verification Results (16/01/2026)

- ✅ BTC ingestion: 43 candles inserted
- ✅ ETH ingestion: 43 candles inserted
- ✅ Deduplication: Re-run returns 0 candles
- ✅ All tests pass: `dotnet test AiTradingRace.Tests`

---

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

---

## Phase 4 Progress (Simulation Engine) — Completed 17/01/2026 ✅

### Components Implemented

- **`IEquityService`** — Interface for equity curve management
- **`EquityService`** — Full implementation with:
  - Equity snapshot capture (cash + positions valuation)
  - Equity curve retrieval with date filtering
  - Performance metrics calculation (return %, max drawdown, win rate)
  - Batch snapshot capture for all agents
- **`EquityController`** — REST endpoints for equity data
- **`AgentsController`** — Leaderboard endpoint with portfolio values
- **`PortfolioController`** — Portfolio state and manual trade execution
- **`TradesController`** — Trade history with pagination

### DTOs Created

- `EquitySnapshotDto` — Snapshot with cash/positions breakdown
- `PerformanceMetrics` — Return, drawdown, Sharpe ratio, trade stats
- `AgentSummaryDto`, `AgentDetailDto` — Leaderboard and detail views
- `TradeDto`, `TradeHistoryResponse` — Trade history with pagination

### Database Changes

- Added `CashValue`, `PositionsValue` columns to `EquitySnapshots`
- Regenerated `InitialCreate` migration with correct SQL Server types
- Fixed design-time factory to prevent SQLite fallback

### API Endpoints (Phase 4)

| Method | Endpoint                              | Description                |
| ------ | ------------------------------------- | -------------------------- |
| GET    | `/api/agents`                         | Leaderboard (all agents)   |
| GET    | `/api/agents/{id}`                    | Agent detail + performance |
| GET    | `/api/agents/{id}/portfolio`          | Current portfolio state    |
| POST   | `/api/agents/{id}/portfolio/trades`   | Execute manual trades      |
| GET    | `/api/agents/{id}/trades`             | Trade history (paginated)  |
| GET    | `/api/agents/{id}/equity`             | Equity curve               |
| GET    | `/api/agents/{id}/equity/latest`      | Latest snapshot            |
| POST   | `/api/agents/{id}/equity/snapshot`    | Capture new snapshot       |
| GET    | `/api/agents/{id}/equity/performance` | Performance metrics        |

### Tests — 48 Total (32 new in Phase 4)

**EquityServiceTests** (14 tests):

- Snapshot capture with/without positions
- Equity curve ordering and filtering
- Performance metrics calculation
- Max drawdown calculation
- Trade win/loss statistics

**PortfolioEquityIntegrationTests** (12 tests):

- Full trade execution flow
- Positive/negative PnL tracking
- Multi-asset portfolio valuation
- Insufficient funds/position handling

**SqlServerIntegrationTests** (7 tests):

- Testcontainers-based real SQL Server tests
- Migration verification
- Schema validation
- Service integration against real DB

### Verification Results (17/01/2026)

- ✅ All 48 tests pass (`dotnet test`)
- ✅ API endpoints verified via curl
- ✅ Equity snapshots capture correctly
- ✅ Portfolio trades execute with PnL tracking
- ✅ Performance metrics calculate accurately

---

## Phase 5 Progress (AI Agent Integration) — Completed 17/01/2026 ✅

### Components Implemented

- **`ModelProvider` enum** — Support for AzureOpenAI, OpenAI, CustomML, Mock
- **`Agent` entity updates** — Added `Strategy`, `Instructions`, `ModelProvider`
- **`IAgentContextBuilder`** — Interface for building agent execution context
- **`AgentContextBuilder`** — Loads agent, portfolio state, and market candles
- **`IAgentModelClient`** — Interface for LLM integration (existing)
- **`AzureOpenAiAgentModelClient`** — Azure OpenAI integration with:
  - System/user prompt construction
  - JSON response parsing
  - Error handling with HOLD fallback
- **`TestAgentModelClient`** — Generates aggressive test orders for E2E testing
- **`IRiskValidator`** — Interface for server-side risk validation
- **`RiskValidator`** — Enforces all risk constraints:
  - Max position size per asset (50%)
  - Minimum cash reserve ($100)
  - Maximum single trade value ($5,000)
  - Minimum order value ($10)
  - Allowed assets whitelist (BTC, ETH)
  - Order quantity adjustments
  - Short selling prevention
- **`IAgentRunner`** — Interface for agent execution (existing)
- **`AgentRunner`** — Full orchestration:
  1. Build context (portfolio + candles)
  2. Generate AI decision
  3. Validate against risk constraints
  4. Execute trades
  5. Capture equity snapshot

### Database Changes

- Migration `20260117160003_AddAgentInstructionsAndModelProvider`:
  - Added `Instructions`, `ModelProvider`, `Strategy` columns to Agents
  - Dropped old `Provider` column
  - Updated seed data

### API Endpoints (Phase 5)

| Method | Endpoint               | Description                 |
| ------ | ---------------------- | --------------------------- |
| POST   | `/api/agents/{id}/run` | Execute agent trading cycle |

### DI Registration

Three registration methods available:

- `AddInfrastructureServices()` — Full Azure OpenAI (requires credentials)
- `AddInfrastructureServicesWithMockAI()` — EchoAgentModelClient (always HOLD)
- `AddInfrastructureServicesWithTestAI()` — TestAgentModelClient (generates orders)

### Configuration

```json
"AzureOpenAI": {
  "Endpoint": "",
  "ApiKey": "",
  "DeploymentName": "gpt-4o",
  "Temperature": 0.7,
  "MaxTokens": 500
}

"RiskValidator": {
  "MaxPositionSizePercent": 0.50,
  "MinCashReserve": 100,
  "MaxSingleTradeValue": 5000,
  "AllowedAssets": ["BTC", "ETH"]
}
```

### Tests — 65 Total (17 new in Phase 5)

**RiskValidatorTests** (11 tests):

- Allowed/unknown asset validation
- Cash reserve enforcement
- Max trade value limits
- Dust order rejection
- Sell validation (no position, short selling)
- Order count limits
- Position size limits

**AgentContextBuilderTests** (6 tests):

- Active/inactive agent handling
- Non-existent agent errors
- Portfolio state inclusion
- Market candle fetching
- Graceful error handling

### E2E Verification Results (17/01/2026)

- ✅ Mock flow test passed (EchoAgentModelClient)
- ✅ Test flow verified risk validation:
  - Proposed: Buy 1.5 BTC ($63k) → Adjusted to 0.106 BTC ($4,450)
  - Proposed: Buy 10 ETH ($25k) → Adjusted to 1.55 ETH ($3,870)
- ✅ Orders correctly capped to MaxSingleTradeValue ($5k)
- ✅ Trades executed, portfolio updated
- ✅ All 65 tests pass

### Note: LLM API Keys Deferred to Phase 8

Real LLM credentials (OpenAI, Azure OpenAI, GitHub Models) will be configured during Phase 8 (Azure Deployment). For development and testing, use `TestAgentModelClient` which validates the full flow without external API calls.

---

## Next Steps (Phase 6+)

### Phase 6 — Azure Functions

- Timer-triggered market data ingestion
- Timer-triggered agent execution
- Scheduled equity snapshots

### Phase 7 — React Dashboard

- Connect to backend API
- Implement equity charts with Recharts
- Real-time updates via polling/WebSocket

### Phase 8 — Azure Deployment

- Deploy to Azure App Service
- Configure Azure Key Vault for secrets
- **Configure LLM API keys** (OpenAI, Azure OpenAI, or GitHub Models)
- Set up CI/CD pipeline
