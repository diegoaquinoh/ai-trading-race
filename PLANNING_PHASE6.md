# Phase 6 – Azure Functions (Scheduler & Automation)

> **Objective:** Automate market data ingestion and agent execution cycles using Azure Functions timer triggers.

> **Prerequisites:** Phase 5b completed ✅ (LLM + ML agents, AgentRunner, RiskValidator, EquityService)

> **Date:** 18/01/2026

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           AZURE FUNCTIONS                                       │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌──────────────────────────┐          ┌──────────────────────────┐           │
│   │   MarketDataFunction     │          │   RunAgentsFunction      │           │
│   │   Timer: 0 */15 * * * *  │          │   Timer: 0 */30 * * * *  │           │
│   │   (every 15 min)         │          │   (every 30 min)         │           │
│   └────────────┬─────────────┘          └────────────┬─────────────┘           │
│                │                                      │                         │
│                ▼                                      ▼                         │
│   ┌──────────────────────────┐          ┌──────────────────────────┐           │
│   │ MarketDataIngestionSvc   │          │      AgentRunner         │           │
│   │ - Fetch CoinGecko OHLC   │          │ - Context building       │           │
│   │ - Dedupe & persist       │          │ - LLM/ML decision        │           │
│   └──────────────────────────┘          │ - Risk validation        │           │
│                                          │ - Trade execution        │           │
│                                          │ - Equity snapshot        │           │
│                                          └──────────────────────────┘           │
│                                                                                 │
│   ┌──────────────────────────┐          ┌──────────────────────────┐           │
│   │ EquitySnapshotFunction   │          │    HealthCheckFunction   │           │
│   │ Timer: 0 0 * * * *       │          │    HTTP trigger          │           │
│   │ (every hour)              │          │    /api/health           │           │
│   └──────────────────────────┘          └──────────────────────────┘           │
│                                                                                 │
└────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │          SQL Server Database         │
                    │  - MarketCandles                     │
                    │  - Agents                            │
                    │  - Trades                            │
                    │  - EquitySnapshots                   │
                    └─────────────────────────────────────┘
```

---

## Current State Audit

### What Already Exists ✅

| Component                     | Location                    | Status                                     |
| ----------------------------- | --------------------------- | ------------------------------------------ |
| `AiTradingRace.Functions`     | `/AiTradingRace.Functions/` | ✅ Isolated worker project scaffolded      |
| `Program.cs`                  | Functions project           | ✅ Basic DI setup                          |
| `host.json`                   | Functions project           | ✅ Configuration file                      |
| `local.settings.json.example` | Functions project           | ✅ Template for local settings             |
| `MarketDataFunction`          | Functions project           | ⚠️ Stub only (needs full implementation)   |
| `RunAgentsFunction`           | Functions project           | ⚠️ Stub only (needs full implementation)   |
| `IMarketDataIngestionService` | Application layer           | ✅ Interface ready                         |
| `MarketDataIngestionService`  | Infrastructure layer        | ✅ Full implementation                     |
| `IAgentRunner`                | Application layer           | ✅ Interface ready                         |
| `AgentRunner`                 | Infrastructure layer        | ✅ Full orchestration with risk validation |
| `IEquityService`              | Application layer           | ✅ Interface ready                         |
| `EquityService`               | Infrastructure layer        | ✅ Snapshot capture                        |
| DI extensions                 | Infrastructure layer        | ✅ `AddInfrastructureServices()`           |

### What's Missing ❌

| Component                 | Description                               | Priority |
| ------------------------- | ----------------------------------------- | -------- |
| `MarketDataFunction` full | Timer-triggered ingestion with logging    | P0       |
| `RunAgentsFunction` full  | Timer-triggered agent execution           | P0       |
| `EquitySnapshotFunction`  | Hourly equity snapshot for all agents     | P1       |
| `HealthCheckFunction`     | HTTP trigger for health/readiness         | P1       |
| `Program.cs` DI updates   | Register all services from Infrastructure | P0       |
| `local.settings.json`     | Connection strings, API keys              | P0       |
| Error handling & retries  | Resilient function execution              | P0       |
| Logging & telemetry       | Structured logging for monitoring         | P1       |
| Unit tests                | Function trigger tests                    | P1       |
| Integration tests         | End-to-end function tests                 | P2       |

---

## Proposed Changes

### Component 1: Functions Project DI Setup

#### [MODIFY] [Program.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Functions/Program.cs)

Update dependency injection to register all services:

```csharp
using AiTradingRace.Infrastructure.DependencyInjection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;

