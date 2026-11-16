namespace AiTradingRace.Application.FixedIncome;

/// <summary>
/// Executes a queued fixed income run (application mode) end to end in-process,
/// cycle by cycle through <see cref="IFixedIncomeCycleRunner"/>.
/// </summary>
public interface IFixedIncomeRunExecutor
{
    Task<RunExecutionResult> ExecuteAsync(string runId, CancellationToken cancellationToken);
}

public sealed record RunExecutionResult(bool Succeeded, string? FailureReason = null, bool Cancelled = false, bool Continuing = false)
{
    public static RunExecutionResult Success() => new(true);

    /// <summary>A forward run processed its due sessions and stays running until its window ends.</summary>
    public static RunExecutionResult Continue() => new(true, Continuing: true);

    public static RunExecutionResult Failure(string reason) => new(false, reason);
}

/// <summary>Background queue of run ids awaiting execution.</summary>
public interface IFixedIncomeRunQueue
{
    /// <summary>Enqueues a run; returns false when the queue is full (the run stays queued in SQL and is picked up on restart).</summary>
    ValueTask<bool> TryEnqueueAsync(string runId, CancellationToken cancellationToken = default);
}
