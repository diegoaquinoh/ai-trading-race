using System.Text.Json;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Request binding (spec 14.6): every TransitionProposal and StrategyResult echoes the canonical hash
/// of the request body the platform sent; the platform passes that hash as ExpectedRequestHash and a
/// signed answer to any other request is rejected (proposal) or audited as an integrity failure
/// (decision). Before the fix ExpectedRequestHash was never set, so these checks never ran.
/// </summary>
public sealed class RequestBindingTests : IDisposable
{
    private const string RunId = "run-app";

    private readonly FiSqliteDatabase _database = new();

    public void Dispose() => _database.Dispose();

    private static string Pf(string strategyId) => FiRunHarness.PortfolioId(RunId, strategyId);

    private static string Cycle(int index) => FiIds.Cycle(FiRunHarness.Week[index]);

    private static FakeDecision RebalanceLlmMarketAt(DecisionRequestDto r, int cycle) =>
        r.StrategyId == "llm_market" && r.CycleId == Cycle(cycle)
            ? FakeDecision.Rebalance((FakeResearchEngine.Sec1, "0.35"), (FakeResearchEngine.Sec2, "0.34"),
                (FakeResearchEngine.Sec3, "0.25"), ("CASH-USD", "0.06"))
            : FakeDecision.Hold;

    // ------------------------------------------------------------------ services

    [Fact]
    public async Task Commit_RejectsAProposalComputedForADifferentRequest_AndCommitsNothing()
    {
        await using (var db = _database.CreateContext())
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
        }

        var proposal = Fi.Seal(Fi.CapitalFlow(Fi.Genesis(), "cmd-1", requestSalt: "another-request"));
        TransitionCommitResult mismatched;
        TransitionCommitResult bound;
        await using (var db = _database.CreateContext())
        {
            mismatched = await Fi.CommitService(db).CommitAsync(Fi.Raw(proposal), new TransitionCommitContext
            {
                ExpectedCommandId = "cmd-1",
                ExpectedRequestHash = Fi.RequestHash("cmd-1"),
            });
        }

        await using (var db = _database.CreateContext())
        {
            Assert.Equal(0, await db.FiCommandRecords.CountAsync());
            Assert.Equal(0, (await db.FiPortfolios.SingleAsync()).CurrentVersion);
            bound = await Fi.CommitService(db).CommitAsync(Fi.Raw(proposal), new TransitionCommitContext
            {
                ExpectedCommandId = "cmd-1",
                ExpectedRequestHash = Fi.RequestHash("cmd-1", "another-request"),
            });
        }

