namespace AiTradingRace.Domain.Entities;

public class Agent
{
    public Guid Id { get; init; }

    public string Name { get; set; } = string.Empty;

    public string Provider { get; set; } = string.Empty;

    public bool IsActive { get; set; } = true;

    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;
}

