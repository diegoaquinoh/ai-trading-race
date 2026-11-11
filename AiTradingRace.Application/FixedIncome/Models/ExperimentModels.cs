using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Application.FixedIncome.Models;

/// <summary>POST /api/v1/experiments body. Persisted as an immutable definition version.</summary>
public sealed record CreateExperimentDefinitionRequest
{
    public string ExperimentId { get; init; } = string.Empty;
    public int Version { get; init; } = 1;
    public string Name { get; init; } = string.Empty;
    public string? Description { get; init; }
    public string DataMode { get; init; } = "synthetic_curve";
    public DateOnly StartDate { get; init; }
    public DateOnly EndDate { get; init; }
    public string RiskPolicyId { get; init; } = "treasury-long-only-v1";
    public string ExecutionModelId { get; init; } = "synthetic-half-spread-0.02-v1";
    public string InstrumentUniverseVersion { get; init; } = string.Empty;
    public string AvailabilityPolicy { get; init; } = "reconstructed_publication_plus_lag_v1";
    public string? EvidenceSnapshotId { get; init; }
    public string? IndexBuildId { get; init; }
    public int Repetitions { get; init; } = 1;
    public List<ExperimentStrategyRequest> Strategies { get; init; } = new();
    public DecisionBudgetDto? Budget { get; init; }

    /// <summary>Free-form, versioned parameters (hashed with the definition).</summary>
    public JsonObject? Parameters { get; init; }
}

public sealed record ExperimentStrategyRequest
{
    public string StrategyId { get; init; } = string.Empty;
    public string StrategyKind { get; init; } = string.Empty;
    public string StrategyConfigId { get; init; } = string.Empty;
    public string? Label { get; init; }
}

public enum ExperimentDefinitionStatus
{
    Created,
    AlreadyExists,
    Conflict,
    Invalid,
}

public sealed record ExperimentDefinitionResult
{
    public ExperimentDefinitionStatus Status { get; init; }
    public ExperimentDefinitionView? Definition { get; init; }
    public IReadOnlyDictionary<string, string[]> Errors { get; init; } = new Dictionary<string, string[]>();
    public string? Message { get; init; }
}

public sealed record ExperimentDefinitionView(
    string ExperimentId,
    int Version,
    string Name,
    string? Description,
    string DataMode,
    string RiskPolicyId,
    string ExecutionModelId,
    string InstrumentUniverseVersion,
    DateOnly StartDate,
    DateOnly EndDate,
    int Repetitions,
    string DefinitionHash,
    JsonNode? Definition,
    DateTimeOffset CreatedAt);

/// <summary>POST /api/v1/experiments/{id}/runs body.</summary>
public sealed record StartRunRequest
{
    /// <summary>Optional logical run id (idempotency key). Generated when omitted.</summary>
    public string? RunId { get; init; }

    /// <summary>Definition version; latest when omitted.</summary>
    public int? ExperimentVersion { get; init; }

    public string RunType { get; init; } = "replay";

    public string ResponseMode { get; init; } = "recorded_replay";
}

public enum StartRunStatus
{
    Accepted,
    AlreadyExists,
    Conflict,
    NotFound,
    Invalid,
}

public sealed record StartRunResult
{
    public StartRunStatus Status { get; init; }
    public string? RunId { get; init; }
    public string? JobState { get; init; }
    public IReadOnlyDictionary<string, string[]> Errors { get; init; } = new Dictionary<string, string[]>();
    public string? Message { get; init; }
}

public enum RunStateChangeStatus
{
    Changed,
    NotFound,
    InvalidTransition,
}

public sealed record RunStateChangeResult(RunStateChangeStatus Status, string? JobState, string? Message = null);
