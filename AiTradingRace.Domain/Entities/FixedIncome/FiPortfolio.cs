namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Authoritative fixed income portfolio header. Distinct from the legacy crypto
/// <see cref="AiTradingRace.Domain.Entities.Portfolio"/>; never reinterprets BTC/ETH units.
/// The state itself lives in <see cref="PortfolioStateVersion"/>.
/// </summary>
public class FiPortfolio
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string RunId { get; set; } = string.Empty;

    public string StrategyId { get; set; } = string.Empty;

    public int Repetition { get; set; }

    /// <summary>Risk policy id resolved against .NET configuration (never chosen by the model).</summary>
    public string RiskPolicyId { get; set; } = string.Empty;

    public string DataMode { get; set; } = FiDataMode.SyntheticCurve;

    public long CurrentVersion { get; set; }

    /// <summary>sha256 of the canonical state JSON of <see cref="CurrentVersion"/>.</summary>
    public string CurrentStateHash { get; set; } = string.Empty;

    /// <summary>Set when a reconciliation failure blocks further commits until operator action.</summary>
    public string? BlockedReason { get; set; }

    public DateTimeOffset? BlockedAt { get; set; }

    public string? BlockedByCommandId { get; set; }

    public DateTimeOffset CreatedAt { get; set; }

    public DateTimeOffset UpdatedAt { get; set; }

    /// <summary>Optimistic concurrency token regenerated on every committed transition.</summary>
    public Guid ConcurrencyStamp { get; set; } = Guid.NewGuid();
}
