using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Live application-mode run against a running Python research engine (no CLI involved).
/// Runs only when FI_RESEARCH_ENGINE_URL and FI_RESEARCH_ENGINE_KEY are set; the proposal
/// signing key is FI_RESEARCH_ENGINE_SIGNING_KEY (defaults to the API key) and the first
/// session searched is FI_RESEARCH_ENGINE_START (default 2024-01-02). Excluded from
/// <c>make test-backend</c> by its Integration category.
/// </summary>
[Trait("Category", "Integration")]
public sealed class FixedIncomeLiveEngineTests
{
    [LiveEngineFact]
    public async Task FiveSessionApplicationRun_CompletesEveryCycle_AndJournalsBalance()
    {
        var url = Environment.GetEnvironmentVariable("FI_RESEARCH_ENGINE_URL")!;
        var key = Environment.GetEnvironmentVariable("FI_RESEARCH_ENGINE_KEY")!;
        var signingKey = Environment.GetEnvironmentVariable("FI_RESEARCH_ENGINE_SIGNING_KEY") ?? key;
        var startText = Environment.GetEnvironmentVariable("FI_RESEARCH_ENGINE_START") ?? "2024-01-02";
        var options = new ResearchEngineOptions { BaseUrl = url, ApiKey = key, SigningKey = signingKey, TimeoutSeconds = 180 };
        using var http = new HttpClient();
        var client = new ResearchEngineClient(http, Options.Create(options), NullLogger<ResearchEngineClient>.Instance);

        var capabilities = await client.GetCapabilitiesAsync();
        Assert.False(string.IsNullOrEmpty(capabilities.EngineVersion));
        options.AllowedEngineVersions = new List<string> { capabilities.EngineVersion };

        var from = DateOnly.ParseExact(startText, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
        var catalogue = await client.GetMarketSessionsAsync(from, from.AddDays(60));
        var window = FirstFiveReadySessions(catalogue.Sessions);
        Assert.True(window.Count == 5, $"Need five consecutive READY sessions after {startText}; found {window.Count}.");

        using var harness = new FiRunHarness(client, Options.Create(options));
        const string runId = "run-live-5";
        await harness.StartRunAsync(runId, new[] { "cash", "static_ladder", "quant_duration" },
            start: window[0], end: window[^1], universe: catalogue.UniverseVersion, dataMode: catalogue.DataMode);

        var result = await harness.ExecuteAsync(runId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        var cycles = await db.FiCycles.AsNoTracking().Where(c => c.RunId == runId).OrderBy(c => c.Sequence).ToListAsync();
        Assert.Equal(5, cycles.Count);
        Assert.All(cycles, c => Assert.True(c.Status == FiCycleStatus.Completed, $"{c.CycleId}: {c.Status} {c.SkipReason} {c.ErrorsJson}"));
        Assert.Equal(15, await db.FiDecisions.CountAsync(d => d.RunId == runId));
        Assert.Empty(await db.FiPortfolios.Where(p => p.RunId == runId && p.BlockedReason != null).ToListAsync());
        await harness.AssertJournalsBalanceAsync(runId);
    }

    private static List<DateOnly> FirstFiveReadySessions(IReadOnlyList<Application.FixedIncome.Contracts.MarketSessionDto> sessions)
    {
        var run = new List<DateOnly>();
        foreach (var session in sessions.OrderBy(s => s.SessionDate, StringComparer.Ordinal))
        {
            var ready = !session.Gap && string.Equals(session.CurveStatus, "READY", StringComparison.OrdinalIgnoreCase) &&
                        session.AvailableAt is not null && session.DecisionAsOf is not null &&
                        FiWire.ParseInstant(session.AvailableAt, "availableAt") <= FiWire.ParseInstant(session.DecisionAsOf, "decisionAsOf");
            if (!ready)
            {
                run.Clear();
                continue;
            }

            run.Add(FiWire.ParseDate(session.SessionDate, "sessionDate"));
            if (run.Count == 5)
            {
                break;
            }
        }

        return run;
    }
}

public sealed class LiveEngineFactAttribute : FactAttribute
{
    public LiveEngineFactAttribute()
    {
        if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FI_RESEARCH_ENGINE_URL")) ||
            string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FI_RESEARCH_ENGINE_KEY")))
        {
            Skip = "Set FI_RESEARCH_ENGINE_URL and FI_RESEARCH_ENGINE_KEY to run against a live research engine.";
        }
    }
}