var host = new HostBuilder()
    .ConfigureFunctionsWorkerDefaults()
    .ConfigureAppConfiguration((context, config) =>
    {
        config.AddJsonFile("local.settings.json", optional: true, reloadOnChange: true);
        config.AddEnvironmentVariables();
    })
    .ConfigureServices((context, services) =>
    {
        var configuration = context.Configuration;

        // Register all infrastructure services (EF, MarketData, Portfolio, Agents)
        services.AddInfrastructureServicesWithTestAI(configuration);

        // Register logging
        services.AddLogging(builder =>
        {
            builder.AddConsole();
            builder.SetMinimumLevel(LogLevel.Information);
        });
    })
    .Build();

await host.RunAsync();
```

---

### Component 2: Market Data Ingestion Function

#### [MODIFY] [MarketDataFunction.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Functions/Functions/MarketDataFunction.cs)

Timer-triggered function to ingest market data (OHLC candles):

```csharp
using AiTradingRace.Application.MarketData;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

public class MarketDataFunction
{
    private readonly IMarketDataIngestionService _ingestionService;
    private readonly ILogger<MarketDataFunction> _logger;

    public MarketDataFunction(
        IMarketDataIngestionService ingestionService,
        ILogger<MarketDataFunction> logger)
    {
        _ingestionService = ingestionService;
        _logger = logger;
    }

    /// <summary>
    /// Ingest market data every 15 minutes.
    /// CRON: 0 */15 * * * * (second, minute, hour, day, month, day-of-week)
    /// </summary>
    [Function(nameof(IngestMarketData))]
    public async Task IngestMarketData(
        [TimerTrigger("0 */15 * * * *")] TimerInfo timer,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Market data ingestion started at {Time}. Next run at {NextRun}",
            DateTime.UtcNow,
            timer.ScheduleStatus?.Next);

        try
        {
            var result = await _ingestionService.IngestAllAssetsAsync(cancellationToken);

            _logger.LogInformation(
                "Market data ingestion completed. Inserted {Count} new candles for {Assets} assets",
                result.TotalCandlesInserted,
                result.AssetsProcessed);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Market data ingestion failed");
            throw; // Let Azure Functions handle retry
        }
    }
}
```

---

### Component 3: Agent Execution Function

#### [MODIFY] [RunAgentsFunction.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Functions/Functions/RunAgentsFunction.cs)

Timer-triggered function to run all active agents:

```csharp
using AiTradingRace.Application.Agents;
using AiTradingRace.Infrastructure.Persistence;
using Microsoft.Azure.Functions.Worker;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

public class RunAgentsFunction
{
    private readonly TradingDbContext _dbContext;
    private readonly IAgentRunner _agentRunner;
    private readonly ILogger<RunAgentsFunction> _logger;

    public RunAgentsFunction(
        TradingDbContext dbContext,
        IAgentRunner agentRunner,
        ILogger<RunAgentsFunction> logger)
    {
        _dbContext = dbContext;
        _agentRunner = agentRunner;
        _logger = logger;
    }

    /// <summary>
    /// Run all active agents every 30 minutes.
    /// CRON: 0 */30 * * * * (at minute 0 and 30 of every hour)
    /// </summary>
    [Function(nameof(RunAllAgents))]
    public async Task RunAllAgents(
        [TimerTrigger("0 */30 * * * *")] TimerInfo timer,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Agent execution cycle started at {Time}. Next run at {NextRun}",
            DateTime.UtcNow,
            timer.ScheduleStatus?.Next);

        var activeAgents = await _dbContext.Agents
            .Where(a => a.IsActive)
            .Select(a => new { a.Id, a.Name })
            .ToListAsync(cancellationToken);

        _logger.LogInformation("Found {Count} active agents to run", activeAgents.Count);

        var successCount = 0;
        var failureCount = 0;

