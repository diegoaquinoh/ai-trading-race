namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Settlement obligation created by a fill. One settlement per fill.</summary>
public class Settlement
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string SettlementId { get; set; } = string.Empty;

    public string FillId { get; set; } = string.Empty;

    public string SecurityId { get; set; } = string.Empty;

    public string Side { get; set; } = string.Empty;

    public decimal Face { get; set; }

    public DateOnly SettlementDate { get; set; }

    /// <summary>Payable for BUY, receivable for SELL (positive, cents).</summary>
    public decimal CashUsd { get; set; }

    /// <summary>pending | completed.</summary>
    public string Status { get; set; } = FiSettlementStatus.Pending;

    public long CreatedInVersion { get; set; }

    public long? CompletedInVersion { get; set; }

    public string SettlementJson { get; set; } = string.Empty;
}
