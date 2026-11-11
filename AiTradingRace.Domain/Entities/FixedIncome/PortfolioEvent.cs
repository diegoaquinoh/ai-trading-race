namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Economic event applied to a portfolio. Unique (PortfolioId, EventId) enforces
/// one committed financial effect per economic event across retries.
/// </summary>
public class PortfolioEvent
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string EventId { get; set; } = string.Empty;

    public string EventType { get; set; } = string.Empty;

    public DateTimeOffset? EffectiveAt { get; set; }

    public int? Priority { get; set; }

    public long CommittedVersion { get; set; }

    public string CommandId { get; set; } = string.Empty;

    /// <summary>Canonical JSON of the event as proposed (null when only referenced by a journal).</summary>
    public string? EventJson { get; set; }
}
