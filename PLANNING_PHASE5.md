# Phase 5 – AI Agent Integration

> **Objectif :** Brancher un premier LLM (Azure OpenAI) et obtenir des décisions de trading exécutées automatiquement.

---

## Current State Audit (17/01/2026)

### What Already Exists ✅

| Component              | Location                     | Status                                             |
| ---------------------- | ---------------------------- | -------------------------------------------------- |
| `IAgentModelClient`    | `Application/Agents/`        | ✅ Interface defined (`GenerateDecisionAsync`)     |
| `IAgentRunner`         | `Application/Agents/`        | ✅ Interface defined (`RunAgentOnceAsync`)         |
| `EchoAgentModelClient` | `Infrastructure/Agents/`     | ✅ Stub (always returns HOLD)                      |
| `NoOpAgentRunner`      | `Infrastructure/Agents/`     | ✅ Stub (placeholder)                              |
| `AgentContext`         | `Application/Common/Models/` | ✅ AgentId, Portfolio, RecentCandles, Instructions |
| `AgentDecision`        | `Application/Common/Models/` | ✅ AgentId, CreatedAt, Orders                      |
| `AgentRunResult`       | `Application/Common/Models/` | ✅ Success, Message, EquitySnapshot                |
| `TradeOrder`           | `Application/Common/Models/` | ✅ AssetSymbol, Side, Quantity, LimitPrice         |
| `IPortfolioService`    | `Application/Portfolios/`    | ✅ ApplyDecisionAsync                              |
| `IEquityService`       | `Application/Equity/`        | ✅ CaptureSnapshotAsync                            |
| `EfMarketDataProvider` | `Infrastructure/MarketData/` | ✅ GetLatestCandlesAsync                           |
| Agent entity           | `Domain/Entities/Agent.cs`   | ✅ Id, Name, Strategy, Portfolio                   |
| Market data            | Phase 3                      | ✅ BTC/ETH candles in DB                           |
| Portfolio engine       | Phase 4                      | ✅ Trade execution with PnL                        |
| API endpoints          | Phase 4                      | ✅ Equity, trades, leaderboard                     |

### What's Missing ❌

| Component                          | Required For Phase 5             | Priority |
| ---------------------------------- | -------------------------------- | -------- |
| `AzureOpenAiAgentModelClient`      | Real LLM-based trading decisions | P0       |
| `AgentRunner` implementation       | Orchestrate context→LLM→trade    | P0       |
| Prompt template                    | Structured trading rules         | P0       |
| Response parsing (JSON→TradeOrder) | Handle LLM output reliably       | P0       |
| Agent execution endpoint           | `POST /api/agents/{id}/run`      | P0       |
| Agent entity updates               | `Instructions`, `ModelProvider`  | P1       |
| Configuration (API keys)           | Azure OpenAI connection          | P0       |
| **Server-side risk validator**     | Enforce limits independently     | P0       |
| Unit tests                         | Mock LLM responses               | P0       |
| Integration tests                  | End-to-end agent run             | P1       |

---

## Proposed Changes

### Component 1: Domain Entity Updates

#### [MODIFY] [Agent.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Domain/Entities/Agent.cs)

Add fields for agent configuration and AI provider:

```csharp
public class Agent
{
    public Guid Id { get; init; }
    public string Name { get; set; } = string.Empty;
    public string Strategy { get; set; } = string.Empty;

    // NEW: AI configuration
    public string Instructions { get; set; } = string.Empty;  // System prompt/rules
    public ModelProvider ModelProvider { get; set; } = ModelProvider.AzureOpenAI;
    public bool IsActive { get; set; } = true;

    // Navigation
    public Portfolio Portfolio { get; set; } = null!;
}
```

#### [NEW] [ModelProvider.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Domain/Entities/ModelProvider.cs)

```csharp
public enum ModelProvider
{
    AzureOpenAI,
    OpenAI,
    CustomML,  // For Phase 5b (Python)
    Mock       // For testing
}
```

---

### Component 2: Application Layer – Service Interfaces

#### [NEW] [IAgentContextBuilder.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/Agents/IAgentContextBuilder.cs)

