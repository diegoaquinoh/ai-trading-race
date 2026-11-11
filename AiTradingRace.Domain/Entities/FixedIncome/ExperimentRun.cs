namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// A run of an experiment definition. <see cref="JobState"/> tracks the job
/// lifecycle (queued/running/completed/failed/cancelled); strategy outcomes are
/// recorded separately on <see cref="Decision"/>.
/// </summary>
public class ExperimentRun
{
    public long Id { get; set; }

    /// <summary>Unique logical run identifier (idempotency key for run creation).</summary>
    public string RunId { get; set; } = string.Empty;

    public long ExperimentDefinitionId { get; set; }

    public ExperimentDefinition? ExperimentDefinition { get; set; }

    public string ExperimentId { get; set; } = string.Empty;

    public int ExperimentVersion { get; set; }

    /// <summary>replay | forward.</summary>
    public string RunType { get; set; } = FiRunType.Replay;

    /// <summary>recorded_replay | fresh_inference.</summary>
    public string ResponseMode { get; set; } = FiResponseMode.RecordedReplay;

    public string DataMode { get; set; } = FiDataMode.SyntheticCurve;

    public string RiskPolicyId { get; set; } = string.Empty;

    public string ExecutionModelId { get; set; } = string.Empty;

    /// <summary>queued | running | completed | failed | cancelled.</summary>
    public string JobState { get; set; } = FiJobState.Queued;

    /// <summary>Failure/cancellation reason for the job (not a strategy outcome).</summary>
    public string? StatusReason { get; set; }

    /// <summary>Canonical JSON of the immutable run manifest written at creation.</summary>
    public string ManifestJson { get; set; } = string.Empty;

    public string ManifestHash { get; set; } = string.Empty;

    /// <summary>Hash of the canonical run-creation request (idempotency binding).</summary>
    public string RequestHash { get; set; } = string.Empty;

    /// <summary>Research-engine version observed when execution started.</summary>
    public string? EngineVersion { get; set; }

    public int CompletedCycles { get; set; }

    public int? TotalCycles { get; set; }

    /// <summary>Simulated clock (decision_as_of of the latest processed cycle); distinct from wall time.</summary>
    public DateTimeOffset? SimulatedClock { get; set; }

    public string? RequestedBy { get; set; }

    public DateTimeOffset CreatedAt { get; set; }

    public DateTimeOffset? StartedAt { get; set; }

    public DateTimeOffset? CompletedAt { get; set; }

    /// <summary>JSON array of run-level classified errors (spec 18.3); cycle errors live on the cycle.</summary>
    public string? ErrorsJson { get; set; }

    /// <summary>Operational time of the latest completed cycle checkpoint (checkpoint-age metric).</summary>
    public DateTimeOffset? LastCheckpointAt { get; set; }

    /// <summary>Optimistic concurrency token for job-state transitions.</summary>
    public Guid ConcurrencyStamp { get; set; } = Guid.NewGuid();

    public ICollection<StrategyInstance> Strategies { get; set; } = new List<StrategyInstance>();
}
