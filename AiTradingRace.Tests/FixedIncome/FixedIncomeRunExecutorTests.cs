using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Application-mode executor (spec 15.1-15.4) against a deterministic fake engine that
/// returns correctly signed proposals/results, through the real verifier, commit service
/// and decision audit on SQLite.
/// </summary>
public sealed class FixedIncomeRunExecutorTests
{
    private const string RunId = "run-app";

    private static string Pf(string strategyId) => FiRunHarness.PortfolioId(RunId, strategyId);

    private static string Cycle(int index) => FiIds.Cycle(FiRunHarness.Week[index]);

    [Fact]
    public async Task FullRun_CompletesEveryCycle_BootstrapsInvestedStrategies_AndJournalsBalance()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.Decide = r => r.StrategyId == "llm_market" && r.CycleId == Cycle(2)
            ? FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.35"), (FakeResearchEngine.Sec2, "0.34"),
                (FakeResearchEngine.Sec3, "0.25"), ("CASH-USD", "0.06"))
            : FakeDecision.Hold;
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        var cycles = await db.FiCycles.AsNoTracking().Where(c => c.RunId == RunId).OrderBy(c => c.Sequence).ToListAsync();
        Assert.Equal(5, cycles.Count);
        Assert.All(cycles, c =>
        {
            Assert.Equal(FiCycleStatus.Completed, c.Status);
            Assert.NotNull(c.CheckpointJson);
            Assert.NotNull(c.InputsJson);
        });

        var run = await db.FiExperimentRuns.AsNoTracking().SingleAsync(r => r.RunId == RunId);
        Assert.Equal(5, run.CompletedCycles);
        Assert.Equal(5, run.TotalCycles);
        Assert.Equal(FiMarketClock.DecisionAt(FiRunHarness.Week[^1]), run.SimulatedClock);
        Assert.Equal(Fi.EngineVersion, run.EngineVersion);

        // Common bootstrap: once, identical for every invested strategy, never for cash.
        Assert.Equal(1, harness.Fake.BootstrapCalls);
        var bootstrapDecisions = await db.FiDecisions.AsNoTracking().Where(d => d.Action == "BOOTSTRAP").ToListAsync();
        Assert.Equal(new[] { "llm_market", "llm_rag", "static_ladder" }, bootstrapDecisions.Select(d => d.StrategyId).OrderBy(s => s));
        Assert.All(bootstrapDecisions, d => Assert.Equal(Cycle(0), d.CycleId));
        var bootstrapOrders = await db.FiOrderIntents.AsNoTracking().Where(o => o.Bootstrap).ToListAsync();
        Assert.Equal(9, bootstrapOrders.Count);
        Assert.All(bootstrapOrders, o => Assert.Equal(FiOrderStatus.Filled, o.Status));
        Assert.False(await db.FiOrderIntents.AnyAsync(o => o.PortfolioId == Pf("cash")));

        // One decision per strategy and cycle, with deterministic ids.
        var decisions = await db.FiDecisions.AsNoTracking().Where(d => d.RunId == RunId).ToListAsync();
        Assert.Equal(20, decisions.Count);
        Assert.Contains(decisions, d => d.DecisionId == $"dec:{RunId}:{Cycle(3)}:llm_rag:0");
        Assert.DoesNotContain(harness.Fake.DecisionRequests, r => r.CycleId == Cycle(0) && r.StrategyId != "cash");
        Assert.All(harness.Fake.DecisionRequests, r => Assert.Equal(r.PortfolioSnapshot.ContentHash,
            CanonicalJson.ContentHash(JsonNode.Parse(r.PortfolioState!.Value.GetRawText()))));

        // The REBALANCE of llm_market was verified and submitted, then filled.
        var rebalance = await db.FiOrderIntents.AsNoTracking()
            .SingleAsync(o => o.PortfolioId == Pf("llm_market") && !o.Bootstrap);
        Assert.Equal($"dec:{RunId}:{Cycle(2)}:llm_market:0", rebalance.DecisionId);
        Assert.Equal(50000m, rebalance.Face);
        Assert.Equal(FiOrderStatus.Filled, rebalance.Status);

        // Capital, valuations and command ids.
        Assert.Equal(4, await db.FiCashFlowEvents.CountAsync(c => c.Kind == "CAPITAL"));
        Assert.Equal(20, await db.FiValuationSnapshots.CountAsync());
        Assert.True(await db.FiCommandRecords.AnyAsync(c => c.CommandId == $"cmd:{RunId}:init:{Pf("cash")}:capital"));
        Assert.True(await db.FiCommandRecords.AnyAsync(c => c.CommandId == $"cmd:{RunId}:{Cycle(4)}:{Pf("llm_rag")}:value"));
        await harness.AssertJournalsBalanceAsync(RunId);
    }

    [Fact]
    public async Task StaleSharedInputs_SkipTheCycle_PersistASkipDecisionForEveryStrategy_AndDelayTheBootstrap()
    {
        using var harness = new FiRunHarness();
        harness.AddSessions(
            FakeResearchEngine.Session(FiRunHarness.Week[0], curveStatus: "FAILED"),
            FakeResearchEngine.Session(FiRunHarness.Week[1]),
            FakeResearchEngine.Session(FiRunHarness.Week[2], late: true),
            FakeResearchEngine.Session(FiRunHarness.Week[3]),
            FakeResearchEngine.Session(FiRunHarness.Week[4], gap: true));
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        var cycles = await db.FiCycles.AsNoTracking().Where(c => c.RunId == RunId).OrderBy(c => c.Sequence).ToListAsync();
        Assert.Equal(new[] { "skipped", "completed", "skipped", "completed", "skipped" }, cycles.Select(c => c.Status));
        Assert.StartsWith("skipped_stale_data: curve_not_ready", cycles[0].SkipReason);
        Assert.StartsWith("skipped_stale_data: curve_not_available_by_decision_time", cycles[2].SkipReason);
        Assert.StartsWith("skipped_stale_data: session_gap", cycles[4].SkipReason);

        foreach (var index in new[] { 0, 2, 4 })
        {
            var skipped = await db.FiDecisions.AsNoTracking().Where(d => d.CycleId == Cycle(index)).ToListAsync();
            Assert.Equal(4, skipped.Count);
            Assert.All(skipped, d =>
            {
                Assert.Equal(FiDecisionOutcome.SkippedStaleData, d.Outcome);
                Assert.Equal(FiAuditIntegrity.Synthesized, d.Integrity);
            });
            Assert.DoesNotContain(harness.Fake.DecisionRequests, r => r.CycleId == Cycle(index));
        }

        // Bootstrap happens on the first eligible session, not on the skipped first session.
        var bootstrap = await db.FiDecisions.AsNoTracking().Where(d => d.Action == "BOOTSTRAP").Select(d => d.CycleId).Distinct().ToListAsync();
        Assert.Equal(new[] { Cycle(1) }, bootstrap);

        // Due events and (incomplete) valuations still run in skipped cycles.
        Assert.Equal(20, await db.FiValuationSnapshots.CountAsync());
        Assert.Equal(12, await db.FiValuationSnapshots.CountAsync(v => !v.Complete));
        Assert.True(harness.Metrics.Total(FixedIncomeMetrics.IncompleteValuations) >= 12);
        Assert.Contains("skipped_stale_data", cycles[0].ErrorsJson);
        await harness.AssertJournalsBalanceAsync(RunId);
    }

    [Fact]
    public async Task RejectedBootstrap_FailsInitializationForTheRun()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.RejectBootstrapFor.Add("llm_rag");
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.False(result.Succeeded);
        Assert.False(result.Cancelled);
        Assert.StartsWith("initialization_failed:", result.FailureReason);
        Assert.Contains("llm_rag", result.FailureReason);
        await using var db = harness.Db();
        var cycles = await db.FiCycles.AsNoTracking().Where(c => c.RunId == RunId).OrderBy(c => c.Sequence).ToListAsync();
        Assert.Equal(FiCycleStatus.Failed, cycles[0].Status);
        Assert.All(cycles.Skip(1), c => Assert.Equal(FiCycleStatus.Pending, c.Status));
        Assert.Contains("bootstrap_rejected", cycles[0].ErrorsJson);
        Assert.DoesNotContain(harness.Fake.DecisionRequests, r => r.CycleId != Cycle(0));
        Assert.Equal(0, await db.FiValuationSnapshots.CountAsync());
    }

    [Fact]
    public async Task FailingStrategy_DoesNotStopOthers_AndItsPortfolioStillGetsEventsAndValuations()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.Decide = r => r.StrategyId switch
        {
            "llm_rag" => FakeDecision.Throw(new ResearchEngineUnavailableException("provider timeout", 503)),
            "llm_market" when r.CycleId == Cycle(1) => FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.36"),
                (FakeResearchEngine.Sec2, "0.34"), (FakeResearchEngine.Sec3, "0.24"), ("CASH-USD", "0.06")),
            _ => FakeDecision.Hold,
        };
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        var ragDecisions = await db.FiDecisions.AsNoTracking().Where(d => d.StrategyId == "llm_rag").OrderBy(d => d.CycleId).ToListAsync();
        Assert.Equal(5, ragDecisions.Count);
        Assert.Equal("BOOTSTRAP", ragDecisions[0].Action);
        Assert.All(ragDecisions.Skip(1), d =>
        {
            Assert.Equal(FiDecisionOutcome.FailedDependency, d.Outcome);
            Assert.Contains("engine_unavailable", d.ReasonsJson);
        });

        // The failed strategy's portfolio still received fills, settlements and every valuation.
        Assert.Equal(3, await db.FiFills.CountAsync(f => f.PortfolioId == Pf("llm_rag")));
        Assert.Equal(3, await db.FiSettlements.CountAsync(s => s.PortfolioId == Pf("llm_rag") && s.Status == FiSettlementStatus.Completed));
        Assert.Equal(5, await db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == Pf("llm_rag")));

        // Others continued: llm_market's rebalance was submitted and filled.
        Assert.True(await db.FiOrderIntents.AnyAsync(o => o.PortfolioId == Pf("llm_market") && !o.Bootstrap && o.Status == FiOrderStatus.Filled));
        var cycle = await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(1));
        Assert.Equal(FiCycleStatus.Completed, cycle.Status);
        var errors = JsonNode.Parse(cycle.ErrorsJson!)!.AsArray();
        Assert.Contains(errors, e => (string?)e!["strategyId"] == "llm_rag" && (string?)e["scope"] == FiErrorScope.Source);
    }

    [Fact]
    public async Task CrashMidRun_RestartReissuesTheSameCommandIds_WithoutDuplicateEffects()
    {
        // Reference run without a crash.
        RunFootprint reference;
        using (var clean = new FiRunHarness())
        {
            clean.AddWeek();
            clean.Fake.Decide = Rebalances;
            await clean.StartRunAsync(RunId);
            Assert.True((await clean.ExecuteAsync(RunId)).Succeeded);
            reference = await clean.FootprintAsync(RunId);
        }

        using var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.Decide = Rebalances;
        var crashCommand = $"cmd:{RunId}:{Cycle(2)}:{Pf("llm_market")}:value";
        var crashed = false;
        harness.Fake.FailTransition = r =>
        {
            if (!crashed && r.CommandId == crashCommand)
            {
                crashed = true;
                return new InvalidOperationException("simulated worker crash");
            }

            return null;
        };
        await harness.StartRunAsync(RunId);

        await Assert.ThrowsAsync<InvalidOperationException>(() => harness.ExecuteAsync(RunId));
        int cycle2Committed;
        int capitalCommands;
        await using (var db = harness.Db())
        {
            cycle2Committed = await db.FiCommandRecords.CountAsync(c => c.CommandId.Contains(Cycle(2)));
            capitalCommands = await db.FiCommandRecords.CountAsync(c => c.CommandId.EndsWith(":capital"));
            Assert.Equal(4 + 1 + 2, cycle2Committed); // process x4, llm_market submit, two valuations before the crash
            Assert.Equal(FiCycleStatus.Running, (await db.FiCycles.SingleAsync(c => c.CycleId == Cycle(2))).Status);
            Assert.True(await db.FiCommandRecords.AnyAsync(c => c.CommandId == $"cmd:{RunId}:{Cycle(2)}:{Pf("llm_market")}:submit"));
        }

        var duplicatesBefore = harness.Metrics.Total(FixedIncomeMetrics.DuplicateCommands, "kind", "command");
        var requestsBefore = harness.Fake.TransitionCommandIds.Count;

        var restart = await harness.ExecuteAsync(RunId);

        Assert.True(restart.Succeeded, restart.FailureReason);
        var after = await harness.FootprintAsync(RunId);
        Assert.True(after.SameAs(reference), $"restart footprint {after} differs from reference {reference}");

        // Cycle 2 was re-executed with the same deterministic command ids; the commands already
        // committed before the crash were detected (no recomputation, no second effect).
        var reissued = harness.Metrics.Total(FixedIncomeMetrics.DuplicateCommands, "kind", "command") - duplicatesBefore;
        Assert.Equal(capitalCommands + cycle2Committed, reissued);
        var restartRequests = harness.Fake.TransitionCommandIds.Skip(requestsBefore).ToList();
        Assert.Contains(crashCommand, restartRequests);
        Assert.DoesNotContain($"cmd:{RunId}:{Cycle(2)}:{Pf("cash")}:process", restartRequests);
        await harness.AssertJournalsBalanceAsync(RunId);

        static FakeDecision Rebalances(Application.FixedIncome.Contracts.DecisionRequestDto r) =>
            r.StrategyId == "llm_market" && r.CycleId == Cycle(2)
                ? FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.35"), (FakeResearchEngine.Sec2, "0.34"),
                    (FakeResearchEngine.Sec3, "0.25"), ("CASH-USD", "0.06"))
                : FakeDecision.Hold;
    }

    [Fact]
    public async Task EveryOutcome_IsPersisted_AndOnlyVerifiedRebalancesCreateOrders()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        var strategies = new[] { "cash", "static_ladder", "quant_duration", "llm_market", "llm_rag", "llm_graph", "llm_team" };
        harness.Fake.Decide = r => r.StrategyId switch
        {
            "static_ladder" => FakeDecision.Hold,
            "quant_duration" => FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.36"), (FakeResearchEngine.Sec2, "0.34"),
                (FakeResearchEngine.Sec3, "0.24"), ("CASH-USD", "0.06")),
            "llm_market" => new FakeDecision(FakeDecisionKind.Budget),
            "llm_rag" => new FakeDecision(FakeDecisionKind.Abstain),
            "llm_graph" => new FakeDecision(FakeDecisionKind.BadSignature),
            "llm_team" => FakeDecision.Throw(new ResearchEngineValidationException("bad request", 422, "{\"detail\":\"invalid\"}")),
            _ => FakeDecision.Hold,
        };
        await harness.StartRunAsync(RunId, strategies, end: FiRunHarness.Week[1]);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        var second = await db.FiDecisions.AsNoTracking().Where(d => d.CycleId == Cycle(1)).ToDictionaryAsync(d => d.StrategyId);
        Assert.Equal(strategies.Length, second.Count);
        Assert.Equal(FiDecisionOutcome.CompletedHold, second["cash"].Outcome);
        Assert.Equal(FiDecisionOutcome.CompletedHold, second["static_ladder"].Outcome);
        Assert.Equal(FiDecisionOutcome.CompletedProposal, second["quant_duration"].Outcome);
        Assert.Equal(FiDecisionOutcome.FailedBudget, second["llm_market"].Outcome);
        Assert.Equal(FiDecisionOutcome.AbstainedInsufficientEvidence, second["llm_rag"].Outcome);
        Assert.Equal(FiAuditIntegrity.SignatureInvalid, second["llm_graph"].Integrity);
        Assert.Equal(FiDecisionOutcome.FailedDependency, second["llm_team"].Outcome);
        Assert.Contains("engine_rejected_request", second["llm_team"].ReasonsJson);
        Assert.All(second.Values.Where(d => d.StrategyId != "llm_team"), d => Assert.NotNull(d.ResultJson));

        // Orders after the bootstrap: only the verified REBALANCE (not the tampered one).
        var discretionary = await db.FiOrderIntents.AsNoTracking().Where(o => !o.Bootstrap).ToListAsync();
        Assert.NotEmpty(discretionary);
        Assert.All(discretionary, o => Assert.Equal(FiRunHarness.PortfolioId(RunId, "quant_duration"), o.PortfolioId));
        Assert.Equal(1, harness.Metrics.Total(FixedIncomeMetrics.BudgetExhausted));
        Assert.True(harness.Metrics.Total(FixedIncomeMetrics.OrdersPending) >= 18 + discretionary.Count);
        var cycle = await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(1));
        Assert.Contains("result_integrity", cycle.ErrorsJson);
    }

    [Fact]
    public async Task OperatorCancellation_StopsUncommittedWork_CommittedEventsRemainAuthoritative()
    {
        using var harness = new FiRunHarness(configure: o => o.MaxParallelDecisions = 1);
        harness.AddWeek();
        var cancelled = 0;
        harness.Fake.OnDecision = r =>
        {
            if (r.CycleId == Cycle(2) && Interlocked.Exchange(ref cancelled, 1) == 0)
            {
                harness.CancelAsync(RunId).GetAwaiter().GetResult();
            }
        };
        harness.Fake.Decide = r => r.StrategyId == "llm_market"
            ? FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.35"), (FakeResearchEngine.Sec2, "0.34"),
                (FakeResearchEngine.Sec3, "0.25"), ("CASH-USD", "0.06"))
            : FakeDecision.Hold;
        await harness.StartRunAsync(RunId);
        var journalsBefore = 0;

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Cancelled);
        Assert.False(result.Succeeded);
        await using var db = harness.Db();
        var run = await db.FiExperimentRuns.AsNoTracking().SingleAsync(r => r.RunId == RunId);
        Assert.Equal(FiJobState.Cancelled, run.JobState);
        var cycles = await db.FiCycles.AsNoTracking().Where(c => c.RunId == RunId).OrderBy(c => c.Sequence).ToListAsync();
        Assert.Equal(new[] { "completed", "completed", "cancelled", "pending", "pending" }, cycles.Select(c => c.Status));

        // Results that arrived are audited; nothing from the cancelled cycle was submitted or valued.
        var cycle2 = await db.FiDecisions.AsNoTracking().Where(d => d.CycleId == Cycle(2)).ToListAsync();
        Assert.Equal(4, cycle2.Count);
        Assert.False(await db.FiCommandRecords.AnyAsync(c => c.CommandId == $"cmd:{RunId}:{Cycle(2)}:{Pf("llm_market")}:submit"));
        Assert.False(await db.FiCommandRecords.AnyAsync(c => c.CommandId.EndsWith(":value") && c.CommandId.Contains(Cycle(2))));
        Assert.DoesNotContain(harness.Fake.TransitionCommandIds, id => id.Contains(Cycle(3)));

        // Committed effects of earlier cycles (and the cycle's due events) remain.
        journalsBefore = await db.FiJournals.CountAsync();
        Assert.True(journalsBefore > 0);
        Assert.Equal(1, await db.FiOrderIntents.CountAsync(o => o.PortfolioId == Pf("llm_market") && !o.Bootstrap));
        await harness.AssertJournalsBalanceAsync(RunId);

        // A cancelled run cannot be resumed by the executor.
        var again = await harness.ExecuteAsync(RunId);
        Assert.True(again.Cancelled);
        Assert.Equal(journalsBefore, await db.FiJournals.CountAsync());
    }

    [Fact]
    public async Task StaleCommitResult_IsRecomputedOnceAgainstTheCurrentState()
    {
        using var harness = new FiRunHarness();
        harness.AddSessions(FakeResearchEngine.Session(FiRunHarness.Week[0]), FakeResearchEngine.Session(FiRunHarness.Week[1]));
        var command = $"cmd:{RunId}:{Cycle(1)}:{Pf("llm_market")}:value";
        harness.Fake.StaleOnce(command);
        await harness.StartRunAsync(RunId, end: FiRunHarness.Week[1]);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        Assert.Equal(1, harness.Metrics.Total(FixedIncomeMetrics.ConcurrencyConflicts));
        Assert.Equal(2, harness.Fake.TransitionCommandIds.Count(id => id == command));
        await using var db = harness.Db();
        Assert.True(await db.FiCommandRecords.AnyAsync(c => c.CommandId == command));
        Assert.Equal(2, await db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == Pf("llm_market")));
        await harness.AssertJournalsBalanceAsync(RunId);
    }

    [Fact]
    public async Task RetriedCycleActivity_ReturnsTheCheckpoint_AndCreatesNoNewEffects()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        await harness.StartRunAsync(RunId);
        var plan = await harness.WithRunnerAsync(r => r.PrepareRunAsync(RunId));
        Assert.Equal(FiPlanStatus.Ready, plan.Status);
        Assert.Equal(5, plan.PendingCycleIds.Count);

        var first = await harness.WithRunnerAsync(r => r.ExecuteCycleAsync(RunId, plan.PendingCycleIds[0]));
        var footprint = await harness.FootprintAsync(RunId);
        var retried = await harness.WithRunnerAsync(r => r.ExecuteCycleAsync(RunId, plan.PendingCycleIds[0]));
        var replanned = await harness.WithRunnerAsync(r => r.PrepareRunAsync(RunId));

        Assert.Equal(FiCycleRunStatus.Completed, first.Status);
        Assert.Equal(FiCycleRunStatus.AlreadyDone, retried.Status);
        Assert.True(footprint.SameAs(await harness.FootprintAsync(RunId)));
        Assert.Equal(plan.PendingCycleIds.Skip(1), replanned.PendingCycleIds);

        // Out-of-order execution is refused (checkpoints are sequential).
        var outOfOrder = await harness.WithRunnerAsync(r => r.ExecuteCycleAsync(RunId, plan.PendingCycleIds[3]));
        Assert.Equal(FiCycleRunStatus.Failed, outOfOrder.Status);
    }

    [Fact]
    public async Task TransientEngineOutage_FailsTheRunAsResumable_ThenResumes()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        var outage = true;
        harness.Fake.FailTransition = r => outage && r.CommandId.Contains(Cycle(1)) && r.CommandId.EndsWith(":value")
            ? new ResearchEngineUnavailableException("engine down", 503)
            : null;
        await harness.StartRunAsync(RunId);

        var failed = await harness.ExecuteAsync(RunId);

        Assert.False(failed.Succeeded);
        Assert.StartsWith("source:", failed.FailureReason);
        Assert.Contains("resumable", failed.FailureReason);

        outage = false;
        var resumed = await harness.ExecuteAsync(RunId);
        Assert.True(resumed.Succeeded, resumed.FailureReason);
        await using var db = harness.Db();
        Assert.Equal(5, await db.FiCycles.CountAsync(c => c.Status == FiCycleStatus.Completed));
        Assert.Equal(20, await db.FiValuationSnapshots.CountAsync());
    }

    [Fact]
    public async Task ForwardPaperCycle_RunsOneSession_AndIgnoresNonSessionDates()
    {
        using var harness = new FiRunHarness();
        harness.AddSessions(FakeResearchEngine.Session(new DateOnly(2030, 3, 4)), FakeResearchEngine.Session(new DateOnly(2030, 3, 5)));
        await harness.StartRunAsync("run-paper", start: new DateOnly(2020, 1, 1), end: new DateOnly(2030, 3, 5), runType: "forward");

        var holiday = await harness.WithRunnerAsync(r => r.PreparePaperCycleAsync("run-paper", new DateOnly(2030, 3, 3)));
        Assert.Equal(FiPlanStatus.NothingToDo, holiday.Status);

        var plan = await harness.WithRunnerAsync(r => r.PreparePaperCycleAsync("run-paper", new DateOnly(2030, 3, 4)));
        Assert.Equal(FiPlanStatus.Ready, plan.Status);
        Assert.Equal(new[] { FiIds.Cycle(new DateOnly(2030, 3, 4)) }, plan.PendingCycleIds);
        Assert.False(plan.WindowComplete);
        var cycle = await harness.WithRunnerAsync(r => r.ExecuteCycleAsync("run-paper", plan.PendingCycleIds[0]));
        Assert.Equal(FiCycleRunStatus.Completed, cycle.Status);

        var last = await harness.WithRunnerAsync(r => r.PreparePaperCycleAsync("run-paper", new DateOnly(2030, 3, 5)));
        Assert.True(last.WindowComplete);
        Assert.Equal(FiCycleRunStatus.Completed, (await harness.WithRunnerAsync(r => r.ExecuteCycleAsync("run-paper", last.PendingCycleIds.Single()))).Status);

        await using var db = harness.Db();
        Assert.Equal(new[] { 1, 2 }, await db.FiCycles.Where(c => c.RunId == "run-paper").OrderBy(c => c.Sequence).Select(c => c.Sequence).ToListAsync());
        Assert.Equal(3, await db.FiDecisions.CountAsync(d => d.RunId == "run-paper" && d.Action == "BOOTSTRAP"));
    }
}
