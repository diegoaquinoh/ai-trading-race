namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Immutable committed portfolio state. <see cref="StateJson"/> is the exact
/// canonical JSON text received from the research engine; it is sent back
/// verbatim in the next request, so .NET never re-serializes state for hashing.
/// </summary>
public class PortfolioStateVersion
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public long Version { get; set; }

    public string StateJson { get; set; } = string.Empty;

    public string StateHash { get; set; } = string.Empty;

    public DateTimeOffset AsOf { get; set; }

    /// <summary>Logical command that produced this version (null for genesis).</summary>
    public string? CommandId { get; set; }

    public string? ProposalHash { get; set; }

    public DateTimeOffset CreatedAt { get; set; }
}
