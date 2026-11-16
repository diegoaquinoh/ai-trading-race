namespace AiTradingRace.Application.Common.Models;

public record AgentDecision(
    Guid AgentId,
    DateTimeOffset CreatedAt,
    IReadOnlyList<TradeOrder> Orders,
    // Knowledge Graph Citations
    List<string>? CitedRuleIds = null,
    string? Rationale = null);

