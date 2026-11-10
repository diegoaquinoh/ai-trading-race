namespace AiTradingRace.Application.FixedIncome;

/// <summary>
/// Shared application-mode run logic (spec 15.1) used by the Web hosted queue
/// (<see cref="IFixedIncomeRunExecutor"/>) and by the Functions durable activities.
/// Every step is idempotent: commands use deterministic ids
/// (<c>cmd:{runId}:{cycleId}:{portfolioId}:{step}</c>) and decisions deterministic ids
/// (<c>dec:{runId}:{cycleId}:{strategyId}:{repetition}</c>), so a retried activity or a
/// restarted worker re-issues identical commands and receives the already-committed
/// results instead of creating a second financial effect.
/// </summary>
public interface IFixedIncomeCycleRunner
{
    /// <summary>
    /// Initializes a replay run: ensures portfolios, commits the initial CAPITAL_FLOW,
    /// freezes the session list into ordered Cycle rows and returns the cycles left to run
    /// (resume point = first cycle that is neither completed nor skipped).
    /// </summary>
    Task<FiRunPlan> PrepareRunAsync(string runId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Freezes one forward (paper) session into a Cycle of a forward run. Returns a plan
    /// with no cycle when the date is not a supported session or the run window is over.
    /// </summary>
    Task<FiRunPlan> PreparePaperCycleAsync(string runId, DateOnly sessionDate, CancellationToken cancellationToken = default);

    /// <summary>Executes one cycle end to end (process events → decisions → valuation → checkpoint).</summary>
    Task<FiCycleResult> ExecuteCycleAsync(string runId, string cycleId, CancellationToken cancellationToken = default);

    /// <summary>Records the terminal job state of a run (completed / failed) with its error summary.</summary>
    Task FinalizeRunAsync(string runId, FiRunFinalization finalization, CancellationToken cancellationToken = default);
}

public enum FiPlanStatus
{
    /// <summary>Cycles are ready to execute.</summary>
    Ready,

    /// <summary>Nothing to execute (e.g. not a supported session); not an error.</summary>
    NothingToDo,

    /// <summary>The run was cancelled by an operator.</summary>
    Cancelled,

    /// <summary>The run cannot start (missing configuration, sessions unavailable, initialization failure).</summary>
    Failed,
}

/// <summary>Serializable plan (also the durable orchestration checkpoint input).</summary>
public sealed record FiRunPlan
{
    public string RunId { get; init; } = string.Empty;
    public FiPlanStatus Status { get; init; }
    public string RunType { get; init; } = "replay";

    /// <summary>All cycle ids of the run in sequence order.</summary>
    public List<string> CycleIds { get; init; } = new();

    /// <summary>Cycle ids still to execute, in order (resume from the last completed checkpoint).</summary>
    public List<string> PendingCycleIds { get; init; } = new();

    public string? Reason { get; init; }

    /// <summary>For forward runs: the experiment window has ended after these cycles.</summary>
    public bool WindowComplete { get; init; }
}

public enum FiCycleRunStatus
{
    Completed,
    Skipped,

    /// <summary>The cycle had already reached a checkpoint (completed or skipped) before this call.</summary>
    AlreadyDone,

    Cancelled,

    /// <summary>The run must stop (initialization failure, out-of-order execution...).</summary>
    Failed,
}

public sealed record FiCycleResult
{
    public string RunId { get; init; } = string.Empty;
    public string CycleId { get; init; } = string.Empty;
    public FiCycleRunStatus Status { get; init; }
    public string? Reason { get; init; }
    public int ErrorCount { get; init; }

    public bool StopsRun => Status is FiCycleRunStatus.Cancelled or FiCycleRunStatus.Failed;
}

public sealed record FiRunFinalization
{
    public bool Succeeded { get; init; }
    public bool Cancelled { get; init; }
    public string? Reason { get; init; }

    /// <summary>Forward runs stay running between paper cycles until their window ends.</summary>
    public bool KeepRunning { get; init; }
}

/// <summary>
/// Raised when the research engine stays unreachable for a financial command after
/// bounded retries. The cycle is left uncommitted at its checkpoint so a retried
/// activity / resumed run re-issues the same command ids.
/// </summary>
public sealed class FiTransientDependencyException : Exception
{
    public FiTransientDependencyException(string message, Exception? inner = null)
        : base(message, inner)
    {
    }
}

/// <summary>Error scopes (spec 18.3): which part of the system an error affects.</summary>
public static class FiErrorScope
{
    public const string Source = "source";
    public const string Strategy = "strategy";
    public const string Cycle = "cycle";
    public const string FinancialState = "financial_state";
}