Responsible for assembling the context sent to the LLM:

```csharp
public interface IAgentContextBuilder
{
    /// <summary>
    /// Builds the context object containing all info needed for agent decision.
    /// </summary>
    Task<AgentContext> BuildContextAsync(
        Guid agentId,
        int candleCount = 24,
        CancellationToken ct = default);
}
```

---

### Component 3: Infrastructure – Azure OpenAI Client

#### [NEW] [AzureOpenAiAgentModelClient.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Agents/AzureOpenAiAgentModelClient.cs)

**Responsibilities:**

1. Build prompt with trading rules and context
2. Call Azure OpenAI Chat Completions API
3. Parse JSON response into `AgentDecision`
4. Handle errors and retries

**Key Implementation:**

```csharp
public sealed class AzureOpenAiAgentModelClient : IAgentModelClient
{
    private readonly OpenAIClient _client;
    private readonly AzureOpenAiOptions _options;
    private readonly ILogger<AzureOpenAiAgentModelClient> _logger;

    public async Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken ct)
    {
        var systemPrompt = BuildSystemPrompt(context.Instructions);
        var userPrompt = BuildUserPrompt(context);

        var chatOptions = new ChatCompletionsOptions
        {
            DeploymentName = _options.DeploymentName,
            Messages =
            {
                new ChatRequestSystemMessage(systemPrompt),
                new ChatRequestUserMessage(userPrompt)
            },
            Temperature = 0.7f,
            MaxTokens = 500,
            ResponseFormat = ChatCompletionsResponseFormat.JsonObject
        };

        var response = await _client.GetChatCompletionsAsync(chatOptions, ct);
        var content = response.Value.Choices[0].Message.Content;

        return ParseDecision(context.AgentId, content);
    }
}
```

#### [NEW] [AzureOpenAiOptions.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Agents/AzureOpenAiOptions.cs)

```csharp
public class AzureOpenAiOptions
{
    public string Endpoint { get; set; } = string.Empty;
    public string ApiKey { get; set; } = string.Empty;
    public string DeploymentName { get; set; } = "gpt-4o";
}
```

---

### Component 4: Prompt Engineering

#### Prompt Template Structure

**System Prompt:**

```
You are a crypto trading AI agent. You analyze market data and make trading decisions.

RULES:
- You can only trade BTC and ETH against USD
- Maximum position size: 50% of portfolio per asset
- No leverage allowed
- Always respond with valid JSON

RESPONSE FORMAT:
{
  "reasoning": "Brief explanation of your decision",
  "orders": [
    {"action": "BUY|SELL|HOLD", "asset": "BTC|ETH", "quantity": 0.0}
  ]
}

If you don't want to trade, return an empty orders array or HOLD actions.

{AGENT_SPECIFIC_INSTRUCTIONS}
```

**User Prompt:**

```
Current Portfolio:
- Cash: ${cash} USD
- Positions: {positions_json}

Recent Market Data (last 24 candles):
{candles_json}

Current prices:
- BTC: ${btc_price}
- ETH: ${eth_price}

What is your trading decision?
```

---

### Component 5: Infrastructure – Agent Runner

#### [MODIFY] [AgentRunner.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Agents/AgentRunner.cs)

Replace `NoOpAgentRunner` with full implementation:

```csharp
public sealed class AgentRunner : IAgentRunner
{
    private readonly IAgentContextBuilder _contextBuilder;
    private readonly IAgentModelClient _modelClient;
    private readonly IPortfolioService _portfolioService;
    private readonly IEquityService _equityService;
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<AgentRunner> _logger;

    public async Task<AgentRunResult> RunAgentOnceAsync(
        Guid agentId,
        CancellationToken ct)
    {
        // 1. Build context
        var context = await _contextBuilder.BuildContextAsync(agentId, ct);

        // 2. Get decision from AI
        var decision = await _modelClient.GenerateDecisionAsync(context, ct);

        // 3. Validate and apply trades
        var portfolio = await _portfolioService.ApplyDecisionAsync(agentId, decision, ct);

        // 4. Capture equity snapshot
        var snapshot = await _equityService.CaptureSnapshotAsync(agentId, ct);

        // 5. Log execution
        _logger.LogInformation(
            "Agent {AgentId} executed {OrderCount} orders. New equity: {Equity}",
            agentId, decision.Orders.Count, snapshot.TotalValue);

        return new AgentRunResult(
            Success: true,
            Message: $"Executed {decision.Orders.Count} orders",
            EquitySnapshot: snapshot);
    }
}
```

