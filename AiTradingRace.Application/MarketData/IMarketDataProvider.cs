using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.MarketData;

public interface IMarketDataProvider
{
    Task<IReadOnlyList<MarketCandleDto>> GetLatestCandlesAsync(
        string assetSymbol,
        int limit = 100,
        CancellationToken cancellationToken = default);
}

