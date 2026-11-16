namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Audit record of one logical strategy decision (spec 14.5, 15.2). Persisted for
/// every outcome including HOLD, abstention, failure, budget exhaustion and stale
/// skips. Has no dependency on the legacy knowledge graph or regime detector.
/// Logical identity: (RunId, CycleId, StrategyId, Repetition).
/// </summary>
public class Decision
{
    public long Id { get; set; }

    public string DecisionId { get; set; } = string.Empty;

    public string RunId { get; set; } = string.Empty;

    public string CycleId { get; set; } = string.Empty;

    public string StrategyId { get; set; } = string.Empty;

    public int Repetition { get; set; }

    public string? StrategyKind { get; set; }

    public string? PortfolioId { get; set; }

    /// <summary>Strategy outcome enum (completed_hold, failed_budget, ...).</summary>
    public string Outcome { get; set; } = string.Empty;

    /// <summary>HOLD | REBALANCE | BOOTSTRAP when a proposal exists.</summary>
    public string? Action { get; set; }

    public DateTimeOffset CompletedAt { get; set; }

    public string ReasonsJson { get; set; } = "[]";

    public string? ProposalJson { get; set; }

    public string? ResearchNoteJson { get; set; }

    public string ValidationJson { get; set; } = "[]";

    public string SpecialistTasksJson { get; set; } = "[]";

    public string? VersionsJson { get; set; }

    public string EvidenceBundleIdsJson { get; set; } = "[]";

    public string? RequestHash { get; set; }

    public string InputHashesJson { get; set; } = "{}";

    public string? ResultHash { get; set; }

    public string? Signature { get; set; }

    /// <summary>verified | synthesized | hash_mismatch | signature_invalid.</summary>
    public string Integrity { get; set; } = FiAuditIntegrity.Verified;

    public string? EngineVersion { get; set; }

    public string? Provider { get; set; }

    public string? Model { get; set; }

    /// <summary>Exact JSON text of the StrategyResult as received (null when synthesized).</summary>
    public string? ResultJson { get; set; }

    public DateTimeOffset RecordedAt { get; set; }

    public ICollection<DecisionAttempt> Attempts { get; set; } = new List<DecisionAttempt>();

    public ICollection<ToolTrace> ToolTraces { get; set; } = new List<ToolTrace>();

    public ICollection<PolicyEvaluation> PolicyEvaluations { get; set; } = new List<PolicyEvaluation>();

    public UsageRecord? Usage { get; set; }
}
