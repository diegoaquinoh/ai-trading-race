namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Policy evaluation reported by the engine plus the independent .NET re-check
/// against its own configured RiskPolicy.
/// </summary>
public class PolicyEvaluation
{
    public long Id { get; set; }

    /// <summary>Owning decision audit row, when known.</summary>
    public long? DecisionDbId { get; set; }

    public string DecisionId { get; set; } = string.Empty;

    public string? PortfolioId { get; set; }

    public string? CommandId { get; set; }

    /// <summary>strategy_result | transition_proposal.</summary>
    public string Source { get; set; } = string.Empty;

    public string PolicyId { get; set; } = string.Empty;

    public string Action { get; set; } = string.Empty;

    public bool Passed { get; set; }

    public bool BreachMode { get; set; }

    public bool BootstrapExemptionApplied { get; set; }

    public decimal? PostTradeNavUsd { get; set; }

    public decimal? PostTradeCashRatio { get; set; }

    public decimal? PostTradeMaxSecurityRatio { get; set; }

    public decimal? PostTradeParallelDv01Usd { get; set; }

    public decimal? TurnoverRatio { get; set; }

    public int OrderCount { get; set; }

    public string RejectedReasonsJson { get; set; } = "[]";

    /// <summary>Result of the .NET re-comparison against its own policy (null if not re-checked).</summary>
    public bool? PlatformRecheckPassed { get; set; }

    public string PlatformRecheckReasonsJson { get; set; } = "[]";

    /// <summary>Canonical JSON of the full evaluation (checks, targets, sized orders).</summary>
    public string EvaluationJson { get; set; } = string.Empty;

    public DateTimeOffset RecordedAt { get; set; }
}
