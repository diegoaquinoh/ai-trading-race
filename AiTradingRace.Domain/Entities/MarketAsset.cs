namespace AiTradingRace.Domain.Entities;

public class MarketAsset
{
    public Guid Id { get; init; }

    public string Symbol { get; set; } = string.Empty;

    public string Name { get; set; } = string.Empty;

    public string QuoteCurrency { get; set; } = "USD";

    public bool IsEnabled { get; set; } = true;
}

