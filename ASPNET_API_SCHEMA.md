# ASP.NET Core API Schema

## Overview

RESTful API for AI trading competition platform managing agents, portfolios, and market data.

**Stack:**
- ASP.NET Core 8.0
- SQL Server + EF Core
- Clean Architecture (Domain → Application → Infrastructure → Web)
- CORS enabled for `http://localhost:5173`

---

## Architecture Layers

### Domain (`AiTradingRace.Domain`)
Core entities with no external dependencies.

```
Agent: Id, Name, Strategy, ModelProvider, IsActive, CreatedAt
Portfolio: Id, AgentId, Cash, Positions[]
Position: Id, PortfolioId, MarketAssetId, Quantity, AverageCost
Trade: Id, PortfolioId, MarketAssetId, Quantity, Price, Side, ExecutedAt
MarketAsset: Id, Symbol, Name, CoinGeckoId, IsEnabled
MarketCandle: Id, MarketAssetId, TimestampUtc, Open, High, Low, Close, Volume
EquitySnapshot: Id, AgentId, TotalValue, Cash, PercentChange, CapturedAt
```

### Application (`AiTradingRace.Application`)
Interfaces and DTOs.

**Services:**
- `IMarketDataProvider` - Market data access
- `IPortfolioService` - Portfolio management
- `IEquityService` - Equity tracking
- `IAgentRunner` - Agent orchestration
- `IRiskValidator` - Risk management

**Models:**
- `AgentContext`, `AgentDecision`, `TradeOrder`, `PortfolioState`, `PerformanceMetrics`

### Infrastructure (`AiTradingRace.Infrastructure`)
Concrete implementations + AI clients.

**AI Clients:**
- `AzureOpenAiAgentModelClient` - GPT-4
- `LlamaAgentModelClient` - Groq/Llama (with rate limiting)
- `CustomMlAgentModelClient` - FastAPI ML service
- `TestAgentModelClient` - Aggressive test orders
- `EchoAgentModelClient` - Mock (always HOLD)

**Risk Rules:**
```json
{
  "MaxPositionSizePercent": 0.50,
  "MinCashReserve": 100,
  "MaxSingleTradeValue": 5000,
  "MinOrderValue": 10,
  "AllowedAssets": ["BTC", "ETH"],
  "MaxOrdersPerCycle": 5
}
```

---

## API Endpoints

### Admin (`/api/admin`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/ingest` | Ingest all assets |
| POST | `/api/admin/ingest/{symbol}` | Ingest specific asset |

---

### Agents (`/api/agents`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents` | Get all agents (leaderboard) |
| GET | `/api/agents/{id}` | Get agent details |
| POST | `/api/agents/{id}/run` | Execute agent trading cycle |

**Response Examples:**
```typescript
// AgentSummaryDto
{ id: string, name: string, strategy: string, isActive: boolean, 
  totalValue: number, percentChange: number, lastUpdated: string }

// AgentRunResultDto
{ agentId: string, startedAt: string, completedAt: string, 
  durationSeconds: number, totalValue: number, cash: number, 
  orderCount: number, executedOrders: OrderDto[] }
```

---

### Equity (`/api/agents/{agentId}/equity`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/equity` | Get equity curve (`from?`, `to?` params) |
| GET | `/equity/latest` | Latest snapshot |
| POST | `/equity/snapshot` | Capture new snapshot |
| GET | `/equity/performance` | Performance metrics |

---

### Leaderboard (`/api/leaderboard`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/leaderboard` | Ranked agents by portfolio value |

---

### Market (`/api/market`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/market/prices` | Latest prices for all assets |
| GET | `/market/prices/{symbol}` | Price for specific asset |

```typescript
// MarketPriceDto
{ symbol: string, name: string, price: number, 
  change24h: number, changePercent24h: number, 
  high24h: number, low24h: number, updatedAt: string }
```

---

### Portfolio (`/api/agents/{agentId}`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/portfolio` | Current portfolio state |
| POST | `/portfolio/trades` | Execute manual trades |

**Request:**
```typescript
{ orders: [{ assetSymbol: string, side: "Buy"|"Sell", 
              quantity: number, limitPrice?: number }] }
```

---

### Trades (`/api/agents/{agentId}/trades`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/trades` | Trade history (`limit?`, `offset?` params) |
| GET | `/trades/summary` | Trade statistics |

---

## Agent Trading Flow

**POST `/api/agents/{id}/run`**

```
1. Validate agent (exists + active)
2. Build AgentContext (portfolio + market data)
3. AI Model Decision (via factory → client)
4. Risk Validation (filter/adjust orders)
5. Execute Trades (update portfolio + positions)
6. Capture Equity Snapshot
7. Return AgentRunResultDto
```

**Error Handling:**
- 404: Agent not found
- 400: Agent inactive / Invalid orders
- 500: AI/DB failures

---

## Configuration

**Startup (`Program.cs`):**
```csharp
builder.Services.AddCors(options => {
    options.AddPolicy("ReactDevServer", policy => 
        policy.WithOrigins("http://localhost:5173")
              .AllowAnyHeader().AllowAnyMethod().AllowCredentials());
});
builder.Services.AddControllers();
builder.Services.AddApplicationServices();
builder.Services.AddInfrastructureServicesWithTestAI(builder.Configuration);
```

**Service Variants:**
- `AddInfrastructureServices` - Production (real AI clients)
- `AddInfrastructureServicesWithMockAI` - Echo client (HOLD only)
- `AddInfrastructureServicesWithTestAI` - Aggressive orders for testing

**appsettings.json:**
```json
{
  "ConnectionStrings": { "TradingDb": "Server=..." },
  "CoinGecko": { "BaseUrl": "...", "TimeoutSeconds": 30 },
  "AzureOpenAI": { "Endpoint": "...", "DeploymentName": "gpt-4o" },
  "CustomMlAgent": { "BaseUrl": "http://localhost:8000" },
  "Llama": { "BaseUrl": "https://api.groq.com/openai/v1", "Model": "llama-3.3-70b-versatile" },
  "RiskValidator": { "MaxPositionSizePercent": 0.50, "AllowedAssets": ["BTC", "ETH"] }
}
```

---

## Resilience (Llama Client)

**Retry Policy:** Exponential backoff (2s, 4s, 8s) on transient errors + 429
**Circuit Breaker:** Opens after 5 failures, stays open 30s
**Rate Limiting:** `MinRequestIntervalMs: 1000`

---

## Testing

```bash
# Run agent
curl -X POST http://localhost:5000/api/agents/{guid}/run

# Ingest data
curl -X POST http://localhost:5000/api/admin/ingest/BTC

# Get leaderboard
curl http://localhost:5000/api/leaderboard
```

---

## Database

**Tables:** Agents, Portfolios, Positions, Trades, MarketAssets, MarketCandles, EquitySnapshots
**Migrations:** `AiTradingRace.Infrastructure/Migrations`
**Connection:** SQL Server or In-Memory (dev)

---

## Deployment

**Local:** `dotnet run` → http://localhost:5000
**Docker:** `docker-compose up web-api`
**Azure:** CI/CD via GitHub Actions (`.github/workflows/backend-ci-cd.yml`)

---

## Related Docs

- [FastAPI ML Service](./ai-trading-race-ml/FASTAPI_SCHEMA.md)
- [Database Schema](./DATABASE.md)
- [Project Architecture](./PROJECT_ARCHITECTURE_REPORT.md)

