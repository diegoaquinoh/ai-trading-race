using System.Text.Json;

namespace AiTradingRace.Application.FixedIncome.Contracts;

// C# mirrors of ai-trading-race-ml/research_engine/contracts/decisions.py.

public sealed record SnapshotRefDto
{
    public string Id { get; init; } = string.Empty;
    public string ContentHash { get; init; } = string.Empty;
    public long? Version { get; init; }
}

public sealed record MarketSnapshotPointerDto
{
    public string Id { get; init; } = string.Empty;
    public string ContentHash { get; init; } = string.Empty;
    public string CurveSnapshotId { get; init; } = string.Empty;
}

public sealed record DecisionBudgetDto
{
    public int MaxGenerationCalls { get; init; } = 6;
    public int MaxToolCalls { get; init; } = 12;
    public int MaxEvidenceCalls { get; init; } = 3;
    public int MaxUniqueEvidenceChunks { get; init; } = 12;
    public int MaxEvidenceTokens { get; init; } = 8000;
    public int MaxInputTokens { get; init; } = 32000;
    public int MaxOutputTokens { get; init; } = 12000;
    public int DeadlineSeconds { get; init; } = 90;
    public string? MaxCostUsd { get; init; }
    public string? PriceScheduleId { get; init; }
    public int MaxDelegationDepth { get; init; } = 1;
    public int MaxSpecialistInvocations { get; init; } = 2;
}

/// <summary>
/// Run calendar context (decisions.py DecisionSessionContext). Sent on every application-mode
/// decision: <see cref="PreviousSessionDate"/> is the previous frozen cycle's session (omitted on
/// the run's first cycle), the value offline replay takes from its session list.
/// </summary>
public sealed record DecisionSessionContextDto
{
    public string? PreviousSessionDate { get; init; }
}

/// <summary>POST /internal/v1/strategies/decisions request.</summary>
public sealed record DecisionRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string ExperimentId { get; init; } = string.Empty;
    public string RunId { get; init; } = string.Empty;
    public string CycleId { get; init; } = string.Empty;
    public string DecisionId { get; init; } = string.Empty;
    public string StrategyId { get; init; } = string.Empty;
    public int Repetition { get; init; }
    public string DecisionAsOf { get; init; } = string.Empty;
    public string MarketSessionDate { get; init; } = string.Empty;
    public string AvailabilityPolicy { get; init; } = string.Empty;
    public string DataMode { get; init; } = string.Empty;
    public SnapshotRefDto PortfolioSnapshot { get; init; } = new();
    public MarketSnapshotPointerDto MarketSnapshot { get; init; } = new();
    public string InstrumentUniverseVersion { get; init; } = string.Empty;
    public string? EvidenceSnapshotId { get; init; }
    public string? IndexBuildId { get; init; }
    public string StrategyConfigId { get; init; } = string.Empty;
    public string RiskPolicyId { get; init; } = string.Empty;
    public string ResponseMode { get; init; } = "recorded_replay";
    public DecisionBudgetDto Budget { get; init; } = new();

    /// <summary>Inline stored canonical state (hash-verified by the receiver).</summary>
    public JsonElement? PortfolioState { get; init; }

    /// <summary>Authoritative previous decision session of the run (additive; omitted when null).</summary>
    public DecisionSessionContextDto? SessionContext { get; init; }
}

public sealed record CitationDto
{
    public string CitationId { get; init; } = string.Empty;
    public string BundleId { get; init; } = string.Empty;
    public string ChunkId { get; init; } = string.Empty;
    public string DocumentVersionId { get; init; } = string.Empty;
    public string? Quote { get; init; }
    public int? StartOffset { get; init; }
    public int? EndOffset { get; init; }
}

public sealed record DocumentaryClaimDto
{
    public string ClaimId { get; init; } = string.Empty;
    public string Text { get; init; } = string.Empty;
    public List<string> CitationIds { get; init; } = new();
    public bool Material { get; init; } = true;
    public string ValidationStatus { get; init; } = "unvalidated";
    public List<string> ValidationNotes { get; init; } = new();
}

public sealed record NumericalFindingDto
{
    public string FindingId { get; init; } = string.Empty;
    public string Text { get; init; } = string.Empty;
    public List<string> CalculationIds { get; init; } = new();
    public List<string> InputSnapshotIds { get; init; } = new();
    public string ValidationStatus { get; init; } = "unvalidated";
}

public sealed record HypothesisDto
{
    public string HypothesisId { get; init; } = string.Empty;
    public string Text { get; init; } = string.Empty;
    public List<string> Assumptions { get; init; } = new();
    public List<string> ScenarioIds { get; init; } = new();
    public List<string> SupportingCitationIds { get; init; } = new();
}

public sealed record ResearchNoteDto
{
    public string Status { get; init; } = string.Empty;
    public List<DocumentaryClaimDto> Claims { get; init; } = new();
    public List<NumericalFindingDto> NumericalFindings { get; init; } = new();
    public List<HypothesisDto> Hypotheses { get; init; } = new();
    public List<string> Counterevidence { get; init; } = new();
    public List<string> CoverageGaps { get; init; } = new();
    public List<CitationDto> Citations { get; init; } = new();
    public List<string> RetrievalRunIds { get; init; } = new();
    public string Explanation { get; init; } = string.Empty;
}

