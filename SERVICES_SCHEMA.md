# Services Architecture Schema

## 🏗️ Service Layers Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │
│  │  Web API         │  │  Azure Functions │  │  Blazor UI       │     │
│  │  (Controllers)   │  │  (Timers)        │  │  (Pages)         │     │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘     │
└───────────┼──────────────────────┼──────────────────────┼───────────────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER (Interfaces)                     │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    CORE BUSINESS SERVICES                        │   │
│  │                                                                  │   │
│  │  IAgentRunner              IPortfolioService    IEquityService  │   │
│  │  IAgentContextBuilder      IMarketDataProvider                  │   │
│  │  IRiskValidator            IMarketDataIngestionService          │   │
│  │                                                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    AI/ML ABSTRACTION                            │   │
│  │                                                                  │   │
│  │  IAgentModelClient         IAgentModelClientFactory             │   │
│  │  IExternalMarketDataClient                                      │   │
│  │                                                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   INFRASTRUCTURE LAYER (Implementations)                │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │
│  │   Portfolio      │  │   Market Data    │  │   Equity         │     │
│  │                  │  │                  │  │                  │     │
│  │ • InMemory       │  │ • EfProvider     │  │ • EquityService  │     │
│  │ • EfPortfolio    │  │ • InMemory       │  │                  │     │
│  │                  │  │ • Ingestion      │  │                  │     │
│  │                  │  │ • CoinGecko      │  │                  │     │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘     │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      AGENT ORCHESTRATION                         │  │
│  │                                                                  │  │
│  │  • AgentRunner          • AgentContextBuilder                   │  │
│  │  • NoOpAgentRunner      • RiskValidator                         │  │
│  │  • AgentModelClientFactory                                      │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      AI MODEL CLIENTS                            │  │
│  │                                                                  │  │
│  │  • AzureOpenAiAgentModelClient    (GPT-4)                       │  │
│  │  • LlamaAgentModelClient          (Local LLM)                   │  │
│  │  • CustomMlAgentModelClient       (FastAPI ML)                  │  │
│  │  • EchoAgentModelClient           (Echo/Test)                   │  │
│  │  • TestAgentModelClient           (Unit Tests)                  │  │
│  │                                                                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                               │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │  PostgreSQL  │  │  Azure       │  │  CoinGecko   │                 │
│  │  Database    │  │  OpenAI      │  │  API         │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      PYTHON ML SERVICE (FastAPI)                        │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │
│  │  DecisionService │  │  CacheService    │  │  TradingPredictor│     │
│  │  (ML Pipeline)   │  │  (Redis Cache)   │  │  (XGBoost Model) │     │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Service Interaction Flow

### Agent Execution Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AGENT DECISION FLOW                             │
└─────────────────────────────────────────────────────────────────────────┘

1️⃣  Trigger
    │
    ├─→ API Endpoint: POST /agents/{id}/run
    ├─→ Azure Function: AgentRunnerFunction (Timer)
    └─→ Blazor UI: Manual Run Button
    
2️⃣  IAgentRunner.RunAgentOnceAsync()
    │
    ├─→ IAgentContextBuilder.BuildContextAsync()
    │   │
    │   ├─→ IPortfolioService.GetPortfolioAsync()      [Get current portfolio]
    │   ├─→ IMarketDataProvider.GetLatestCandlesAsync() [Get market data]
    │   └─→ Load agent config from DB
    │
    ├─→ IAgentModelClientFactory.GetClient(provider)
    │   │
    │   └─→ Returns: AzureOpenAi | Llama | CustomML | Echo
    │
    ├─→ IAgentModelClient.GenerateDecisionAsync(context)
    │   │
    │   ├─→ [Azure OpenAI] → GPT-4 API
    │   ├─→ [Llama] → Local Ollama Server
    │   ├─→ [CustomML] → FastAPI ML Service
    │   │                  │
    │   │                  ├─→ CacheService.get()
    │   │                  ├─→ DecisionService.generate_decision()
    │   │                  │   └─→ TradingPredictor.predict()
    │   │                  └─→ CacheService.set()
    │   │
    │   └─→ [Echo] → Mock response
    │
    ├─→ IRiskValidator.ValidateDecisionAsync(decision, portfolio)
    │   │
    │   └─→ Check position limits, cash reserves, allowed assets
    │
    ├─→ IPortfolioService.ApplyDecisionAsync(agentId, decision)
    │   │
    │   └─→ Update positions, cash, transaction history
    │
    └─→ IEquityService.CaptureSnapshotAsync(agentId)
        │
        └─→ Calculate and store equity snapshot

