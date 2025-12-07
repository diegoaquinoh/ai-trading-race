namespace AiTradingRace.Domain.Entities;

public class MarketCandle
{
    public Guid Id { get; init; }

    public Guid MarketAssetId { get; set; }

    public DateTimeOffset TimestampUtc { get; set; }

    public decimal Open { get; set; }

    public decimal High { get; set; }

    public decimal Low { get; set; }

    public decimal Close { get; set; }

    public decimal Volume { get; set; }
}

