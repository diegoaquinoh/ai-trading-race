namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>One model call / attempt under a logical decision (retained even when malformed).</summary>
public class DecisionAttempt
{
    public long Id { get; set; }

    public long DecisionDbId { get; set; }

    public string AttemptId { get; set; } = string.Empty;

    public int AttemptNumber { get; set; }

    public string AgentRole { get; set; } = string.Empty;

    public string Purpose { get; set; } = string.Empty;

    public string Provider { get; set; } = string.Empty;

    public string Model { get; set; } = string.Empty;

    public int InputTokens { get; set; }

    public int OutputTokens { get; set; }

    public DateTimeOffset StartedAt { get; set; }

    public int DurationMs { get; set; }

    public string Status { get; set; } = string.Empty;

    public string? RecordedResponseId { get; set; }

    public string? Error { get; set; }
}
