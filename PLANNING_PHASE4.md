# Phase 4 – Simulation Engine (Portfolio & PnL)

> **Objectif :** Être capable de simuler des trades et d'actualiser la valeur d'un portefeuille avec calcul de PnL.

---

## Current State Audit (16/01/2026)

### What Already Exists ✅

| Component                  | Location                            | Status                                                               |
| -------------------------- | ----------------------------------- | -------------------------------------------------------------------- |
| `Portfolio` entity         | `Domain/Entities/Portfolio.cs`      | ✅ Id, AgentId, Cash, BaseCurrency, Positions collection             |
| `Position` entity          | `Domain/Entities/Position.cs`       | ✅ Id, PortfolioId, MarketAssetId, Quantity, AverageEntryPrice       |
| `Trade` entity             | `Domain/Entities/Trade.cs`          | ✅ Id, PortfolioId, MarketAssetId, ExecutedAt, Quantity, Price, Side |
| `TradeSide` enum           | `Domain/Entities/TradeSide.cs`      | ✅ Buy, Sell, Hold                                                   |
| `EquitySnapshot` entity    | `Domain/Entities/EquitySnapshot.cs` | ✅ Id, PortfolioId, CapturedAt, TotalValue, UnrealizedPnL            |
| `IPortfolioService`        | `Application/Portfolios/`           | ✅ GetPortfolioAsync, ApplyDecisionAsync                             |
| `EfPortfolioService`       | `Infrastructure/Portfolios/`        | ✅ Full implementation with trade execution                          |
| `InMemoryPortfolioService` | `Infrastructure/Portfolios/`        | ✅ In-memory fallback                                                |
| `PortfolioState` record    | `Application/Common/Models/`        | ✅ DTO with positions, cash, total value                             |
| `AgentDecision` record     | `Application/Common/Models/`        | ✅ AgentId, CreatedAt, Orders                                        |
| `TradeOrder` record        | `Application/Common/Models/`        | ✅ AssetSymbol, Side, Quantity, LimitPrice                           |
| `TradingDbContext`         | `Infrastructure/Database/`          | ✅ All entities configured with relationships                        |
| Market data ingestion      | Phase 3                             | ✅ BTC/ETH candles available in DB                                   |

### What's Missing ❌

| Component                       | Required For Phase 4                               | Priority |
| ------------------------------- | -------------------------------------------------- | -------- |
| `IEquityService` interface      | Dedicated equity curve management                  | P0       |
| `EquityService` implementation  | Generate snapshots from portfolio + current prices | P0       |
| Equity API endpoint             | `GET /api/agents/{id}/equity` for frontend         | P0       |
| Portfolio API endpoints         | `GET /api/agents/{id}/portfolio`                   | P1       |
| Trades API endpoint             | `GET /api/agents/{id}/trades`                      | P1       |
| Portfolio creation endpoint     | Create portfolio for agent (if not exists)         | P1       |
| Manual trade execution endpoint | Testing purposes before AI integration             | P2       |
| Unit tests                      | Validate PnL calculations                          | P0       |
| Integration tests               | End-to-end portfolio operations                    | P1       |

---

## Proposed Changes

### Component 1: Application Layer – Equity Service Interface

Define a dedicated service for equity curve management.

#### [NEW] [IEquityService.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/Equity/IEquityService.cs)

```csharp
namespace AiTradingRace.Application.Equity;

public interface IEquityService
{
    /// <summary>
    /// Creates an equity snapshot for the agent's portfolio using current market prices.
    /// </summary>
    Task<EquitySnapshotDto> CaptureSnapshotAsync(
        Guid agentId,
        CancellationToken ct = default);

    /// <summary>
    /// Retrieves the equity curve (historical snapshots) for an agent.
    /// </summary>
    Task<IReadOnlyList<EquitySnapshotDto>> GetEquityCurveAsync(
        Guid agentId,
        DateTimeOffset? from = null,
        DateTimeOffset? to = null,
        CancellationToken ct = default);

    /// <summary>
    /// Gets the latest equity snapshot for an agent.
    /// </summary>
    Task<EquitySnapshotDto?> GetLatestSnapshotAsync(
        Guid agentId,
        CancellationToken ct = default);

    /// <summary>
    /// Calculates performance metrics for an agent.
    /// </summary>
    Task<PerformanceMetrics> CalculatePerformanceAsync(
        Guid agentId,
        CancellationToken ct = default);
}
```

