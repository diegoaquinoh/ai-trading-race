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
        // Generate deterministic BatchId from orchestrator instance ID
        // This ensures different orchestrator instances (manual vs scheduled) get different BatchIds
        var batchId = GenerateDeterministicBatchId(request.OrchestratorInstanceId);
        
        _logger.LogInformation(
            "Ingesting market data for batch {BatchId} at {Timestamp} (Orchestrator: {InstanceId})",
            batchId, request.Timestamp, request.OrchestratorInstanceId);

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

    /// <summary>
    /// Generates a deterministic BatchId from an orchestrator instance ID.
    /// Same instance ID always produces the same GUID for idempotency.
    /// 
    /// BENEFITS:
    /// - Different orchestrator instances get different BatchIds (manual vs scheduled)
    /// - Orchestrator replays produce same BatchId (deterministic)
    /// - No collision between concurrent operations
    /// - Allows historical reprocessing with unique instance IDs
    /// 
    /// EXAMPLE:
    /// - "market-cycle-20260205-1430"        → BatchId: abc123...
    /// - "market-cycle-manual-20260205-1430" → BatchId: def456... (different!)
    /// </summary>
    private static Guid GenerateDeterministicBatchId(string orchestratorInstanceId)
    {
        // Use SHA256 hash of instance ID to create deterministic GUID
        using var sha256 = System.Security.Cryptography.SHA256.Create();
        var hashBytes = sha256.ComputeHash(System.Text.Encoding.UTF8.GetBytes(orchestratorInstanceId));
        
        // Take first 16 bytes of hash to create GUID
        var guidBytes = new byte[16];
        Array.Copy(hashBytes, guidBytes, 16);
        
        // Ensure it's a valid RFC 4122 GUID (version 5, variant 2)
        guidBytes[6] = (byte)((guidBytes[6] & 0x0F) | 0x50); // Version 5
        guidBytes[8] = (byte)((guidBytes[8] & 0x3F) | 0x80); // Variant 2
        
        return new Guid(guidBytes);
    }
}
