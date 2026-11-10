using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Application.FixedIncome;

/// <summary>
/// Persists every strategy outcome with attempts, tool traces, usage and policy
/// evaluation (spec 14.7, 15.2). No dependency on the legacy knowledge graph or
/// regime detector.
/// </summary>
public interface IDecisionAuditService
{
    /// <summary>Records a StrategyResult as received (hash/signature verified and recorded as integrity status).</summary>
    Task<DecisionAuditResult> RecordResultAsync(RawContractJson strategyResult, DecisionAuditContext context, CancellationToken cancellationToken = default);

    /// <summary>Records an outcome synthesized by the platform when no engine result exists (dependency failure, stale skip, cancel).</summary>
    Task<DecisionAuditResult> RecordSynthesizedOutcomeAsync(SynthesizedDecisionOutcome outcome, CancellationToken cancellationToken = default);
}

public sealed record DecisionAuditContext
{
    public string? PortfolioId { get; init; }
    public string? ExpectedDecisionId { get; init; }

    /// <summary>
    /// Canonical hash of the DecisionRequest body sent. An authentic result echoing another hash is
    /// recorded with integrity <c>request_hash_mismatch</c> and is never actionable.
    /// </summary>
    public string? ExpectedRequestHash { get; init; }
}

public sealed record SynthesizedDecisionOutcome
{
    public string RunId { get; init; } = string.Empty;
    public string CycleId { get; init; } = string.Empty;
    public string DecisionId { get; init; } = string.Empty;
    public string StrategyId { get; init; } = string.Empty;
    public int Repetition { get; init; }
    public string? StrategyKind { get; init; }
    public string? PortfolioId { get; init; }
    public string Outcome { get; init; } = string.Empty;
    public IReadOnlyList<string> Reasons { get; init; } = Array.Empty<string>();
    public DateTimeOffset CompletedAt { get; init; }
    public string? RequestHash { get; init; }
    public string? EngineVersion { get; init; }

    /// <summary>Optional platform action (e.g. BOOTSTRAP for the common bootstrap allocation).</summary>
    public string? Action { get; init; }

    /// <summary>Optional canonical proposal JSON (action + target weights) for platform-originated decisions.</summary>
    public string? ProposalJson { get; init; }
}

public enum DecisionAuditStatus
{
    Recorded,
    AlreadyRecorded,
    Conflict,
    Rejected,
}

public sealed record DecisionAuditResult
{
    public DecisionAuditStatus Status { get; init; }
    public string DecisionId { get; init; } = string.Empty;
    public string? Outcome { get; init; }
    public string? Integrity { get; init; }

    /// <summary>Integrity verified and the outcome is a proposal that may lead to orders.</summary>
    public bool ActionableProposal { get; init; }

    public IReadOnlyList<string> Issues { get; init; } = Array.Empty<string>();
}