public sealed record ProposalDto
{
    public string Action { get; init; } = string.Empty;
    public List<TargetWeightDto> TargetWeights { get; init; } = new();
    public List<string> SupportingClaimIds { get; init; } = new();
    public List<string> SupportingCalculationIds { get; init; } = new();
}

public sealed record ToolTraceDto
{
    public string TraceId { get; init; } = string.Empty;
    public string AgentRole { get; init; } = string.Empty;
    public string ToolName { get; init; } = string.Empty;
    public JsonElement Request { get; init; }
    public JsonElement ResponseSummary { get; init; }
    public string? OutputRef { get; init; }
    public string StartedAt { get; init; } = string.Empty;
    public int DurationMs { get; init; }
    public string Status { get; init; } = string.Empty;
    public string? Error { get; init; }
}

public sealed record DecisionAttemptDto
{
    public string AttemptId { get; init; } = string.Empty;
    public int AttemptNumber { get; init; }
    public string AgentRole { get; init; } = string.Empty;
    public string Purpose { get; init; } = string.Empty;
    public string Provider { get; init; } = string.Empty;
    public string Model { get; init; } = string.Empty;
    public int InputTokens { get; init; }
    public int OutputTokens { get; init; }
    public string StartedAt { get; init; } = string.Empty;
    public int DurationMs { get; init; }
    public string Status { get; init; } = string.Empty;
    public string? RecordedResponseId { get; init; }
    public string? Error { get; init; }
}

public sealed record SpecialistTaskDto
{
    public string TaskId { get; init; } = string.Empty;
    public string Role { get; init; } = string.Empty;
    public string Instruction { get; init; } = string.Empty;
    public List<string> InputSnapshotIds { get; init; } = new();
    public string ExpectedOutputSchema { get; init; } = string.Empty;
    public Dictionary<string, int> BudgetReserved { get; init; } = new();
    public string Status { get; init; } = string.Empty;
    public List<string> Findings { get; init; } = new();
    public List<string> ClaimIds { get; init; } = new();
    public Dictionary<string, int> Usage { get; init; } = new();
}

public sealed record UsageSummaryDto
{
    public int GenerationCalls { get; init; }
    public int ToolCalls { get; init; }
    public int EvidenceCalls { get; init; }
    public int UniqueEvidenceChunks { get; init; }
    public int EvidenceTokens { get; init; }
    public int InputTokens { get; init; }
    public int OutputTokens { get; init; }
    public int DurationMs { get; init; }
    public string? EstimatedCostUsd { get; init; }
    public string? PriceScheduleId { get; init; }
    public string? BudgetExhausted { get; init; }
}

public sealed record ValidationResultDto
{
    public string Step { get; init; } = string.Empty;
    public bool Passed { get; init; }
    public string Severity { get; init; } = "blocking";
    public List<string> Details { get; init; } = new();
}

public sealed record VersionInfoDto
{
    public string? Provider { get; init; }
    public string? Model { get; init; }
    public string? PromptVersion { get; init; }
    public string? ToolSchemaVersion { get; init; }
    public string EngineVersion { get; init; } = string.Empty;
    public string? EvidenceSnapshotId { get; init; }
    public string? IndexBuildId { get; init; }
    public string RetrievalMode { get; init; } = "none";
    public string? StrategyConfigHash { get; init; }
}

/// <summary>Signed strategy result envelope (spec 14.5) returned for every outcome.</summary>
public sealed record StrategyResultDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RunId { get; init; } = string.Empty;
    public string CycleId { get; init; } = string.Empty;
    public string DecisionId { get; init; } = string.Empty;
    public string StrategyId { get; init; } = string.Empty;
    public string StrategyKind { get; init; } = string.Empty;
    public int Repetition { get; init; }
    public string RequestHash { get; init; } = string.Empty;
    public Dictionary<string, string> InputHashes { get; init; } = new();
    public string Outcome { get; init; } = string.Empty;
    public string CompletedAt { get; init; } = string.Empty;
    public List<string> Reasons { get; init; } = new();
    public ProposalDto? Proposal { get; init; }
    public ResearchNoteDto? ResearchNote { get; init; }
    public List<ValidationResultDto> Validation { get; init; } = new();
    public PolicyEvaluationDto? PolicyEvaluation { get; init; }
    public List<DecisionAttemptDto> Attempts { get; init; } = new();
    public List<ToolTraceDto> ToolTraces { get; init; } = new();
    public List<SpecialistTaskDto> SpecialistTasks { get; init; } = new();
    public UsageSummaryDto Usage { get; init; } = new();
    public VersionInfoDto Versions { get; init; } = new();
    public List<string> EvidenceBundleIds { get; init; } = new();
    public string? ResultHash { get; init; }
    public string? Signature { get; init; }
}
