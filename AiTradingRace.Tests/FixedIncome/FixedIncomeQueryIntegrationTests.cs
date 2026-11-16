using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Moq;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Read models after a full application-mode run: run window / checkpoint / classified errors,
/// cycle errors, decision frozen inputs and links, portfolio cash and payment calendar, and
/// comparison metrics requested from the research engine (never computed in .NET) and cached
/// per committed state. Also checks the authoritative previous-session context of decisions.
/// </summary>
public sealed class FixedIncomeQueryIntegrationTests
{
    private const string RunId = "run-query";

    private static string Pf(string strategyId) => FiRunHarness.PortfolioId(RunId, strategyId);

    private static string Cycle(int index) => FiIds.Cycle(FiRunHarness.Week[index]);

    private static decimal D(string value) => decimal.Parse(value, System.Globalization.CultureInfo.InvariantCulture);

    private static async Task<FiRunHarness> CompletedRunAsync()
    {
        var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.Decide = r => r.StrategyId == "llm_market" && r.CycleId == Cycle(2)
            ? FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.35"), (FakeResearchEngine.Sec2, "0.34"),
                (FakeResearchEngine.Sec3, "0.25"), ("CASH-USD", "0.06"))
            : FakeDecision.Hold;
        await harness.StartRunAsync(RunId);
        var result = await harness.ExecuteAsync(RunId);
        Assert.True(result.Succeeded, result.FailureReason);
        return harness;
    }

    [Fact]
    public async Task Decisions_CarryTheRunsPreviousSession_AsAuthoritativeContext()
    {
        using var harness = await CompletedRunAsync();
        var requests = harness.Fake.DecisionRequests.ToList();

        Assert.All(requests, r => Assert.NotNull(r.SessionContext));
        Assert.All(requests.Where(r => r.CycleId == Cycle(0)), r => Assert.Null(r.SessionContext!.PreviousSessionDate));
        for (var i = 1; i < FiRunHarness.Week.Length; i++)
        {
            var expected = FiWire.FormatDate(FiRunHarness.Week[i - 1]);
            Assert.All(requests.Where(r => r.CycleId == Cycle(i)), r => Assert.Equal(expected, r.SessionContext!.PreviousSessionDate));
        }
    }

    [Fact]
    public async Task Runs_ExposeWindowCheckpointManifestAndErrorClassification()
    {
        using var harness = await CompletedRunAsync();
        await using var db = harness.Db();
        var queries = new FixedIncomeQueryService(db, Fi.Policies(), harness.Fake, new FiAnalyticsCache());

        var list = await queries.ListRunsAsync(new());
        var summary = Assert.Single(list.Items);
        Assert.Equal(FiRunHarness.Week[0], summary.StartDate);
        Assert.Equal(FiRunHarness.Week[^1], summary.EndDate);
        Assert.StartsWith("sha256:", summary.ManifestHash);
        Assert.NotNull(summary.Checkpoint);
        Assert.Equal(Cycle(4), summary.Checkpoint!.CycleId);
        Assert.Equal(5, summary.Checkpoint.Sequence);
        Assert.Equal(5, summary.Checkpoint.CheckpointedCycles);
        Assert.NotNull(summary.Errors);
        Assert.Equal(5, summary.Errors!.CycleStatusCounts[FiCycleStatus.Completed]);

        var detail = await queries.GetRunAsync(RunId);
        Assert.NotNull(detail);
        Assert.NotNull(detail!.RunErrors);
        Assert.Equal(summary.Checkpoint, detail.Run.Checkpoint);

        var cycles = await queries.GetRunCyclesAsync(RunId, 1, 50);
        Assert.NotNull(cycles);
        Assert.All(cycles!.Items, c =>
        {
            Assert.True(c.Checkpointed);
            Assert.NotNull(c.Errors);
            Assert.NotNull(c.Checkpoint);
        });
    }

    [Fact]
    public async Task CycleErrors_AreClassifiedOnCyclesAndRuns()
    {
        using var harness = new FiRunHarness();
        harness.AddSessions(
            FakeResearchEngine.Session(FiRunHarness.Week[0]),
            FakeResearchEngine.Session(FiRunHarness.Week[1], late: true));
        await harness.StartRunAsync(RunId, end: FiRunHarness.Week[1]);
        Assert.True((await harness.ExecuteAsync(RunId)).Succeeded);
        await using var db = harness.Db();
        var queries = new FixedIncomeQueryService(db, Fi.Policies());

        var cycles = (await queries.GetRunCyclesAsync(RunId, 1, 50))!.Items;
        var skipped = Assert.Single(cycles, c => c.Status == FiCycleStatus.Skipped);
        Assert.NotNull(skipped.SkipReason);
        var warning = Assert.Single(skipped.Errors!, e => e.Scope == "cycle");
        Assert.Equal(("warning", "skipped_stale_data"), (warning.Severity, warning.Code));
        Assert.Equal(skipped.CycleId, warning.CycleId);
        // Every portfolio is still valued without a market snapshot: classified financial_state warnings.
        var incomplete = skipped.Errors!.Where(e => e.Scope == "financial_state").ToList();
        Assert.Equal(4, incomplete.Count);
        Assert.All(incomplete, e => Assert.Equal("valuation_incomplete", e.Code));
        Assert.Equal(5, skipped.WarningCount);
        Assert.Equal(0, skipped.ErrorCount);

        var run = (await queries.GetRunAsync(RunId))!.Run;
        Assert.Equal(5, run.Errors!.CycleWarnings);
        Assert.Equal(1, run.Errors.ByScope["cycle"]);
        Assert.Equal(4, run.Errors.ByScope["financial_state"]);
        Assert.Equal(1, run.Errors.CycleStatusCounts[FiCycleStatus.Skipped]);
    }

    [Fact]
    public async Task DecisionDetail_ExposesCutoffFrozenInputsAndResultingOrders()
    {
        using var harness = await CompletedRunAsync();
        await using var db = harness.Db();
        var queries = new FixedIncomeQueryService(db, Fi.Policies());
        var decisionId = $"dec:{RunId}:{Cycle(2)}:llm_market:0";

        var detail = await queries.GetDecisionAsync(decisionId);

        Assert.NotNull(detail);
        var cycle = await db.FiCycles.AsNoTracking().SingleAsync(c => c.RunId == RunId && c.CycleId == Cycle(2));
        Assert.Equal(cycle.DecisionAsOf, detail!.DecisionAsOf);
        Assert.Equal(FiRunHarness.Week[2], detail.MarketSessionDate);
        Assert.Equal(3, detail.CycleSequence);
        var inputs = detail.FrozenInputs!;
        Assert.Equal(cycle.MarketSnapshotId, inputs.MarketSnapshotId);
        Assert.Equal(cycle.MarketSnapshotHash, inputs.MarketSnapshotHash);
        Assert.Equal(cycle.CurveSnapshotId, inputs.CurveSnapshotId);
        Assert.Equal("llm_market-config-v1", inputs.StrategyConfigId);
        Assert.NotNull(inputs.PortfolioSnapshotHash);
        Assert.NotNull(inputs.PortfolioSnapshotVersion);
        Assert.Equal(FiIds.PortfolioSnapshot(Pf("llm_market"), inputs.PortfolioSnapshotVersion!.Value), inputs.PortfolioSnapshotId);
        var sent = harness.Fake.DecisionRequests.Single(r => r.DecisionId == decisionId);
        Assert.Equal(sent.PortfolioSnapshot.Id, inputs.PortfolioSnapshotId);
        Assert.Equal(sent.PortfolioSnapshot.ContentHash, inputs.PortfolioSnapshotHash);
        Assert.Equal(sent.InstrumentUniverseVersion, inputs.InstrumentUniverseVersion);

        var order = Assert.Single(detail.Orders);
        Assert.NotNull(order.Fill);
        Assert.Equal(new[] { order.Fill!.FillId }, detail.FillIds);
        Assert.Equal($"/api/v1/portfolios/{Uri.EscapeDataString(Pf("llm_market"))}/orders?decisionId={Uri.EscapeDataString(decisionId)}",
            detail.Links!.Orders);
    }

    [Fact]
    public async Task Portfolio_ExposesCashBreakdownAndEngineProjectedPaymentCalendar()
    {
        using var harness = await CompletedRunAsync();
        await using var db = harness.Db();
        var cache = new FiAnalyticsCache();
        var queries = new FixedIncomeQueryService(db, Fi.Policies(), harness.Fake, cache);

        var portfolio = await queries.GetPortfolioAsync(Pf("static_ladder"));

        Assert.NotNull(portfolio);
        var state = FiWire.Deserialize<PortfolioStateDto>(portfolio!.State!);
        var cash = portfolio.Cash!;
        var payables = state.PendingSettlements.Where(s => s.Side == "BUY").Sum(s => D(s.CashUsd));
        Assert.Equal(D(state.CashUsd), D(cash.SettledCashUsd));
        Assert.Equal(D(state.CashUsd) - D(state.ReservedCashUsd) - payables, D(cash.AvailableCashUsd));
        Assert.Equal(D(state.ReservedCashUsd) + payables, D(cash.CommittedCashUsd));

        Assert.Equal("available", portfolio.PaymentCalendar!.Status);
        var request = Assert.Single(harness.Fake.PaymentCalendarRequests);
        Assert.Equal(portfolio.StateHash, request.PortfolioStateHash);
        Assert.Equal(state.Positions.Count, portfolio.PaymentCalendar.Calendar!["items"]!.AsArray().Count);

        await queries.GetPortfolioAsync(Pf("static_ladder"));
        Assert.Single(harness.Fake.PaymentCalendarRequests); // cached per (portfolio, version)

        var cashOnly = await queries.GetPortfolioAsync(Pf("cash"));
        Assert.Equal("no_holdings", cashOnly!.PaymentCalendar!.Status);

        var offline = await new FixedIncomeQueryService(db, Fi.Policies()).GetPortfolioAsync(Pf("static_ladder"));
        Assert.Equal("unavailable", offline!.PaymentCalendar!.Status);
        Assert.Equal("research_engine_not_configured", offline.PaymentCalendar.UnavailableReason);
    }

    [Fact]
    public async Task Comparison_RequestsEngineMetricsFromStoredSeries_AndCachesPerCommittedState()
    {
        using var harness = await CompletedRunAsync();
        await using var db = harness.Db();
        var cache = new FiAnalyticsCache();
        var queries = new FixedIncomeQueryService(db, Fi.Policies(), harness.Fake, cache);

        var comparison = await queries.GetRunComparisonAsync(RunId);

        Assert.NotNull(comparison);
        Assert.Equal("available", comparison!.Metrics!.Status);
        Assert.Equal("metrics-v1", comparison.Metrics.MetricsVersion);
        Assert.Equal(FiRunHarness.Week[0], comparison.Group.StartDate);
        Assert.Equal(FiRunHarness.Week[^1], comparison.Group.EndDate);
        Assert.Equal("replay", comparison.Group.RunType);
        Assert.All(comparison.Entries, e =>
        {
            Assert.NotNull(e.Metrics);
            Assert.Null(e.MetricsUnavailableReason);
            Assert.Equal(e.ValuationCount, e.Metrics!["valuationCount"]!.GetValue<int>());
        });

        var request = Assert.Single(harness.Fake.PerformanceRequests);
        Assert.Equal(RunId, request.RunId);
        Assert.Equal(4, request.Portfolios.Count);
        Assert.Equal(3, request.Pairs.Count);
        Assert.All(request.Pairs, p => Assert.Equal(Pf("cash"), p.VersusPortfolioId));

        // The series is exactly what was stored: valuation JSON values and the committed state's balances.
        var ladder = request.Portfolios.Single(p => p.PortfolioId == Pf("static_ladder"));
        var stored = await db.FiValuationSnapshots.AsNoTracking().Where(v => v.PortfolioId == Pf("static_ladder"))
            .OrderBy(v => v.Id).ToListAsync();
        Assert.Equal(stored.Select(v => v.ValuationId), ladder.Valuations.Select(v => v.ValuationId));
        var last = stored[^1];
        var lastPoint = ladder.Valuations[^1];
        Assert.Equal(JsonNode.Parse(last.ValuationJson)!["equityUsd"]!.GetValue<string>(), lastPoint.EquityUsd);
        var state = FiWire.Deserialize<PortfolioStateDto>(JsonNode.Parse((await db.FiPortfolioStateVersions.AsNoTracking()
            .SingleAsync(s => s.PortfolioId == Pf("static_ladder") && s.Version == last.CommittedVersion)).StateJson)!);
        Assert.Equal(state.SpreadCostUsd, lastPoint.Ledger.SpreadCostUsd);
        Assert.Equal(state.ExternalCapitalUsd, lastPoint.Ledger.ExternalCapitalUsd);
        Assert.Equal(state.Positions.SelectMany(p => p.Lots).Count(), lastPoint.Ledger.LotAccruedPurchasedUsd.Count);
        Assert.Equal(await db.FiFills.CountAsync(f => f.PortfolioId == Pf("static_ladder")), ladder.Fills.Count);
        Assert.Equal(5, ladder.DecisionOutcomes.Values.Sum());

        await queries.GetRunComparisonAsync(RunId);
        await queries.GetExperimentComparisonAsync(FiRunHarness.ExperimentId);
        Assert.Single(harness.Fake.PerformanceRequests); // cached: no new commit since the first request
    }

    [Fact]
    public async Task Comparison_ReportsUnavailableMetrics_WhenTheEngineFails()
    {
        using var harness = await CompletedRunAsync();
        await using var db = harness.Db();
        var engine = new Mock<IResearchEngineClient>();
        engine.Setup(e => e.GetPerformanceAsync(It.IsAny<PerformanceRequestDto>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ResearchEngineUnavailableException("engine down"));
        var queries = new FixedIncomeQueryService(db, Fi.Policies(), engine.Object, new FiAnalyticsCache());

        var comparison = await queries.GetRunComparisonAsync(RunId);

        Assert.Equal("unavailable", comparison!.Metrics!.Status);
        Assert.StartsWith("research_engine_unavailable", comparison.Metrics.UnavailableReason);
        Assert.All(comparison.Entries, e =>
        {
            Assert.Null(e.Metrics);
            Assert.StartsWith("research_engine_unavailable", e.MetricsUnavailableReason);
        });
    }
}
