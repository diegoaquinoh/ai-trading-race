using System.Collections.Concurrent;
using System.Diagnostics.Metrics;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Executor metrics (spec 18.3) on the <c>AiTradingRace.FixedIncome</c> meter (exported by
/// any OpenTelemetry/Application Insights listener) plus in-process totals that tests and
/// the logs can read. Counters: pending/expired orders, duplicate-command detections,
/// concurrency conflicts, budget exhaustion, incomplete valuations, decision outcomes,
/// classified errors and cycle checkpoints.
/// </summary>
public sealed class FixedIncomeMetrics : IDisposable
{
    public const string MeterName = "AiTradingRace.FixedIncome";

    public const string OrdersPending = "fi.orders.pending";
    public const string OrdersExpired = "fi.orders.expired";
    public const string DuplicateCommands = "fi.commands.duplicate_detections";
    public const string ConcurrencyConflicts = "fi.commands.concurrency_conflicts";
    public const string BudgetExhausted = "fi.decisions.budget_exhausted";
    public const string IncompleteValuations = "fi.valuations.incomplete";
    public const string DecisionOutcomes = "fi.decisions.outcomes";
    public const string Errors = "fi.errors";
    public const string Cycles = "fi.cycles.checkpoints";

    private readonly Meter _meter = new(MeterName);
    private readonly ConcurrentDictionary<string, Counter<long>> _counters = new(StringComparer.Ordinal);
    private readonly ConcurrentDictionary<string, long> _totals = new(StringComparer.Ordinal);

    public void Add(string name, long value = 1, string? tagKey = null, string? tagValue = null)
    {
        if (value == 0)
        {
            return;
        }

        var counter = _counters.GetOrAdd(name, n => _meter.CreateCounter<long>(n));
        if (tagKey is null)
        {
            counter.Add(value);
        }
        else
        {
            counter.Add(value, new KeyValuePair<string, object?>(tagKey, tagValue));
        }

        _totals.AddOrUpdate(name, value, (_, current) => current + value);
        if (tagKey is not null)
        {
            _totals.AddOrUpdate($"{name}[{tagKey}={tagValue}]", value, (_, current) => current + value);
        }
    }

    /// <summary>Process-lifetime total of a counter (optionally for one tag value).</summary>
    public long Total(string name, string? tagKey = null, string? tagValue = null) =>
        _totals.TryGetValue(tagKey is null ? name : $"{name}[{tagKey}={tagValue}]", out var value) ? value : 0;

    public IReadOnlyDictionary<string, long> Snapshot() => new Dictionary<string, long>(_totals, StringComparer.Ordinal);

    public void Dispose() => _meter.Dispose();
}