3️⃣  Return AgentRunResult
    │
    └─→ Contains: decision, validation warnings, new portfolio state
```

---

## 🎯 Core Services Detail

### 1. Portfolio Management

```csharp
// Interface
public interface IPortfolioService
{
    Task<PortfolioState> GetPortfolioAsync(Guid agentId);
    Task<PortfolioState> ApplyDecisionAsync(Guid agentId, AgentDecision decision);
}

// Implementations
├── InMemoryPortfolioService    // Fast, non-persistent (testing)
└── EfPortfolioService          // Persistent via Entity Framework
```

**Responsibilities:**
- Track agent cash balances
- Manage asset positions (BTC, ETH)
- Record transaction history
- Calculate available buying power

---

### 2. Market Data Services

```csharp
// Data Access
public interface IMarketDataProvider
{
    Task<IReadOnlyList<MarketCandleDto>> GetLatestCandlesAsync(
        string assetSymbol, int limit = 100);
}

// Data Ingestion
public interface IMarketDataIngestionService
{
    Task<int> IngestLatestCandlesAsync(string assetSymbol);
    Task<int> IngestAllAssetsAsync();
}

// External API
public interface IExternalMarketDataClient
{
    Task<IReadOnlyList<ExternalCandleDto>> GetCandlesAsync(
        string coinId, string vsCurrency, int days);
}
```

**Flow:**
```
CoinGecko API → IExternalMarketDataClient → MarketDataIngestionService
                                             ↓
                                        PostgreSQL DB
                                             ↓
                                    IMarketDataProvider → Agents
```

---

### 3. Equity & Performance

```csharp
public interface IEquityService
{
    Task<EquitySnapshotDto> CaptureSnapshotAsync(Guid agentId);
    Task<IReadOnlyList<EquitySnapshotDto>> GetEquityCurveAsync(Guid agentId);
    Task<PerformanceMetrics> CalculatePerformanceAsync(Guid agentId);
}
```

**Calculates:**
- Total equity value (cash + positions)
- Returns (absolute, percentage)
- Drawdown statistics
- Win rate, trade counts
- Sharpe ratio, other metrics

---

### 4. Agent Orchestration

```csharp
public interface IAgentRunner
{
    Task<AgentRunResult> RunAgentOnceAsync(Guid agentId);
}

public interface IAgentContextBuilder
{
    Task<AgentContext> BuildContextAsync(Guid agentId, int candleCount = 24);
}

public interface IRiskValidator
{
    Task<TradeValidationResult> ValidateDecisionAsync(
        AgentDecision decision, PortfolioState portfolio);
}
```

**Risk Validation Rules:**
- Max position size per asset
- Minimum cash reserve
- Only allowed assets (BTC, ETH)
- No short positions
- Quantity adjustments for oversized orders

---

### 5. AI Model Clients

```csharp
public interface IAgentModelClient
{
    Task<AgentDecision> GenerateDecisionAsync(AgentContext context);
}

