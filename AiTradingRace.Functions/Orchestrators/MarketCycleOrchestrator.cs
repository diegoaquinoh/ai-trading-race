using AiTradingRace.Functions.Activities;
using AiTradingRace.Functions.Models;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Orchestrators;

/// <summary>
/// Durable orchestrator for the market data cycle.
/// Runs every 5 minutes to:
/// 1. Ingest market data
/// 2. Capture equity snapshots
/// 3. Every 15 minutes: run agent decisions
/// </summary>
public sealed class MarketCycleOrchestrator
{
    private readonly ILogger<MarketCycleOrchestrator> _logger;

    public MarketCycleOrchestrator(ILogger<MarketCycleOrchestrator> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Main orchestrator function that coordinates the market cycle.
    /// </summary>
    [Function(nameof(MarketCycleOrchestrator))]
    public async Task<MarketCycleResult> RunOrchestrator(
        [OrchestrationTrigger] TaskOrchestrationContext context)
    {
        var logger = context.CreateReplaySafeLogger<MarketCycleOrchestrator>();
        var startTime = context.CurrentUtcDateTime;
        var timestamp = new DateTimeOffset(startTime, TimeSpan.Zero);
        
        // Decision cycle runs at :00, :15, :30, :45
        var isDecisionMinute = timestamp.Minute % 15 == 0;
        
        logger.LogInformation(
            "Market cycle started at {Timestamp}. Decision cycle: {IsDecision}",
            timestamp, isDecisionMinute);

        // Step 1: Ingest market data
        var marketResult = await context.CallActivityAsync<MarketDataResult>(
            nameof(IngestMarketDataActivity),
            new IngestMarketDataRequest(timestamp));

        logger.LogInformation(
            "Market data ingested. BatchId: {BatchId}, Prices: {PriceCount}",
            marketResult.BatchId, marketResult.Prices.Count);

        // Step 2: Capture equity snapshots (pre-trade baseline)
        var snapshotCount = await context.CallActivityAsync<int>(
            nameof(CaptureAllSnapshotsActivity),
            new CaptureSnapshotsRequest(marketResult.BatchId, timestamp));

        logger.LogInformation("Captured {Count} equity snapshots", snapshotCount);

        // Step 3: Decision cycle (every 15 minutes)
        int agentsRun = 0;
        int tradesExecuted = 0;

        if (isDecisionMinute)
        {
            logger.LogInformation("Starting agent decision cycle");

            // Get all active agents
            var agentIds = await context.CallActivityAsync<List<Guid>>(
                nameof(GetActiveAgentsActivity),
                new object());

            logger.LogInformation("Running {Count} agents in parallel", agentIds.Count);

            // Fan-out: Run all agents in parallel
            var decisionTasks = agentIds.Select(agentId =>
                context.CallActivityAsync<AgentDecisionResult>(
                    nameof(RunAgentDecisionActivity),
                    new AgentDecisionRequest(agentId, marketResult.BatchId, timestamp)));

            var decisions = await Task.WhenAll(decisionTasks);
            agentsRun = decisions.Length;

            // Log results
            var successful = decisions.Count(d => d.Success);
            var failed = decisions.Count(d => !d.Success);
            logger.LogInformation(
                "Agent decisions completed. Success: {Success}, Failed: {Failed}",
                successful, failed);

            // Execute trades (post-processing)
            tradesExecuted = await context.CallActivityAsync<int>(
                nameof(ExecuteTradesActivity),
                new ExecuteTradesRequest(decisions.ToList(), timestamp));

            logger.LogInformation("Executed {Count} trades", tradesExecuted);

            // Capture post-trade equity snapshots
            await context.CallActivityAsync<int>(
                nameof(CaptureAllSnapshotsActivity),
                new CaptureSnapshotsRequest(marketResult.BatchId, timestamp));

            logger.LogInformation("Captured post-trade equity snapshots");
        }

        var duration = context.CurrentUtcDateTime - startTime;

        logger.LogInformation(
            "Market cycle completed in {Duration}ms. BatchId: {BatchId}",
            duration.TotalMilliseconds, marketResult.BatchId);

        return new MarketCycleResult(
            marketResult.BatchId,
            timestamp,
            snapshotCount,
            isDecisionMinute,
            agentsRun,
            tradesExecuted,
            duration);
    }

    /// <summary>
    /// Timer trigger to start the market cycle every 5 minutes.
    /// CRON: 0 */5 * * * * (at minute 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)
    /// </summary>
    [Function(nameof(StartMarketCycle))]
    public async Task StartMarketCycle(
        [TimerTrigger("0 */5 * * * *")] TimerInfo timer,
        [DurableClient] DurableTaskClient client,
        CancellationToken ct)
    {
        var now = DateTime.UtcNow;
        var instanceId = $"market-cycle-{now:yyyyMMdd-HHmm}";

        // Check if already running (idempotency)
        try
        {
            var existing = await client.GetInstanceAsync(instanceId, cancellation: ct);
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
            // Instance doesn't exist, which is fine
            _logger.LogDebug(ex, "Instance {InstanceId} check failed, proceeding", instanceId);
        }

        await client.ScheduleNewOrchestrationInstanceAsync(
            nameof(MarketCycleOrchestrator),
            options: new StartOrchestrationOptions { InstanceId = instanceId },
            cancellation: ct);

        _logger.LogInformation(
            "Started market cycle orchestration: {InstanceId}. Next run: {NextRun}",
            instanceId, timer.ScheduleStatus?.Next);
    }

    /// <summary>
    /// HTTP endpoint to manually trigger a market cycle.
    /// POST /api/market-cycle/trigger
    /// </summary>
    [Function("TriggerMarketCycle")]
    public async Task<string> TriggerMarketCycle(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "market-cycle/trigger")] 
        Microsoft.Azure.Functions.Worker.Http.HttpRequestData req,
        [DurableClient] DurableTaskClient client,
        CancellationToken ct)
    {
        var now = DateTime.UtcNow;
        var instanceId = $"market-cycle-manual-{now:yyyyMMdd-HHmmss}";

        await client.ScheduleNewOrchestrationInstanceAsync(
            nameof(MarketCycleOrchestrator),
            options: new StartOrchestrationOptions { InstanceId = instanceId },
            cancellation: ct);

        _logger.LogInformation("Manual market cycle triggered: {InstanceId}", instanceId);

        return instanceId;
    }
}
