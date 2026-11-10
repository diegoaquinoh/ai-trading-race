using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;

namespace AiTradingRace.Tests.FixedIncome;

public sealed class ExperimentServiceTests : IDisposable
{
    private readonly FiSqliteDatabase _database = new();

    public void Dispose() => _database.Dispose();

    internal static ExperimentService Service(TradingDbContext db) =>
        new(db, Fi.Policies(), NullLogger<ExperimentService>.Instance);

    internal static CreateExperimentDefinitionRequest Definition(string name = "Graph vs RAG", int version = 1) => new()
    {
        ExperimentId = "exp-demo",
        Version = version,
        Name = name,
        DataMode = FiDataMode.SyntheticCurve,
        StartDate = new DateOnly(2025, 1, 2),
        EndDate = new DateOnly(2025, 3, 31),
        InstrumentUniverseVersion = "universe-synthetic-v1",
        Repetitions = 2,
        Strategies = new List<ExperimentStrategyRequest>
        {
            new() { StrategyId = "cash_reference", StrategyKind = FiStrategyKind.CashReference, StrategyConfigId = "cash-v1" },
            new() { StrategyId = "llm_graph", StrategyKind = FiStrategyKind.SingleAgent, StrategyConfigId = "graph-policy-v1" },
        },
        Parameters = new JsonObject { ["seed"] = 7, ["note"] = "decimal values as strings: 0.02" },
    };

    [Fact]
    public async Task Definition_IsImmutable_IdempotentOnSameHash_ConflictOnDifferentContent()
    {
        await using var db = _database.CreateContext();
        var service = Service(db);

        var created = await service.CreateDefinitionAsync(Definition(), "op@example.com");
        var repeated = await service.CreateDefinitionAsync(Definition(), "op@example.com");
        var changed = await service.CreateDefinitionAsync(Definition(name: "Renamed"), "op@example.com");
        var newVersion = await service.CreateDefinitionAsync(Definition(name: "Renamed", version: 2), "op@example.com");

        Assert.Equal(ExperimentDefinitionStatus.Created, created.Status);
        Assert.Equal(ExperimentDefinitionStatus.AlreadyExists, repeated.Status);
        Assert.Equal(created.Definition!.DefinitionHash, repeated.Definition!.DefinitionHash);
        Assert.Equal(ExperimentDefinitionStatus.Conflict, changed.Status);
        Assert.Equal(ExperimentDefinitionStatus.Created, newVersion.Status);
        Assert.Equal(2, await db.FiExperimentDefinitions.CountAsync());
    }

    [Fact]
    public async Task Definition_RejectsUnknownPolicyAndFloatParameters()
    {
        await using var db = _database.CreateContext();
        var service = Service(db);

        var unknownPolicy = await service.CreateDefinitionAsync(Definition() with { RiskPolicyId = "made-up-policy" }, null);
        var floats = await service.CreateDefinitionAsync(Definition() with { Parameters = new JsonObject { ["x"] = 0.5 } }, null);
        var noStrategies = await service.CreateDefinitionAsync(Definition() with { Strategies = new List<ExperimentStrategyRequest>() }, null);

        Assert.Equal(ExperimentDefinitionStatus.Invalid, unknownPolicy.Status);
        Assert.Contains("riskPolicyId", unknownPolicy.Errors.Keys);
        Assert.Equal(ExperimentDefinitionStatus.Invalid, floats.Status);
        Assert.Equal(ExperimentDefinitionStatus.Invalid, noStrategies.Status);
    }