---

#### [NEW] [EquitySnapshotDto.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/Common/Models/EquitySnapshotDto.cs)

```csharp
namespace AiTradingRace.Application.Common.Models;

public record EquitySnapshotDto(
    Guid Id,
    Guid PortfolioId,
    Guid AgentId,
    DateTimeOffset CapturedAt,
    decimal TotalValue,
    decimal CashValue,
    decimal PositionsValue,
    decimal UnrealizedPnL,
    decimal? PercentChange);
```

---

#### [NEW] [PerformanceMetrics.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/Common/Models/PerformanceMetrics.cs)

```csharp
namespace AiTradingRace.Application.Common.Models;

public record PerformanceMetrics(
    Guid AgentId,
    decimal InitialValue,
    decimal CurrentValue,
    decimal TotalReturn,
    decimal PercentReturn,
    decimal MaxDrawdown,
    decimal? SharpeRatio,
    int TotalTrades,
    int WinningTrades,
    int LosingTrades,
    decimal WinRate,
    DateTimeOffset CalculatedAt);
```

---

### Component 2: Infrastructure Layer – Equity Service Implementation

#### [NEW] [EquityService.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Equity/EquityService.cs)

**Responsibilities:**

1. Load portfolio with positions for an agent
2. Fetch latest market prices for all held assets
3. Calculate total portfolio value (cash + Σ(quantity × currentPrice))
4. Calculate unrealized PnL: Σ((currentPrice - averageEntryPrice) × quantity)
5. Persist `EquitySnapshot` to database
6. Calculate performance metrics (return %, max drawdown, win rate)

**Snapshot Capture Logic:**

```csharp
public async Task<EquitySnapshotDto> CaptureSnapshotAsync(Guid agentId, CancellationToken ct)
{
    var portfolio = await _dbContext.Portfolios
        .Include(p => p.Positions)
        .FirstOrDefaultAsync(p => p.AgentId == agentId, ct)
        ?? throw new InvalidOperationException($"No portfolio for agent {agentId}");

    var latestPrices = await GetLatestPricesAsync(ct);

    decimal positionsValue = 0;
    decimal unrealizedPnL = 0;

    foreach (var position in portfolio.Positions)
    {
        if (latestPrices.TryGetValue(position.MarketAssetId, out var price))
        {
            var posValue = position.Quantity * price;
            positionsValue += posValue;
            unrealizedPnL += (price - position.AverageEntryPrice) * position.Quantity;
        }
    }

    var totalValue = portfolio.Cash + positionsValue;

    var snapshot = new EquitySnapshot
    {
        Id = Guid.NewGuid(),
        PortfolioId = portfolio.Id,
        CapturedAt = DateTimeOffset.UtcNow,
        TotalValue = totalValue,
        UnrealizedPnL = unrealizedPnL
    };

    _dbContext.EquitySnapshots.Add(snapshot);
    await _dbContext.SaveChangesAsync(ct);

    return MapToDto(snapshot, portfolio, positionsValue);
}
```

**Max Drawdown Calculation:**

```csharp
private decimal CalculateMaxDrawdown(IReadOnlyList<EquitySnapshot> snapshots)
{
    if (snapshots.Count < 2) return 0;

    decimal peak = snapshots[0].TotalValue;
    decimal maxDrawdown = 0;

    foreach (var snapshot in snapshots)
    {
        if (snapshot.TotalValue > peak)
            peak = snapshot.TotalValue;

        var drawdown = (peak - snapshot.TotalValue) / peak;
        if (drawdown > maxDrawdown)
            maxDrawdown = drawdown;
    }

    return maxDrawdown;
}
```

---

### Component 3: Web API – Equity Controller

#### [NEW] [EquityController.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/Controllers/EquityController.cs)