        foreach (var agent in activeAgents)
        {
            try
            {
                _logger.LogInformation(
                    "Running agent {AgentName} ({AgentId})",
                    agent.Name, agent.Id);

                var result = await _agentRunner.RunAgentOnceAsync(agent.Id, cancellationToken);

                if (result.Success)
                {
                    successCount++;
                    _logger.LogInformation(
                        "Agent {AgentName} completed: {Message}. Equity: {Equity:C}",
                        agent.Name, result.Message, result.EquitySnapshot?.TotalValue ?? 0);
                }
                else
                {
                    failureCount++;
                    _logger.LogWarning(
                        "Agent {AgentName} completed with issues: {Message}",
                        agent.Name, result.Message);
                }
            }
            catch (Exception ex)
            {
                failureCount++;
                _logger.LogError(ex, "Agent {AgentName} ({AgentId}) failed", agent.Name, agent.Id);
                // Continue with next agent, don't fail entire batch
            }
        }

        _logger.LogInformation(
            "Agent execution cycle completed. Success: {Success}, Failures: {Failures}",
            successCount, failureCount);
    }
}
```

---

### Component 4: Equity Snapshot Function

#### [NEW] [EquitySnapshotFunction.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Functions/Functions/EquitySnapshotFunction.cs)

Hourly snapshot capture for all agents:

```csharp
using AiTradingRace.Application.Equity;
using AiTradingRace.Infrastructure.Persistence;
using Microsoft.Azure.Functions.Worker;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

public class EquitySnapshotFunction
{
    private readonly TradingDbContext _dbContext;
    private readonly IEquityService _equityService;
    private readonly ILogger<EquitySnapshotFunction> _logger;

    public EquitySnapshotFunction(
        TradingDbContext dbContext,
        IEquityService equityService,
        ILogger<EquitySnapshotFunction> logger)
    {
        _dbContext = dbContext;
        _equityService = equityService;
        _logger = logger;
    }

    /// <summary>
    /// Capture equity snapshots for all agents every hour.
    /// CRON: 0 0 * * * * (at the top of every hour)
    /// </summary>
    [Function(nameof(CaptureEquitySnapshots))]
    public async Task CaptureEquitySnapshots(
        [TimerTrigger("0 0 * * * *")] TimerInfo timer,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Equity snapshot capture started at {Time}",
            DateTime.UtcNow);

        var agents = await _dbContext.Agents
            .Where(a => a.IsActive)
            .Select(a => new { a.Id, a.Name })
            .ToListAsync(cancellationToken);

        var capturedCount = 0;

        foreach (var agent in agents)
        {
            try
            {
                var snapshot = await _equityService.CaptureSnapshotAsync(
                    agent.Id, cancellationToken);

                capturedCount++;
                _logger.LogDebug(
                    "Captured snapshot for {AgentName}: {Value:C}",
                    agent.Name, snapshot.TotalValue);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex,
                    "Failed to capture snapshot for agent {AgentName} ({AgentId})",
                    agent.Name, agent.Id);
            }
        }

        _logger.LogInformation(
            "Equity snapshot capture completed. Captured {Count}/{Total} snapshots",
            capturedCount, agents.Count);
    }
}
```

---

### Component 5: Health Check Function

#### [NEW] [HealthCheckFunction.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Functions/Functions/HealthCheckFunction.cs)

HTTP-triggered health check for monitoring:

```csharp
using AiTradingRace.Infrastructure.Persistence;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using System.Net;
using System.Text.Json;

namespace AiTradingRace.Functions.Functions;

public class HealthCheckFunction
{
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<HealthCheckFunction> _logger;

    public HealthCheckFunction(
        TradingDbContext dbContext,
        ILogger<HealthCheckFunction> logger)
    {
        _dbContext = dbContext;
        _logger = logger;
    }

    [Function(nameof(HealthCheck))]
    public async Task<HttpResponseData> HealthCheck(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", Route = "health")]
        HttpRequestData req,
        CancellationToken cancellationToken)
    {
        var healthStatus = new
        {
            Status = "Healthy",
            Timestamp = DateTime.UtcNow,
            Database = await CheckDatabaseAsync(cancellationToken),
            AgentCount = await GetActiveAgentCountAsync(cancellationToken),
            LatestCandle = await GetLatestCandleTimeAsync(cancellationToken)
        };

        var isHealthy = healthStatus.Database == "Connected";
        var response = req.CreateResponse(
            isHealthy ? HttpStatusCode.OK : HttpStatusCode.ServiceUnavailable);

        response.Headers.Add("Content-Type", "application/json");
        await response.WriteStringAsync(
            JsonSerializer.Serialize(healthStatus, new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            }),
            cancellationToken);

