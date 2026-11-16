namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Execution against an eligible later observation. One fill per order.</summary>
public class Fill
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string FillId { get; set; } = string.Empty;

    public string OrderId { get; set; } = string.Empty;

    public string SecurityId { get; set; } = string.Empty;

    public string Side { get; set; } = string.Empty;

    public decimal Face { get; set; }

    public DateTimeOffset ExecutedAt { get; set; }

    public string ObservationId { get; set; } = string.Empty;

    public string QuoteKind { get; set; } = string.Empty;

    public decimal ReferenceCleanPricePer100 { get; set; }

    public decimal ExecutionCleanPricePer100 { get; set; }

    public decimal AccruedPer100 { get; set; }

    public decimal DirtyPricePer100 { get; set; }

    public decimal HalfSpreadPer100 { get; set; }

    public DateOnly SettlementDate { get; set; }

    /// <summary>Cash consideration in cents.</summary>
    public decimal ConsiderationUsd { get; set; }

    public decimal FeesUsd { get; set; }

    /// <summary>Analytic spread cost embedded in the execution price.</summary>
    public decimal SpreadCostUsd { get; set; }

    public string TimingLabel { get; set; } = string.Empty;

    public long CommittedVersion { get; set; }

    public string FillJson { get; set; } = string.Empty;
}
