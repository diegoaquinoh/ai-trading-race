namespace AiTradingRace.Application.Common.Models;

public record AgentDecision(
    Guid AgentId,
    DateTimeOffset CreatedAt,
    IReadOnlyList<TradeOrder> Orders);

