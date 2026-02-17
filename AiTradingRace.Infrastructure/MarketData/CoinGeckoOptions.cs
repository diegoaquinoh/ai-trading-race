namespace AiTradingRace.Infrastructure.MarketData;

/// <summary>
/// Configuration options for CoinGecko API client.
/// </summary>
public sealed class CoinGeckoOptions
{
    /// <summary>
    /// Configuration section name in appsettings.json.
    /// </summary>
    public const string SectionName = "CoinGecko";

    /// <summary>
    /// Base URL for CoinGecko API. Default: https://api.coingecko.com/api/v3
    /// </summary>
    public string BaseUrl { get; set; } = "https://api.coingecko.com/api/v3/";

    /// <summary>
    /// API key for CoinGecko. Required even for the free Demo plan.
    /// Get one at https://www.coingecko.com/en/api/pricing
    /// </summary>
    public string? ApiKey { get; set; }

    /// <summary>
    /// HTTP request timeout in seconds. Default: 30 seconds.
    /// </summary>
    public int TimeoutSeconds { get; set; } = 30;

    /// <summary>
    /// Default number of days of historical data to fetch. Default: 1 day.
    /// </summary>
    public int DefaultDays { get; set; } = 1;
}
