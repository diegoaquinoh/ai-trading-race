using AiTradingRace.Application.MarketData;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

public sealed class MarketDataFunction
{
    private readonly IMarketDataProvider _marketDataProvider;
    private readonly ILogger<MarketDataFunction> _logger;

    public MarketDataFunction(
        IMarketDataProvider marketDataProvider,
        ILogger<MarketDataFunction> logger)
    {
        _marketDataProvider = marketDataProvider;
        _logger = logger;
    }

    [Function(nameof(MarketDataFunction))]
    public async Task RunAsync(
        [TimerTrigger("0 */15 * * * *")] TimerInfo timerInfo,
        CancellationToken cancellationToken)
    {
        var candles = await _marketDataProvider.GetLatestCandlesAsync("BTC", 5, cancellationToken);
        _logger.LogInformation("Market data function ran at {Timestamp}, fetched {Count} candles.", DateTimeOffset.UtcNow, candles.Count);
    }
}

