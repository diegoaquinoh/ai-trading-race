using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.MarketData;

/// <summary>
/// Client for fetching market data from an external provider (e.g., CoinGecko, Binance).
/// </summary>
public interface IExternalMarketDataClient
{
    /// <summary>
    /// Fetches OHLC candles from an external market data provider.
    /// </summary>
    /// <param name="coinId">External coin identifier (e.g., "bitcoin", "ethereum" for CoinGecko).</param>
    /// <param name="vsCurrency">Quote currency (e.g., "usd").</param>
    /// <param name="days">Number of days of historical data to fetch (1, 7, 14, 30, 90, 180, 365, max).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>List of candles from the external provider.</returns>
    Task<IReadOnlyList<ExternalCandleDto>> GetCandlesAsync(
        string coinId,
        string vsCurrency,
        int days,
        CancellationToken cancellationToken = default);
}