    [Fact]
    public async Task StartRun_CreatesQueuedRunWithManifestStrategiesAndGenesisPortfolios()
    {
        await using var db = _database.CreateContext();
        var service = Service(db);
        await service.CreateDefinitionAsync(Definition(), null);

        var result = await service.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-a" }, "op");

        Assert.Equal(StartRunStatus.Accepted, result.Status);
        var run = await db.FiExperimentRuns.SingleAsync();
        Assert.Equal(FiJobState.Queued, run.JobState);
        Assert.Equal(CanonicalJson.Sha256(run.ManifestJson), run.ManifestHash);
        var manifest = JsonNode.Parse(run.ManifestJson)!;
        Assert.Equal("treasury-long-only-v1", manifest["riskPolicy"]!["policyId"]!.GetValue<string>());
        Assert.Equal("0.40", manifest["riskPolicy"]!["maxSingleSecurityRatio"]!.GetValue<string>());
        Assert.Equal(4, await db.FiStrategyInstances.CountAsync());
        Assert.Equal(4, await db.FiPortfolios.CountAsync());
        var genesis = await db.FiPortfolioStateVersions.FirstAsync(v => v.PortfolioId == "pf-run-a-llm_graph-r1");
        Assert.Equal(CanonicalJson.Sha256(genesis.StateJson), genesis.StateHash);
        Assert.Contains("\"asOf\":\"2025-01-02T00:00:00Z\"", genesis.StateJson);
    }

    [Fact]
    public async Task StartRun_SameRunIdSameParameters_IsIdempotent_DifferentParameters_Conflict()
    {
        await using var db = _database.CreateContext();
        var service = Service(db);
        await service.CreateDefinitionAsync(Definition(), null);

        var first = await service.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-a" }, null);
        var retry = await service.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-a" }, null);
        var conflict = await service.StartRunAsync("exp-demo",
            new StartRunRequest { RunId = "run-a", ResponseMode = FiResponseMode.FreshInference }, null);

        Assert.Equal(StartRunStatus.Accepted, first.Status);
        Assert.Equal(StartRunStatus.AlreadyExists, retry.Status);
        Assert.Equal(StartRunStatus.Conflict, conflict.Status);
        Assert.Equal(1, await db.FiExperimentRuns.CountAsync());
    }

    [Fact]
    public async Task JobLifecycle_IsSeparateFromOutcomes_AndCancellationIsFinal()
    {
        await using var db = _database.CreateContext();
        var service = Service(db);
        await service.CreateDefinitionAsync(Definition(), null);
        await service.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-a" }, null);

        Assert.True(await service.TryMarkRunningAsync("run-a"));
        Assert.False(await service.TryMarkRunningAsync("run-a"));
        var cancelled = await service.CancelRunAsync("run-a", "op");
        await service.MarkCompletedAsync("run-a");

        Assert.Equal(RunStateChangeStatus.Changed, cancelled.Status);
        Assert.Equal(FiJobState.Cancelled, await service.GetJobStateAsync("run-a"));
        Assert.Equal(RunStateChangeStatus.InvalidTransition, (await service.CancelRunAsync("run-a", "op")).Status);
    }

    [Fact]
    public async Task Comparison_GroupsRunsByCompatibleDataModeAndPolicy()
    {
        await using var db = _database.CreateContext();
        var service = Service(db);
        await service.CreateDefinitionAsync(Definition(), null);
        await service.CreateDefinitionAsync(Definition(version: 2) with { DataMode = FiDataMode.ObservedSecurity }, null);
        await service.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-syn", ExperimentVersion = 1 }, null);
        await service.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-obs", ExperimentVersion = 2 }, null);

        var comparison = await new FixedIncomeQueryService(db, Fi.Policies()).GetExperimentComparisonAsync("exp-demo");

        Assert.NotNull(comparison);
        Assert.Equal(2, comparison!.Groups.Count);
        Assert.All(comparison.Groups, g => Assert.Single(g.Runs));
        Assert.Contains(comparison.Groups, g => g.Group.DataMode == FiDataMode.SyntheticCurve && g.Runs[0].RunId == "run-syn");
        Assert.Contains(comparison.Groups, g => g.Group.DataMode == FiDataMode.ObservedSecurity && g.Runs[0].RunId == "run-obs");
        Assert.NotEmpty(comparison.Notes);
    }
}
