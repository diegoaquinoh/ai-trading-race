using AiTradingRace.Application.MarketData;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

/// <summary>
/// Timer-triggered function to ingest market data (OHLC candles) from external APIs.
/// </summary>
public sealed class MarketDataFunction
{
    private readonly IMarketDataIngestionService _ingestionService;
    private readonly ILogger<MarketDataFunction> _logger;

    public MarketDataFunction(
        IMarketDataIngestionService ingestionService,
        ILogger<MarketDataFunction> logger)
    {
        _ingestionService = ingestionService;
        _logger = logger;
    }

    /// <summary>
    /// Ingest market data every 15 minutes.
    /// CRON: 0 */15 * * * * (second, minute, hour, day, month, day-of-week)
    /// </summary>
    [Function(nameof(IngestMarketData))]
    public async Task IngestMarketData(
        [TimerTrigger("0 */15 * * * *")] TimerInfo timer,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Market data ingestion started at {Time}. Next run at {NextRun}",
            DateTime.UtcNow,
            timer.ScheduleStatus?.Next);

        try
        {
            var insertedCount = await _ingestionService.IngestAllAssetsAsync(cancellationToken);

            _logger.LogInformation(
                "Market data ingestion completed. Inserted {Count} new candles",
                insertedCount);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Market data ingestion failed");
            throw; // Let Azure Functions handle retry
        }
    }
}

