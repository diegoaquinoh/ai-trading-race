namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>One decision cycle of a run against a frozen common market cutoff.</summary>
public class Cycle
{
    public long Id { get; set; }

    public string RunId { get; set; } = string.Empty;

    public string CycleId { get; set; } = string.Empty;

    public int Sequence { get; set; }

    public DateOnly SessionDate { get; set; }

    /// <summary>Information cutoff for every competitor in this cycle (simulated time).</summary>
    public DateTimeOffset DecisionAsOf { get; set; }

    /// <summary>pending | running | completed | skipped | failed | cancelled.</summary>
    public string Status { get; set; } = FiCycleStatus.Pending;

    public string? SkipReason { get; set; }

    public string? MarketSnapshotId { get; set; }

    public string? MarketSnapshotHash { get; set; }

    public string? CurveSnapshotId { get; set; }

    public DateTimeOffset? StartedAt { get; set; }

    public DateTimeOffset? CompletedAt { get; set; }

    /// <summary>
    /// Canonical JSON of the frozen common inputs of the session (market/curve pointers,
    /// availability, decision/execution/valuation instants) captured when the run was planned.
    /// </summary>
    public string? InputsJson { get; set; }

    /// <summary>
    /// Checkpoint written when the cycle completes (spec 15.4): portfolio versions and state
    /// hashes, simulated clock and manifest references. Resume starts after the last checkpoint.
    /// </summary>
    public string? CheckpointJson { get; set; }

    /// <summary>JSON array of classified errors (scope source|strategy|cycle|financial_state, spec 18.3).</summary>
    public string? ErrorsJson { get; set; }
}
