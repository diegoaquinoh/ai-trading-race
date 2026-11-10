using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>Commit protocol on SQLite in-memory: real transactions and unique constraints.</summary>
public sealed class TransitionCommitServiceTests : IDisposable
{
    private readonly FiSqliteDatabase _database = new();

    public void Dispose() => _database.Dispose();

    private async Task<JsonObject> CreatePortfolioAsync()
    {
        await using var db = _database.CreateContext();
        var snapshot = await Fi.CommitService(db).CreatePortfolioAsync(new CreateFiPortfolioRequest
        {
            PortfolioId = Fi.PortfolioId,
            RunId = Fi.RunId,
            StrategyId = Fi.StrategyId,
            RiskPolicyId = Fi.PolicyId,
            DataMode = FiDataMode.SyntheticCurve,
            AsOf = Fi.GenesisAsOf,
        });
        return (JsonObject)JsonNode.Parse(snapshot.StateJson)!;
    }

    private async Task<TransitionCommitResult> CommitAsync(JsonObject proposal, string? expectedCommandId = null)
    {
        await using var db = _database.CreateContext();
        return await Fi.CommitService(db).CommitAsync(Fi.Raw(proposal),
            new TransitionCommitContext { ExpectedCommandId = expectedCommandId });
    }

    [Fact]
    public async Task Genesis_StateTextAndHashAreStoredVerbatim()
    {
        var genesis = await CreatePortfolioAsync();

        await using var db = _database.CreateContext();
        var state = await Fi.CommitService(db).GetCurrentStateAsync(Fi.PortfolioId);

        Assert.NotNull(state);
        Assert.Equal(0, state!.Version);
        Assert.Equal(CanonicalJson.Serialize(Fi.Genesis()), state.StateJson);
        Assert.Equal(CanonicalJson.Sha256(state.StateJson), state.StateHash);
        Assert.Equal(CanonicalJson.ContentHash(genesis), state.StateHash);
    }