---

### Component 6: Infrastructure – Context Builder

#### [NEW] [AgentContextBuilder.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Agents/AgentContextBuilder.cs)

```csharp
public sealed class AgentContextBuilder : IAgentContextBuilder
{
    private readonly TradingDbContext _dbContext;
    private readonly IPortfolioService _portfolioService;

    public async Task<AgentContext> BuildContextAsync(
        Guid agentId,
        int candleCount = 24,
        CancellationToken ct = default)
    {
        // Load agent with instructions
        var agent = await _dbContext.Agents
            .FirstOrDefaultAsync(a => a.Id == agentId, ct)
            ?? throw new InvalidOperationException($"Agent {agentId} not found");

        // Get current portfolio state
        var portfolio = await _portfolioService.GetPortfolioAsync(agentId, ct);

        // Get recent candles for all assets
        var candles = await _dbContext.MarketCandles
            .Include(c => c.MarketAsset)
            .Where(c => c.MarketAsset.IsEnabled)
            .OrderByDescending(c => c.TimestampUtc)
            .Take(candleCount * 2)  // 2 assets × candleCount
            .Select(c => new MarketCandleDto(
                c.MarketAsset.Symbol,
                c.TimestampUtc,
                c.Open, c.High, c.Low, c.Close, c.Volume))
            .ToListAsync(ct);

        return new AgentContext(
            agentId,
            portfolio,
            candles,
            agent.Instructions);
    }
}
```

---

### Component 7: Web API – Agent Execution Endpoint

#### [MODIFY] [AgentsController.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/Controllers/AgentsController.cs)

Add endpoint to run an agent:

```csharp
/// <summary>
/// Execute a single trading cycle for an agent.
/// </summary>
[HttpPost("{id:guid}/run")]
public async Task<ActionResult<AgentRunResult>> RunAgent(
    Guid id,
    CancellationToken ct)
{
    try
    {
        var result = await _agentRunner.RunAgentOnceAsync(id, ct);
        return Ok(result);
    }
    catch (InvalidOperationException ex)
    {
        return NotFound(new { message = ex.Message });
    }
}
```

---

### Component 8: Dependency Injection Updates

#### [MODIFY] [InfrastructureServiceCollectionExtensions.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/DependencyInjection/InfrastructureServiceCollectionExtensions.cs)

Add registrations:

```csharp
// Azure OpenAI configuration
services.Configure<AzureOpenAiOptions>(configuration.GetSection("AzureOpenAI"));

// Agent services
services.AddSingleton(sp =>
{
    var options = sp.GetRequiredService<IOptions<AzureOpenAiOptions>>().Value;
    return new OpenAIClient(
        new Uri(options.Endpoint),
        new AzureKeyCredential(options.ApiKey));
});

services.AddScoped<IAgentContextBuilder, AgentContextBuilder>();
services.AddScoped<IAgentModelClient, AzureOpenAiAgentModelClient>();
services.AddScoped<IAgentRunner, AgentRunner>();
```

---

### Component 9: Configuration

#### [MODIFY] [appsettings.json](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/appsettings.json)

Add Azure OpenAI configuration (secrets via user-secrets or Key Vault):

```json
{
  "AzureOpenAI": {
    "Endpoint": "https://<your-resource>.openai.azure.com/",
    "ApiKey": "", // Use user-secrets or Key Vault
    "DeploymentName": "gpt-4o"
  }
}
```

#### User Secrets

```bash
cd AiTradingRace.Web
dotnet user-secrets set "AzureOpenAI:Endpoint" "https://your-resource.openai.azure.com/"
dotnet user-secrets set "AzureOpenAI:ApiKey" "your-api-key"
dotnet user-secrets set "AzureOpenAI:DeploymentName" "gpt-4o"
```

---