        return response;
    }

    private async Task<string> CheckDatabaseAsync(CancellationToken ct)
    {
        try
        {
            await _dbContext.Database.CanConnectAsync(ct);
            return "Connected";
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Database health check failed");
            return $"Error: {ex.Message}";
        }
    }

    private async Task<int> GetActiveAgentCountAsync(CancellationToken ct)
    {
        try
        {
            return await _dbContext.Agents.CountAsync(a => a.IsActive, ct);
        }
        catch
        {
            return -1;
        }
    }

    private async Task<DateTime?> GetLatestCandleTimeAsync(CancellationToken ct)
    {
        try
        {
            return await _dbContext.MarketCandles
                .MaxAsync(c => (DateTime?)c.TimestampUtc, ct);
        }
        catch
        {
            return null;
        }
    }
}
```

---

### Component 6: Configuration

#### [NEW] [local.settings.json](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Functions/local.settings.json)

> [!CAUTION]
> Do not commit secrets. Use Azure Key Vault in production.

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "dotnet-isolated"
  },
  "ConnectionStrings": {
    "TradingDb": "Server=localhost,1433;Database=AiTradingRace;User Id=sa;Password=YourStrong@Password;TrustServerCertificate=True"
  },
  "CoinGecko": {
    "BaseUrl": "https://api.coingecko.com/api/v3/",
    "TimeoutSeconds": 30,
    "DefaultDays": 1
  },
  "RiskValidator": {
    "MaxPositionSizePercent": 0.5,
    "MinCashReserve": 100,
    "MaxSingleTradeValue": 5000,
    "AllowedAssets": ["BTC", "ETH"]
  },
  "CustomMlAgent": {
    "BaseUrl": "http://localhost:8000",
    "TimeoutSeconds": 30,
    "ApiKey": "your-dev-api-key"
  }
}
```

---

### Component 7: Package References

#### [MODIFY] [AiTradingRace.Functions.csproj](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Functions/AiTradingRace.Functions.csproj)

Ensure correct packages:

```xml
<ItemGroup>
  <PackageReference Include="Microsoft.Azure.Functions.Worker" Version="1.22.0" />
  <PackageReference Include="Microsoft.Azure.Functions.Worker.Sdk" Version="1.17.4" />
  <PackageReference Include="Microsoft.Azure.Functions.Worker.Extensions.Timer" Version="4.3.1" />
  <PackageReference Include="Microsoft.Azure.Functions.Worker.Extensions.Http" Version="3.2.0" />
  <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.0" />
  <PackageReference Include="Microsoft.Extensions.Http" Version="8.0.0" />
</ItemGroup>

<ItemGroup>
  <ProjectReference Include="..\AiTradingRace.Application\AiTradingRace.Application.csproj" />
  <ProjectReference Include="..\AiTradingRace.Infrastructure\AiTradingRace.Infrastructure.csproj" />
</ItemGroup>
```

---

## Timer Schedule Summary

| Function                 | Schedule (CRON)  | Frequency        | Purpose                   |
| ------------------------ | ---------------- | ---------------- | ------------------------- |
| `IngestMarketData`       | `0 */15 * * * *` | Every 15 minutes | Fetch new OHLC candles    |
| `RunAllAgents`           | `0 */30 * * * *` | Every 30 minutes | Execute trading decisions |
| `CaptureEquitySnapshots` | `0 0 * * * *`    | Every hour       | Record portfolio values   |
| `HealthCheck`            | HTTP (on-demand) | On request       | Service health monitoring |

> [!NOTE]
> Azure Functions CRON uses 6 fields: `{second} {minute} {hour} {day} {month} {day-of-week}`

---

## Verification Plan

### Local Testing

1. **Start Azurite** (Azure storage emulator):

   ```bash
   azurite --silent --location ./azurite --debug ./azurite-debug.log
   ```

2. **Start SQL Server** (Docker):

   ```bash
   docker start sql-server-trading
   ```

3. **Start Python ML service** (if using CustomML agents):

   ```bash
   cd ai-trading-race-ml
   uvicorn app.main:app --reload --port 8000
   ```

4. **Run Functions locally**:

   ```bash
   cd AiTradingRace.Functions
   func start
   ```

5. **Verify endpoints**:
   - Health check: `curl http://localhost:7071/api/health`
   - Manually trigger (Azure Functions Core Tools)

