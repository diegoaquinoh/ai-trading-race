using AiTradingRace.Application.MarketData;
using AiTradingRace.Functions.Models;
using AiTradingRace.Infrastructure.Database;
using Microsoft.Azure.Functions.Worker;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Activities;

/// <summary>
/// Activity function to ingest market data from external APIs.
/// </summary>
public sealed class IngestMarketDataActivity
{
    private readonly IMarketDataIngestionService _ingestionService;
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<IngestMarketDataActivity> _logger;

    public IngestMarketDataActivity(
        IMarketDataIngestionService ingestionService,
        TradingDbContext dbContext,
        ILogger<IngestMarketDataActivity> logger)
    {
        _ingestionService = ingestionService;
        _dbContext = dbContext;
        _logger = logger;
    }

    [Function(nameof(IngestMarketDataActivity))]
    public async Task<MarketDataResult> Run(
        [ActivityTrigger] IngestMarketDataRequest request,
        CancellationToken ct)
    {
        var batchId = Guid.NewGuid();
        
        _logger.LogInformation(
            "Ingesting market data for batch {BatchId} at {Timestamp}",
            batchId, request.Timestamp);

        // Ingest latest candles from CoinGecko
        var insertedCount = await _ingestionService.IngestAllAssetsAsync(ct);
        
        _logger.LogInformation(
            "Ingested {Count} candles for batch {BatchId}",
            insertedCount, batchId);

        // Get latest prices from the database
        var prices = await GetLatestPricesAsync(ct);

        return new MarketDataResult(batchId, request.Timestamp, prices);
    }

    private async Task<Dictionary<string, decimal>> GetLatestPricesAsync(CancellationToken ct)
    {
        // Get all assets
        var assets = await _dbContext.MarketAssets
            .AsNoTracking()
            .Select(a => new { a.Id, a.Symbol })
            .ToListAsync(ct);

        // Get latest candle for each asset
        var assetIds = assets.Select(a => a.Id).ToList();
        
        var latestCandles = await _dbContext.MarketCandles
            .AsNoTracking()
            .Where(c => assetIds.Contains(c.MarketAssetId))
            .GroupBy(c => c.MarketAssetId)
            .Select(g => new
            {
                AssetId = g.Key,
                Price = g.OrderByDescending(c => c.TimestampUtc).First().Close
            })
            .ToListAsync(ct);

        // Map asset IDs to symbols
        var assetIdToSymbol = assets.ToDictionary(a => a.Id, a => a.Symbol);
        
        return latestCandles
            .Where(c => assetIdToSymbol.ContainsKey(c.AssetId))
            .ToDictionary(
                c => assetIdToSymbol[c.AssetId],
                c => c.Price);
    }
}
