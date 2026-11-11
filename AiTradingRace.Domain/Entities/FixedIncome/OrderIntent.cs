namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Authorized order intent (market order, next-session-only time in force).</summary>
public class OrderIntent
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string OrderId { get; set; } = string.Empty;

    public string DecisionId { get; set; } = string.Empty;

    public string SecurityId { get; set; } = string.Empty;

    /// <summary>BUY | SELL.</summary>
    public string Side { get; set; } = string.Empty;

    /// <summary>USD face amount.</summary>
    public decimal Face { get; set; }

    public DateTimeOffset SubmittedAt { get; set; }

    public DateOnly EligibleSessionDate { get; set; }

    public DateTimeOffset ExpiresAt { get; set; }

    /// <summary>ACCEPTED | FILLED | EXPIRED | CANCELLED | REJECTED.</summary>
    public string Status { get; set; } = FiOrderStatus.Accepted;

    public string? StatusReason { get; set; }

    public decimal ReservedCashUsd { get; set; }

    public int BatchPriority { get; set; }

    public bool Bootstrap { get; set; }

    public long CreatedInVersion { get; set; }

    public long LastUpdatedVersion { get; set; }

    /// <summary>Canonical JSON of the latest proposed order record.</summary>
    public string OrderJson { get; set; } = string.Empty;
}
