namespace AiTradingRace.Application.MarketData;

/// <summary>
/// Service for ingesting market data from external providers into the database.
/// </summary>
public interface IMarketDataIngestionService
{
    /// <summary>
    /// Fetches latest candles from external API and persists new ones to the database.
    /// </summary>
    /// <param name="assetSymbol">Asset symbol (e.g., "BTC", "ETH").</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Count of newly inserted candles.</returns>
    Task<int> IngestLatestCandlesAsync(string assetSymbol, CancellationToken cancellationToken = default);

    /// <summary>
    /// Ingests candles for all enabled assets.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Total count of newly inserted candles.</returns>
    Task<int> IngestAllAssetsAsync(CancellationToken cancellationToken = default);
}