```csharp
[ApiController]
[Route("api/agents/{agentId:guid}/equity")]
public class EquityController : ControllerBase
{
    private readonly IEquityService _equityService;

    public EquityController(IEquityService equityService)
    {
        _equityService = equityService;
    }

    /// <summary>
    /// Get the equity curve for an agent.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<EquitySnapshotDto>>> GetEquityCurve(
        Guid agentId,
        [FromQuery] DateTimeOffset? from,
        [FromQuery] DateTimeOffset? to,
        CancellationToken ct)
    {
        var curve = await _equityService.GetEquityCurveAsync(agentId, from, to, ct);
        return Ok(curve);
    }

    /// <summary>
    /// Get the latest equity snapshot for an agent.
    /// </summary>
    [HttpGet("latest")]
    public async Task<ActionResult<EquitySnapshotDto>> GetLatestSnapshot(
        Guid agentId,
        CancellationToken ct)
    {
        var snapshot = await _equityService.GetLatestSnapshotAsync(agentId, ct);
        if (snapshot == null)
            return NotFound(new { message = $"No equity snapshots found for agent {agentId}" });

        return Ok(snapshot);
    }

    /// <summary>
    /// Capture a new equity snapshot for an agent.
    /// </summary>
    [HttpPost("snapshot")]
    public async Task<ActionResult<EquitySnapshotDto>> CaptureSnapshot(
        Guid agentId,
        CancellationToken ct)
    {
        var snapshot = await _equityService.CaptureSnapshotAsync(agentId, ct);
        return CreatedAtAction(nameof(GetLatestSnapshot), new { agentId }, snapshot);
    }

    /// <summary>
    /// Get performance metrics for an agent.
    /// </summary>
    [HttpGet("performance")]
    public async Task<ActionResult<PerformanceMetrics>> GetPerformance(
        Guid agentId,
        CancellationToken ct)
    {
        var metrics = await _equityService.CalculatePerformanceAsync(agentId, ct);
        return Ok(metrics);
    }
}
```

---

### Component 4: Web API – Portfolio Controller

#### [NEW] [PortfolioController.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/Controllers/PortfolioController.cs)

```csharp
[ApiController]
[Route("api/agents/{agentId:guid}")]
public class PortfolioController : ControllerBase
{
    private readonly IPortfolioService _portfolioService;

    public PortfolioController(IPortfolioService portfolioService)
    {
        _portfolioService = portfolioService;
    }

    /// <summary>
    /// Get the current portfolio state for an agent.
    /// </summary>
    [HttpGet("portfolio")]
    public async Task<ActionResult<PortfolioState>> GetPortfolio(
        Guid agentId,
        CancellationToken ct)
    {
        var portfolio = await _portfolioService.GetPortfolioAsync(agentId, ct);
        return Ok(portfolio);
    }

    /// <summary>
    /// Execute trades for an agent (for testing purposes).
    /// </summary>
    [HttpPost("trades")]
    public async Task<ActionResult<PortfolioState>> ExecuteTrades(
        Guid agentId,
        [FromBody] ExecuteTradesRequest request,
        CancellationToken ct)
    {
        var decision = new AgentDecision(agentId, DateTimeOffset.UtcNow, request.Orders);
        var result = await _portfolioService.ApplyDecisionAsync(agentId, decision, ct);
        return Ok(result);
    }
}

public record ExecuteTradesRequest(IReadOnlyList<TradeOrderRequest> Orders);
public record TradeOrderRequest(string AssetSymbol, string Side, decimal Quantity, decimal? LimitPrice = null);
```

---

### Component 5: Web API – Trades Controller

#### [NEW] [TradesController.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/Controllers/TradesController.cs)

```csharp
[ApiController]
[Route("api/agents/{agentId:guid}/trades")]
public class TradesController : ControllerBase
{
    private readonly TradingDbContext _dbContext;

    public TradesController(TradingDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    /// <summary>
    /// Get trade history for an agent.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<TradeDto>>> GetTrades(
        Guid agentId,
        [FromQuery] int limit = 50,
        [FromQuery] int offset = 0,
        CancellationToken ct)
    {
        var trades = await _dbContext.Trades
            .Include(t => t.MarketAsset)
            .Where(t => t.Portfolio.AgentId == agentId)
            .OrderByDescending(t => t.ExecutedAt)
            .Skip(offset)
            .Take(limit)
            .Select(t => new TradeDto(
                t.Id,
                t.MarketAsset.Symbol,
                t.ExecutedAt,
                t.Quantity,
                t.Price,
                t.Side.ToString(),
                t.Quantity * t.Price))
            .ToListAsync(ct);

        return Ok(trades);
    }
}

public record TradeDto(
    Guid Id,
    string AssetSymbol,
    DateTimeOffset ExecutedAt,
    decimal Quantity,
    decimal Price,
    string Side,
    decimal TotalValue);
```

