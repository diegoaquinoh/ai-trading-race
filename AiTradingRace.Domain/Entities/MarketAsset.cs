namespace AiTradingRace.Domain.Entities;

public class MarketAsset
{
    public Guid Id { get; init; }

    public string Symbol { get; set; } = string.Empty;

    public string Name { get; set; } = string.Empty;

    public string QuoteCurrency { get; set; } = "USD";

    /// <summary>
    /// External identifier for API providers (e.g., "bitcoin" for CoinGecko).
    /// </summary>
    public string ExternalId { get; set; } = string.Empty;

    public bool IsEnabled { get; set; } = true;
}

