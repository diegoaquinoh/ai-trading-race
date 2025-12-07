namespace AiTradingRace.Domain.Entities;

public class Position
{
    public Guid Id { get; init; }

    public Guid PortfolioId { get; set; }

    public Guid MarketAssetId { get; set; }

    public decimal Quantity { get; set; }

    public decimal AverageEntryPrice { get; set; }
}

