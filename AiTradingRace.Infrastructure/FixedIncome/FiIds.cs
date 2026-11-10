using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Deterministic identifiers of the application-mode executor. Same inputs → same ids, so
/// a retried activity or a restarted run re-issues identical logical commands/decisions.
/// Ids satisfy the contract <c>OpaqueId</c> pattern (≤ 160 chars); longer ids keep a
/// readable prefix plus a content digest (same scheme as the Python <c>make_id</c>).
/// </summary>
public static class FiIds
{
    public const int MaxLength = 160;
    public const string InitCycleId = "init";

    public static class Steps
    {
        public const string Capital = "capital";
        public const string Process = "process";
        public const string Submit = "submit";
        public const string Value = "value";
    }

    /// <summary><c>cycle-YYYY-MM-DD</c>: one cycle per supported market session.</summary>
    public static string Cycle(DateOnly sessionDate) => "cycle-" + FiWire.FormatDate(sessionDate);

    /// <summary><c>dec:{runId}:{cycleId}:{strategyId}:{repetition}</c>.</summary>
    public static string Decision(string runId, string cycleId, string strategyId, int repetition) =>
        Make("dec", runId, cycleId, strategyId, repetition.ToString(System.Globalization.CultureInfo.InvariantCulture));

    /// <summary><c>cmd:{runId}:{cycleId}:{portfolioId}:{step}</c>.</summary>
    public static string Command(string runId, string cycleId, string portfolioId, string step) =>
        Make("cmd", runId, cycleId, portfolioId, step);

    /// <summary>Portfolio snapshot reference id sent with a decision request.</summary>
    public static string PortfolioSnapshot(string portfolioId, long version) =>
        Make("pfs", portfolioId, "v" + version.ToString(System.Globalization.CultureInfo.InvariantCulture));

    public static string Make(params string[] parts)
    {
        var text = string.Join(":", parts);
        if (text.Length <= MaxLength)
        {
            return text;
        }

        var digest = CanonicalJson.ContentHash(JsonValue.Create(text))[FiContract.HashPrefix.Length..][..32];
        var head = string.Join(":", parts.Take(2));
        if (head.Length > MaxLength - 34)
        {
            head = head[..(MaxLength - 34)];
        }

        return head + ":" + digest;
    }
}