---

### Component 6: Web API – Agents Controller (Leaderboard)

#### [NEW] [AgentsController.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/Controllers/AgentsController.cs)

```csharp
[ApiController]
[Route("api/[controller]")]
public class AgentsController : ControllerBase
{
    private readonly TradingDbContext _dbContext;
    private readonly IEquityService _equityService;

    public AgentsController(TradingDbContext dbContext, IEquityService equityService)
    {
        _dbContext = dbContext;
        _equityService = equityService;
    }

    /// <summary>
    /// Get all agents with their current portfolio value.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<AgentSummaryDto>>> GetAgents(CancellationToken ct)
    {
        var agents = await _dbContext.Agents
            .Include(a => a.Portfolio)
            .ToListAsync(ct);

        var summaries = new List<AgentSummaryDto>();
        foreach (var agent in agents)
        {
            var latestSnapshot = await _equityService.GetLatestSnapshotAsync(agent.Id, ct);
            summaries.Add(new AgentSummaryDto(
                agent.Id,
                agent.Name,
                agent.Strategy,
                latestSnapshot?.TotalValue ?? 10000m,  // Default starting value
                latestSnapshot?.PercentChange ?? 0m,
                latestSnapshot?.CapturedAt ?? DateTimeOffset.UtcNow));
        }

        return Ok(summaries.OrderByDescending(a => a.TotalValue));
    }

    /// <summary>
    /// Get details for a specific agent.
    /// </summary>
    [HttpGet("{id:guid}")]
    public async Task<ActionResult<AgentDetailDto>> GetAgent(Guid id, CancellationToken ct)
    {
        var agent = await _dbContext.Agents
            .Include(a => a.Portfolio)
            .ThenInclude(p => p.Positions)
            .FirstOrDefaultAsync(a => a.Id == id, ct);

        if (agent == null)
            return NotFound();

        var latestSnapshot = await _equityService.GetLatestSnapshotAsync(id, ct);
        var performance = await _equityService.CalculatePerformanceAsync(id, ct);

        return Ok(new AgentDetailDto(
            agent.Id,
            agent.Name,
            agent.Strategy,
            latestSnapshot,
            performance));
    }
}

public record AgentSummaryDto(
    Guid Id,
    string Name,
    string Strategy,
    decimal TotalValue,
    decimal? PercentChange,
    DateTimeOffset LastUpdated);

public record AgentDetailDto(
    Guid Id,
    string Name,
    string Strategy,
    EquitySnapshotDto? LatestSnapshot,
    PerformanceMetrics? Performance);
```

---

### Component 7: Domain Entity Updates

#### [MODIFY] [Trade.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Domain/Entities/Trade.cs)

Add navigation property for MarketAsset:

```csharp
public class Trade
{
    public Guid Id { get; init; }
    public Guid PortfolioId { get; set; }
    public Guid MarketAssetId { get; set; }
    public DateTimeOffset ExecutedAt { get; set; }
    public decimal Quantity { get; set; }
    public decimal Price { get; set; }
    public TradeSide Side { get; set; } = TradeSide.Buy;

    // Navigation properties
    public Portfolio Portfolio { get; set; } = null!;
    public MarketAsset MarketAsset { get; set; } = null!;
}
```

#### [MODIFY] [EquitySnapshot.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Domain/Entities/EquitySnapshot.cs)

Add cash/positions breakdown and navigation:

```csharp
public class EquitySnapshot
{
    public Guid Id { get; init; }
    public Guid PortfolioId { get; set; }
    public DateTimeOffset CapturedAt { get; set; }
    public decimal TotalValue { get; set; }
    public decimal CashValue { get; set; }
    public decimal PositionsValue { get; set; }
    public decimal UnrealizedPnL { get; set; }

    // Navigation
    public Portfolio Portfolio { get; set; } = null!;
}
```

