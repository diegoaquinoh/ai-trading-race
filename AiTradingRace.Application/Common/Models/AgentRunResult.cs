namespace AiTradingRace.Application.Common.Models;

public record AgentRunResult(
    Guid AgentId,
    DateTimeOffset StartedAt,
    DateTimeOffset CompletedAt,
    PortfolioState Portfolio,
    AgentDecision Decision);