### Component 10: Database Migration

#### New Migration

```bash
cd AiTradingRace.Web
dotnet ef migrations add AddAgentInstructionsAndProvider \
    -p ../AiTradingRace.Infrastructure
dotnet ef database update -p ../AiTradingRace.Infrastructure
```

---

### Component 11: Server-Side Risk Constraints ⚠️

> [!IMPORTANT] > **Never trust the LLM to follow trading rules.** All constraints must be enforced server-side before trade execution. The prompt rules are guidance only — the server is the source of truth.

#### [NEW] [IRiskValidator.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/Agents/IRiskValidator.cs)

Interface for validating agent decisions against risk rules:

```csharp
namespace AiTradingRace.Application.Agents;

public interface IRiskValidator
{
    /// <summary>
    /// Validates and sanitizes an agent decision against risk constraints.
    /// Returns a modified decision with invalid orders removed or adjusted.
    /// </summary>
    Task<TradeValidationResult> ValidateDecisionAsync(
        AgentDecision decision,
        PortfolioState portfolio,
        CancellationToken ct = default);
}
```

#### [NEW] [TradeValidationResult.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/Common/Models/TradeValidationResult.cs)

```csharp
namespace AiTradingRace.Application.Common.Models;

public record TradeValidationResult(
    AgentDecision ValidatedDecision,
    IReadOnlyList<RejectedOrder> RejectedOrders,
    bool HasWarnings);

public record RejectedOrder(
    TradeOrder OriginalOrder,
    string RejectionReason);
```

#### [NEW] [RiskValidatorOptions.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Agents/RiskValidatorOptions.cs)

Configurable risk limits:

```csharp
namespace AiTradingRace.Infrastructure.Agents;

public class RiskValidatorOptions
{
    /// <summary>
    /// Maximum percentage of portfolio value that can be allocated to a single asset.
    /// Default: 50% (0.50)
    /// </summary>
    public decimal MaxPositionSizePercent { get; set; } = 0.50m;

    /// <summary>
    /// Minimum cash reserve that must be maintained.
    /// Default: $100 USD
    /// </summary>
    public decimal MinCashReserve { get; set; } = 100m;

    /// <summary>
    /// Maximum trade value per single order.
    /// Default: $5,000 USD
    /// </summary>
    public decimal MaxSingleTradeValue { get; set; } = 5000m;

    /// <summary>
    /// Minimum order value (avoid dust trades).
    /// Default: $10 USD
    /// </summary>
    public decimal MinOrderValue { get; set; } = 10m;

    /// <summary>
    /// Allowed asset symbols for trading.
    /// </summary>
    public string[] AllowedAssets { get; set; } = ["BTC", "ETH"];

    /// <summary>
    /// Maximum number of orders per execution cycle.
    /// Default: 5
    /// </summary>
    public int MaxOrdersPerCycle { get; set; } = 5;

    /// <summary>
    /// Allow leverage (shorting/margin). Always false for this simulation.
    /// </summary>
    public bool AllowLeverage { get; set; } = false;

    /// <summary>
    /// Maximum price slippage tolerance (percent).
    /// Default: 2%
    /// </summary>
    public decimal MaxSlippagePercent { get; set; } = 0.02m;
}
```

#### [NEW] [RiskValidator.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Agents/RiskValidator.cs)

Full server-side validation implementation:

