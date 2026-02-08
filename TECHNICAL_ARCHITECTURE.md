# 🔧 Technical Architecture Deep Dive

## Orchestration, Consistency, Reliability & Fault Tolerance

This document provides an in-depth technical analysis of how the AI Trading Race system ensures reliable, consistent, and fault-tolerant operation across distributed components.

---

## Table of Contents

1. [Orchestration Pattern: Durable Functions](#orchestration-pattern-durable-functions)
2. [Data Consistency & Transactions](#data-consistency--transactions)
3. [Idempotency & Duplicate Prevention](#idempotency--duplicate-prevention)
4. [Fault Tolerance & Error Handling](#fault-tolerance--error-handling)
5. [Concurrency Control](#concurrency-control)
6. [Retry Mechanisms](#retry-mechanisms)
7. [State Management](#state-management)
8. [Monitoring & Observability](#monitoring--observability)

---

## 1. Orchestration Pattern: Durable Functions

### Why Durable Functions?

The system uses **Azure Durable Functions** (v4) with the Task Hub pattern to orchestrate complex, long-running workflows with guaranteed execution semantics.

#### Key Benefits:
- **Automatic checkpointing**: Progress is saved after each activity
- **Replay determinism**: Orchestrators can replay from checkpoints
- **Built-in retry logic**: Exponential backoff for transient failures
- **Parallel execution**: Fan-out/fan-in patterns for agent execution
- **State persistence**: Orchestration state survives process crashes

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        TIMER TRIGGER                             │
│              CRON: 0 */5 * * * * (Every 5 minutes)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MarketCycleOrchestrator                         │
│                  (Durable Orchestrator)                          │
│                                                                  │
│  Instance ID: market-cycle-{yyyyMMdd-HHmm}                      │
│  Idempotency: Check if already running before starting          │
│  State: Stored in Azurite (local) or Azure Storage (prod)       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────────┐                 ┌──────────────────────┐
│  Activity 1      │                 │  Activity 2          │
│  IngestMarket    │ ──Sequential──> │  CaptureSnapshots    │
│  Data            │                 │  (Pre-trade)         │
└──────────────────┘                 └──────────────────────┘
                                              │
                            ┌─────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │  Decision Cycle? │
                    │  (Every 15 min)  │
                    └────┬─────────────┘
                         │
            YES ─────────┤
                         │
                         ▼
        ┌────────────────────────────────┐
        │  Activity 3: GetActiveAgents   │
        └────────────┬───────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │    FAN-OUT (Parallel)          │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ RunAgentDecision(Agent1) │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ RunAgentDecision(Agent2) │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ┌──────────────────────────┐  │
        │  │ RunAgentDecision(Agent3) │  │
        │  └──────────────────────────┘  │
        │                                │
        │  ... (All agents in parallel)  │
        └────────────┬───────────────────┘
                     │
                     ▼ (FAN-IN)
        ┌────────────────────────────────┐
        │  Activity 4: ExecuteTrades     │
        └────────────┬───────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │  Activity 5: CaptureSnapshots  │
        │  (Post-trade)                  │
        └────────────────────────────────┘
```

### Code Analysis: Orchestrator Implementation

**File**: `AiTradingRace.Functions/Orchestrators/MarketCycleOrchestrator.cs`

#### 1. Timer-Based Instance Creation

```csharp
[Function(nameof(StartMarketCycle))]
public async Task StartMarketCycle(
    [TimerTrigger("0 */5 * * * *")] TimerInfo timer,
    [DurableClient] DurableTaskClient client,
    CancellationToken ct)
{
    var now = DateTime.UtcNow;
    var instanceId = $"market-cycle-{now:yyyyMMdd-HHmm}";

    // CRITICAL: Idempotency check before starting
    try
    {
        var existing = await client.GetInstanceAsync(instanceId, cancellation: ct);
        
        // If already running, skip to prevent duplicate execution
        if (existing?.RuntimeStatus == OrchestrationRuntimeStatus.Running ||
            existing?.RuntimeStatus == OrchestrationRuntimeStatus.Pending)
        {
            _logger.LogWarning(
                "Orchestration {InstanceId} already running (status: {Status}), skipping",
                instanceId, existing.RuntimeStatus);
            return;
        }
    }
    catch (Exception ex)
    {
        // Instance doesn't exist, which is expected for first run
        _logger.LogDebug(ex, "Instance {InstanceId} check failed, proceeding", instanceId);
    }

    // Start new orchestration instance
    await client.ScheduleNewOrchestrationInstanceAsync(
        nameof(MarketCycleOrchestrator),
        options: new StartOrchestrationOptions { InstanceId = instanceId },
        cancellation: ct);
}
```

**Key Design Decisions**:

1. **Deterministic Instance IDs**: `market-cycle-{yyyyMMdd-HHmm}`
   - Same ID for same 5-minute window
   - Prevents duplicate orchestrations for the same time window
   - Example: `market-cycle-20260205-1430`

2. **Idempotency at Orchestrator Level**:
   - Before starting, check if instance already exists
   - If running/pending, skip instead of creating duplicate
   - Critical for timer misfires or deployment overlaps

3. **Graceful Degradation**:
   - If status check fails (network issue), proceed anyway
   - Better to risk duplicate (handled elsewhere) than miss a cycle

#### 2. Orchestrator Execution Flow

```csharp
[Function(nameof(MarketCycleOrchestrator))]
public async Task<MarketCycleResult> RunOrchestrator(
    [OrchestrationTrigger] TaskOrchestrationContext context)
{
    // IMPORTANT: Use context.CreateReplaySafeLogger for deterministic logging
    var logger = context.CreateReplaySafeLogger<MarketCycleOrchestrator>();
    
    // Use context.CurrentUtcDateTime for deterministic time
    var startTime = context.CurrentUtcDateTime;
    var timestamp = new DateTimeOffset(startTime, TimeSpan.Zero);
    
    // Step 1: Ingest market data (ALWAYS runs)
    var marketResult = await context.CallActivityAsync<MarketDataResult>(
        nameof(IngestMarketDataActivity),
        new IngestMarketDataRequest(timestamp));

    // Step 2: Capture pre-trade equity snapshots (ALWAYS runs)
    var snapshotCount = await context.CallActivityAsync<int>(
        nameof(CaptureAllSnapshotsActivity),
        new CaptureSnapshotsRequest(marketResult.BatchId, timestamp));

    // Step 3: Decision cycle (CONDITIONAL: every 15 minutes)
    var isDecisionMinute = timestamp.Minute % 15 == 0;
    
    if (isDecisionMinute)
    {
        // Get all active agents
        var agentIds = await context.CallActivityAsync<List<Guid>>(
            nameof(GetActiveAgentsActivity), 
            new object());

        // FAN-OUT: Run all agents in parallel
        var decisionTasks = agentIds.Select(agentId =>
            context.CallActivityAsync<AgentDecisionResult>(
                nameof(RunAgentDecisionActivity),
                new AgentDecisionRequest(agentId, marketResult.BatchId, timestamp)));

        // FAN-IN: Wait for all agents to complete
        var decisions = await Task.WhenAll(decisionTasks);
        
        // Execute trades sequentially (could be parallelized per agent)
        tradesExecuted = await context.CallActivityAsync<int>(
            nameof(ExecuteTradesActivity),
            new ExecuteTradesRequest(decisions.ToList(), timestamp));

        // Post-trade equity snapshots
        await context.CallActivityAsync<int>(
            nameof(CaptureAllSnapshotsActivity),
            new CaptureSnapshotsRequest(marketResult.BatchId, timestamp));
    }

    return new MarketCycleResult(...);
}
```

**Critical Orchestration Patterns**:

1. **Replay-Safe Logging**:
   ```csharp
   var logger = context.CreateReplaySafeLogger<T>();
   ```
   - Durable Functions replay orchestrators from checkpoints
   - Regular `ILogger` would log duplicates during replay
   - `CreateReplaySafeLogger` only logs during non-replay execution

2. **Deterministic Time**:
   ```csharp
   var startTime = context.CurrentUtcDateTime;
   ```
   - Never use `DateTime.UtcNow` in orchestrator
   - Breaks replay determinism (different time on each replay)
   - `context.CurrentUtcDateTime` returns checkpoint time

3. **Sequential Activity Calls**:
   ```csharp
   await context.CallActivityAsync<T>(activityName, input);
   ```
   - Each activity completes before the next starts
   - Progress checkpointed after each activity
   - If failure occurs, replay starts from last checkpoint

4. **Parallel Fan-Out**:
   ```csharp
   var tasks = agentIds.Select(id => 
       context.CallActivityAsync<T>(activityName, input));
   await Task.WhenAll(tasks);
   ```
   - All agents execute simultaneously
   - Massive performance gain (5 agents in parallel vs. sequential)
   - Each agent activity is independent (no shared state)

### Checkpoint & Replay Mechanism

**How Durable Functions Ensures Reliability**:

```
Execution Timeline:

T0: Orchestrator starts
    ├─> Checkpoint 0: Initial state saved
    
T1: IngestMarketDataActivity completes
    ├─> Checkpoint 1: Market data result saved
    │   State: { batchId: guid, prices: {...} }
    
T2: CaptureAllSnapshotsActivity completes
    ├─> Checkpoint 2: Snapshot count saved
    │   State: { batchId: guid, snapshotCount: 5 }

** CRASH/RESTART **

T3: Orchestrator replays from Checkpoint 2
    ├─> Skips IngestMarketDataActivity (already completed)
    ├─> Skips CaptureAllSnapshotsActivity (already completed)
    └─> Continues from GetActiveAgentsActivity
    
T4: GetActiveAgentsActivity completes
    ├─> Checkpoint 3: Agent IDs saved
    
T5: RunAgentDecisionActivity (all 5 agents in parallel)
    ├─> Agent1: Success
    ├─> Agent2: Success
    ├─> Agent3: Failure (LLM timeout)
    ├─> Agent4: Success
    └─> Agent5: Success

** AUTOMATIC RETRY **

T6: Agent3 retries (exponential backoff: 2s)
    └─> Success on retry
    
T7: ExecuteTradesActivity completes
    ├─> Checkpoint 4: Trades executed
    
T8: Orchestrator completes successfully
```

**Key Observations**:
- Activities are **idempotent** (can safely replay)
- Orchestrator state is **persistent** (survives crashes)
- Failures trigger **automatic retries** before giving up
- No data loss or duplicate work

---

## 2. Data Consistency & Transactions

### Database Transaction Strategy

The system uses **SQL Server transactions** with EF Core to ensure ACID properties for critical operations.

#### Portfolio Update Transaction

**File**: `AiTradingRace.Infrastructure/Portfolios/EfPortfolioService.cs`

```csharp
public async Task<PortfolioState> ApplyDecisionAsync(
    Guid agentId,
    AgentDecision decision,
    CancellationToken cancellationToken = default)
{
    var portfolio = await GetOrCreatePortfolioAsync(agentId, cancellationToken);

    // BEGIN TRANSACTION - Explicit transaction for consistency
    await using var transaction = await _dbContext.Database.BeginTransactionAsync(
        cancellationToken);

    // Load all positions for this portfolio
    var positions = await _dbContext.Positions
        .Where(p => p.PortfolioId == portfolio.Id)
        .ToDictionaryAsync(p => p.MarketAssetId, cancellationToken);

    var cash = portfolio.Cash;

    // Execute all orders within the transaction
    foreach (var order in decision.Orders)
    {
        var asset = await GetEnabledAssetAsync(order.AssetSymbol, cancellationToken);
        var price = await ResolvePriceAsync(asset.Id, order.AssetSymbol, 
            order.LimitPrice, cancellationToken);
        var notional = order.Quantity * price;

        switch (order.Side)
        {
            case TradeSide.Buy:
                // Validate sufficient cash BEFORE modifying state
                if (notional > cash)
                {
                    throw new InvalidOperationException(
                        $"Insufficient cash ({cash}) to buy {order.Quantity}");
                }

                cash -= notional;

                // Update or create position
                if (!positions.TryGetValue(asset.Id, out var position))
                {
                    position = new Position { ... };
                    _dbContext.Positions.Add(position);
                    positions[asset.Id] = position;
                }
                else
                {
                    position.AverageEntryPrice = CalculateNewAveragePrice(...);
                    position.Quantity += order.Quantity;
                }

                // Record trade
                _dbContext.Trades.Add(new Trade { ... });
                break;

            case TradeSide.Sell:
                // Validate sufficient holdings BEFORE modifying state
                if (position is null || position.Quantity < order.Quantity)
                {
                    throw new InvalidOperationException(
                        $"Cannot sell {order.Quantity} without sufficient holdings");
                }

                cash += notional;
                position.Quantity -= order.Quantity;

                // Remove position if quantity becomes zero
                if (position.Quantity <= 0)
                {
                    _dbContext.Positions.Remove(position);
                    positions.Remove(asset.Id);
                }

                _dbContext.Trades.Add(new Trade { ... });
                break;
        }
    }

    // Update portfolio cash
    portfolio.Cash = cash;

    // Persist all changes atomically
    await _dbContext.SaveChangesAsync(cancellationToken);

    // Build final portfolio state
    var state = await BuildPortfolioStateAsync(portfolio, 
        captureSnapshot: true, cancellationToken);

    // COMMIT TRANSACTION - All-or-nothing guarantee
    await transaction.CommitAsync(cancellationToken);
    
    return state;
}
```

### Transaction Guarantees

**ACID Properties**:

1. **Atomicity**: All orders execute or none do
   - Example: Agent wants to buy 0.5 BTC and sell 10 ETH
   - If sell fails (insufficient holdings), buy is also rolled back
   - Portfolio never ends up in inconsistent state

2. **Consistency**: Business rules enforced
   - Cash balance never goes negative
   - Cannot sell more than you own
   - Position quantities always accurate

3. **Isolation**: Concurrent agent executions don't interfere
   - Default isolation level: `READ COMMITTED`
   - Agent1 updating their portfolio doesn't block Agent2
   - Each agent has their own portfolio (no shared resources)

4. **Durability**: Committed trades persist through crashes
   - Once `CommitAsync()` returns, data is on disk
   - SQL Server write-ahead logging ensures recovery

### Isolation Levels Explained

```sql
-- Default for SQL Server: READ COMMITTED
-- What it means:
-- ✓ Agent1 can read Agent2's committed trades
-- ✓ Agent1 cannot read Agent2's uncommitted trades (dirty read prevention)
-- ✓ Agent1's read might see different values on re-read (non-repeatable read)
-- ✓ Multiple agents can read the same data simultaneously

-- Why this works for us:
-- 1. Each agent operates on their own portfolio (different rows)
-- 2. Market data reads are snapshot-based (batch ID)
-- 3. No cross-agent state dependencies
```

**No Explicit Isolation Level Configuration**:
- System uses SQL Server defaults (READ COMMITTED)
- Sufficient because:
  - Agents don't share portfolios (row-level isolation)
  - Market data is read-only during decision cycles
  - Equity snapshots use separate rows per agent

### Transaction Rollback Scenarios

```csharp
try
{
    await using var transaction = await _dbContext.Database.BeginTransactionAsync();
    
    // ... portfolio operations ...
    
    await _dbContext.SaveChangesAsync();
    await transaction.CommitAsync();
}
catch (DbUpdateException ex)
{
    // Database constraint violation (e.g., FK constraint)
    // Transaction automatically rolled back
    _logger.LogError(ex, "Database error during trade execution");
    throw;
}
catch (InvalidOperationException ex)
{
    // Business rule violation (e.g., insufficient cash)
    // Transaction automatically rolled back
    _logger.LogError(ex, "Business rule violation during trade execution");
    throw;
}
catch (Exception ex)
{
    // Any other error
    // Transaction automatically rolled back
    _logger.LogError(ex, "Unexpected error during trade execution");
    throw;
}
// Transaction is disposed here (auto-rollback if not committed)
```

**Automatic Rollback**:
- `await using var transaction` ensures disposal
- If exception thrown before `CommitAsync()`, automatic rollback
- No explicit `RollbackAsync()` needed
- Database returns to state before transaction began

---

## 3. Idempotency & Duplicate Prevention

### Multi-Layer Idempotency Strategy

The system implements idempotency at **three levels**:

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: Orchestrator Instance IDs                          │
│  Prevents duplicate orchestration instances                  │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 2: Market Data Batch IDs                              │
│  Prevents duplicate market data ingestion                    │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: ML Service Redis Cache                             │
│  Prevents duplicate ML predictions                           │
└──────────────────────────────────────────────────────────────┘
```

#### Layer 1: Orchestrator Instance ID Idempotency

**Location**: `MarketCycleOrchestrator.cs`

```csharp
var instanceId = $"market-cycle-{now:yyyyMMdd-HHmm}";

// Check if already running
var existing = await client.GetInstanceAsync(instanceId);
if (existing?.RuntimeStatus == OrchestrationRuntimeStatus.Running)
{
    _logger.LogWarning("Already running, skipping");
    return;
}
```

**Scenario**: Timer Misfire
```
14:30:00 - Timer fires, creates instance "market-cycle-20260205-1430"
14:30:05 - Timer misfires, tries to create same instance
           ├─> GetInstanceAsync finds existing instance (Running)
           └─> Skips creation (idempotency preserved)
```

#### Layer 2: Market Data Batch ID Idempotency

**Location**: `IngestMarketDataActivity.cs`

```csharp
public async Task<MarketDataResult> Run(
    [ActivityTrigger] IngestMarketDataRequest request)
{
    var batchId = Guid.NewGuid();  // Unique per activity execution
    
    // Ingest candles with BatchId
    var candles = await _ingestionService.IngestAllAssetsAsync();
    
    foreach (var candle in candles)
    {
        candle.BatchId = batchId;  // Tag with batch ID
        await _dbContext.MarketCandles.AddAsync(candle);
    }
    
    return new MarketDataResult(batchId, ...);
}
```

**Database Schema**:
```sql
CREATE TABLE MarketCandles (
    Id UNIQUEIDENTIFIER PRIMARY KEY,
    BatchId UNIQUEIDENTIFIER NOT NULL,  -- Links candles to ingestion cycle
    MarketAssetId UNIQUEIDENTIFIER NOT NULL,
    TimestampUtc DATETIME2 NOT NULL,
    [Close] DECIMAL(18,8) NOT NULL,
    -- Unique constraint prevents duplicate candles for same timestamp
    CONSTRAINT UQ_MarketCandles_Asset_Timestamp 
        UNIQUE (MarketAssetId, TimestampUtc)
);

CREATE INDEX IX_MarketCandles_BatchId ON MarketCandles(BatchId);
CREATE INDEX IX_MarketCandles_Timestamp ON MarketCandles(TimestampUtc DESC);
```

**Benefits**:
- Query all candles for a specific ingestion cycle: `WHERE BatchId = @batchId`
- Prevent duplicate ingestion with unique constraint
- Trace which market cycle used which price data

#### Layer 3: ML Service Idempotency

**Location**: `ai-trading-race-ml/app/middleware/idempotency.py`

```python
class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Prevents duplicate ML predictions using Redis cache.
    
    Client sends 'Idempotency-Key' header with unique identifier.
    If same key seen within TTL (1 hour), cached response is returned.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only apply to POST /predict endpoint
        if request.method != "POST" or not request.url.path.endswith("/predict"):
            return await call_next(request)

        # Get idempotency key from header
        idempotency_key = request.headers.get("Idempotency-Key")
        
        if not idempotency_key:
            return await call_next(request)  # No key, process normally

        # Check Redis cache
        if cache_service.is_available:
            cached_response = cache_service.get(idempotency_key)
            
            if cached_response:
                logger.info(f"Returning cached response for key: {idempotency_key}")
                return Response(
                    content=cached_response["body"],
                    status_code=cached_response["status_code"],
                    headers=cached_response["headers"],
                )

        # Process request
        response = await call_next(request)

        # Cache successful responses (2xx status codes)
        if 200 <= response.status_code < 300:
            cache_data = {
                "body": body_bytes.decode("utf-8"),
                "status_code": response.status_code,
                "headers": dict(response.headers),
            }
            cache_service.set(idempotency_key, cache_data, ttl=3600)  # 1 hour

        return response
```

**Usage Example**:
```http
POST /predict HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Idempotency-Key: agent-123-batch-456-20260205-1430
X-API-Key: secret-key

{ "agent_context": { ... } }
```

**Response Flow**:
```
First Request:
  ├─> Redis check: MISS
  ├─> Execute ML model (expensive: 500ms)
  ├─> Cache result: SET key="agent-123-batch-456-20260205-1430" ttl=3600
  └─> Return response

Duplicate Request (within 1 hour):
  ├─> Redis check: HIT
  ├─> Skip ML model execution
  └─> Return cached response (fast: 5ms)
```

**Redis Key Structure**:
```
Key Format: {agentId}-{batchId}-{timestamp}
Example: agent-abc123-batch-def456-20260205-1430

TTL: 3600 seconds (1 hour)
Rationale: Decision cycles are 15 minutes, 1 hour provides 4x safety margin
```

---

## 4. Fault Tolerance & Error Handling

### Error Handling Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│  Level 1: Activity-Level Error Handling                     │
│  Catch exceptions, log, return error result                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Level 2: Orchestrator Error Aggregation                    │
│  Collect all agent results (success + failures)             │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Level 3: Partial Success Processing                        │
│  Execute trades for successful agents only                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Level 4: Monitoring & Alerting                             │
│  Log failures, track metrics, alert on threshold            │
└─────────────────────────────────────────────────────────────┘
```

### Activity-Level Error Handling

**File**: `RunAgentDecisionActivity.cs`

```csharp
[Function(nameof(RunAgentDecisionActivity))]
public async Task<AgentDecisionResult> Run(
    [ActivityTrigger] AgentDecisionRequest request,
    CancellationToken ct)
{
    var agent = await _dbContext.Agents
        .AsNoTracking()
        .Where(a => a.Id == request.AgentId)
        .FirstOrDefaultAsync(ct);

    if (agent is null)
    {
        _logger.LogWarning("Agent {AgentId} not found", request.AgentId);
        
        // Return error result instead of throwing
        return new AgentDecisionResult(
            request.AgentId,
            "Unknown",
            CreateEmptyDecision(request.AgentId),
            0m,
            Success: false,
            ErrorMessage: "Agent not found");
    }

    try
    {
        // Execute agent logic
        var result = await _agentRunner.RunAgentOnceAsync(agent.Id, ct);

        return new AgentDecisionResult(
            agent.Id,
            agent.Name,
            result.Decision,
            result.Portfolio.TotalValue,
            Success: true);
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Agent {AgentName} ({AgentId}) failed", 
            agent.Name, agent.Id);
        
        // CRITICAL: Return error result, don't throw
        // Allows other agents to continue even if this one fails
        return new AgentDecisionResult(
            agent.Id,
            agent.Name,
            CreateEmptyDecision(agent.Id, ex.Message),
            0m,
            Success: false,
            ErrorMessage: ex.Message);
    }
}
```

**Key Design Principle**: **Graceful Degradation**
- Activity catches all exceptions internally
- Returns structured error result instead of throwing
- Allows orchestrator to continue with partial results
- Failed agent doesn't block other agents

### Orchestrator Error Aggregation

**File**: `MarketCycleOrchestrator.cs`

```csharp
// Fan-out: Run all agents in parallel
var decisionTasks = agentIds.Select(agentId =>
    context.CallActivityAsync<AgentDecisionResult>(
        nameof(RunAgentDecisionActivity),
        new AgentDecisionRequest(agentId, marketResult.BatchId, timestamp)));

// Fan-in: Wait for ALL agents (including failures)
var decisions = await Task.WhenAll(decisionTasks);
agentsRun = decisions.Length;

// Separate successful from failed
var successful = decisions.Count(d => d.Success);
var failed = decisions.Count(d => !d.Success);

logger.LogInformation(
    "Agent decisions completed. Success: {Success}, Failed: {Failed}",
    successful, failed);

// Continue with successful agents only
var successfulDecisions = decisions.Where(d => d.Success).ToList();

tradesExecuted = await context.CallActivityAsync<int>(
    nameof(ExecuteTradesActivity),
    new ExecuteTradesRequest(successfulDecisions, timestamp));
```

**Partial Success Pattern**:
```
Scenario: 5 agents, 1 fails

Agent1: ✅ Success → BUY 0.2 BTC
Agent2: ✅ Success → HOLD
Agent3: ❌ Failed → OpenAI API timeout
Agent4: ✅ Success → SELL 5 ETH
Agent5: ✅ Success → BUY 0.1 BTC

Result:
├─ Market cycle completes successfully
├─ Agent3 logged as failed (no trades executed)
├─ Agents 1,2,4,5 trades executed normally
└─ Next cycle, Agent3 will retry (fresh attempt)
```

### Error Recovery Strategies

#### 1. Transient Failures: Automatic Retry

**LLM API Timeout Example**:
```csharp
// Polly retry policy in ServiceCollectionExtensions.cs
private static IAsyncPolicy<HttpResponseMessage> GetLlamaRetryPolicy()
{
    return HttpPolicyExtensions
        .HandleTransientHttpError()  // 408, 5xx errors
        .WaitAndRetryAsync(
            retryCount: 3,
            sleepDurationProvider: retryAttempt => 
                TimeSpan.FromSeconds(Math.Pow(2, retryAttempt)),  // Exponential backoff
            onRetry: (outcome, timespan, retryAttempt, context) =>
            {
                logger.LogWarning(
                    "Retry {Attempt} after {Delay}ms due to {Reason}",
                    retryAttempt, timespan.TotalMilliseconds, outcome.Exception?.Message);
            });
}
```

**Retry Behavior**:
```
Attempt 1: API call fails with 503 Service Unavailable
           Wait 2 seconds (2^1)
           
Attempt 2: API call fails with 504 Gateway Timeout
           Wait 4 seconds (2^2)
           
Attempt 3: API call fails with 503 Service Unavailable
           Wait 8 seconds (2^3)
           
Attempt 4: GIVE UP, return error result
```

#### 2. Persistent Failures: Fail Fast

**Invalid Configuration Example**:
```csharp
public async Task<AgentDecision> GenerateDecisionAsync(
    AgentContext context, 
    CancellationToken ct)
{
    if (string.IsNullOrWhiteSpace(_options.ApiKey))
    {
        // No retry - configuration error
        throw new InvalidOperationException(
            "OpenAI API key not configured. Set OpenAI:ApiKey in configuration.");
    }
    
    // ... normal logic ...
}
```

**Don't Retry When**:
- Configuration error (missing API key)
- Business rule violation (insufficient cash)
- Data integrity error (agent not found)

#### 3. Database Deadlocks: Automatic Retry

**EF Core Execution Strategy**:
```csharp
services.AddDbContext<TradingDbContext>(options =>
{
    options.UseSqlServer(
        connectionString,
        sqlOptions => 
        {
            // Enable automatic retry on transient errors
            sqlOptions.EnableRetryOnFailure(
                maxRetryCount: 3,
                maxRetryDelay: TimeSpan.FromSeconds(5),
                errorNumbersToAdd: new[] { 1205 }); // Deadlock error number
        });
});
```

**Deadlock Scenario**:
```sql
-- Unlikely but possible if two agents try to update shared data

Transaction 1:
BEGIN TRANSACTION
UPDATE Portfolio SET Cash = 50000 WHERE AgentId = 'Agent1'
UPDATE MarketCandles SET ... WHERE BatchId = 'Batch1'  -- Blocked by Tx2

Transaction 2:
BEGIN TRANSACTION
UPDATE MarketCandles SET ... WHERE BatchId = 'Batch1'
UPDATE Portfolio SET Cash = 60000 WHERE AgentId = 'Agent2'  -- Blocked by Tx1

Result: DEADLOCK (SQL Server kills one transaction)

EF Core:
├─ Detects deadlock error (1205)
├─ Automatically retries failed transaction
└─ Usually succeeds on retry (lock contention resolved)
```

**Why This is Rare**:
- Agents operate on separate portfolios (different rows)
- Market data is read-only during cycles
- Minimal lock contention

---

## 5. Concurrency Control

### Agent Isolation Strategy

**Agents are Isolated by Design**:

```sql
-- Each agent has their own portfolio (separate rows)
SELECT * FROM Portfolios WHERE AgentId = @agentId;

-- Each agent has their own positions (separate rows)
SELECT * FROM Positions WHERE PortfolioId = @portfolioId;

-- Each agent has their own trades (separate rows)
SELECT * FROM Trades WHERE PortfolioId = @portfolioId;

-- Market data is READ-ONLY (no conflicts)
SELECT * FROM MarketCandles WHERE BatchId = @batchId;
```

**No Concurrency Tokens Needed**:
- No `RowVersion` or `[ConcurrencyCheck]` attributes
- Agents don't compete for resources
- Each agent modifies only their own data

### Parallel Execution Safety

**Fan-Out Pattern Analysis**:

```csharp
// This is SAFE because each agent operates on different data
var tasks = agentIds.Select(agentId =>
    context.CallActivityAsync<AgentDecisionResult>(
        nameof(RunAgentDecisionActivity),
        new AgentDecisionRequest(agentId, ...)));

await Task.WhenAll(tasks);
```

**What Each Agent Reads** (No Conflicts):
```sql
-- Agent1 reads its own portfolio
SELECT * FROM Portfolios WHERE AgentId = 'Agent1';  -- Row 1

-- Agent2 reads its own portfolio
SELECT * FROM Portfolios WHERE AgentId = 'Agent2';  -- Row 2

-- Both read same market data (no locks with READ COMMITTED)
SELECT * FROM MarketCandles WHERE BatchId = 'Batch1';  -- Shared read
```

**What Each Agent Writes** (Isolated):
```sql
-- Agent1 updates its own portfolio
UPDATE Portfolios SET Cash = 45000 WHERE AgentId = 'Agent1';  -- Row 1

-- Agent2 updates its own portfolio
UPDATE Portfolios SET Cash = 60000 WHERE AgentId = 'Agent2';  -- Row 2

-- No row-level conflict (different rows)
```

### Race Condition Prevention

**Scenario**: What if two orchestrator instances run simultaneously?

```
Instance A: market-cycle-20260205-1430
Instance B: market-cycle-20260205-1430 (duplicate)

Execution Timeline:

T1: Instance A starts, creates BatchId: AAA
T2: Instance B starts, creates BatchId: BBB

T3: Both ingest market data
    ├─ Instance A: Inserts candles with BatchId=AAA
    └─ Instance B: Inserts candles with BatchId=BBB
    
    Result: Duplicate candles in database ❌

T4: Both run agents
    ├─ Agent1 processed by Instance A
    └─ Agent1 processed by Instance B (duplicate decision) ❌
```

**Protection Mechanisms**:

1. **Instance ID Check** (Primary Defense):
   ```csharp
   var existing = await client.GetInstanceAsync(instanceId);
   if (existing?.RuntimeStatus == OrchestrationRuntimeStatus.Running)
       return;  // Skip if already running
   ```

2. **Unique Constraint** (Secondary Defense):
   ```sql
   CONSTRAINT UQ_MarketCandles_Asset_Timestamp 
       UNIQUE (MarketAssetId, TimestampUtc)
   ```
   - Second ingestion attempt fails on constraint violation
   - Prevents duplicate candles even if orchestrator check fails

3. **Idempotency Keys** (Tertiary Defense):
   - ML service uses Redis cache with idempotency keys
   - Duplicate prediction requests return cached result
   - No duplicate processing

---

## 6. Retry Mechanisms

### Retry Strategy Matrix

| Component | Mechanism | Max Retries | Backoff | Errors Retried |
|-----------|-----------|-------------|---------|----------------|
| Durable Functions Activity | Automatic | Configurable | Exponential | All transient |
| HTTP Client (Llama API) | Polly | 3 | Exponential (2^n) | 408, 5xx |
| EF Core DB Operations | SQL Server | 3 | Linear | Deadlock, timeout |
| ML Service Predictions | Redis cache | N/A | N/A | Idempotency |

### Durable Functions Retry Policy

**Configuration**: `host.json`

```json
{
  "version": "2.0",
  "extensions": {
    "durableTask": {
      "hubName": "AiTradingRaceHub",
      "storageProvider": {
        "connectionStringName": "AzureWebJobsStorage",
        "controlQueueBatchSize": 32,
        "partitionCount": 4
      },
      "maxConcurrentActivityFunctions": 10,
      "maxConcurrentOrchestratorFunctions": 5,
      "extendedSessionsEnabled": false,
      "tracing": {
        "traceInputsAndOutputs": false,
        "traceReplayEvents": false
      }
    }
  },
  "retry": {
    "strategy": "exponentialBackoff",
    "maxRetryCount": 3,
    "minRetryInterval": "00:00:02",
    "maxRetryInterval": "00:00:30"
  }
}
```

**Retry Calculation**:
```
Attempt 1: Immediate
Attempt 2: Wait 2 seconds (minRetryInterval)
Attempt 3: Wait 4 seconds (2^1 * minRetryInterval)
Attempt 4: Wait 8 seconds (2^2 * minRetryInterval)
Max wait: 30 seconds (maxRetryInterval cap)
```

### HTTP Client Retry with Polly

**Configuration**: `ServiceCollectionExtensions.cs`

```csharp
services.AddHttpClient<ILlamaClient, LlamaClient>()
    .AddPolicyHandler(GetLlamaRetryPolicy());

private static IAsyncPolicy<HttpResponseMessage> GetLlamaRetryPolicy()
{
    return HttpPolicyExtensions
        .HandleTransientHttpError()  // 408, 5xx
        .Or<TimeoutException>()      // HTTP timeout
        .WaitAndRetryAsync(
            retryCount: 3,
            sleepDurationProvider: retryAttempt => 
                TimeSpan.FromSeconds(Math.Pow(2, retryAttempt)),
            onRetry: (outcome, timespan, retryAttempt, context) =>
            {
                var logger = context.GetLogger();
                logger.LogWarning(
                    "Retry {Attempt} after {Delay}s. Reason: {Reason}",
                    retryAttempt, 
                    timespan.TotalSeconds, 
                    outcome.Exception?.Message ?? outcome.Result.StatusCode.ToString());
            });
}
```

**What Triggers Retry**:
- `HttpRequestException` (network failure)
- HTTP 408 (Request Timeout)
- HTTP 500 (Internal Server Error)
- HTTP 502 (Bad Gateway)
- HTTP 503 (Service Unavailable)
- HTTP 504 (Gateway Timeout)

**What Does NOT Trigger Retry**:
- HTTP 400 (Bad Request) - Client error, won't fix with retry
- HTTP 401 (Unauthorized) - Auth error, won't fix with retry
- HTTP 404 (Not Found) - Resource doesn't exist
- HTTP 422 (Unprocessable Entity) - Validation error

### EF Core Retry on Failure

**Configuration**: `ServiceCollectionExtensions.cs`

```csharp
services.AddDbContext<TradingDbContext>(options =>
{
    options.UseSqlServer(
        connectionString,
        sqlOptions => 
        {
            sqlOptions.EnableRetryOnFailure(
                maxRetryCount: 3,
                maxRetryDelay: TimeSpan.FromSeconds(5),
                errorNumbersToAdd: new[] { 1205 });  // SQL Server deadlock
        });
});
```

**SQL Server Transient Errors** (Auto-Retried):
- Error 1205: Deadlock detected
- Error -2: Timeout expired
- Error 40197: Service unavailable
- Error 40501: Service busy
- Error 40613: Database unavailable

**Retry Flow**:
```csharp
try
{
    await _dbContext.SaveChangesAsync();
}
catch (SqlException ex) when (ex.Number == 1205)
{
    // EF Core automatically retries (up to 3 times)
    // If all retries fail, exception propagates
}
```

---

## 7. State Management

### Durable Functions State Persistence

**Storage Backend**: Azurite (local) or Azure Storage (production)

**State Tables**:

1. **Instances Table**: Orchestrator instance metadata
   ```
   PartitionKey: TaskHub name
   RowKey: Instance ID
   Columns: RuntimeStatus, Input, Output, CreatedTime, LastUpdatedTime
   ```

2. **History Table**: Orchestrator execution events
   ```
   PartitionKey: Instance ID
   RowKey: Event ID (sequence)
   Columns: EventType, Timestamp, Name, Input, Result
   ```

3. **Work Items Queue**: Pending activities
   ```
   Messages: Activity invocation payloads
   Visibility Timeout: 5 minutes (configurable)
   ```

### State Checkpoint Example

**Orchestrator Execution**:

```csharp
[Function(nameof(MarketCycleOrchestrator))]
public async Task<MarketCycleResult> RunOrchestrator(
    [OrchestrationTrigger] TaskOrchestrationContext context)
{
    // Checkpoint 0: Orchestrator started
    // State: { instanceId: "market-cycle-20260205-1430", status: "Running" }
    
    var marketResult = await context.CallActivityAsync<MarketDataResult>(
        nameof(IngestMarketDataActivity), ...);
    
    // Checkpoint 1: Activity completed
    // State: { batchId: "guid", prices: {...} }
    
    var snapshotCount = await context.CallActivityAsync<int>(
        nameof(CaptureAllSnapshotsActivity), ...);
    
    // Checkpoint 2: Activity completed
    // State: { snapshotCount: 5 }
    
    // If process crashes here, replay starts from Checkpoint 2
    
    var agentIds = await context.CallActivityAsync<List<Guid>>(
        nameof(GetActiveAgentsActivity), ...);
    
    // Checkpoint 3: Activity completed
    // State: { agentIds: ["guid1", "guid2", ...] }
    
    return result;
}
```

**History Table Events**:
```json
[
  {
    "eventType": "OrchestratorStarted",
    "timestamp": "2026-02-05T14:30:00Z",
    "input": { "timestamp": "2026-02-05T14:30:00Z" }
  },
  {
    "eventType": "TaskScheduled",
    "name": "IngestMarketDataActivity",
    "timestamp": "2026-02-05T14:30:01Z"
  },
  {
    "eventType": "TaskCompleted",
    "name": "IngestMarketDataActivity",
    "timestamp": "2026-02-05T14:30:05Z",
    "result": { "batchId": "guid", "prices": {...} }
  },
  {
    "eventType": "TaskScheduled",
    "name": "CaptureAllSnapshotsActivity",
    "timestamp": "2026-02-05T14:30:06Z"
  },
  // ... more events ...
]
```

### Database State Management

**Portfolio State** (Mutable):
```sql
-- Current state (single row per agent)
SELECT * FROM Portfolios WHERE AgentId = @agentId;

-- Positions (0-N rows per portfolio)
SELECT * FROM Positions WHERE PortfolioId = @portfolioId;
```

**Equity Snapshots** (Immutable):
```sql
-- Historical snapshots (append-only)
SELECT * FROM EquitySnapshots 
WHERE AgentId = @agentId 
ORDER BY TimestampUtc DESC;
```

**Trades** (Immutable):
```sql
-- Historical trades (append-only)
SELECT * FROM Trades 
WHERE PortfolioId = @portfolioId 
ORDER BY ExecutedAt DESC;
```

**Design Pattern**: Event Sourcing (Partial)
- Portfolios: Current state (mutable)
- Trades: Event log (immutable)
- Equity Snapshots: Snapshot log (immutable)

**Reconstruction Capability**:
```csharp
// Can reconstruct portfolio at any point in time
public async Task<PortfolioState> GetPortfolioAtTimestampAsync(
    Guid agentId, 
    DateTimeOffset timestamp)
{
    // Start with initial state
    var portfolio = new Portfolio { Cash = 100_000m };
    
    // Replay all trades up to timestamp
    var trades = await _dbContext.Trades
        .Where(t => t.PortfolioId == portfolioId && t.ExecutedAt <= timestamp)
        .OrderBy(t => t.ExecutedAt)
        .ToListAsync();
    
    foreach (var trade in trades)
    {
        ApplyTrade(portfolio, trade);
    }
    
    return portfolio;
}
```

---

## 8. Monitoring & Observability

### Structured Logging

**Log Levels**:
```csharp
_logger.LogTrace("Detailed diagnostic info (development only)");
_logger.LogDebug("Internal system state (development only)");
_logger.LogInformation("Normal operation events (always)");
_logger.LogWarning("Unexpected but recoverable (always)");
_logger.LogError("Error that requires attention (always)");
_logger.LogCritical("System failure (always)");
```

**Structured Logging Example**:
```csharp
_logger.LogInformation(
    "Agent {AgentName} ({AgentId}) executed {TradeCount} trades. " +
    "Portfolio value: {PortfolioValue:C}. " +
    "Return: {Return:P2}",
    agent.Name,           // Structured parameter
    agent.Id,             // Structured parameter
    tradeCount,           // Structured parameter
    portfolioValue,       // Structured parameter (formatted as currency)
    returnPercent);       // Structured parameter (formatted as percentage)
```

**Log Output** (JSON):
```json
{
  "timestamp": "2026-02-05T14:30:15Z",
  "level": "Information",
  "message": "Agent GPT-4 Trader (abc-123) executed 2 trades. Portfolio value: $110,500.00. Return: 10.50%",
  "properties": {
    "AgentName": "GPT-4 Trader",
    "AgentId": "abc-123",
    "TradeCount": 2,
    "PortfolioValue": 110500.00,
    "Return": 0.1050
  }
}
```

### Key Metrics to Monitor

**Orchestration Metrics**:
- Market cycle duration (target: < 30 seconds)
- Agent decision duration (target: < 10 seconds per agent)
- Failed agent count per cycle (alert if > 20%)

**Database Metrics**:
- Transaction duration (target: < 1 second)
- Deadlock count (target: 0 per hour)
- Connection pool exhaustion (alert if > 80%)

**External API Metrics**:
- CoinGecko API latency (target: < 2 seconds)
- LLM API latency (target: < 5 seconds)
- ML service latency (target: < 1 second)

### Health Checks

**Endpoint**: `/health`

```csharp
builder.Services.AddHealthChecks()
    .AddDbContextCheck<TradingDbContext>("database")
    .AddRedis(configuration["Redis:ConnectionString"], "redis")
    .AddUrlGroup(new Uri("http://ml-service:8000/health"), "ml-service");

app.MapHealthChecks("/health", new HealthCheckOptions
{
    ResponseWriter = async (context, report) =>
    {
        var result = new
        {
            status = report.Status.ToString(),
            checks = report.Entries.Select(e => new
            {
                name = e.Key,
                status = e.Value.Status.ToString(),
                duration = e.Value.Duration.TotalMilliseconds,
                description = e.Value.Description,
                error = e.Value.Exception?.Message
            })
        };
        
        await context.Response.WriteAsJsonAsync(result);
    }
});
```

**Health Check Response**:
```json
{
  "status": "Healthy",
  "checks": [
    {
      "name": "database",
      "status": "Healthy",
      "duration": 15.2,
      "description": "SQL Server connection",
      "error": null
    },
    {
      "name": "redis",
      "status": "Healthy",
      "duration": 5.8,
      "description": "Redis cache",
      "error": null
    },
    {
      "name": "ml-service",
      "status": "Unhealthy",
      "duration": 5000.0,
      "description": "ML prediction service",
      "error": "Request timeout after 5000ms"
    }
  ]
}
```

---

## Summary: How It All Works Together

### Reliability Guarantees

1. **Orchestration**: Durable Functions ensures no lost cycles
   - Checkpointing after each activity
   - Automatic replay on failure
   - Idempotent instance IDs

2. **Data Consistency**: Transactions ensure atomic portfolio updates
   - All-or-nothing trade execution
   - No partial state updates
   - Automatic rollback on errors

3. **Idempotency**: Multi-layer duplicate prevention
   - Orchestrator instance uniqueness
   - Market data batch IDs
   - ML service Redis cache

4. **Fault Tolerance**: Graceful degradation
   - Activity-level error containment
   - Partial success processing
   - Automatic retries for transient errors

5. **Concurrency**: Agent isolation by design
   - Separate portfolio rows per agent
   - Parallel execution without conflicts
   - Minimal lock contention

### Trade-offs & Design Decisions

| Decision | Benefits | Trade-offs |
|----------|----------|------------|
| Durable Functions | Automatic retry, checkpointing | Learning curve, Azure dependency |
| SQL transactions | ACID guarantees | Reduced throughput (locks) |
| Agent isolation | No concurrency conflicts | Can't implement agent interactions |
| Partial success | High availability | Inconsistent agent execution timing |
| Redis idempotency | Fast duplicate detection | External dependency, TTL management |

### Performance Characteristics

**Typical Execution Times** (local dev):
- Market data ingestion: 500ms - 2s
- Pre-trade snapshots: 100ms - 500ms
- Agent decision (GPT-4): 3s - 10s
- Agent decision (ML): 200ms - 1s
- Trade execution: 50ms - 200ms
- Post-trade snapshots: 100ms - 500ms

**Total Cycle Duration**:
- Non-decision cycle (data only): 1s - 3s
- Decision cycle (5 agents parallel): 5s - 15s

**Scalability**:
- Vertical: Limited by SQL Server connection pool
- Horizontal: Durable Functions supports multiple instances
- Bottleneck: LLM API rate limits (e.g., OpenAI: 3,500 RPM)

---

## Future Enhancements

### Phase 9: Message Queue (RabbitMQ)

**Current**: Direct database writes
**Future**: Event-driven architecture

```
Agent Decision → Publish Event → RabbitMQ → Consumer → Trade Execution
```

Benefits:
- Decoupled components
- Better scaling
- Guaranteed delivery

### Phase 10: Distributed Tracing

**Current**: Structured logging
**Future**: OpenTelemetry + Application Insights

```
Request ID → Trace entire flow → Visualize in distributed trace viewer
```

Benefits:
- End-to-end visibility
- Performance bottleneck identification
- Dependency mapping

### Phase 11: Advanced Retry Strategies

**Current**: Simple exponential backoff
**Future**: Circuit breaker + bulkhead patterns

```
Circuit Breaker: Stop retrying after N consecutive failures (prevent cascading)
Bulkhead: Isolate failures (one agent failure doesn't affect others)
```

Benefits:
- Faster failure detection
- Reduced resource waste
- Better isolation

---

This architecture provides **enterprise-grade reliability** while maintaining **developer-friendly simplicity**. The combination of Durable Functions, transactional consistency, multi-layer idempotency, and graceful error handling ensures the system can run 24/7 with minimal human intervention.