---

### Component 8: Dependency Injection Updates

#### [MODIFY] [InfrastructureServiceCollectionExtensions.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/DependencyInjection/InfrastructureServiceCollectionExtensions.cs)

Add registrations:

```csharp
// Equity service
services.AddScoped<IEquityService, EquityService>();
```

---

## Implementation Order

| Step | Task                                                    | Files                               | Priority | Status  |
| ---- | ------------------------------------------------------- | ----------------------------------- | -------- | ------- |
| 1    | Update domain entities (Trade, EquitySnapshot)          | Domain                              | P0       | ✅ Done |
| 2    | Create DTOs (`EquitySnapshotDto`, `PerformanceMetrics`) | Application/Common/Models           | P0       | ✅ Done |
| 3    | Create `IEquityService` interface                       | Application/Equity/                 | P0       | ✅ Done |
| 4    | Implement `EquityService`                               | Infrastructure/Equity/              | P0       | ✅ Done |
| 5    | Generate migration for entity changes                   | Infrastructure/Migrations/          | P0       | ✅ Done |
| 6    | Register services in DI                                 | Infrastructure/DependencyInjection/ | P0       | ✅ Done |
| 7    | Create `EquityController`                               | Web/Controllers/                    | P0       |         |
| 8    | Create `AgentsController`                               | Web/Controllers/                    | P1       |         |
| 9    | Create `PortfolioController`                            | Web/Controllers/                    | P1       |         |
| 10   | Create `TradesController`                               | Web/Controllers/                    | P1       |         |
| 11   | Add unit tests for EquityService                        | Tests/                              | P0       |         |
| 12   | Add integration tests                                   | Tests/                              | P1       |         |
| 13   | Manual verification via API                             | Swagger/curl                        | P0       |         |

---

## Verification Plan

### Automated Tests

#### Unit Tests to Create

1. **`EquityServiceTests`**

   - Test snapshot capture with mock prices
   - Test equity curve retrieval
   - Test max drawdown calculation
   - Test performance metrics (return %, win rate)
   - Test edge cases (no positions, no trades)

2. **`PortfolioServiceTests`** (extend existing)
   - Test buy trade execution
   - Test sell trade execution
   - Test insufficient funds handling
   - Test position averaging on multiple buys
   - Test PnL calculation (positive and negative)

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
2. Database migrated with market data from Phase 3
3. At least one agent seeded in the database

#### Steps

1. **Apply migrations:**

   ```bash
   cd AiTradingRace.Web
   dotnet ef database update -p ../AiTradingRace.Infrastructure
   ```

2. **Start the Web API:**

   ```bash
   cd AiTradingRace.Web
   dotnet run
   ```

3. **Get agents list (should show seeded agents):**

   ```bash
   curl https://localhost:7XXX/api/agents
   ```

   Expected: List of agents with default values

4. **Get portfolio for an agent:**

   ```bash
   curl https://localhost:7XXX/api/agents/{agentId}/portfolio
   ```

   Expected: Portfolio with $10,000 cash, empty positions

5. **Execute a manual BTC buy trade:**

   ```bash
   curl -X POST https://localhost:7XXX/api/agents/{agentId}/trades \
     -H "Content-Type: application/json" \
     -d '{"orders": [{"assetSymbol": "BTC", "side": "Buy", "quantity": 0.1}]}'
   ```

   Expected: Updated portfolio with BTC position, reduced cash

6. **Capture an equity snapshot:**

   ```bash
   curl -X POST https://localhost:7XXX/api/agents/{agentId}/equity/snapshot
   ```

   Expected: New snapshot with calculated total value

7. **Get the equity curve:**

   ```bash
   curl https://localhost:7XXX/api/agents/{agentId}/equity
   ```

   Expected: Array with at least one snapshot