```csharp
namespace AiTradingRace.Infrastructure.Agents;

public sealed class RiskValidator : IRiskValidator
{
    private readonly RiskValidatorOptions _options;
    private readonly IMarketDataProvider _marketDataProvider;
    private readonly ILogger<RiskValidator> _logger;

    public RiskValidator(
        IOptions<RiskValidatorOptions> options,
        IMarketDataProvider marketDataProvider,
        ILogger<RiskValidator> logger)
    {
        _options = options.Value;
        _marketDataProvider = marketDataProvider;
        _logger = logger;
    }

    public async Task<TradeValidationResult> ValidateDecisionAsync(
        AgentDecision decision,
        PortfolioState portfolio,
        CancellationToken ct)
    {
        var validOrders = new List<TradeOrder>();
        var rejectedOrders = new List<RejectedOrder>();
        var latestPrices = await _marketDataProvider.GetLatestPricesAsync(ct);

        foreach (var order in decision.Orders.Take(_options.MaxOrdersPerCycle))
        {
            var validation = ValidateSingleOrder(order, portfolio, latestPrices);

            if (validation.IsValid)
            {
                validOrders.Add(validation.AdjustedOrder ?? order);
            }
            else
            {
                rejectedOrders.Add(new RejectedOrder(order, validation.Reason!));
                _logger.LogWarning(
                    "Order rejected for agent {AgentId}: {Asset} {Side} {Qty} - {Reason}",
                    decision.AgentId, order.AssetSymbol, order.Side, order.Quantity, validation.Reason);
            }
        }

        // Log if orders were truncated
        if (decision.Orders.Count > _options.MaxOrdersPerCycle)
        {
            _logger.LogWarning(
                "Agent {AgentId} submitted {Count} orders, truncated to {Max}",
                decision.AgentId, decision.Orders.Count, _options.MaxOrdersPerCycle);
        }

        var validatedDecision = new AgentDecision(
            decision.AgentId,
            decision.CreatedAt,
            validOrders);

        return new TradeValidationResult(
            validatedDecision,
            rejectedOrders,
            rejectedOrders.Count > 0);
    }

    private OrderValidation ValidateSingleOrder(
        TradeOrder order,
        PortfolioState portfolio,
        IReadOnlyDictionary<string, decimal> prices)
    {
        // 1. Check allowed assets
        if (!_options.AllowedAssets.Contains(order.AssetSymbol, StringComparer.OrdinalIgnoreCase))
        {
            return OrderValidation.Rejected($"Asset '{order.AssetSymbol}' not in allowed list");
        }

        // 2. Skip HOLD orders (valid but no action)
        if (order.Side == TradeSide.Hold)
        {
            return OrderValidation.Valid();
        }

        // 3. Get current price
        if (!prices.TryGetValue(order.AssetSymbol, out var currentPrice) || currentPrice <= 0)
        {
            return OrderValidation.Rejected($"No price available for '{order.AssetSymbol}'");
        }

        // 4. Validate quantity is positive
        if (order.Quantity <= 0)
        {
            return OrderValidation.Rejected("Quantity must be positive");
        }

        var orderValue = order.Quantity * currentPrice;

        // 5. Check minimum order value (avoid dust)
        if (orderValue < _options.MinOrderValue)
        {
            return OrderValidation.Rejected($"Order value ${orderValue:F2} below minimum ${_options.MinOrderValue}");
        }

        // 6. Check maximum single trade value
        if (orderValue > _options.MaxSingleTradeValue)
        {
            // Adjust quantity down to max allowed
            var adjustedQty = _options.MaxSingleTradeValue / currentPrice;
            return OrderValidation.ValidWithAdjustment(
                order with { Quantity = adjustedQty },
                $"Quantity reduced from {order.Quantity} to {adjustedQty:F8} (max trade value)");
        }

        if (order.Side == TradeSide.Buy)
        {
            return ValidateBuyOrder(order, portfolio, currentPrice, orderValue);
        }
        else // Sell
        {
            return ValidateSellOrder(order, portfolio);
        }
    }

    private OrderValidation ValidateBuyOrder(
        TradeOrder order,
        PortfolioState portfolio,
        decimal currentPrice,
        decimal orderValue)
    {
        // Check available cash (with reserve)
        var availableCash = portfolio.Cash - _options.MinCashReserve;
        if (orderValue > availableCash)
        {
            if (availableCash <= _options.MinOrderValue)
            {
                return OrderValidation.Rejected($"Insufficient funds: ${portfolio.Cash:F2} (reserve: ${_options.MinCashReserve})");
            }
            // Adjust to max affordable
            var adjustedQty = availableCash / currentPrice;
            return OrderValidation.ValidWithAdjustment(
                order with { Quantity = adjustedQty },
                $"Quantity reduced to affordable amount: {adjustedQty:F8}");
        }

        // Check max position size
        var currentPosition = portfolio.Positions
            .FirstOrDefault(p => p.Symbol.Equals(order.AssetSymbol, StringComparison.OrdinalIgnoreCase));
        var currentPositionValue = (currentPosition?.Quantity ?? 0) * currentPrice;
        var newPositionValue = currentPositionValue + orderValue;
        var maxAllowedValue = portfolio.TotalValue * _options.MaxPositionSizePercent;

        if (newPositionValue > maxAllowedValue)
        {
            var allowedBuyValue = maxAllowedValue - currentPositionValue;
            if (allowedBuyValue <= _options.MinOrderValue)
            {
                return OrderValidation.Rejected(
                    $"Position limit reached: {order.AssetSymbol} at {(currentPositionValue / portfolio.TotalValue):P0} of portfolio");
            }
            var adjustedQty = allowedBuyValue / currentPrice;
            return OrderValidation.ValidWithAdjustment(
                order with { Quantity = adjustedQty },
                $"Quantity reduced to respect {_options.MaxPositionSizePercent:P0} position limit");
        }

        return OrderValidation.Valid();
    }

    private OrderValidation ValidateSellOrder(TradeOrder order, PortfolioState portfolio)
    {
        // Check if we have the position
        var position = portfolio.Positions
            .FirstOrDefault(p => p.Symbol.Equals(order.AssetSymbol, StringComparison.OrdinalIgnoreCase));

        if (position == null || position.Quantity <= 0)
        {
            return OrderValidation.Rejected($"No {order.AssetSymbol} position to sell");
        }

        // No shorting allowed
        if (order.Quantity > position.Quantity)
        {
            if (!_options.AllowLeverage)
            {
                // Adjust to available quantity
                return OrderValidation.ValidWithAdjustment(
                    order with { Quantity = position.Quantity },
                    $"Sell quantity reduced to available: {position.Quantity}");
            }
            return OrderValidation.Rejected("Short selling not allowed");
        }

        return OrderValidation.Valid();
    }

    private record OrderValidation(bool IsValid, string? Reason, TradeOrder? AdjustedOrder)
    {
        public static OrderValidation Valid() => new(true, null, null);
        public static OrderValidation Rejected(string reason) => new(false, reason, null);
        public static OrderValidation ValidWithAdjustment(TradeOrder adjusted, string reason) =>
            new(true, reason, adjusted);
    }
}
```

