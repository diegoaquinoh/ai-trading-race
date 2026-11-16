namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>Balanced journal posted by an authorized transition.</summary>
public class Journal
{
    public long Id { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string JournalId { get; set; } = string.Empty;

    public string EventId { get; set; } = string.Empty;

    public string EventType { get; set; } = string.Empty;

    public DateTimeOffset EffectiveAt { get; set; }

    /// <summary>Posting template id, e.g. buy_fill_v1.</summary>
    public string Template { get; set; } = string.Empty;

    public long CommittedVersion { get; set; }

    public string CommandId { get; set; } = string.Empty;

    public ICollection<JournalEntry> Entries { get; set; } = new List<JournalEntry>();
}
