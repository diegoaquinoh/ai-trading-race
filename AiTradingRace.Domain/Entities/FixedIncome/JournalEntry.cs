namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>One-sided journal line in USD cents.</summary>
public class JournalEntry
{
    public long Id { get; set; }

    public long JournalDbId { get; set; }

    public Journal? Journal { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string LineId { get; set; } = string.Empty;

    public int LineNumber { get; set; }

    /// <summary>Chart-of-accounts code (CASH, BOND_PRINCIPAL, ...).</summary>
    public string Account { get; set; } = string.Empty;

    public string? SecurityId { get; set; }

    public decimal DebitUsd { get; set; }

    public decimal CreditUsd { get; set; }

    public string? Memo { get; set; }
}
