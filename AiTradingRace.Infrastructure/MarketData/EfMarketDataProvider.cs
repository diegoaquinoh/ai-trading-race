using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Infrastructure.MarketData;

public sealed class EfMarketDataProvider : IMarketDataProvider
{
    private const int MaxLimit = 1_000;
    private readonly TradingDbContext _dbContext;

    public EfMarketDataProvider(TradingDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<IReadOnlyList<MarketCandleDto>> GetLatestCandlesAsync(
        string assetSymbol,
        int limit = 100,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(assetSymbol);

        if (limit <= 0 || limit > MaxLimit)
        {
            throw new ArgumentOutOfRangeException(nameof(limit), $"Limit must be between 1 and {MaxLimit}.");
        }

        var normalizedSymbol = assetSymbol.ToUpperInvariant();
        var asset = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled)
            .SingleOrDefaultAsync(a => a.Symbol == normalizedSymbol, cancellationToken);

        if (asset is null)
        {
            return Array.Empty<MarketCandleDto>();
        }

        var candles = await _dbContext.MarketCandles
            .AsNoTracking()
            .Where(c => c.MarketAssetId == asset.Id)
            .OrderByDescending(c => c.TimestampUtc)
            .Take(limit)
            .OrderBy(c => c.TimestampUtc)
            .Select(c => new MarketCandleDto(
                normalizedSymbol,
                c.TimestampUtc,
                c.Open,
                c.High,
                c.Low,
                c.Close,
                c.Volume))
            .ToListAsync(cancellationToken);

        return candles;
    }
}

