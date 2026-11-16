namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Coupon, redemption, capital or cash-interest flow committed exactly once.</summary>
public class CashFlowEvent
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string CashFlowId { get; set; } = string.Empty;

    public string SecurityId { get; set; } = string.Empty;

    /// <summary>COUPON | REDEMPTION | CAPITAL | CASH_INTEREST.</summary>
    public string Kind { get; set; } = string.Empty;

    public DateOnly PaymentDate { get; set; }

    public decimal EntitledFace { get; set; }

    public decimal AmountUsd { get; set; }

    public long CommittedVersion { get; set; }
}
