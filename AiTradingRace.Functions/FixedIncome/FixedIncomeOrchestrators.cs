using AiTradingRace.Application.FixedIncome;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.FixedIncome;

/// <summary>
/// Durable replay of an application-mode fixed income run: one activity per cycle, so the
/// durable history checkpoints between cycles and a host restart resumes at the next cycle.
/// Deterministic: the workflow (<see cref="FixedIncomeReplayOrchestration"/>) never reads the
/// wall clock; non-deterministic I/O (engine calls, SQL) runs only inside activities.
/// The legacy <c>MarketCycleOrchestrator</c> is independent and untouched.
/// </summary>
public sealed class FixedIncomeReplayOrchestrator
{
    [Function(nameof(FixedIncomeReplayOrchestrator))]
    public Task<FiOrchestrationOutcome> Run([OrchestrationTrigger] TaskOrchestrationContext context)
    {
        var input = context.GetInput<FiReplayInput>() ?? throw new InvalidOperationException("Missing replay input.");
        var logger = context.CreateReplaySafeLogger<FixedIncomeReplayOrchestrator>();
        logger.LogInformation("Fixed income replay orchestration {InstanceId} for run {RunId}", context.InstanceId, input.RunId);
        return FixedIncomeReplayOrchestration.RunReplayAsync(new DurableFiContext(context), input);
    }
}

/// <summary>One forward (paper) cycle of a forward run, triggered by <see cref="FixedIncomePaperCycleTimer"/>.</summary>
public sealed class FixedIncomePaperCycleOrchestrator
{
    [Function(nameof(FixedIncomePaperCycleOrchestrator))]
    public Task<FiOrchestrationOutcome> Run([OrchestrationTrigger] TaskOrchestrationContext context)
    {
        var input = context.GetInput<FiPaperCycleInput>() ?? throw new InvalidOperationException("Missing paper-cycle input.");
        var logger = context.CreateReplaySafeLogger<FixedIncomePaperCycleOrchestrator>();
        logger.LogInformation("Fixed income paper cycle {InstanceId} for run {RunId} session {SessionDate}",
            context.InstanceId, input.RunId, input.SessionDate);
        return FixedIncomeReplayOrchestration.RunPaperCycleAsync(new DurableFiContext(context), input);
    }
}

/// <summary>
/// Adapter over <see cref="TaskOrchestrationContext"/>. Activities are retried by the
/// durable runtime (3 attempts, exponential backoff); retries are safe because every
/// financial command id is deterministic and committed commands are detected first.
/// </summary>
internal sealed class DurableFiContext : IFiOrchestrationContext
{
    private static readonly TaskOptions RetryOptions = TaskOptions.FromRetryPolicy(new RetryPolicy(
        maxNumberOfAttempts: 3,
        firstRetryInterval: TimeSpan.FromSeconds(15),
        backoffCoefficient: 2.0,
        maxRetryInterval: TimeSpan.FromMinutes(2)));

    private readonly TaskOrchestrationContext _context;

    public DurableFiContext(TaskOrchestrationContext context)
    {
        _context = context;
    }

    public Task<T> CallActivityAsync<T>(string activityName, object input) =>
        _context.CallActivityAsync<T>(activityName, input, RetryOptions);
}
