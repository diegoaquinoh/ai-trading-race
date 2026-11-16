using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Decision audit persists every outcome (HOLD, failures, synthesized skips) with
/// attempts, tool traces, usage and policy evaluation. The service is constructed
/// without any knowledge-graph or regime dependency.
/// </summary>
public sealed class DecisionAuditServiceTests : IDisposable
{
    private readonly FiSqliteDatabase _database = new();

    public void Dispose() => _database.Dispose();

    private static DecisionAuditService Service(Infrastructure.Database.TradingDbContext db) =>
        new(db, Fi.EngineOptions(), NullLogger<DecisionAuditService>.Instance);

    internal static JsonObject StrategyResult(string outcome, string decisionId = "dec-1", string cycleId = "cycle-2025-01-03",
        bool withProposal = true, string action = "HOLD")
    {
        var result = new JsonObject
        {
            ["schemaVersion"] = "1.0",
            ["runId"] = Fi.RunId,
            ["cycleId"] = cycleId,
            ["decisionId"] = decisionId,
            ["strategyId"] = Fi.StrategyId,
            ["strategyKind"] = "single_agent",
            ["repetition"] = 0,
            ["requestHash"] = Fi.RequestHash(decisionId),
            ["inputHashes"] = new JsonObject { ["portfolioState"] = CanonicalJson.ContentHash(Fi.Genesis()) },
            ["outcome"] = outcome,
            ["completedAt"] = "2025-01-04T00:00:12Z",
            ["reasons"] = outcome == "completed_hold" ? new JsonArray() : new JsonArray("model output failed schema validation twice"),
            ["proposal"] = withProposal
                ? new JsonObject
                {
                    ["action"] = action,
                    ["targetWeights"] = new JsonArray(),
                    ["supportingClaimIds"] = new JsonArray("claim-1"),
                    ["supportingCalculationIds"] = new JsonArray(),
                }
                : null,
            ["researchNote"] = new JsonObject
            {
                ["status"] = "supported",
                ["claims"] = new JsonArray(),
                ["numericalFindings"] = new JsonArray(),
                ["hypotheses"] = new JsonArray(),
                ["counterevidence"] = new JsonArray(),
                ["coverageGaps"] = new JsonArray("no FOMC minutes in window"),
                ["citations"] = new JsonArray(),
                ["retrievalRunIds"] = new JsonArray(),
                ["explanation"] = "Curve unchanged; holding.",
            },
            ["validation"] = new JsonArray(new JsonObject
            {
                ["step"] = "schema",
                ["passed"] = outcome == "completed_hold",
                ["severity"] = "blocking",
                ["details"] = new JsonArray(),
            }),
            ["policyEvaluation"] = Fi.PolicyEvaluation(decisionId, "HOLD", 0),
            ["attempts"] = new JsonArray(
                Attempt("att-1", 1, outcome == "completed_hold" ? "ok" : "malformed"),
                Attempt("att-2", 2, outcome == "completed_hold" ? "ok" : "malformed")),
            ["toolTraces"] = new JsonArray(new JsonObject
            {
                ["traceId"] = "trace-1",
                ["agentRole"] = "single",
                ["toolName"] = "price_instruments",
                ["request"] = new JsonObject { ["securityIds"] = new JsonArray(Fi.Security) },
                ["responseSummary"] = new JsonObject { ["calculationId"] = "calc-1" },
                ["outputRef"] = "calc-1",
                ["startedAt"] = "2025-01-04T00:00:01Z",
                ["durationMs"] = 35,
                ["status"] = "ok",
                ["error"] = null,
            }),
            ["specialistTasks"] = new JsonArray(),
            ["usage"] = new JsonObject
            {
                ["generationCalls"] = 2,
                ["toolCalls"] = 1,
                ["evidenceCalls"] = 0,
                ["uniqueEvidenceChunks"] = 0,
                ["evidenceTokens"] = 0,
                ["inputTokens"] = 1200,
                ["outputTokens"] = 300,
                ["durationMs"] = 4100,
                ["estimatedCostUsd"] = "0.0042",
                ["priceScheduleId"] = "recorded-zero-v1",
                ["budgetExhausted"] = null,
            },
            ["versions"] = new JsonObject
            {
                ["provider"] = "recorded",
                ["model"] = "reference-heuristic-v1",
                ["promptVersion"] = "single-v1",
                ["toolSchemaVersion"] = "tools-v1",
                ["engineVersion"] = Fi.EngineVersion,
                ["evidenceSnapshotId"] = null,
                ["indexBuildId"] = null,
                ["retrievalMode"] = "none",
                ["strategyConfigHash"] = null,
            },
            ["evidenceBundleIds"] = new JsonArray(),
            ["resultHash"] = null,
            ["signature"] = null,
        };
        return Seal(result);
    }