---

#### Updated AgentRunner with Risk Validation

Update `AgentRunner` to include validation step:

```csharp
public sealed class AgentRunner : IAgentRunner
{
    private readonly IAgentContextBuilder _contextBuilder;
    private readonly IAgentModelClient _modelClient;
    private readonly IRiskValidator _riskValidator;  // NEW
    private readonly IPortfolioService _portfolioService;
    private readonly IEquityService _equityService;
    private readonly ILogger<AgentRunner> _logger;

    public async Task<AgentRunResult> RunAgentOnceAsync(Guid agentId, CancellationToken ct)
    {
        // 1. Build context
        var context = await _contextBuilder.BuildContextAsync(agentId, ct);

        // 2. Get decision from AI
        var rawDecision = await _modelClient.GenerateDecisionAsync(context, ct);

        // 3. ⚠️ VALIDATE against server-side risk constraints
        var validation = await _riskValidator.ValidateDecisionAsync(
            rawDecision,
            context.Portfolio,
            ct);

        if (validation.RejectedOrders.Count > 0)
        {
            _logger.LogWarning(
                "Agent {AgentId}: {Rejected} orders rejected, {Valid} orders accepted",
                agentId, validation.RejectedOrders.Count, validation.ValidatedDecision.Orders.Count);
        }

        // 4. Apply VALIDATED trades only
        var portfolio = await _portfolioService.ApplyDecisionAsync(
            agentId,
            validation.ValidatedDecision,  // Use validated decision
            ct);

        // 5. Capture equity snapshot
        var snapshot = await _equityService.CaptureSnapshotAsync(agentId, ct);

        return new AgentRunResult(
            Success: true,
            Message: $"Executed {validation.ValidatedDecision.Orders.Count} orders " +
                     $"({validation.RejectedOrders.Count} rejected)",
            EquitySnapshot: snapshot);
    }
}
```

