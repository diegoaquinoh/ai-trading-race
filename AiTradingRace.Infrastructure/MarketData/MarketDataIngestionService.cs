using AiTradingRace.Application.MarketData;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.MarketData;

/// <summary>
/// Service for ingesting market data from external providers and persisting to database.
/// Handles duplicate prevention by checking existing timestamps.
/// </summary>
public sealed class MarketDataIngestionService : IMarketDataIngestionService
{
    private readonly TradingDbContext _dbContext;
    private readonly IExternalMarketDataClient _externalClient;
    private readonly CoinGeckoOptions _options;
    private readonly ILogger<MarketDataIngestionService> _logger;

    public MarketDataIngestionService(
        TradingDbContext dbContext,
        IExternalMarketDataClient externalClient,
        IOptions<CoinGeckoOptions> options,
        ILogger<MarketDataIngestionService> logger)
    {
        _dbContext = dbContext;
        _externalClient = externalClient;
        _options = options.Value;
        _logger = logger;
    }

    /// <inheritdoc />
    public async Task<int> IngestLatestCandlesAsync(
        string assetSymbol,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(assetSymbol);

        var normalizedSymbol = assetSymbol.ToUpperInvariant();

        // Find the asset in DB
        var asset = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled && a.Symbol == normalizedSymbol)
            .SingleOrDefaultAsync(cancellationToken);

        if (asset is null)
        {
            _logger.LogWarning("Asset {Symbol} not found or not enabled", normalizedSymbol);
            return 0;
        }

        if (string.IsNullOrWhiteSpace(asset.ExternalId))
        {
            _logger.LogWarning("Asset {Symbol} has no ExternalId configured", normalizedSymbol);
            return 0;
        }

        return await IngestCandlesForAssetAsync(asset, cancellationToken);
    }

    /// <inheritdoc />
    public async Task<int> IngestAllAssetsAsync(CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Starting ingestion for all enabled assets");

        var enabledAssets = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled)
            .ToListAsync(cancellationToken);

        var totalInserted = 0;

        foreach (var asset in enabledAssets)
        {
            if (string.IsNullOrWhiteSpace(asset.ExternalId))
            {
                _logger.LogWarning("Asset {Symbol} has no ExternalId configured, skipping", asset.Symbol);
                continue;
            }

            var insertedCount = await IngestCandlesForAssetAsync(asset, cancellationToken);
            totalInserted += insertedCount;

            // Small delay to respect CoinGecko rate limits (free tier: ~10-30 requests/minute)
            if (enabledAssets.Count > 1)
            {
                await Task.Delay(2500, cancellationToken);
            }
        }

        _logger.LogInformation(
            "Completed ingestion for {AssetCount} assets. Total candles inserted: {TotalInserted}",
            enabledAssets.Count,
            totalInserted);

        return totalInserted;
    }

    private async Task<int> IngestCandlesForAssetAsync(
        MarketAsset asset,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation("Fetching candles for {Symbol} ({ExternalId})", asset.Symbol, asset.ExternalId);

        // Fetch candles from external API
        var externalCandles = await _externalClient.GetCandlesAsync(
            asset.ExternalId,
            asset.QuoteCurrency.ToLowerInvariant(),
            _options.DefaultDays,
            cancellationToken);

        if (externalCandles.Count == 0)
        {
            _logger.LogWarning("No candles returned for {Symbol}", asset.Symbol);
            return 0;
        }

        // Get existing timestamps to prevent duplicates
        var existingTimestamps = await _dbContext.MarketCandles
            .Where(c => c.MarketAssetId == asset.Id)
            .Select(c => c.TimestampUtc)
            .ToHashSetAsync(cancellationToken);

        // Filter out duplicates and map to entities
        var newCandles = externalCandles
            .Where(c => !existingTimestamps.Contains(c.TimestampUtc))
            .Select(c => new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = asset.Id,
                TimestampUtc = c.TimestampUtc,
                Open = c.Open,
                High = c.High,
                Low = c.Low,
                Close = c.Close,
                Volume = 0 // CoinGecko OHLC endpoint doesn't include volume
            })
            .ToList();

        if (newCandles.Count == 0)
        {
            _logger.LogDebug(
                "No new candles for {Symbol}. Skipped {SkippedCount} duplicates.",
                asset.Symbol,
                externalCandles.Count);
            return 0;
        }

        // Bulk insert new candles
        _dbContext.MarketCandles.AddRange(newCandles);
        await _dbContext.SaveChangesAsync(cancellationToken);

        _logger.LogInformation(
            "Inserted {InsertedCount} new candles for {Symbol}. Skipped {SkippedCount} duplicates.",
            newCandles.Count,
            asset.Symbol,
            externalCandles.Count - newCandles.Count);

        return newCandles.Count;
    }
}

/// <summary>
/// Extension method to convert IQueryable to HashSet asynchronously.
/// </summary>
internal static class QueryableExtensions
{
    public static async Task<HashSet<T>> ToHashSetAsync<T>(
        this IQueryable<T> source,
        CancellationToken cancellationToken = default)
    {
        var list = await source.ToListAsync(cancellationToken);
        return new HashSet<T>(list);
    }
}