### Expected Results

| Test                  | Expected Outcome                                             |
| --------------------- | ------------------------------------------------------------ |
| Health check endpoint | Returns 200 with database status, agent count, latest candle |
| Market data ingestion | Logs "Inserted X new candles"                                |
| Agent execution       | Logs "Success: X, Failures: 0" with equity values            |
| Equity snapshots      | Logs "Captured X/X snapshots"                                |

---

## Implementation Order

| Step | Task                               | Files                                         | Priority | Status |
| ---- | ---------------------------------- | --------------------------------------------- | -------- | ------ |
| 1    | Update `Program.cs` with full DI   | Functions/Program.cs                          | P0       | ⬜     |
| 2    | Update project references          | Functions/AiTradingRace.Functions.csproj      | P0       | ⬜     |
| 3    | Create `local.settings.json`       | Functions/local.settings.json                 | P0       | ⬜     |
| 4    | Implement `MarketDataFunction`     | Functions/Functions/MarketDataFunction.cs     | P0       | ⬜     |
| 5    | Implement `RunAgentsFunction`      | Functions/Functions/RunAgentsFunction.cs      | P0       | ⬜     |
| 6    | Implement `EquitySnapshotFunction` | Functions/Functions/EquitySnapshotFunction.cs | P1       | ⬜     |
| 7    | Implement `HealthCheckFunction`    | Functions/Functions/HealthCheckFunction.cs    | P1       | ⬜     |
| 8    | Test locally with Azurite          | Manual testing                                | P0       | ⬜     |
| 9    | Add unit tests for functions       | Tests project                                 | P1       | ⬜     |

---

## Exit Criteria

✅ **Phase 6 is complete when:**

- [ ] All four functions compile and run locally
- [ ] `MarketDataFunction` ingests candles on schedule (can be triggered manually)
- [ ] `RunAgentsFunction` executes all active agents without errors
- [ ] `EquitySnapshotFunction` captures snapshots for all agents
- [ ] `HealthCheckFunction` returns correct status
- [ ] Local testing with Azurite and SQL Server passes
- [ ] All existing tests continue to pass (`dotnet test`)

---

## Future Enhancements (Phase 8)

> [!TIP]
> The following are deferred to Phase 8 (Azure Deployment):

- **Azure Queue/Service Bus**: Decouple agent execution (one message per agent for scalability)
- **Azure Key Vault**: Secure connection strings and API keys
- **Application Insights**: Integrated monitoring and alerting
- **Retry policies**: Polly-based resilience for external API calls
- **Dead letter queue**: Handle consistently failing agents

---

## Dependencies

| Dependency                 | Version | Purpose                  |
| -------------------------- | ------- | ------------------------ |
| Azure Functions Worker     | 1.22.0  | Isolated process hosting |
| Azure Functions Worker SDK | 1.17.4  | Build tooling            |
| Timer Extensions           | 4.3.1   | Timer trigger support    |
| HTTP Extensions            | 3.2.0   | HTTP trigger support     |
| Azure Functions Core Tools | 4.x     | Local development        |
| Azurite                    | 3.x     | Local storage emulator   |

---

## Risks & Mitigations

| Risk                           | Impact | Mitigation                                   |
| ------------------------------ | ------ | -------------------------------------------- |
| CoinGecko rate limits          | Medium | 15-minute interval respects free tier limits |
| Agent execution takes too long | Medium | 30-minute interval provides ample buffer     |
| DB connection pool exhaustion  | Low    | Scoped DbContext per function invocation     |
| Python ML service unavailable  | Low    | Fallback to MockAgent if configured          |
| Azurite not running locally    | Low    | Clear setup instructions in README           |

---

## Related Documents

- [PLANNING_GLOBAL.md](file:///Users/diegoaquino/Projets/ai-trading-race/PLANNING_GLOBAL.md) — Overall project phases
- [PLANNING_PHASE5.md](file:///Users/diegoaquino/Projets/ai-trading-race/PLANNING_PHASE5.md) — LLM agent integration
- [PLANNING_PHASE5_B.md](file:///Users/diegoaquino/Projets/ai-trading-race/PLANNING_PHASE5_B.md) — Python ML service integration
- [RECAP.md](file:///Users/diegoaquino/Projets/ai-trading-race/RECAP.md) — Completed milestones
