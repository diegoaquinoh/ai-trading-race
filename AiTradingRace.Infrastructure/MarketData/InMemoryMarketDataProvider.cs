using System.Collections.Generic;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;

namespace AiTradingRace.Infrastructure.MarketData;

public sealed class InMemoryMarketDataProvider : IMarketDataProvider
{
    private const int MaxLimit = 1_000;

    public Task<IReadOnlyList<MarketCandleDto>> GetLatestCandlesAsync(
        string assetSymbol,
        int limit = 100,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(assetSymbol);

        if (limit <= 0 || limit > MaxLimit)
        {
            throw new ArgumentOutOfRangeException(nameof(limit), $"Limit must be between 1 and {MaxLimit}.");
        }

        var now = DateTimeOffset.UtcNow;
        var list = new List<MarketCandleDto>(limit);

        for (var i = limit - 1; i >= 0; i--)
        {
            var timestamp = now.AddMinutes(-i);
            var price = 50_000m + (decimal)Math.Sin(i) * 1_000m;
            var high = price + 100m;
            var low = price - 100m;
            list.Add(new MarketCandleDto(
                assetSymbol.ToUpperInvariant(),
                timestamp,
                price,
                high,
                low,
                price,
                1_000m + i));
        }

        return Task.FromResult<IReadOnlyList<MarketCandleDto>>(list.AsReadOnly());
    }
}

