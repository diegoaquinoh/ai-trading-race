namespace AiTradingRace.Domain.Entities;

public class EquitySnapshot
{
    public Guid Id { get; init; }

    public Guid PortfolioId { get; set; }

    public DateTimeOffset CapturedAt { get; set; }

    public decimal TotalValue { get; set; }

    public decimal CashValue { get; set; }

    public decimal PositionsValue { get; set; }

    public decimal UnrealizedPnL { get; set; }

    // Navigation property
    public Portfolio Portfolio { get; set; } = null!;
}

