using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Failure isolation (spec 15.3, 14.6). A deterministic engine error on one portfolio's command
/// (500 after the configured retries, or a 422 rejection with a stable code) affects only that
/// portfolio: it is impaired for discretionary commits with an operator-visible reason, its due
/// events and valuations continue, every other strategy proceeds, and the run completes. Only
/// transient failures (502/503/504, timeouts, 429) pause the run, and a paused run resumes.
/// Before the fix every 5xx was transient: one portfolio's deterministic engine error aborted the
/// cycle for every strategy and re-failed identically on every resume.
/// </summary>
public sealed class FailureIsolationTests
{
    private const string RunId = "run-app";

    private static string Pf(string strategyId) => FiRunHarness.PortfolioId(RunId, strategyId);

    private static string Cycle(int index) => FiIds.Cycle(FiRunHarness.Week[index]);

    private static string Command(int cycle, string strategyId, string step) => $"cmd:{RunId}:{Cycle(cycle)}:{Pf(strategyId)}:{step}";

    private static ResearchEngineServerException EngineError() =>
        new("Research engine failed to process the request (500).", 500,
            "{\"status\":500,\"code\":\"internal_error\",\"title\":\"Internal Server Error\"}");

    private static ResearchEngineValidationException LedgerViolation() =>
        new("Research engine rejected the request (422).", 422,
            "{\"status\":422,\"code\":\"ledger_invariant_violation\",\"title\":\"Ledger invariant violated\"}");