---

#### Configuration in appsettings.json

```json
{
  "RiskValidator": {
    "MaxPositionSizePercent": 0.5,
    "MinCashReserve": 100,
    "MaxSingleTradeValue": 5000,
    "MinOrderValue": 10,
    "AllowedAssets": ["BTC", "ETH"],
    "MaxOrdersPerCycle": 5,
    "AllowLeverage": false,
    "MaxSlippagePercent": 0.02
  }
}
```

---

## Implementation Order

| Step | Task                                      | Files                               | Priority | Status  |
| ---- | ----------------------------------------- | ----------------------------------- | -------- | ------- |
| 1    | Add `ModelProvider` enum                  | Domain/Entities/                    | P0       | ✅ Done |
| 2    | Update `Agent` entity                     | Domain/Entities/Agent.cs            | P0       | ✅ Done |
| 3    | Generate and apply migration              | Infrastructure/Migrations/          | P0       | ✅ Done |
| 4    | Create `AzureOpenAiOptions`               | Infrastructure/Agents/              | P0       | ✅ Done |
| 5    | Create `IAgentContextBuilder` interface   | Application/Agents/                 | P0       | ✅ Done |
| 6    | Implement `AgentContextBuilder`           | Infrastructure/Agents/              | P0       | ✅ Done |
| 7    | Implement `AzureOpenAiAgentModelClient`   | Infrastructure/Agents/              | P0       | ✅ Done |
| 8    | **Create `IRiskValidator` interface**     | Application/Agents/                 | P0       | ✅ Done |
| 9    | **Create `RiskValidatorOptions`**         | Infrastructure/Agents/              | P0       | ✅ Done |
| 10   | **Implement `RiskValidator`**             | Infrastructure/Agents/              | P0       | ✅ Done |
| 11   | Implement `AgentRunner` (with validation) | Infrastructure/Agents/              | P0       | ✅ Done |
| 12   | Register services in DI                   | Infrastructure/DependencyInjection/ | P0       |         |
| 13   | Add `POST /api/agents/{id}/run` endpoint  | Web/Controllers/AgentsController.cs | P0       |         |
| 14   | Add configuration to appsettings          | Web/appsettings.json                | P0       |         |
| 15   | Add unit tests (incl. risk validator)     | Tests/                              | P0       |         |
| 16   | Add integration tests                     | Tests/                              | P1       |         |
| 17   | Manual verification                       | Swagger/curl                        | P0       |         |

---

## Verification Plan

### Automated Tests

#### Unit Tests to Create

1. **`AzureOpenAiAgentModelClientTests`**

   - Mock `OpenAIClient` to simulate responses
   - Test valid JSON parsing → `AgentDecision`
   - Test malformed JSON handling
   - Test empty orders array
   - Test rate limit/error handling

2. **`AgentContextBuilderTests`**

   - Test context building with mock DB
   - Test missing agent handling
   - Test candle aggregation

3. **`AgentRunnerTests`**

   - Mock `IAgentModelClient`, `IRiskValidator`, `IPortfolioService`, `IEquityService`
   - Test full execution flow
   - Test error propagation
   - Test logging behavior

4. **`RiskValidatorTests`** ⚠️
   - Test max position size enforcement
   - Test minimum order value rejection
   - Test order quantity adjustment (buy too much)
   - Test sell quantity capped to available position
   - Test disallowed asset rejection
   - Test insufficient funds handling
   - Test max orders per cycle truncation
   - Test short selling prevention
   - Test cash reserve enforcement

**Run Command:**

```bash
dotnet test AiTradingRace.Tests
```

---

### Manual Verification

> [!TIP]
> Use these steps to verify the feature works end-to-end.

#### Prerequisites

1. SQL Server running (Docker)
2. Azure OpenAI resource with deployed model (gpt-4o or gpt-35-turbo)
3. API key configured via user-secrets
4. Market data ingested (Phase 3)

#### Steps

1. **Configure Azure OpenAI secrets:**

   ```bash
   cd AiTradingRace.Web
   dotnet user-secrets set "AzureOpenAI:Endpoint" "https://your-resource.openai.azure.com/"
   dotnet user-secrets set "AzureOpenAI:ApiKey" "your-key"
   dotnet user-secrets set "AzureOpenAI:DeploymentName" "gpt-4o"
   ```

