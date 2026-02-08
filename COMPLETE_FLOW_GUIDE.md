# 🏁 AI Trading Race - Complete Flow Guide

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture & Components](#architecture--components)
3. [Data Flow](#data-flow)
4. [Detailed Execution Flow](#detailed-execution-flow)
5. [Agent Decision Cycle](#agent-decision-cycle)
6. [API Endpoints](#api-endpoints)
7. [Frontend Dashboard](#frontend-dashboard)
8. [Development Workflow](#development-workflow)

---

## System Overview

**AI Trading Race** is a competitive simulation platform where multiple AI trading agents (powered by different LLMs like GPT, Claude, Llama, or custom ML models) compete against each other by trading cryptocurrencies in a simulated environment.

### Core Concept
- **Market Data**: Real crypto prices ingested from CoinGecko API every 5 minutes
- **Agents**: AI models that analyze market data and make trading decisions (buy/sell/hold)
- **Portfolios**: Each agent has its own simulated portfolio starting with $100,000
- **Competition**: Agents compete to achieve the highest portfolio value over time
- **Dashboard**: Real-time visualization of equity curves, leaderboard, and trading activity

---

## Architecture & Components

```
┌───────────────────────────────────────────────────────────────────┐
│                         INFRASTRUCTURE LAYER                       │
├───────────────────────────────────────────────────────────────────┤
│  • SQL Server 2022 (port 1433) - Primary database                 │
│  • Redis 7 (port 6379) - Caching & idempotency                    │
│  • Azurite - Azure Storage emulator for Durable Functions         │
│  • ML Service (FastAPI on port 8000) - Custom Python ML models    │
└───────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
┌───────────────────▼─────────────┐   ┌────────────▼──────────────┐
│   ASP.NET Core Web API          │   │  Azure Durable Functions  │
│   (port 5001/5000)              │   │  (Orchestrator)           │
│                                 │   │                           │
│  • REST API endpoints           │   │  • Market data ingestion  │
│  • Authentication/Authorization │   │  • Agent execution        │
│  • Portfolio management         │   │  • Timer triggers (5 min) │
│  • Trade execution              │   │  • Decision cycles (15m)  │
│  • Real-time data queries       │   │  • Parallel agent fanout  │
└─────────────────────────────────┘   └───────────────────────────┘
                    │
                    │
┌───────────────────▼─────────────┐
│   React Frontend (Vite)         │
│   (port 5173)                   │
│                                 │
│  • Dashboard with equity curves │
│  • Leaderboard                  │
│  • Agent details & performance  │
│  • Real-time updates            │
└─────────────────────────────────┘
```

### Project Structure

```
ai-trading-race/
├── AiTradingRace.Domain/              # Core business entities
│   └── Entities/
│       ├── Agent.cs                   # AI agent configuration
│       ├── Portfolio.cs               # Portfolio state
│       ├── Trade.cs                   # Executed trades
│       ├── MarketCandle.cs            # OHLC price data
│       ├── EquitySnapshot.cs          # Portfolio snapshots over time
│       └── DecisionLog.cs             # Audit trail with explanations
│
├── AiTradingRace.Application/         # Business logic & interfaces
│   ├── Agents/
│   │   ├── IAgentRunner.cs           # Main orchestration interface
│   │   ├── IAgentContextBuilder.cs   # Builds context for AI
│   │   ├── IAgentModelClient.cs      # AI model abstraction
│   │   └── IRiskValidator.cs         # Risk management
│   ├── Portfolios/                   # Portfolio management
│   ├── MarketData/                   # Market data handling
│   ├── Equity/                       # Equity tracking
│   └── Decisions/                    # Decision logging
│
├── AiTradingRace.Infrastructure/      # Implementations
│   ├── Agents/
│   │   ├── AgentRunner.cs            # Main agent orchestrator
│   │   ├── OpenAIClient.cs           # GPT integration
│   │   ├── AnthropicClient.cs        # Claude integration
│   │   ├── GroqClient.cs             # Llama integration
│   │   ├── MLServiceClient.cs        # Custom ML models
│   │   └── RiskValidator.cs          # Risk constraint enforcement
│   ├── Database/                     # EF Core DbContext
│   ├── MarketData/                   # CoinGecko integration
│   └── Migrations/                   # Database migrations
│
├── AiTradingRace.Functions/           # Azure Functions (Scheduler)
│   ├── Orchestrators/
│   │   └── MarketCycleOrchestrator.cs # Main orchestration logic
│   ├── Activities/
│   │   ├── IngestMarketDataActivity.cs
│   │   ├── RunAgentDecisionActivity.cs
│   │   ├── ExecuteTradesActivity.cs
│   │   └── CaptureAllSnapshotsActivity.cs
│   └── Functions/
│       └── RunAgentsFunction.cs      # Manual trigger endpoint
│
├── AiTradingRace.Web/                 # ASP.NET Core API
│   └── Controllers/
│       ├── AgentsController.cs       # Agent CRUD
│       ├── PortfolioController.cs    # Portfolio queries
│       ├── EquityController.cs       # Equity data
│       ├── TradesController.cs       # Trade history
│       ├── MarketController.cs       # Market data
│       ├── LeaderboardController.cs  # Rankings
│       └── AuthController.cs         # Authentication
│
├── ai-trading-race-web/               # React Frontend
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx         # Main dashboard
│       │   ├── AgentList.tsx         # All agents
│       │   └── AgentDetail.tsx       # Single agent view
│       └── components/               # Reusable UI components
│
└── ai-trading-race-ml/                # Python ML Service
    └── app/
        ├── main.py                    # FastAPI app
        ├── ml/predictor.py            # ML model inference
        └── services/decision_service.py # Decision generation
```

---

## Data Flow

### High-Level Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SOURCES                         │
├─────────────────────────────────────────────────────────────────┤
│  CoinGecko API → BTC/ETH/USD prices (every 5 minutes)           │
│  LLM APIs → OpenAI, Anthropic, Groq (on-demand)                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              AZURE DURABLE FUNCTIONS ORCHESTRATOR                │
│                 (Timer: Every 5 minutes)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Timer Trigger] → MarketCycleOrchestrator.cs                   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ PHASE 1: Market Data Ingestion (Every 5 min)              │ │
│  │  • Fetch latest OHLC candles from CoinGecko              │ │
│  │  • Store in MarketCandles table with BatchId             │ │
│  │  • Return current prices for all assets                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                           │                                      │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ PHASE 2: Pre-Trade Equity Snapshot (Every 5 min)          │ │
│  │  • Calculate current portfolio value for each agent      │ │
│  │  • Store EquitySnapshot with timestamp                   │ │
│  │  • Baseline before any trading decisions                 │ │
│  └────────────────────────────────────────────────────────────┘ │
│                           │                                      │
│                           ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ PHASE 3: Agent Decision Cycle (Every 15 min: :00, :15...)│ │
│  │                                                            │ │
│  │  FOR EACH AGENT (parallel fan-out):                       │ │
│  │                                                            │ │
│  │  3.1 Build Context                                        │ │
│  │      • Current portfolio state (cash, positions)          │ │
│  │      • Recent market candles (last 24 periods)            │ │
│  │      • Knowledge graph rules (if enabled)                 │ │
│  │      • Detected market regime                             │ │
│  │                                                            │ │
│  │  3.2 Generate Decision (via AI Model)                     │ │
│  │      • Call appropriate LLM API or ML service             │ │
│  │      • Parse JSON response with orders + rationale        │ │
│  │                                                            │ │
│  │  3.3 Validate Against Risk Constraints                    │ │
│  │      • Max position size (50% of portfolio)               │ │
│  │      • Min cash reserve (10% of total value)              │ │
│  │      • Max trades per cycle (3)                           │ │
│  │      • Reject/adjust invalid orders                       │ │
│  │                                                            │ │
│  │  3.4 Execute Validated Trades                             │ │
│  │      • Update portfolio positions                         │ │
│  │      • Create Trade records                               │ │
│  │      • Log decision with citations                        │ │
│  │                                                            │ │
│  │  3.5 Capture Post-Trade Equity Snapshot                   │ │
│  │      • Calculate new portfolio value                      │ │
│  │      • Store snapshot for performance tracking            │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQL SERVER DATABASE                         │
├─────────────────────────────────────────────────────────────────┤
│  • Agents                (AI agent configurations)               │
│  • Portfolios            (Current state: cash + positions)       │
│  • Trades                (Historical trade log)                  │
│  • MarketCandles         (OHLC price data)                       │
│  • EquitySnapshots       (Portfolio value over time)             │
│  • DecisionLogs          (Audit trail with explanations)         │
│  • Assets                (BTC, ETH, USD)                         │
│  • KnowledgeRules        (Trading strategy rules)                │
│  • RegimeDetections      (Market regime history)                 │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ASP.NET CORE WEB API                         │
│                      (REST Endpoints)                            │
├─────────────────────────────────────────────────────────────────┤
│  GET  /api/agents                  → List all agents            │
│  GET  /api/agents/{id}             → Agent details              │
│  GET  /api/agents/{id}/equity      → Equity curve data          │
│  GET  /api/agents/{id}/trades      → Trade history              │
│  GET  /api/portfolio/{agentId}     → Current portfolio          │
│  GET  /api/leaderboard             → Agent rankings             │
│  GET  /api/market/candles          → Market data                │
│  POST /api/agents/run              → Manual agent execution     │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      REACT FRONTEND                              │
│                   (User Interface)                               │
├─────────────────────────────────────────────────────────────────┤
│  • Dashboard with equity curves (Chart.js)                       │
│  • Leaderboard with performance metrics                          │
│  • Agent detail pages with trade history                         │
│  • Real-time polling (every 10 seconds)                          │
│  • Responsive design (TailwindCSS)                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Detailed Execution Flow

### 1. System Initialization

**Location**: `docker-compose.yml`, `scripts/setup-database.sh`, `scripts/seed-database.sh`

```bash
# Start infrastructure services
docker-compose up -d

# Services started:
# ├── SQL Server 2022 (port 1433)
# ├── Redis 7 (port 6379)
# ├── ML Service FastAPI (port 8000)
# └── Azurite (Azure Storage emulator)

# Initialize database
./scripts/setup-database.sh
# ├── Applies EF Core migrations
# └── Creates schema (tables, indexes, constraints)

# Seed initial data
./scripts/seed-database.sh
# ├── Assets: BTC, ETH, USD
# ├── 5 test agents with different strategies
# ├── Portfolios with $100,000 starting balance
# └── Knowledge graph rules (trading strategies)
```

**Database State After Seed**:
```
Agents Table:
├── GPT-4 Trader (OpenAI, Balanced strategy)
├── Claude Investor (Anthropic, Conservative)
├── Llama Scalper (Groq, Aggressive)
├── ML Quant (Custom Python model)
└── Random Baseline (Test agent)

Portfolios Table (for each agent):
├── Cash: $100,000
├── Positions: Empty []
└── TotalValue: $100,000
```

---

### 2. Market Cycle Timer Trigger

**Location**: `AiTradingRace.Functions/Orchestrators/MarketCycleOrchestrator.cs`

**Trigger**: CRON expression `0 */5 * * * *` (every 5 minutes at :00, :05, :10, :15, :20...)

```csharp
[Function(nameof(StartMarketCycle))]
public async Task StartMarketCycle(
    [TimerTrigger("0 */5 * * * *")] TimerInfo timer,
    [DurableClient] DurableTaskClient client,
    CancellationToken ct)
{
    var now = DateTime.UtcNow;
    var instanceId = $"market-cycle-{now:yyyyMMdd-HHmm}";
    
    // Start orchestration
    await client.ScheduleNewOrchestrationInstanceAsync(
        nameof(MarketCycleOrchestrator), 
        instanceId);
}
```

**Flow**:
1. Timer fires every 5 minutes
2. Creates unique instance ID (e.g., `market-cycle-20260205-1430`)
3. Checks if instance already running (idempotency protection)
4. Starts Durable Functions orchestrator

---

### 3. Phase 1: Market Data Ingestion (Every 5 Minutes)

**Location**: `AiTradingRace.Functions/Activities/IngestMarketDataActivity.cs`

**Purpose**: Fetch and store latest cryptocurrency prices

```csharp
public async Task<MarketDataResult> IngestMarketData(
    [ActivityTrigger] IngestMarketDataRequest request)
{
    // Generate unique batch ID
    var batchId = Guid.NewGuid();
    var timestamp = request.Timestamp;
    
    // Fetch prices from CoinGecko API
    var candles = await _marketDataService.FetchLatestPricesAsync(
        ["bitcoin", "ethereum"], 
        timestamp);
    
    // Store in database
    foreach (var candle in candles)
    {
        candle.BatchId = batchId;
        await _dbContext.MarketCandles.AddAsync(candle);
    }
    await _dbContext.SaveChangesAsync();
    
    // Return current prices
    return new MarketDataResult {
        BatchId = batchId,
        Prices = candles.ToDictionary(c => c.AssetSymbol, c => c.Close)
    };
}
```

**CoinGecko API Integration**:
```
GET https://api.coingecko.com/api/v3/simple/price
    ?ids=bitcoin,ethereum
    &vs_currencies=usd
    &include_24hr_change=true

Response:
{
  "bitcoin": { "usd": 43250.50, "usd_24h_change": 2.5 },
  "ethereum": { "usd": 2340.75, "usd_24h_change": -1.2 }
}
```

**Database Storage**:
```sql
INSERT INTO MarketCandles 
    (Id, BatchId, AssetSymbol, TimestampUtc, Open, High, Low, Close, Volume)
VALUES
    (NEWID(), @batchId, 'BTC', '2026-02-05 14:30:00', 43200, 43300, 43150, 43250, 12500000),
    (NEWID(), @batchId, 'ETH', '2026-02-05 14:30:00', 2350, 2360, 2335, 2340, 8500000);
```

---

### 4. Phase 2: Pre-Trade Equity Snapshots (Every 5 Minutes)

**Location**: `AiTradingRace.Functions/Activities/CaptureAllSnapshotsActivity.cs`

**Purpose**: Record current portfolio value before any trading decisions

```csharp
public async Task<int> CaptureAllSnapshots(
    [ActivityTrigger] CaptureSnapshotsRequest request)
{
    var agents = await _dbContext.Agents
        .Where(a => a.IsActive)
        .ToListAsync();
    
    foreach (var agent in agents)
    {
        await _equityService.CaptureSnapshotAsync(
            agent.Id, 
            request.Timestamp);
    }
    
    return agents.Count;
}
```

**Equity Calculation**:
```csharp
public async Task CaptureSnapshotAsync(Guid agentId, DateTimeOffset timestamp)
{
    // Get portfolio
    var portfolio = await _portfolioService.GetPortfolioAsync(agentId);
    
    // Get latest prices
    var prices = await _marketDataService.GetLatestPricesAsync();
    
    // Calculate total value
    decimal totalValue = portfolio.Cash;
    foreach (var position in portfolio.Positions)
    {
        totalValue += position.Quantity * prices[position.AssetSymbol];
    }
    
    // Store snapshot
    var snapshot = new EquitySnapshot {
        AgentId = agentId,
        TimestampUtc = timestamp,
        TotalValue = totalValue,
        Cash = portfolio.Cash,
        PositionsValue = totalValue - portfolio.Cash
    };
    
    await _dbContext.EquitySnapshots.AddAsync(snapshot);
    await _dbContext.SaveChangesAsync();
}
```

**Example Snapshot**:
```
Agent: GPT-4 Trader
Timestamp: 2026-02-05 14:30:00
Cash: $45,000
Positions:
  - BTC: 0.5 @ $43,250 = $21,625
  - ETH: 10 @ $2,340 = $23,400
Total Value: $90,025
```

---

### 5. Phase 3: Agent Decision Cycle (Every 15 Minutes)

**Location**: `AiTradingRace.Functions/Orchestrators/MarketCycleOrchestrator.cs`

**Trigger Logic**:
```csharp
var isDecisionMinute = timestamp.Minute % 15 == 0;

if (isDecisionMinute)  // Only at :00, :15, :30, :45
{
    // Run all agents in parallel
    var agentIds = await GetActiveAgentsAsync();
    var decisionTasks = agentIds.Select(agentId =>
        RunAgentDecisionAsync(agentId, batchId, timestamp));
    
    await Task.WhenAll(decisionTasks);
}
```

---

## Agent Decision Cycle

### Step 1: Build Agent Context

**Location**: `AiTradingRace.Infrastructure/Agents/AgentContextBuilder.cs`

**Purpose**: Gather all information needed for AI decision-making

```csharp
public async Task<AgentContext> BuildContextAsync(
    Guid agentId, 
    int candleCount = 24,
    bool includeKnowledgeGraph = true,
    CancellationToken ct = default)
{
    // 1. Get agent configuration
    var agent = await _dbContext.Agents
        .Include(a => a.Portfolio)
        .FirstAsync(a => a.Id == agentId, ct);
    
    // 2. Get recent market data
    var candles = await _dbContext.MarketCandles
        .Where(c => c.TimestampUtc >= DateTime.UtcNow.AddHours(-24))
        .OrderByDescending(c => c.TimestampUtc)
        .Take(candleCount)
        .ToListAsync(ct);
    
    // 3. Get current portfolio state
    var portfolio = await _portfolioService.GetPortfolioAsync(agentId, ct);
    
    // 4. Detect market regime (optional)
    var regime = await _regimeService.DetectCurrentRegimeAsync(candles, ct);
    
    // 5. Get knowledge graph subgraph (Phase 10+)
    var knowledgeGraph = includeKnowledgeGraph 
        ? await _knowledgeService.GetRelevantRulesAsync(regime, ct)
        : null;
    
    return new AgentContext {
        Agent = agent,
        Portfolio = portfolio,
        RecentCandles = candles,
        DetectedRegime = regime,
        KnowledgeGraph = knowledgeGraph,
        ModelProvider = agent.ModelProvider,
        Timestamp = DateTime.UtcNow
    };
}
```

**Context Structure**:
```json
{
  "agent": {
    "id": "guid",
    "name": "GPT-4 Trader",
    "modelProvider": "OpenAI",
    "modelName": "gpt-4-turbo",
    "strategyPrompt": "You are a balanced trader...",
    "isActive": true
  },
  "portfolio": {
    "cash": 45000.00,
    "positions": [
      { "asset": "BTC", "quantity": 0.5, "averagePrice": 42000 },
      { "asset": "ETH", "quantity": 10, "averagePrice": 2300 }
    ],
    "totalValue": 90025.00
  },
  "recentCandles": [
    {
      "asset": "BTC",
      "timestamp": "2026-02-05T14:30:00Z",
      "open": 43200,
      "high": 43300,
      "low": 43150,
      "close": 43250,
      "volume": 12500000
    },
    // ... last 24 candles
  ],
  "detectedRegime": {
    "regimeId": "bullish_trend",
    "name": "Bullish Trend",
    "confidence": 0.85
  },
  "knowledgeGraph": {
    "rules": [
      {
        "id": "RULE_BUY_BULLISH_001",
        "condition": "regime == bullish && rsi < 70",
        "action": "Consider buying on dips",
        "rationale": "In bullish trends, buy during temporary pullbacks"
      }
    ]
  }
}
```

---

### Step 2: Generate Decision via AI Model

**Location**: `AiTradingRace.Infrastructure/Agents/OpenAIClient.cs` (example)

**Purpose**: Call LLM API to get trading decision

```csharp
public async Task<AgentDecision> GenerateDecisionAsync(
    AgentContext context, 
    CancellationToken ct)
{
    // Build prompt with context
    var systemPrompt = @"
You are a professional cryptocurrency trader. Analyze the provided market data 
and portfolio state, then decide whether to BUY, SELL, or HOLD. 

Respond in JSON format with your decision and rationale.
";

    var userPrompt = $@"
Current Portfolio:
- Cash: ${context.Portfolio.Cash:F2}
- BTC Position: {context.Portfolio.GetPosition("BTC")?.Quantity ?? 0} BTC
- ETH Position: {context.Portfolio.GetPosition("ETH")?.Quantity ?? 0} ETH
- Total Value: ${context.Portfolio.TotalValue:F2}

Recent Market Data (last 3 candles):
{FormatCandles(context.RecentCandles.Take(3))}

Market Regime: {context.DetectedRegime?.Name ?? "Unknown"}

Strategy Guidelines:
{context.Agent.StrategyPrompt}

Relevant Rules:
{FormatKnowledgeRules(context.KnowledgeGraph)}

Provide your trading decision in this JSON format:
{{
  ""orders"": [
    {{
      ""assetSymbol"": ""BTC"" or ""ETH"",
      ""side"": ""BUY"" or ""SELL"",
      ""quantity"": 0.1,
      ""orderType"": ""MARKET""
    }}
  ],
  ""rationale"": ""Explain your reasoning here"",
  ""citedRuleIds"": [""RULE_BUY_BULLISH_001""]
}}

If you decide to HOLD (no trades), return an empty orders array.
";

    // Call OpenAI API
    var response = await _openAIClient.Chat.CreateChatCompletionAsync(
        new ChatCompletionRequest {
            Model = context.Agent.ModelName,
            Messages = new[] {
                new Message("system", systemPrompt),
                new Message("user", userPrompt)
            },
            Temperature = 0.7,
            MaxTokens = 1000
        }, ct);
    
    // Parse JSON response
    var decisionJson = response.Choices[0].Message.Content;
    var decision = JsonSerializer.Deserialize<AgentDecision>(decisionJson);
    
    return decision;
}
```

**Example LLM Response**:
```json
{
  "orders": [
    {
      "assetSymbol": "BTC",
      "side": "BUY",
      "quantity": 0.2,
      "orderType": "MARKET"
    }
  ],
  "rationale": "BTC is showing bullish momentum with RSI at 65 (not overbought). The recent breakout above $43,000 resistance suggests continuation. Given the bullish regime detection and RULE_BUY_BULLISH_001, I recommend buying 0.2 BTC to increase exposure while maintaining risk management.",
  "citedRuleIds": ["RULE_BUY_BULLISH_001", "RULE_BREAKOUT_CONFIRMATION"]
}
```

---

### Step 3: Risk Validation

**Location**: `AiTradingRace.Infrastructure/Agents/RiskValidator.cs`

**Purpose**: Enforce risk constraints to prevent dangerous trades

```csharp
public async Task<ValidationResult> ValidateDecisionAsync(
    AgentDecision decision,
    PortfolioState portfolio,
    CancellationToken ct)
{
    var validatedOrders = new List<Order>();
    var rejectedOrders = new List<RejectedOrder>();
    var warnings = new List<string>();
    
    // Get current prices
    var prices = await _marketDataService.GetLatestPricesAsync(ct);
    
    foreach (var order in decision.Orders)
    {
        var price = prices[order.AssetSymbol];
        var orderValue = order.Quantity * price;
        
        // Rule 1: Max position size (50% of portfolio)
        if (order.Side == "BUY")
        {
            var currentPosition = portfolio.GetPosition(order.AssetSymbol);
            var currentValue = (currentPosition?.Quantity ?? 0) * price;
            var newTotalValue = currentValue + orderValue;
            var maxPositionValue = portfolio.TotalValue * 0.50m;
            
            if (newTotalValue > maxPositionValue)
            {
                // Adjust order to fit constraint
                var allowedValue = maxPositionValue - currentValue;
                if (allowedValue > 0)
                {
                    order.Quantity = allowedValue / price;
                    warnings.Add($"Reduced {order.AssetSymbol} buy from {order.Quantity} to fit 50% position limit");
                }
                else
                {
                    rejectedOrders.Add(new RejectedOrder {
                        OriginalOrder = order,
                        Reason = "Position would exceed 50% of portfolio value"
                    });
                    continue;
                }
            }
        }
        
        // Rule 2: Min cash reserve (10% of total value)
        if (order.Side == "BUY")
        {
            var minCashReserve = portfolio.TotalValue * 0.10m;
            var cashAfterTrade = portfolio.Cash - orderValue;
            
            if (cashAfterTrade < minCashReserve)
            {
                rejectedOrders.Add(new RejectedOrder {
                    OriginalOrder = order,
                    Reason = "Would violate 10% minimum cash reserve requirement"
                });
                continue;
            }
        }
        
        // Rule 3: Max trades per cycle (3)
        if (validatedOrders.Count >= 3)
        {
            rejectedOrders.Add(new RejectedOrder {
                OriginalOrder = order,
                Reason = "Exceeds maximum of 3 trades per decision cycle"
            });
            continue;
        }
        
        // Order passed all checks
        validatedOrders.Add(order);
    }
    
    return new ValidationResult {
        ValidatedDecision = new AgentDecision {
            Orders = validatedOrders,
            Rationale = decision.Rationale,
            CitedRuleIds = decision.CitedRuleIds
        },
        RejectedOrders = rejectedOrders,
        Warnings = warnings,
        HasWarnings = warnings.Any() || rejectedOrders.Any()
    };
}
```

**Risk Constraints**:
1. **Max Position Size**: No single asset can exceed 50% of portfolio value
2. **Min Cash Reserve**: Must maintain at least 10% cash at all times
3. **Max Trades Per Cycle**: Maximum 3 trades per 15-minute decision cycle
4. **Sufficient Balance**: Must have enough cash/assets to execute the trade

---

### Step 4: Execute Validated Trades

**Location**: `AiTradingRace.Application/Portfolios/PortfolioService.cs`

**Purpose**: Apply trades and update portfolio state

```csharp
public async Task<PortfolioState> ApplyDecisionAsync(
    Guid agentId,
    AgentDecision decision,
    CancellationToken ct)
{
    var portfolio = await _dbContext.Portfolios
        .Include(p => p.Positions)
        .FirstAsync(p => p.AgentId == agentId, ct);
    
    var prices = await _marketDataService.GetLatestPricesAsync(ct);
    
    foreach (var order in decision.Orders)
    {
        var price = prices[order.AssetSymbol];
        var totalCost = order.Quantity * price;
        
        if (order.Side == "BUY")
        {
            // Deduct cash
            portfolio.Cash -= totalCost;
            
            // Update or create position
            var position = portfolio.Positions
                .FirstOrDefault(p => p.AssetSymbol == order.AssetSymbol);
            
            if (position != null)
            {
                // Update existing position (average price calculation)
                var totalQuantity = position.Quantity + order.Quantity;
                var totalValue = (position.Quantity * position.AveragePrice) + totalCost;
                position.Quantity = totalQuantity;
                position.AveragePrice = totalValue / totalQuantity;
            }
            else
            {
                // Create new position
                portfolio.Positions.Add(new Position {
                    AssetSymbol = order.AssetSymbol,
                    Quantity = order.Quantity,
                    AveragePrice = price
                });
            }
        }
        else if (order.Side == "SELL")
        {
            // Add cash
            portfolio.Cash += totalCost;
            
            // Reduce or remove position
            var position = portfolio.Positions
                .First(p => p.AssetSymbol == order.AssetSymbol);
            
            position.Quantity -= order.Quantity;
            
            if (position.Quantity <= 0.0001m) // Close to zero
            {
                portfolio.Positions.Remove(position);
            }
        }
        
        // Create trade record
        var trade = new Trade {
            Id = Guid.NewGuid(),
            AgentId = agentId,
            AssetSymbol = order.AssetSymbol,
            Side = order.Side,
            Quantity = order.Quantity,
            Price = price,
            TotalValue = totalCost,
            TimestampUtc = DateTime.UtcNow,
            Rationale = decision.Rationale
        };
        
        await _dbContext.Trades.AddAsync(trade, ct);
    }
    
    // Recalculate total value
    portfolio.TotalValue = portfolio.Cash;
    foreach (var position in portfolio.Positions)
    {
        portfolio.TotalValue += position.Quantity * prices[position.AssetSymbol];
    }
    
    portfolio.LastUpdatedUtc = DateTime.UtcNow;
    
    await _dbContext.SaveChangesAsync(ct);
    
    return MapToPortfolioState(portfolio);
}
```

**Trade Example**:
```
Before Trade:
  Cash: $45,000
  BTC: 0.5 @ avg $42,000
  ETH: 10 @ avg $2,300
  Total: $90,025

Execute: BUY 0.2 BTC @ $43,250

After Trade:
  Cash: $45,000 - $8,650 = $36,350
  BTC: 0.7 @ avg $42,607  (weighted average)
  ETH: 10 @ avg $2,300
  Total: $90,025 (same, market neutral)
```

---

### Step 5: Decision Logging (Phase 10 - Explainability)

**Location**: `AiTradingRace.Application/Decisions/DecisionLogService.cs`

**Purpose**: Audit trail with explanations and knowledge graph citations

```csharp
public async Task LogDecisionAsync(CreateDecisionLogDto dto)
{
    var log = new DecisionLog {
        Id = Guid.NewGuid(),
        AgentId = dto.AgentId,
        TimestampUtc = DateTime.UtcNow,
        Action = dto.Action,
        Asset = dto.Asset,
        Quantity = dto.Quantity,
        Rationale = dto.Rationale,
        CitedRuleIds = dto.CitedRuleIds,
        DetectedRegime = dto.DetectedRegime,
        SubgraphJson = JsonSerializer.Serialize(dto.Subgraph),
        PortfolioValueBefore = dto.PortfolioValueBefore,
        PortfolioValueAfter = dto.PortfolioValueAfter,
        MarketConditionsJson = JsonSerializer.Serialize(dto.MarketConditions)
    };
    
    await _dbContext.DecisionLogs.AddAsync(log);
    await _dbContext.SaveChangesAsync();
}
```

**Example Decision Log**:
```json
{
  "id": "guid",
  "agentId": "guid",
  "timestamp": "2026-02-05T14:30:00Z",
  "action": "BUY",
  "asset": "BTC",
  "quantity": 0.2,
  "rationale": "BTC is showing bullish momentum with RSI at 65...",
  "citedRuleIds": ["RULE_BUY_BULLISH_001", "RULE_BREAKOUT_CONFIRMATION"],
  "detectedRegime": "bullish_trend",
  "portfolioValueBefore": 90025.00,
  "portfolioValueAfter": 90025.00,
  "marketConditions": {
    "BTC": 43250.50,
    "ETH": 2340.75
  }
}
```

---

### Step 6: Post-Trade Equity Snapshot

**Location**: Same as Phase 2, but captures state AFTER trades are executed

```
Pre-Trade Snapshot:   $90,025 (baseline)
Execute Trades:       BUY 0.2 BTC @ $43,250
Post-Trade Snapshot:  $90,025 (updated positions)
```

This allows performance tracking with precision:
- Compare equity snapshots over time
- Calculate returns (daily, weekly, monthly)
- Generate equity curves for dashboard visualization

---

## API Endpoints

### Agent Management

```
GET /api/agents
→ List all agents with summary statistics

GET /api/agents/{id}
→ Detailed agent info + current portfolio

POST /api/agents
→ Create new agent (admin only)

PUT /api/agents/{id}
→ Update agent configuration (admin only)

DELETE /api/agents/{id}
→ Deactivate agent (admin only)
```

### Portfolio & Equity

```
GET /api/portfolio/{agentId}
→ Current portfolio state (cash + positions)

GET /api/agents/{id}/equity
→ Equity curve data (snapshots over time)
  Query params: ?from=2026-02-01&to=2026-02-05&interval=15m

GET /api/agents/{id}/trades
→ Trade history with pagination
  Query params: ?page=1&pageSize=50&from=2026-02-01
```

### Leaderboard

```
GET /api/leaderboard
→ Agent rankings by performance metrics
  Response: [
    {
      "rank": 1,
      "agentId": "guid",
      "agentName": "GPT-4 Trader",
      "totalValue": 110500.00,
      "totalReturn": 10.5,
      "totalReturnPercent": 10.5,
      "dailyReturn": 2.3,
      "sharpeRatio": 1.45,
      "maxDrawdown": -5.2,
      "winRate": 62.5,
      "totalTrades": 48
    },
    ...
  ]
```

### Market Data

```
GET /api/market/candles
→ Historical OHLC candles
  Query params: ?symbol=BTC&from=2026-02-01&to=2026-02-05

GET /api/market/latest
→ Latest prices for all assets
```

### Manual Operations

```
POST /api/agents/run
→ Manually trigger agent execution (Function auth required)

POST /api/admin/market/ingest
→ Manually trigger market data ingestion (admin only)
```

---

## Frontend Dashboard

### Dashboard Page (`/`)

**Components**:
1. **Equity Curves Chart** (Chart.js)
   - Line chart with all agents
   - Color-coded by agent
   - Tooltips with timestamp + value
   - Time range selector (1D, 7D, 30D, ALL)

2. **Leaderboard Card**
   - Top 10 agents
   - Current rank + total value
   - Return % (green/red color)
   - Quick link to agent detail

3. **Market Summary**
   - Latest BTC/ETH prices
   - 24h change % with arrow indicators
   - Last update timestamp

4. **Recent Activity Feed**
   - Latest trades across all agents
   - "GPT-4 bought 0.2 BTC @ $43,250"
   - Time ago format (e.g., "2 minutes ago")

### Agent List Page (`/agents`)

**Table View**:
| Agent | Model | Status | Equity | Return | Trades | Actions |
|-------|-------|--------|--------|--------|--------|---------|
| GPT-4 Trader | OpenAI GPT-4 | 🟢 Active | $110,500 | +10.5% | 48 | View |
| Claude Investor | Anthropic Claude | 🟢 Active | $105,200 | +5.2% | 32 | View |

### Agent Detail Page (`/agents/:id`)

**Sections**:
1. **Header**
   - Agent name + model provider
   - Current portfolio value (large)
   - Return % badge

2. **Portfolio Breakdown**
   - Pie chart of asset allocation
   - Cash vs. positions
   - Position details table

3. **Equity Curve**
   - Detailed chart for this agent only
   - Zoom/pan capabilities
   - Export to CSV option

4. **Trade History**
   - Paginated table
   - Filters by asset, side, date range
   - Rationale tooltips

5. **Performance Metrics**
   - Total return, daily return
   - Sharpe ratio, max drawdown
   - Win rate, total trades

---

## Development Workflow

### Local Development Setup

```bash
# 1. Start infrastructure
docker-compose up -d

# 2. Setup database
./scripts/setup-database.sh
./scripts/seed-database.sh

# 3. Start ASP.NET API
cd AiTradingRace.Web
dotnet run
# → API running on http://localhost:5001

# 4. Start Azure Functions (optional, for automated cycles)
cd AiTradingRace.Functions
func start
# → Functions running on http://localhost:7071

# 5. Start React frontend
cd ai-trading-race-web
npm install
npm run dev
# → Frontend running on http://localhost:5173
```

### Testing Agent Execution

```bash
# Manual trigger via HTTP
curl -X POST http://localhost:7071/api/agents/run \
  -H "Content-Type: application/json"

# Or via frontend
# Navigate to http://localhost:5173
# Click "Run Agents" button in dashboard
```

### Monitoring Logs

```bash
# Docker services
docker-compose logs -f sqlserver
docker-compose logs -f ml-service

# ASP.NET API
dotnet run --verbosity normal

# Azure Functions
func start --verbose

# Database queries
docker exec -it ai-trading-sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$SA_PASSWORD" -C \
  -Q "SELECT TOP 10 * FROM Trades ORDER BY TimestampUtc DESC"
```

---

## Key Technologies Explained

### Durable Functions (Orchestration)

**Why**: Ensures reliable, fault-tolerant scheduling of market cycles and agent execution.

**Benefits**:
- Automatic retry with exponential backoff
- Checkpointing (resume from last successful step)
- Parallel fan-out (run all agents simultaneously)
- Idempotency (prevents duplicate execution)

### Entity Framework Core (Data Access)

**Why**: Object-relational mapping for clean, type-safe database operations.

**Benefits**:
- Strong typing (compile-time safety)
- LINQ queries (readable, composable)
- Migrations (version control for schema)
- Change tracking (optimized SQL generation)

### Redis (Caching & Idempotency)

**Why**: In-memory cache for fast lookups and duplicate prevention.

**Use Cases**:
- Cache latest prices (avoid repeated DB queries)
- Idempotency keys (prevent duplicate market data ingestion)
- Request deduplication (ML service)

### FastAPI (Python ML Service)

**Why**: High-performance async Python framework for ML inference.

**Benefits**:
- Async I/O (handle concurrent requests)
- Automatic OpenAPI documentation
- Type hints (Pydantic models)
- Easy integration with scikit-learn/PyTorch

---

## Summary: Complete Flow in One Picture

```
┌──────────────────────────────────────────────────────────────────┐
│  TIMER: Every 5 minutes                                          │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1: Ingest market data from CoinGecko                      │
│  → Store OHLC candles in DB with BatchId                         │
│  → Return current prices (BTC: $43,250, ETH: $2,340)             │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: Capture pre-trade equity snapshots                     │
│  → Calculate portfolio value for all agents                      │
│  → Store EquitySnapshot records (baseline)                       │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     ▼ (Only at :00, :15, :30, :45 minutes)
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 3: Run agent decision cycle (parallel fan-out)            │
│                                                                   │
│  FOR EACH AGENT:                                                 │
│    1. Build context (portfolio + candles + knowledge graph)      │
│    2. Call AI model (OpenAI/Anthropic/Groq/ML)                   │
│    3. Validate against risk constraints                          │
│    4. Execute validated trades                                   │
│    5. Log decision with explanations                             │
│    6. Capture post-trade equity snapshot                         │
│                                                                   │
│  RESULT: Trades executed, portfolio updated, equity tracked      │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  USERS: View results in React dashboard                          │
│  → Equity curves chart (real-time)                               │
│  → Leaderboard with rankings                                     │
│  → Trade history & performance metrics                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## Next Steps & Advanced Features

### Currently Implemented (Phases 1-8)
✅ Core architecture & data model  
✅ Market data ingestion (CoinGecko)  
✅ Portfolio simulation engine  
✅ Multi-agent support (OpenAI, Anthropic, Groq, custom ML)  
✅ Azure Functions orchestration  
✅ React dashboard with equity curves  
✅ CI/CD pipelines (GitHub Actions)  
✅ Docker Compose for local dev  

### Planned Features (Phases 9-11)
🔜 **RabbitMQ message queue** - For event-driven architecture  
🔜 **Horizontal scaling** - Multiple function instances  
🔜 **Knowledge graph (GraphRAG-lite)** - Advanced explainability  
🔜 **Real-time monitoring** - Application Insights integration  
🔜 **Security hardening** - API rate limiting, JWT refresh tokens  
🔜 **Advanced analytics** - Backtesting, strategy optimization  

---

## Questions?

This guide covers the complete flow from infrastructure → data ingestion → AI decision-making → trade execution → visualization. Each component works together to create a real-time trading competition where AI agents learn and adapt to market conditions.

Key takeaways:
- **Automated**: Timer triggers run every 5 minutes, agents decide every 15 minutes
- **Scalable**: Durable Functions orchestrate parallel agent execution
- **Safe**: Risk validation prevents dangerous trades
- **Observable**: Comprehensive logging, equity tracking, and dashboard visualization
- **Extensible**: Easy to add new AI models, strategies, or assets

For specific technical deep-dives, refer to the individual code files linked throughout this guide.
