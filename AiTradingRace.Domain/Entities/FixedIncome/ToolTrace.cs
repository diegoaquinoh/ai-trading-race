namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Typed tool invocation trace under a decision.</summary>
public class ToolTrace
{
    public long Id { get; set; }

    public long DecisionDbId { get; set; }

    public string TraceId { get; set; } = string.Empty;

    public string AgentRole { get; set; } = string.Empty;

    public string ToolName { get; set; } = string.Empty;

    public string RequestJson { get; set; } = "{}";

    public string ResponseSummaryJson { get; set; } = "{}";

    public string? OutputRef { get; set; }

    public DateTimeOffset StartedAt { get; set; }

    public int DurationMs { get; set; }

    public string Status { get; set; } = string.Empty;

    public string? Error { get; set; }
}