2. **Apply migrations:**

   ```bash
   dotnet ef database update -p ../AiTradingRace.Infrastructure
   ```

3. **Start the Web API:**

   ```bash
   dotnet run
   ```

4. **Run agent once:**

   ```bash
   curl -X POST https://localhost:7XXX/api/agents/{agentId}/run
   ```

   Expected: `AgentRunResult` with success=true, equity snapshot

5. **Verify trades were created:**

   ```bash
   curl https://localhost:7XXX/api/agents/{agentId}/trades
   ```

   Expected: New trades matching LLM decision

6. **Verify equity updated:**

   ```bash
   curl https://localhost:7XXX/api/agents/{agentId}/equity/latest
   ```

   Expected: Updated portfolio value

7. **Run multiple times and observe:**

   ```bash
   for i in {1..3}; do
       curl -X POST https://localhost:7XXX/api/agents/{agentId}/run
       sleep 2
   done
   ```

   Expected: Agent makes different decisions based on changing context

---

## Exit Criteria

✅ Phase 5 is complete when:

1. [x] `ModelProvider` enum created ✅ **17/01/2026**
2. [x] `Agent` entity updated with `Instructions`, `ModelProvider`, `Strategy` ✅ **17/01/2026**
3. [x] Migration generated and applied ✅ **17/01/2026** (`AddAgentInstructionsAndModelProvider`)
4. [x] `AzureOpenAiOptions` configuration class created ✅ **17/01/2026**
5. [x] `IAgentContextBuilder` interface and implementation created ✅ **17/01/2026**
6. [x] `AzureOpenAiAgentModelClient` implemented with: ✅ **17/01/2026**
   - [x] Prompt construction
   - [x] Azure OpenAI API call
   - [x] JSON response parsing
   - [x] Error handling
7. [x] **Server-side risk validation implemented:** ✅ **17/01/2026**
   - [x] `IRiskValidator` interface created
   - [x] `RiskValidatorOptions` with configurable limits
   - [x] `RiskValidator` enforces all constraints
   - [x] Orders adjusted/rejected before execution
8. [x] `AgentRunner` implemented with full orchestration + validation ✅ **17/01/2026**
9. [ ] `POST /api/agents/{id}/run` endpoint added
10. [ ] DI registrations updated
11. [ ] Configuration added (appsettings + user-secrets docs)
12. [ ] Unit tests pass (incl. `RiskValidatorTests`)
13. [ ] Manual verification passes (LLM generates trades, risky trades rejected)

---

## Risks & Considerations

> [!WARNING] > **API Costs:** Azure OpenAI calls are charged per token. Add rate limiting and cost tracking for production.

> [!CAUTION] > **Response Reliability:** LLMs may return invalid JSON or unexpected formats. Implement robust parsing with fallback to HOLD.

> [!IMPORTANT] > **Secrets Management:** Never commit API keys. Use `dotnet user-secrets` for dev and Azure Key Vault for production.

### Error Handling Strategy

| Error Type           | Handling                                 |
| -------------------- | ---------------------------------------- |
| Invalid JSON         | Return HOLD decision, log warning        |
| API timeout          | Retry once, then return HOLD             |
| Rate limit (429)     | Exponential backoff with max 3 retries   |
| Invalid trade values | Validate quantities, skip invalid orders |
| Insufficient funds   | Let `PortfolioService` reject the trade  |

### Performance Considerations

- Cache prompt templates (don't rebuild on every call)
- Consider streaming responses for faster perceived latency
- Add telemetry for API response times

---

## API Summary (Phase 5 Additions)

| Method | Endpoint               | Description        |
| ------ | ---------------------- | ------------------ |
| POST   | `/api/agents/{id}/run` | Execute agent once |

---

## Future Improvements (Out of Scope)

- Multiple LLM provider support (OpenAI, Anthropic, local models)
- Agent memory/conversation history
- Configurable trading rules per agent
- A/B testing between prompts
- Batch agent execution
