namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Resource usage of a logical decision (all attempts, tools and evidence).</summary>
public class UsageRecord
{
    public long Id { get; set; }

    public long DecisionDbId { get; set; }

    public int GenerationCalls { get; set; }

    public int ToolCalls { get; set; }

    public int EvidenceCalls { get; set; }

    public int UniqueEvidenceChunks { get; set; }

    public int EvidenceTokens { get; set; }

    public int InputTokens { get; set; }

    public int OutputTokens { get; set; }

    public int DurationMs { get; set; }

    public decimal? EstimatedCostUsd { get; set; }

    public string? PriceScheduleId { get; set; }

    public string? BudgetExhausted { get; set; }
}
