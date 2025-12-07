namespace AiTradingRace.Application.Common.Models;

public record AgentContext(
    Guid AgentId,
    PortfolioState Portfolio,
    IReadOnlyList<MarketCandleDto> RecentCandles,
    string Instructions);