    internal static JsonObject Seal(JsonObject result)
    {
        var hash = CanonicalJson.EnvelopeHash(result, "resultHash");
        result["resultHash"] = hash;
        result["signature"] = CanonicalJson.Sign(hash, Fi.KeyBytes);
        return result;
    }

    private static JsonObject Attempt(string id, int number, string status) => new()
    {
        ["attemptId"] = id,
        ["attemptNumber"] = number,
        ["agentRole"] = "single",
        ["purpose"] = number == 1 ? "single" : "repair",
        ["provider"] = "recorded",
        ["model"] = "reference-heuristic-v1",
        ["inputTokens"] = 600,
        ["outputTokens"] = 150,
        ["startedAt"] = "2025-01-04T00:00:00Z",
        ["durationMs"] = 2000,
        ["status"] = status,
        ["recordedResponseId"] = "rec-" + id,
        ["error"] = status == "ok" ? null : "missing field targetWeights",
    };

    [Fact]
    public async Task HoldOutcome_IsPersistedWithFullAudit()
    {
        await using (var db = _database.CreateContext())
        {
            var result = await Service(db).RecordResultAsync(Fi.Raw(StrategyResult("completed_hold")),
                new DecisionAuditContext { PortfolioId = Fi.PortfolioId, ExpectedDecisionId = "dec-1" });

            Assert.Equal(DecisionAuditStatus.Recorded, result.Status);
            Assert.Equal(FiAuditIntegrity.Verified, result.Integrity);
            Assert.False(result.ActionableProposal);
        }

        await using (var db = _database.CreateContext())
        {
            var decision = await db.FiDecisions.Include(d => d.Attempts).Include(d => d.ToolTraces).Include(d => d.Usage)
                .Include(d => d.PolicyEvaluations).SingleAsync();
            Assert.Equal(FiDecisionOutcome.CompletedHold, decision.Outcome);
            Assert.Equal("HOLD", decision.Action);
            Assert.Equal(2, decision.Attempts.Count);
            Assert.Single(decision.ToolTraces);
            Assert.Equal(1200, decision.Usage!.InputTokens);
            Assert.Equal(0.0042m, decision.Usage.EstimatedCostUsd);
            Assert.Single(decision.PolicyEvaluations);
            Assert.Null(decision.PolicyEvaluations.Single().PlatformRecheckPassed);
            Assert.Contains("no FOMC minutes", decision.ResearchNoteJson);
            Assert.NotNull(decision.ResultJson);

            var detail = await new FixedIncomeQueryService(db, Fi.Policies()).GetDecisionAsync("dec-1");
            Assert.NotNull(detail);
            Assert.Equal(2, detail!.Attempts.Count);
            Assert.Single(detail.ToolTraces);
            Assert.Single(detail.PolicyEvaluations);
        }
    }

    [Theory]
    [InlineData("failed_invalid_output")]
    [InlineData("failed_budget")]
    [InlineData("abstained_insufficient_evidence")]
    public async Task FailureAndAbstentionOutcomes_ArePersisted(string outcome)
    {
        await using var db = _database.CreateContext();
        var result = await Service(db).RecordResultAsync(
            Fi.Raw(StrategyResult(outcome, withProposal: false)), new DecisionAuditContext());

        Assert.Equal(DecisionAuditStatus.Recorded, result.Status);
        var decision = await db.FiDecisions.Include(d => d.Attempts).SingleAsync();
        Assert.Equal(outcome, decision.Outcome);
        Assert.Null(decision.ProposalJson);
        Assert.Contains("schema validation", decision.ReasonsJson);
        Assert.All(decision.Attempts, a => Assert.Equal("malformed", a.Status));
    }