    private static FakeDecision MarketRebalancesAt(DecisionRequestDto r, int cycle) =>
        r.StrategyId == "llm_market" && r.CycleId == Cycle(cycle)
            ? FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.35"), (FakeResearchEngine.Sec2, "0.34"),
                (FakeResearchEngine.Sec3, "0.25"), ("CASH-USD", "0.06"))
            : FakeDecision.Hold;

    [Fact]
    public async Task PersistentEngineError_OnOnePortfoliosCommand_IsIsolatedAfterRetries_AndTheRunCompletes()
    {
        using var harness = new FiRunHarness(configure: o => o.TransientRetryAttempts = 2);
        harness.AddWeek();
        harness.Fake.Decide = r => MarketRebalancesAt(r, 3);
        var failing = Command(2, "llm_rag", "process");
        harness.Fake.FailTransition = r => r.CommandId == failing ? EngineError() : null;
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        Assert.Equal(3, harness.Fake.TransitionCommandIds.Count(id => id == failing)); // 1 + 2 configured retries, then isolated

        await using var db = harness.Db();
        Assert.Equal(5, await db.FiCycles.CountAsync(c => c.RunId == RunId && c.Status == FiCycleStatus.Completed));

        // Only llm_rag is impaired, with an operator-visible reason and the failing command.
        var portfolios = await db.FiPortfolios.AsNoTracking().Where(p => p.RunId == RunId).ToListAsync();
        var rag = Assert.Single(portfolios, p => p.BlockedReason is not null);
        Assert.Equal(Pf("llm_rag"), rag.PortfolioId);
        Assert.True(FiPortfolioRestriction.IsImpairment(rag.BlockedReason));
        Assert.Contains("internal_error", rag.BlockedReason);
        Assert.Equal(failing, rag.BlockedByCommandId);

        // No further discretionary decision for llm_rag; outcomes persisted with the reason.
        var ragDecisions = await db.FiDecisions.AsNoTracking()
            .Where(d => d.StrategyId == "llm_rag" && (d.CycleId == Cycle(2) || d.CycleId == Cycle(3) || d.CycleId == Cycle(4)))
            .ToListAsync();
        Assert.Equal(3, ragDecisions.Count);
        Assert.All(ragDecisions, d => Assert.Equal(FiDecisionOutcome.FailedDependency, d.Outcome));
        Assert.Contains(ragDecisions, d => d.ReasonsJson.Contains("portfolio_impaired"));
        Assert.DoesNotContain(harness.Fake.DecisionRequests, r => r.StrategyId == "llm_rag" && r.CycleId != Cycle(0) && r.CycleId != Cycle(1));

        // The impaired portfolio still receives due events and every valuation.
        Assert.True(await db.FiCommandRecords.AnyAsync(c => c.CommandId == Command(3, "llm_rag", "process")));
        Assert.Equal(3, await db.FiSettlements.CountAsync(s => s.PortfolioId == Pf("llm_rag") && s.Status == FiSettlementStatus.Completed));
        Assert.Equal(5, await db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == Pf("llm_rag")));

        // Every other strategy continued: llm_market's later rebalance was submitted and filled.
        Assert.True(await db.FiOrderIntents.AnyAsync(o => o.PortfolioId == Pf("llm_market") && !o.Bootstrap && o.Status == FiOrderStatus.Filled));
        Assert.Equal(20, await db.FiValuationSnapshots.CountAsync());

        var errors = JsonNode.Parse((await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(2))).ErrorsJson!)!.AsArray();
        Assert.Contains(errors, e => (string?)e!["code"] == "portfolio_impaired" && (string?)e["scope"] == FiErrorScope.FinancialState &&
                                     (string?)e["portfolioId"] == Pf("llm_rag") && (string?)e["commandId"] == failing);
        Assert.Contains(errors, e => (string?)e!["code"] == "process_events_failed" && (string?)e["strategyId"] == "llm_rag");

        // Re-executing the completed run never re-issues the failing command.
        var requests = harness.Fake.TransitionCommandIds.Count;
        Assert.True((await harness.ExecuteAsync(RunId)).Succeeded);
        Assert.Equal(requests, harness.Fake.TransitionCommandIds.Count);
    }

    [Fact]
    public async Task DeterministicRejection_OfOneSubmission_IsIsolatedImmediately_WithoutRetry()
    {
        using var harness = new FiRunHarness(configure: o => o.TransientRetryAttempts = 2);
        harness.AddWeek();
        harness.Fake.Decide = r => MarketRebalancesAt(r, 2);
        var failing = Command(2, "llm_market", "submit");
        harness.Fake.FailTransition = r => r.CommandId == failing ? LedgerViolation() : null;
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        Assert.Equal(1, harness.Fake.TransitionCommandIds.Count(id => id == failing));
        await using var db = harness.Db();
        var market = await db.FiPortfolios.AsNoTracking().SingleAsync(p => p.PortfolioId == Pf("llm_market"));
        Assert.True(FiPortfolioRestriction.IsImpairment(market.BlockedReason));
        Assert.Contains("ledger_invariant_violation", market.BlockedReason);
        Assert.False(await db.FiOrderIntents.AnyAsync(o => o.PortfolioId == Pf("llm_market") && !o.Bootstrap));
        var errors = JsonNode.Parse((await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(2))).ErrorsJson!)!.AsArray();
        Assert.Contains(errors, e => (string?)e!["code"] == "submit_decision_failed" && (string?)e["scope"] == FiErrorScope.Strategy);
        Assert.Equal(5, await db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == Pf("llm_market")));
        // The other competitors are untouched.
        Assert.Null((await db.FiPortfolios.AsNoTracking().SingleAsync(p => p.PortfolioId == Pf("llm_rag"))).BlockedReason);
        Assert.Equal(4, harness.Fake.DecisionRequests.Count(r => r.StrategyId == "llm_rag"));
    }

    [Fact]
    public async Task EngineError_OnOneCompetitorsBootstrap_LeavesItOut_AndTheOthersStartIdentically()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        var failing = Command(0, "llm_rag", "submit");
        harness.Fake.FailTransition = r => r.CommandId == failing ? LedgerViolation() : null;
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        // Before the fix: "initialization_failed: llm_rag: bootstrap rejected" stopped the run for everyone.
        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        Assert.Equal(5, await db.FiCycles.CountAsync(c => c.RunId == RunId && c.Status == FiCycleStatus.Completed));
        Assert.False(await db.FiOrderIntents.AnyAsync(o => o.PortfolioId == Pf("llm_rag")));
        Assert.True(FiPortfolioRestriction.IsImpairment(
            (await db.FiPortfolios.AsNoTracking().SingleAsync(p => p.PortfolioId == Pf("llm_rag"))).BlockedReason));
        foreach (var strategy in new[] { "static_ladder", "llm_market" })
        {
            Assert.Equal(3, await db.FiFills.CountAsync(f => f.PortfolioId == Pf(strategy)));
        }

        Assert.Equal(5, await db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == Pf("llm_rag")));
        Assert.Contains("bootstrap_isolated", (await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(0))).ErrorsJson);
    }

    [Fact]
    public async Task ProcessEventsFailure_BeforeTheBootstrap_IsolatesThatCompetitorOnly()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        var failing = Command(0, "llm_market", "process");
        harness.Fake.FailTransition = r => r.CommandId == failing ? EngineError() : null;
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        var bootstrap = await db.FiDecisions.AsNoTracking()
            .SingleAsync(d => d.StrategyId == "llm_market" && d.CycleId == Cycle(0));
        Assert.Equal(FiDecisionOutcome.FailedDependency, bootstrap.Outcome);
        Assert.Contains("bootstrap_skipped", bootstrap.ReasonsJson);
        Assert.Equal(3, await db.FiFills.CountAsync(f => f.PortfolioId == Pf("llm_rag")));
        Assert.Equal(0, await db.FiFills.CountAsync(f => f.PortfolioId == Pf("llm_market")));
    }

    [Fact]
    public async Task TransientOutage_PausesTheRunWithVisibleErrors_AndAResumeCompletesIt()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        var outage = true;
        harness.Fake.FailTransition = r => outage && r.CommandId == Command(1, "llm_market", "value")
            ? new ResearchEngineUnavailableException("Research engine dependency unavailable (503).", 503,
                "{\"status\":503,\"code\":\"dependency_unavailable\"}")
            : null;
        await harness.StartRunAsync(RunId);

        var paused = await harness.ExecuteAsync(RunId);

        Assert.False(paused.Succeeded);
        Assert.Contains("resumable", paused.FailureReason);
        await using (var db = harness.Db())
        {
            // Nobody is impaired by a transient outage; the pause is visible on the cycle and the run.
            Assert.False(await db.FiPortfolios.AnyAsync(p => p.BlockedReason != null));
            var cycle = await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(1));
            Assert.Equal(FiCycleStatus.Failed, cycle.Status);
            Assert.StartsWith("paused (resumable)", cycle.SkipReason);
            Assert.Contains("engine_unavailable", cycle.ErrorsJson);

            var queries = new FixedIncomeQueryService(db, Fi.Policies());
            var detail = (await queries.GetRunAsync(RunId))!;
            Assert.Contains(detail.RunErrors!, e => e.Code == "engine_unavailable" && e.Scope == FiErrorScope.Source);
            var cycles = (await queries.GetRunCyclesAsync(RunId, 1, 50))!.Items;
            Assert.Contains(cycles.Single(c => c.CycleId == Cycle(1)).Errors!, e => e.Code == "engine_unavailable");
            Assert.Empty(detail.ImpairedPortfolios!);
        }

        outage = false;
        var resumed = await harness.ExecuteAsync(RunId);

        Assert.True(resumed.Succeeded, resumed.FailureReason);
        await using var after = harness.Db();
        Assert.Equal(5, await after.FiCycles.CountAsync(c => c.Status == FiCycleStatus.Completed));
        Assert.Equal(20, await after.FiValuationSnapshots.CountAsync());
    }

    [Fact]
    public async Task RunDetailAndPortfolio_ExposeImpairedPortfolios()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        var failing = Command(1, "static_ladder", "value");
        harness.Fake.FailTransition = r => r.CommandId == failing ? EngineError() : null;
        await harness.StartRunAsync(RunId);
        Assert.True((await harness.ExecuteAsync(RunId)).Succeeded);

        await using var db = harness.Db();
        var queries = new FixedIncomeQueryService(db, Fi.Policies());
        var detail = (await queries.GetRunAsync(RunId))!;
        var impaired = Assert.Single(detail.ImpairedPortfolios!);
        Assert.Equal(Pf("static_ladder"), impaired.PortfolioId);
        Assert.Equal("static_ladder", impaired.StrategyId);
        Assert.Equal(FiPortfolioRestriction.Impaired, impaired.Kind);
        Assert.Equal(failing, impaired.CommandId);
        Assert.Contains("value_portfolio", impaired.Reason);

        var portfolio = (await queries.GetPortfolioAsync(Pf("static_ladder")))!;
        Assert.Equal(FiPortfolioRestriction.Impaired, portfolio.Restriction);
        Assert.Null((await queries.GetPortfolioAsync(Pf("llm_rag")))!.Restriction);

        var cycle = (await queries.GetRunCyclesAsync(RunId, 1, 50))!.Items.Single(c => c.CycleId == Cycle(1));
        Assert.Contains(cycle.Errors!, e => e.Code == "valuation_deferred" && e.PortfolioId == Pf("static_ladder"));
        Assert.Contains(cycle.Errors!, e => e.Code == "portfolio_impaired" && e.CommandId == failing);
        var checkpoint = cycle.Checkpoint!["portfolios"]!.AsArray()
            .Single(p => (string?)p!["portfolioId"] == Pf("static_ladder"))!;
        Assert.Equal(FiPortfolioRestriction.Impaired, (string?)checkpoint["restriction"]);
    }

    [Fact]
    public async Task ImpairedPortfolio_RefusesDiscretionaryCommits_ButAcceptsOthers_UntilUnblocked()
    {
        using var database = new FiSqliteDatabase();
        await using (var db = database.CreateContext())
        {
            await Fi.CommitService(db).CreatePortfolioAsync(new CreateFiPortfolioRequest
            {
                PortfolioId = Fi.PortfolioId,
                RunId = Fi.RunId,
                StrategyId = Fi.StrategyId,
                RiskPolicyId = Fi.PolicyId,
                DataMode = FiDataMode.SyntheticCurve,
                AsOf = Fi.GenesisAsOf,
            });
            Assert.True(await Fi.CommitService(db).MarkImpairedAsync(Fi.PortfolioId, "value_portfolio cmd-x failed: 500", "cmd-x"));
        }

        var capital = Fi.Seal(Fi.CapitalFlow(Fi.Genesis(), "cmd-capital"));
        var funded = Fi.NextState(capital);
        var submit = Fi.Seal(Fi.SubmitDecision(funded, "cmd-submit"));

        await using (var db = database.CreateContext())
        {
            var service = Fi.CommitService(db);
            Assert.Equal(TransitionCommitStatus.Committed,
                (await service.CommitAsync(Fi.Raw(capital), new TransitionCommitContext { ExpectedCommandId = "cmd-capital" })).Status);
        }

        await using (var db = database.CreateContext())
        {
            var refused = await Fi.CommitService(db).CommitAsync(Fi.Raw(submit), new TransitionCommitContext { ExpectedCommandId = "cmd-submit" });
            Assert.Equal(TransitionCommitStatus.PortfolioBlocked, refused.Status);
            Assert.Contains("impaired", refused.Message);
        }

        await using (var db = database.CreateContext())
        {
            var service = Fi.CommitService(db);
            Assert.True(await service.UnblockAsync(Fi.PortfolioId, "operator", "engine fixed"));
            Assert.Equal(TransitionCommitStatus.Committed,
                (await service.CommitAsync(Fi.Raw(submit), new TransitionCommitContext { ExpectedCommandId = "cmd-submit" })).Status);
        }
    }

    [Fact]
    public async Task Impairment_NeverDowngradesAReconciliationBlock()
    {
        using var database = new FiSqliteDatabase();
        await using var db = database.CreateContext();
        var service = Fi.CommitService(db);
        await service.CreatePortfolioAsync(new CreateFiPortfolioRequest
        {
            PortfolioId = Fi.PortfolioId,
            RunId = Fi.RunId,
            StrategyId = Fi.StrategyId,
            RiskPolicyId = Fi.PolicyId,
            DataMode = FiDataMode.SyntheticCurve,
            AsOf = Fi.GenesisAsOf,
        });
        var broken = Fi.CapitalFlow(Fi.Genesis(), "cmd-capital");
        broken["reconciliation"] = Fi.Reconciliation(false);
        Assert.Equal(TransitionCommitStatus.PortfolioBlocked,
            (await service.CommitAsync(Fi.Raw(Fi.Seal(broken)), new TransitionCommitContext { ExpectedCommandId = "cmd-capital" })).Status);

        Assert.True(await service.MarkImpairedAsync(Fi.PortfolioId, "later engine error", "cmd-later"));

        var portfolio = await db.FiPortfolios.AsNoTracking().SingleAsync();
        Assert.StartsWith("reconciliation_failed", portfolio.BlockedReason);
        Assert.Equal(FiPortfolioRestriction.Blocked, FiPortfolioRestriction.KindOf(portfolio.BlockedReason));
        Assert.True(FiPortfolioRestriction.Forbids(portfolio.BlockedReason, FiCommandType.ValuePortfolio));
    }
}