public interface IAgentModelClientFactory
{
    IAgentModelClient GetClient(ModelProvider provider);
}
```

**Supported Models:**

| Client | Provider | Technology | Use Case |
|--------|----------|------------|----------|
| `AzureOpenAiAgentModelClient` | Azure OpenAI | GPT-4 | Production LLM trading |
| `LlamaAgentModelClient` | Ollama | Llama 3.2 | Local LLM testing |
| `CustomMlAgentModelClient` | FastAPI | XGBoost | ML-based predictions |
| `EchoAgentModelClient` | Mock | N/A | Testing/debugging |
| `TestAgentModelClient` | Mock | N/A | Unit tests |

---

## 🐍 Python ML Service

```
FastAPI Endpoint: POST /api/v1/predict
│
├─→ CacheService.get(idempotency_key)  [Redis lookup]
│   └─→ If cached → return cached response
│
├─→ DecisionService.generate_decision(context)
│   │
│   ├─→ Parse portfolio & market data
│   ├─→ Calculate technical indicators (SMA, RSI, etc.)
│   ├─→ Prepare feature matrix
│   │
│   └─→ TradingPredictor.predict(features)
│       │
│       └─→ XGBoost model inference
│           ├─→ Action: BUY, SELL, HOLD
│           ├─→ Confidence score
│           └─→ Position sizing
│
└─→ CacheService.set(idempotency_key, response)  [Cache result]
```

**Features Generated:**
- Price momentum (returns)
- Volatility
- Moving averages (SMA 7, 14, 21)
- RSI (Relative Strength Index)
- Position ratios
- Cash availability

---

## 📈 Service Dependencies Graph

```
                    ┌─────────────────┐
                    │  IAgentRunner   │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────┐  ┌──────────────┐  ┌────────────────┐
│IAgentContext    │  │IRiskValidator│  │IPortfolioService│
│Builder          │  └──────────────┘  └────────────────┘
└────────┬────────┘                             ▲
         │                                      │
    ┌────┼────┐                                │
    │    │    │                                │
    ▼    ▼    ▼                                │
┌────┐ ┌───┐ ┌──────────────────┐             │
│DB  │ │IMarket│IAgentModel     │             │
│Agent│ │Data   │ClientFactory   │             │
└────┘ │Provider│                │             │
       └───────┘└────────┬───────┘             │
                         │                     │
          ┌──────────────┼──────────────┐     │
          │              │              │     │
          ▼              ▼              ▼     │
    ┌──────────┐  ┌──────────┐  ┌──────────┐ │
    │Azure     │  │Llama     │  │CustomML  │ │
    │OpenAI    │  │Agent     │  │Agent     │ │
    │Client    │  │Client    │  │Client    │ │
    └──────────┘  └──────────┘  └────┬─────┘ │
                                     │        │
                                     ▼        │
                            ┌─────────────────┐│
                            │Python ML Service││
                            │(FastAPI)        ││
                            │• DecisionService││
                            │• CacheService   ││
                            │• Predictor      ││
                            └─────────────────┘│
                                                │
                                                │
       ┌────────────────────────────────────────┘
       │
       ▼
┌────────────────┐     ┌──────────────────┐
│IEquityService  │     │IMarketData       │
│                │     │IngestionService  │
└────────────────┘     └─────────┬────────┘
                                 │
                                 ▼
                      ┌──────────────────────┐
                      │IExternalMarketData  │
                      │Client (CoinGecko)   │
                      └──────────────────────┘
```

---

## 🔄 Data Flow Examples

### Example 1: Manual Agent Run

```
User → Blazor UI → HTTP POST /agents/{id}/run
                    ↓
              AgentsController
                    ↓
              IAgentRunner.RunAgentOnceAsync()
                    ↓
         [Context Building + AI Decision + Risk Validation]
                    ↓
              IPortfolioService.ApplyDecisionAsync()
                    ↓
              IEquityService.CaptureSnapshotAsync()
                    ↓
              Return AgentRunResult → Display in UI
