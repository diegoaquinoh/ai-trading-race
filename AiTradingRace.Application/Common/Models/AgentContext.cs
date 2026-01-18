using AiTradingRace.Domain.Entities;

namespace AiTradingRace.Application.Common.Models;

public record AgentContext(
    Guid AgentId,
    ModelProvider ModelProvider,
    PortfolioState Portfolio,
    IReadOnlyList<MarketCandleDto> RecentCandles,
    string Instructions);