    [Fact]
    public async Task SynthesizedDependencyFailure_IsPersistedWithoutEngineResult()
    {
        await using var db = _database.CreateContext();
        var result = await Service(db).RecordSynthesizedOutcomeAsync(new SynthesizedDecisionOutcome
        {
            RunId = Fi.RunId,
            CycleId = "cycle-2025-01-03",
            DecisionId = "dec-dep",
            StrategyId = Fi.StrategyId,
            Outcome = FiDecisionOutcome.FailedDependency,
            Reasons = new[] { "research engine unavailable (503)" },
            CompletedAt = new DateTimeOffset(2025, 1, 4, 0, 0, 0, TimeSpan.Zero),
        });
        var again = await Service(db).RecordSynthesizedOutcomeAsync(new SynthesizedDecisionOutcome
        {
            RunId = Fi.RunId,
            CycleId = "cycle-2025-01-03",
            DecisionId = "dec-dep",
            StrategyId = Fi.StrategyId,
            Outcome = FiDecisionOutcome.FailedDependency,
        });

        Assert.Equal(DecisionAuditStatus.Recorded, result.Status);
        Assert.Equal(DecisionAuditStatus.AlreadyRecorded, again.Status);
        var decision = await db.FiDecisions.Include(d => d.Usage).SingleAsync();
        Assert.Equal(FiAuditIntegrity.Synthesized, decision.Integrity);
        Assert.NotNull(decision.Usage);
    }

    [Fact]
    public async Task SameLogicalDecision_IsIdempotentAndDifferentResultConflicts()
    {
        await using var db = _database.CreateContext();
        var service = Service(db);
        var hold = StrategyResult("completed_hold");

        var first = await service.RecordResultAsync(Fi.Raw(hold), new DecisionAuditContext());
        var retry = await service.RecordResultAsync(Fi.Raw(hold), new DecisionAuditContext());
        var different = await service.RecordResultAsync(
            Fi.Raw(StrategyResult("failed_budget", decisionId: "dec-1b", withProposal: false)), new DecisionAuditContext());

        Assert.Equal(DecisionAuditStatus.Recorded, first.Status);
        Assert.Equal(DecisionAuditStatus.AlreadyRecorded, retry.Status);
        Assert.Equal(DecisionAuditStatus.Conflict, different.Status);
        Assert.Equal(1, await db.FiDecisions.CountAsync());
    }

    [Fact]
    public async Task TamperedResult_IsAuditedButNeverActionable()
    {
        var proposal = StrategyResult("completed_proposal", action: "REBALANCE");
        proposal["outcome"] = "completed_proposal";
        proposal["reasons"] = new JsonArray("tampered after signing");

        await using var db = _database.CreateContext();
        var result = await Service(db).RecordResultAsync(Fi.Raw(proposal), new DecisionAuditContext());

        Assert.Equal(DecisionAuditStatus.Recorded, result.Status);
        Assert.Equal(FiAuditIntegrity.HashMismatch, result.Integrity);
        Assert.False(result.ActionableProposal);
    }

    [Fact]
    public async Task VerifiedRebalanceProposal_IsActionable()
    {
        await using var db = _database.CreateContext();
        var result = await Service(db).RecordResultAsync(
            Fi.Raw(StrategyResult("completed_proposal", action: "REBALANCE")), new DecisionAuditContext());

        Assert.True(result.ActionableProposal);
    }

    [Fact]
    public async Task UnknownSchemaMajor_IsRejected()
    {
        var result = StrategyResult("completed_hold");
        result["schemaVersion"] = "2.0";
        Seal(result);

        await using var db = _database.CreateContext();
        var outcome = await Service(db).RecordResultAsync(Fi.Raw(result), new DecisionAuditContext());

        Assert.Equal(DecisionAuditStatus.Rejected, outcome.Status);
        Assert.Equal(0, await db.FiDecisions.CountAsync());
    }

    [Fact]
    public void Service_HasNoKnowledgeGraphOrRegimeDependency()
    {
        var parameters = typeof(DecisionAuditService).GetConstructors().Single().GetParameters();

        Assert.DoesNotContain(parameters, p => p.ParameterType.Namespace?.Contains("Knowledge") == true);
        Assert.DoesNotContain(parameters, p => p.ParameterType.Name.Contains("Regime"));
    }
}