```

### Example 2: Scheduled Data Ingestion

```
Azure Function Timer (every 4 hours)
            ↓
  MarketDataIngestionFunction
            ↓
  IMarketDataIngestionService.IngestAllAssetsAsync()
            ↓
  For each asset (BTC, ETH):
      ↓
  IExternalMarketDataClient.GetCandlesAsync()
      ↓
  CoinGecko API Request
      ↓
  Parse & deduplicate candles
      ↓
  Save to PostgreSQL (new candles only)
      ↓
  Return count of inserted candles
```

### Example 3: Performance Analysis

```
User → Web API → GET /agents/{id}/performance
                    ↓
              AgentsController
                    ↓
              IEquityService.CalculatePerformanceAsync()
                    ↓
         Load all equity snapshots from DB
                    ↓
         Load all transactions from DB
                    ↓
         Calculate metrics:
         • Total Return
         • Max Drawdown
         • Win Rate
         • Sharpe Ratio
                    ↓
         Return PerformanceMetrics JSON
```

---

## 🧪 Testing Services

```
Test Layer                Real Implementation
─────────────────────────────────────────────────
TestAgentModelClient  →   Real IAgentModelClient
EchoAgentModelClient  →   Mock responses
NoOpAgentRunner       →   Skips execution

InMemoryPortfolio     →   Fast non-persistent
InMemoryMarketData    →   No DB required
```

---

## 📦 Service Registration (DI)

### Application Layer
```csharp
services.AddScoped<IAgentContextBuilder, AgentContextBuilder>();
services.AddScoped<IRiskValidator, RiskValidator>();
services.AddScoped<IAgentModelClientFactory, AgentModelClientFactory>();
```

### Infrastructure Layer
```csharp
// Portfolio
services.AddScoped<IPortfolioService, EfPortfolioService>();
// or: services.AddSingleton<IPortfolioService, InMemoryPortfolioService>();

// Market Data
services.AddScoped<IMarketDataProvider, EfMarketDataProvider>();
services.AddScoped<IMarketDataIngestionService, MarketDataIngestionService>();
services.AddHttpClient<IExternalMarketDataClient, CoinGeckoMarketDataClient>();

// Equity
services.AddScoped<IEquityService, EquityService>();

// Agent Execution
services.AddScoped<IAgentRunner, AgentRunner>();

// AI Clients
services.AddScoped<AzureOpenAiAgentModelClient>();
services.AddScoped<LlamaAgentModelClient>();
services.AddScoped<CustomMlAgentModelClient>();
services.AddScoped<EchoAgentModelClient>();
```

---

## 🎯 Service Boundaries

| Layer | Responsibility | Cannot Access |
|-------|----------------|---------------|
| **Application** | Define contracts, DTOs | Database, External APIs |
| **Infrastructure** | Implement interfaces | Nothing (can access all) |
| **Domain** | Business entities | Application, Infrastructure |
| **Presentation** | HTTP/UI layer | Domain entities directly |

**Key Principle:** All dependencies point inward (Dependency Inversion)

---

## 🚀 Performance Considerations

### Caching Strategy
- **Python ML Service:** Redis cache with 1-hour TTL (idempotency)
- **Market Data:** PostgreSQL indexed queries
- **Portfolio:** In-memory option for high-speed testing

### Async Operations
- All service methods use `async/await`
- CancellationToken support throughout
- HTTP clients with connection pooling

### Rate Limiting
- **CoinGecko API:** 10-30 calls/minute (Free tier)
- **Azure OpenAI:** Configurable TPM limits
- **Llama (Local):** Custom rate limiting handler

---

## 📝 Summary Statistics

| Category | Count | Technologies |
|----------|-------|-------------|
| **C# Services** | 21 | .NET 8, EF Core, Npgsql |
| **Python Services** | 2 | FastAPI, Redis, XGBoost |
| **Interfaces** | 10 | Application contracts |
| **AI Clients** | 5 | Azure, Ollama, FastAPI |
| **Total Services** | 23 | Polyglot architecture |

---

**Last Updated:** Phase 8 (January 2026)
