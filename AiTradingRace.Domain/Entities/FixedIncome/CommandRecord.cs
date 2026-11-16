namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Logical command ledger (spec 9.5, 14.6). The unique CommandId is bound to the
/// canonical request hash: a retry with the same hash returns the committed
/// result; the same id with a different hash is a conflict.
/// </summary>
public class CommandRecord
{
    public long Id { get; set; }

    public string CommandId { get; set; } = string.Empty;

    public string CommandType { get; set; } = string.Empty;

    public string PortfolioId { get; set; } = string.Empty;

    public string RequestHash { get; set; } = string.Empty;

    public string ProposalHash { get; set; } = string.Empty;

    public string ProposalId { get; set; } = string.Empty;

    public string EngineVersion { get; set; } = string.Empty;

    public long ExpectedVersion { get; set; }

    /// <summary>Version after commit (equal to ExpectedVersion for no-op proposals; null when rejected).</summary>
    public long? CommittedVersion { get; set; }

    /// <summary>committed | rejected_reconciliation.</summary>
    public string Status { get; set; } = FiCommandStatus.Committed;

    public string? Reason { get; set; }

    /// <summary>JSON summary returned to retried callers.</summary>
    public string ResultJson { get; set; } = "{}";

    public DateTimeOffset CreatedAt { get; set; }
}
