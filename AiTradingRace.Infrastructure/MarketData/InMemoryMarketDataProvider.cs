using System.Linq;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;

namespace AiTradingRace.Infrastructure.MarketData;

public sealed class InMemoryMarketDataProvider : IMarketDataProvider
{
    public Task<IReadOnlyList<MarketCandleDto>> GetLatestCandlesAsync(
        string assetSymbol,
        int limit = 100,
        CancellationToken cancellationToken = default)
    {
        var now = DateTime.UtcNow;
        var data = Enumerable.Range(0, Math.Max(1, limit))
            .Select(index =>
            {
                var timestamp = now.AddMinutes(-index);
                var price = 50000m + (decimal)Math.Sin(index) * 1000m;
                var high = price + 100m;
                var low = price - 100m;
                return new MarketCandleDto(
                    assetSymbol.ToUpperInvariant(),
                    timestamp,
                    price,
                    high,
                    low,
                    price,
                    1000m + index);
            })
            .OrderBy(candle => candle.TimestampUtc)
            .ToList()
            .AsReadOnly();

        return Task.FromResult<IReadOnlyList<MarketCandleDto>>(data);
    }
}