    [Fact]
    public async Task Commit_AppliesVerifiedProposalAtomically()
    {
        var genesis = await CreatePortfolioAsync();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));

        var result = await CommitAsync(proposal, "cmd-1");

        Assert.Equal(TransitionCommitStatus.Committed, result.Status);
        Assert.Equal(1, result.CommittedVersion);
        await using var db = _database.CreateContext();
        var portfolio = await db.FiPortfolios.SingleAsync();
        Assert.Equal(1, portfolio.CurrentVersion);
        Assert.Equal(proposal["newStateHash"]!.GetValue<string>(), portfolio.CurrentStateHash);
        var stored = await db.FiPortfolioStateVersions.SingleAsync(v => v.Version == 1);
        Assert.Equal(CanonicalJson.Serialize(proposal["newState"]), stored.StateJson);
        Assert.Equal(1, await db.FiJournals.CountAsync());
        Assert.Equal(2, await db.FiJournalEntries.CountAsync());
        Assert.Equal(1, await db.FiPortfolioEvents.CountAsync());
        Assert.Equal(1, await db.FiCashFlowEvents.CountAsync());
        var command = await db.FiCommandRecords.SingleAsync();
        Assert.Equal(FiCommandStatus.Committed, command.Status);
        Assert.Equal(proposal["requestHash"]!.GetValue<string>(), command.RequestHash);
    }

    [Fact]
    public async Task IdempotentRetry_ProducesExactlyOneEffect()
    {
        var genesis = await CreatePortfolioAsync();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));

        var first = await CommitAsync(proposal);
        var second = await CommitAsync(proposal);
        var third = await CommitAsync(proposal);

        Assert.Equal(TransitionCommitStatus.Committed, first.Status);
        Assert.Equal(TransitionCommitStatus.AlreadyCommitted, second.Status);
        Assert.Equal(TransitionCommitStatus.AlreadyCommitted, third.Status);
        Assert.Equal(first.CommittedVersion, second.CommittedVersion);
        Assert.Equal(first.StateHash, second.StateHash);
        await using var db = _database.CreateContext();
        Assert.Equal(1, await db.FiCommandRecords.CountAsync());
        Assert.Equal(1, await db.FiJournals.CountAsync());
        Assert.Equal(2, await db.FiPortfolioStateVersions.CountAsync());
        Assert.Equal(1, (await db.FiPortfolios.SingleAsync()).CurrentVersion);
    }

    [Fact]
    public async Task SameCommandId_DifferentPayload_IsConflict()
    {
        var genesis = await CreatePortfolioAsync();
        await CommitAsync(Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1")));

        var different = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1", amount: "2000000.00", eventId: "evt-capital-2", requestSalt: "other"));
        var result = await CommitAsync(different);

        Assert.Equal(TransitionCommitStatus.Conflict, result.Status);
        await using var db = _database.CreateContext();
        Assert.Equal(1, await db.FiJournals.CountAsync());
        Assert.Equal(1, (await db.FiPortfolios.SingleAsync()).CurrentVersion);
    }

    [Fact]
    public async Task StaleVersion_IsRejectedWithoutEffects()
    {
        var genesis = await CreatePortfolioAsync();
        var first = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        var computedAgainstOldState = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-2", eventId: "evt-capital-2"));
        await CommitAsync(first);

        var result = await CommitAsync(computedAgainstOldState);

        Assert.Equal(TransitionCommitStatus.Stale, result.Status);
        Assert.Contains(result.Issues, i => i.Code == VerificationCodes.StaleVersion);
        await using var db = _database.CreateContext();
        Assert.Equal(1, await db.FiCommandRecords.CountAsync());
        Assert.Equal(1, (await db.FiPortfolios.SingleAsync()).CurrentVersion);
    }

    [Fact]
    public async Task ReconciliationFailure_BlocksFurtherCommitsUntilOperatorAction()
    {
        var genesis = await CreatePortfolioAsync();
        var broken = Fi.CapitalFlow(genesis, "cmd-broken");
        broken["reconciliation"] = Fi.Reconciliation(false);
        Fi.Seal(broken);

        var blocked = await CommitAsync(broken);
        var retryOfBroken = await CommitAsync(broken);
        var valid = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-valid", eventId: "evt-capital-9"));
        var rejectedWhileBlocked = await CommitAsync(valid);

        Assert.Equal(TransitionCommitStatus.PortfolioBlocked, blocked.Status);
        Assert.Equal(TransitionCommitStatus.PortfolioBlocked, retryOfBroken.Status);
        Assert.Equal(TransitionCommitStatus.PortfolioBlocked, rejectedWhileBlocked.Status);
        await using (var db = _database.CreateContext())
        {
            var portfolio = await db.FiPortfolios.SingleAsync();
            Assert.StartsWith("reconciliation_failed", portfolio.BlockedReason);
            Assert.Equal(0, portfolio.CurrentVersion);
            Assert.Equal(0, await db.FiJournals.CountAsync());
            var record = await db.FiCommandRecords.SingleAsync();
            Assert.Equal(FiCommandStatus.RejectedReconciliation, record.Status);
            Assert.Null(record.CommittedVersion);
        }

        await using (var db = _database.CreateContext())
        {
            Assert.True(await Fi.CommitService(db).UnblockAsync(Fi.PortfolioId, "admin@example.com", "ledger investigated"));
        }

        var afterUnblock = await CommitAsync(valid);
        Assert.Equal(TransitionCommitStatus.Committed, afterUnblock.Status);
    }

    [Fact]
    public async Task DuplicateEventId_IsRejected()
    {
        var genesis = await CreatePortfolioAsync();
        var first = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1", eventId: "evt-capital-1"));
        await CommitAsync(first);

        var replayedEvent = Fi.Seal(Fi.CapitalFlow(Fi.NextState(first), "cmd-2", eventId: "evt-capital-1"));
        var result = await CommitAsync(replayedEvent);

        Assert.Equal(TransitionCommitStatus.Rejected, result.Status);
        Assert.Contains(result.Issues, i => i.Code == "duplicate_event");
        await using var db = _database.CreateContext();
        Assert.Equal(1, await db.FiPortfolioEvents.CountAsync());
        Assert.Equal(1, (await db.FiPortfolios.SingleAsync()).CurrentVersion);
    }

    [Fact]
    public async Task UniqueConstraint_IsTheBackstopForOneEffectPerEvent()
    {
        await CreatePortfolioAsync();
        await using var db = _database.CreateContext();
        db.FiPortfolioEvents.Add(new PortfolioEvent { PortfolioId = Fi.PortfolioId, EventId = "evt-x", EventType = "capital_flow", CommandId = "c1" });
        db.FiPortfolioEvents.Add(new PortfolioEvent { PortfolioId = Fi.PortfolioId, EventId = "evt-x", EventType = "capital_flow", CommandId = "c2" });

        await Assert.ThrowsAsync<DbUpdateException>(() => db.SaveChangesAsync());
    }

    [Fact]
    public async Task TamperedProposal_IsRejectedAndConsumesNoCommandId()
    {
        var genesis = await CreatePortfolioAsync();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        proposal["newState"]!["cashUsd"] = "5000000.00";

        var result = await CommitAsync(proposal);

        Assert.Equal(TransitionCommitStatus.Rejected, result.Status);
        await using var db = _database.CreateContext();
        Assert.Equal(0, await db.FiCommandRecords.CountAsync());
        Assert.Equal(0, (await db.FiPortfolios.SingleAsync()).CurrentVersion);
    }

    [Fact]
    public async Task PolicyViolation_IsRejected()
    {
        var genesis = await CreatePortfolioAsync();
        var capital = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        await CommitAsync(capital);
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, cashRatio: "0.01");
        var decision = Fi.Seal(Fi.SubmitDecision(Fi.NextState(capital), "cmd-2", policyEvaluation: evaluation));

        var result = await CommitAsync(decision);

        Assert.Equal(TransitionCommitStatus.Rejected, result.Status);
        Assert.Contains(result.Issues, i => i.Code == VerificationCodes.PolicyLimitExceeded);
        await using var db = _database.CreateContext();
        Assert.Equal(0, await db.FiOrderIntents.CountAsync());
    }

    [Fact]
    public async Task FullLifecycle_OrderFillSettlement_OneFillPerOrder()
    {
        var genesis = await CreatePortfolioAsync();
        var capital = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        Assert.Equal(TransitionCommitStatus.Committed, (await CommitAsync(capital)).Status);

        var decision = Fi.Seal(Fi.SubmitDecision(Fi.NextState(capital), "cmd-2"));
        var submitted = await CommitAsync(decision);
        Assert.Equal(TransitionCommitStatus.Committed, submitted.Status);

        var fill = Fi.Seal(Fi.FillOrder(Fi.NextState(decision), "cmd-3"));
        var filled = await CommitAsync(fill);
        Assert.Equal(TransitionCommitStatus.Committed, filled.Status);
        Assert.Equal(3, filled.CommittedVersion);

        // A second fill for the same order (different ids, recomputed on the latest state) is refused.
        var secondFill = Fi.Seal(Fi.FillOrder(Fi.NextState(fill), "cmd-4", fillId: "fill-2", settlementId: "stl-2", eventId: "evt-exec-2"));
        var duplicate = await CommitAsync(secondFill);
        Assert.Equal(TransitionCommitStatus.Rejected, duplicate.Status);

        await using var db = _database.CreateContext();
        var order = await db.FiOrderIntents.SingleAsync();
        Assert.Equal(FiOrderStatus.Filled, order.Status);
        Assert.Equal(3, order.LastUpdatedVersion);
        Assert.Equal(100000m, order.Face);
        var storedFill = await db.FiFills.SingleAsync();
        Assert.Equal(100520.00m, storedFill.ConsiderationUsd);
        Assert.Equal(100.12m, storedFill.ExecutionCleanPricePer100);
        var settlement = await db.FiSettlements.SingleAsync();
        Assert.Equal(FiSettlementStatus.Pending, settlement.Status);
        Assert.Equal(1, await db.FiPolicyEvaluations.CountAsync());
        Assert.True((await db.FiPolicyEvaluations.SingleAsync()).PlatformRecheckPassed);
        Assert.Equal(3, (await db.FiPortfolios.SingleAsync()).CurrentVersion);

        var journalEntries = await db.FiJournalEntries.ToListAsync();
        Assert.Equal(journalEntries.Sum(e => e.DebitUsd), journalEntries.Sum(e => e.CreditUsd));
    }

    [Fact]
    public async Task UnknownPortfolio_IsNotFound()
    {
        var proposal = Fi.Seal(Fi.CapitalFlow(Fi.Genesis(), "cmd-1"));

        var result = await CommitAsync(proposal);

        Assert.Equal(TransitionCommitStatus.NotFound, result.Status);
    }

    [Fact]
    public async Task GetCommand_ReturnsCommittedRecordForRetryShortCircuit()
    {
        var genesis = await CreatePortfolioAsync();
        await CommitAsync(Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1")));

        await using var db = _database.CreateContext();
        var record = await Fi.CommitService(db).GetCommandAsync("cmd-1");

        Assert.NotNull(record);
        Assert.Equal(1, record!.CommittedVersion);
        Assert.Null(await Fi.CommitService(db).GetCommandAsync("cmd-unknown"));
    }
}