8. **Execute a sell trade and verify PnL:**

   ```bash
   curl -X POST https://localhost:7XXX/api/agents/{agentId}/trades \
     -H "Content-Type: application/json" \
     -d '{"orders": [{"assetSymbol": "BTC", "side": "Sell", "quantity": 0.05}]}'
   ```

   Expected: Reduced BTC position, increased cash, new snapshot shows realized gain/loss

9. **Get performance metrics:**

   ```bash
   curl https://localhost:7XXX/api/agents/{agentId}/equity/performance
   ```

   Expected: Metrics including return %, max drawdown, trade statistics

10. **Verify in database:**

    ```sql
    -- Check equity snapshots
    SELECT
        es.CapturedAt,
        es.TotalValue,
        es.CashValue,
        es.PositionsValue,
        es.UnrealizedPnL
    FROM EquitySnapshots es
    JOIN Portfolios p ON es.PortfolioId = p.Id
    ORDER BY es.CapturedAt DESC;

    -- Check trades
    SELECT
        t.ExecutedAt,
        ma.Symbol,
        t.Side,
        t.Quantity,
        t.Price,
        t.Quantity * t.Price AS TotalValue
    FROM Trades t
    JOIN MarketAssets ma ON t.MarketAssetId = ma.Id
    ORDER BY t.ExecutedAt DESC;
    ```

---

## Exit Criteria

✅ Phase 4 is complete when:

1. [x] `IEquityService` interface created with snapshot/curve/performance methods
2. [x] `EquityService` implemented with EF Core persistence
3. [x] Domain entities updated (`Trade`, `EquitySnapshot` with navigation/extra fields)
4. [x] Migration generated and applied
5. [ ] `EquityController` with endpoints:
   - [ ] `GET /api/agents/{id}/equity` (curve)
   - [ ] `GET /api/agents/{id}/equity/latest` (latest snapshot)
   - [ ] `POST /api/agents/{id}/equity/snapshot` (capture)
   - [ ] `GET /api/agents/{id}/equity/performance` (metrics)
6. [ ] `AgentsController` with leaderboard endpoint
7. [ ] `PortfolioController` with portfolio/trades endpoints
8. [ ] `TradesController` with trade history endpoint
9. [x] DI registrations added
10. [ ] Unit tests for equity calculations pass
11. [ ] Manual verification passes (trades update portfolio, snapshots captured)

---

## Risks & Considerations

> [!WARNING] > **Concurrent Access:** Multiple equity snapshot captures or trade executions could cause race conditions. Consider adding optimistic concurrency tokens to Portfolio and Position entities.

> [!CAUTION] > **Price Staleness:** Equity calculations depend on latest market prices. If market data ingestion fails, PnL calculations will be stale. Add logging and health checks in Phase 6.

> [!IMPORTANT] > **Initial Portfolio Creation:** Ensure each agent has a portfolio created with starting capital before any trades. Consider auto-creating portfolios when capturing first snapshot.

### Performance Considerations

- **Equity Curve Queries:** For agents with many snapshots, add pagination support
- **Leaderboard:** Cache agent rankings if called frequently
- **Bulk Snapshots:** Consider batch snapshot capture for all agents (will be needed in Phase 6)

### Future Improvements (out of scope for Phase 4)

- Real-time WebSocket updates for portfolio changes
- Transaction history with realized P&L per trade
- Benchmark comparison (vs. HODL strategy)
- Risk metrics (Sharpe ratio, Sortino ratio, VaR)
- Multi-currency support

---

## API Summary

| Method | Endpoint                              | Description                         |
| ------ | ------------------------------------- | ----------------------------------- |
| GET    | `/api/agents`                         | List all agents with current values |
| GET    | `/api/agents/{id}`                    | Get agent details with performance  |
| GET    | `/api/agents/{id}/portfolio`          | Get current portfolio state         |
| POST   | `/api/agents/{id}/trades`             | Execute manual trades               |
| GET    | `/api/agents/{id}/trades`             | Get trade history                   |
| GET    | `/api/agents/{id}/equity`             | Get equity curve                    |
| GET    | `/api/agents/{id}/equity/latest`      | Get latest snapshot                 |
| POST   | `/api/agents/{id}/equity/snapshot`    | Capture new snapshot                |
| GET    | `/api/agents/{id}/equity/performance` | Get performance metrics             |
