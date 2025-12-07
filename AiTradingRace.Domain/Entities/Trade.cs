namespace AiTradingRace.Domain.Entities;

public class Trade
{
    public Guid Id { get; init; }

    public Guid PortfolioId { get; set; }

    public Guid MarketAssetId { get; set; }

    public DateTimeOffset ExecutedAt { get; set; }

    public decimal Quantity { get; set; }

    public decimal Price { get; set; }

    public TradeSide Side { get; set; } = TradeSide.Buy;
}

