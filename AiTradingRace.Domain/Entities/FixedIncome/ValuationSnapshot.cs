namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Saved valuation with anchors and completeness (produced by the research engine).</summary>
public class ValuationSnapshot
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string ValuationId { get; set; } = string.Empty;

    public long StateVersion { get; set; }

    public DateTimeOffset ValuationAt { get; set; }

    public string DataMode { get; set; } = string.Empty;

    public string? CurveSnapshotId { get; set; }

    public string MarkPolicy { get; set; } = string.Empty;

    public bool Complete { get; set; }

    public string IncompleteReasonsJson { get; set; } = "[]";

    public decimal CashUsd { get; set; }

    public decimal? BondValueUsd { get; set; }

    public decimal? ReceivablesPvUsd { get; set; }

    public decimal? PayablesPvUsd { get; set; }

    public decimal? EquityUsd { get; set; }

    public decimal? ParallelDv01Usd { get; set; }

    public decimal? EffectiveDurationYears { get; set; }

    public long CommittedVersion { get; set; }

    /// <summary>Canonical JSON of the full valuation snapshot (marks, calculation ids).</summary>
    public string ValuationJson { get; set; } = string.Empty;
}