        Assert.Equal(TransitionCommitStatus.Rejected, mismatched.Status);
        Assert.Contains(mismatched.Issues, i => i.Code == VerificationCodes.RequestHashMismatch);
        Assert.Equal(TransitionCommitStatus.Committed, bound.Status);
    }

    [Fact]
    public async Task StrategyResult_ForADifferentRequest_IsAuditedAsAnIntegrityFailure_AndIsNotActionable()
    {
        var result = DecisionAuditServiceTests.StrategyResult("completed_proposal", action: "REBALANCE");
        await using var db = _database.CreateContext();
        var audit = new DecisionAuditService(db, Fi.EngineOptions(), NullLogger<DecisionAuditService>.Instance);

        var recorded = await audit.RecordResultAsync(Fi.Raw(result), new DecisionAuditContext
        {
            ExpectedDecisionId = "dec-1",
            ExpectedRequestHash = Fi.RequestHash("dec-1", "the-request-actually-sent"),
        });

        Assert.Equal(DecisionAuditStatus.Recorded, recorded.Status);
        Assert.Equal(FiAuditIntegrity.RequestHashMismatch, recorded.Integrity);
        Assert.False(recorded.ActionableProposal);
        var stored = await db.FiDecisions.AsNoTracking().SingleAsync(d => d.DecisionId == "dec-1");
        Assert.Equal(FiAuditIntegrity.RequestHashMismatch, stored.Integrity);
        Assert.Equal(Fi.RequestHash("dec-1"), stored.RequestHash);
    }

    // ------------------------------------------------------------------ executor

    [Fact]
    public async Task EveryCommitAndDecision_IsBoundToTheHashOfTheRequestBodySent()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.Decide = r => RebalanceLlmMarketAt(r, 2);
        await harness.StartRunAsync(RunId);

        Assert.True((await harness.ExecuteAsync(RunId)).Succeeded);

        await using var db = harness.Db();
        var received = harness.Fake.TransitionRequestHashes.ToList();
        var commands = await db.FiCommandRecords.AsNoTracking().ToListAsync();
        Assert.NotEmpty(commands);
        Assert.All(commands, c => Assert.Equal(received.Last(r => r.CommandId == c.CommandId).RequestHash, c.RequestHash));

        var requests = harness.Fake.DecisionRequests.ToDictionary(r => r.DecisionId);
        var verified = await db.FiDecisions.AsNoTracking().Where(d => d.Integrity == FiAuditIntegrity.Verified).ToListAsync();
        Assert.NotEmpty(verified);
        Assert.All(verified, d => Assert.Equal(FiRequestBody.Hash(requests[d.DecisionId]), d.RequestHash));
        Assert.True(await db.FiOrderIntents.AnyAsync(o => o.PortfolioId == Pf("llm_market") && !o.Bootstrap));
    }

    [Fact]
    public async Task SignedProposalForAnotherRequest_IsRejected_AndOnlyThatSubmissionIsLost()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.Decide = r => RebalanceLlmMarketAt(r, 2);
        var target = $"cmd:{RunId}:{Cycle(2)}:{Pf("llm_market")}:submit";
        harness.Fake.WrongRequestHashFor = id => id == target;
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        Assert.False(await db.FiCommandRecords.AnyAsync(c => c.CommandId == target));
        Assert.False(await db.FiOrderIntents.AnyAsync(o => o.PortfolioId == Pf("llm_market") && !o.Bootstrap));
        var cycle = await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(2));
        Assert.Equal(FiCycleStatus.Completed, cycle.Status);
        Assert.Contains("submit_decision_failed", cycle.ErrorsJson);
        Assert.Contains(VerificationCodes.RequestHashMismatch, cycle.ErrorsJson);
        Assert.Equal(5, await db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == Pf("llm_market")));
    }

    [Fact]
    public async Task SignedStrategyResultForAnotherRequest_IsAuditedAsIntegrityFailure_AndCreatesNoOrder()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        harness.Fake.Decide = r => RebalanceLlmMarketAt(r, 2);
        var decisionId = FiIds.Decision(RunId, Cycle(2), "llm_market", 0);
        harness.Fake.WrongRequestHashFor = id => id == decisionId;
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        await using var db = harness.Db();
        var decision = await db.FiDecisions.AsNoTracking().SingleAsync(d => d.DecisionId == decisionId);
        Assert.Equal(FiAuditIntegrity.RequestHashMismatch, decision.Integrity);
        Assert.Equal(FiDecisionOutcome.CompletedProposal, decision.Outcome);
        Assert.False(await db.FiOrderIntents.AnyAsync(o => o.DecisionId == decisionId));
        Assert.Contains("result_integrity", (await db.FiCycles.AsNoTracking().SingleAsync(c => c.CycleId == Cycle(2))).ErrorsJson);
    }

    [Fact]
    public async Task StaleRecompute_BindsTheCommitToTheRecomputedRequest()
    {
        using var harness = new FiRunHarness();
        harness.AddWeek();
        var target = $"cmd:{RunId}:{Cycle(1)}:{Pf("cash")}:value";
        var injected = false;
        harness.Fake.BeforeTransition = async request =>
        {
            if (injected || request.CommandId != target)
            {
                return;
            }

            // A concurrent writer commits another command on the same portfolio while the engine
            // computes this one: the proposal becomes stale and is recomputed against the new state.
            injected = true;
            using var scope = harness.Provider.CreateScope();
            var commits = scope.ServiceProvider.GetRequiredService<ITransitionCommitService>();
            var state = (await commits.GetCurrentStateAsync(Pf("cash")))!;
            var concurrent = request with
            {
                CommandId = "cmd:concurrent-top-up",
                CommandType = FiCommandType.CapitalFlow,
                PortfolioState = JsonDocument.Parse(state.StateJson).RootElement.Clone(),
                PortfolioStateHash = state.StateHash,
                MarketSnapshot = null,
                CapitalAmountUsd = "1.00",
            };
            var proposal = await harness.Fake.ProposeTransitionAsync(concurrent);
            var committed = await commits.CommitAsync(proposal, new TransitionCommitContext
            {
                ExpectedCommandId = concurrent.CommandId,
                ExpectedRequestHash = FiRequestBody.Hash(concurrent),
            });
            Assert.Equal(TransitionCommitStatus.Committed, committed.Status);
        };
        await harness.StartRunAsync(RunId);

        var result = await harness.ExecuteAsync(RunId);

        Assert.True(result.Succeeded, result.FailureReason);
        var attempts = harness.Fake.TransitionRequestHashes.Where(r => r.CommandId == target).Select(r => r.RequestHash).ToList();
        Assert.Equal(2, attempts.Count);
        Assert.NotEqual(attempts[0], attempts[1]);
        await using var db = harness.Db();
        var record = await db.FiCommandRecords.AsNoTracking().SingleAsync(c => c.CommandId == target);
        Assert.Equal(attempts[1], record.RequestHash);
        Assert.Equal(1, harness.Metrics.Total(FixedIncomeMetrics.ConcurrencyConflicts));
        Assert.Equal(5, await db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == Pf("cash")));
    }
}
