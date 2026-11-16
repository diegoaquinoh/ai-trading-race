using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Application-mode executor wired like production (one DI scope per cycle step) on the
/// SQLite fi schema, with a <see cref="FakeResearchEngine"/> or a real engine client.
/// </summary>
public sealed class FiRunHarness : IDisposable
{
    public const string ExperimentId = "exp-app";

    public static readonly string[] DefaultStrategies = { "cash", "static_ladder", "llm_market", "llm_rag" };

    public static readonly DateOnly[] Week =
    {
        new(2025, 1, 6), new(2025, 1, 7), new(2025, 1, 8), new(2025, 1, 9), new(2025, 1, 10),
    };

    private readonly FiSqliteDatabase _database = new();

    public FiRunHarness(IResearchEngineClient? engine = null, IOptions<ResearchEngineOptions>? engineOptions = null,
        Action<FixedIncomeExecutionOptions>? configure = null)
    {
        Engine = engine as FakeResearchEngine;
        var execution = new FixedIncomeExecutionOptions
        {
            MaxParallelDecisions = 3,
            TransientRetryAttempts = 0,
            TransientRetryDelayMs = 0,
            CycleRetryAttempts = 0,
        };
        configure?.Invoke(execution);

        var services = new ServiceCollection();
        services.AddLogging();
        services.AddScoped(_ => _database.CreateContext());
        services.AddSingleton(Fi.Policies());
        services.AddSingleton(engineOptions ?? Fi.EngineOptions());
        services.AddSingleton(Options.Create(new FixedIncomeOptions { Execution = execution }));
        services.AddSingleton<IProposalVerifier>(sp => new ProposalVerifier(sp.GetRequiredService<IOptions<ResearchEngineOptions>>()));
        services.AddSingleton(engine ?? (Engine = new FakeResearchEngine()));
        services.AddSingleton(Metrics);
        services.AddScoped<ITransitionCommitService>(sp => new TransitionCommitService(
            sp.GetRequiredService<TradingDbContext>(), sp.GetRequiredService<IProposalVerifier>(),
            sp.GetRequiredService<IRiskPolicyProvider>(), NullLogger<TransitionCommitService>.Instance));
        services.AddScoped<IDecisionAuditService>(sp => new DecisionAuditService(
            sp.GetRequiredService<TradingDbContext>(), sp.GetRequiredService<IOptions<ResearchEngineOptions>>(),
            NullLogger<DecisionAuditService>.Instance));
        services.AddScoped<IExperimentService>(sp => new ExperimentService(
            sp.GetRequiredService<TradingDbContext>(), sp.GetRequiredService<IRiskPolicyProvider>(),
            NullLogger<ExperimentService>.Instance));
        services.AddScoped<IFixedIncomeCycleRunner>(sp => new FixedIncomeCycleRunner(
            sp.GetRequiredService<TradingDbContext>(), sp.GetRequiredService<IResearchEngineClient>(),
            sp.GetRequiredService<ITransitionCommitService>(), sp.GetRequiredService<IDecisionAuditService>(),
            sp.GetRequiredService<IExperimentService>(), sp.GetRequiredService<IRiskPolicyProvider>(),
            sp.GetRequiredService<IOptions<FixedIncomeOptions>>(), sp.GetRequiredService<IOptions<ResearchEngineOptions>>(),
            sp.GetRequiredService<FixedIncomeMetrics>(), NullLogger<FixedIncomeCycleRunner>.Instance));
        services.AddScoped<IFixedIncomeRunExecutor>(sp => new FixedIncomeRunExecutor(
            sp.GetRequiredService<IServiceScopeFactory>(), sp.GetRequiredService<IOptions<FixedIncomeOptions>>(),
            NullLogger<FixedIncomeRunExecutor>.Instance));
        Provider = services.BuildServiceProvider();
    }

    public FakeResearchEngine? Engine { get; private set; }

    public FakeResearchEngine Fake => Engine ?? throw new InvalidOperationException("Not a fake engine.");

    public FixedIncomeMetrics Metrics { get; } = new();

    public ServiceProvider Provider { get; }

    public TradingDbContext Db() => _database.CreateContext();

    public void Dispose()
    {
        Provider.Dispose();
        Metrics.Dispose();
        _database.Dispose();
    }

    public void AddSessions(params MarketSessionDto[] sessions) => Fake.Sessions.AddRange(sessions);

    public void AddWeek() => AddSessions(Week.Select(d => FakeResearchEngine.Session(d)).ToArray());

    /// <summary>Creates the experiment definition and a queued, then running, run.</summary>
    public async Task<string> StartRunAsync(string runId = "run-app", IEnumerable<string>? strategies = null,
        DateOnly? start = null, DateOnly? end = null, string runType = "replay", bool markRunning = true,
        string universe = FakeResearchEngine.Universe, string dataMode = "synthetic_curve")
    {
        using var scope = Provider.CreateScope();
        var experiments = scope.ServiceProvider.GetRequiredService<IExperimentService>();
        var definition = await experiments.CreateDefinitionAsync(new CreateExperimentDefinitionRequest
        {
            ExperimentId = ExperimentId,
            Version = 1,
            Name = "Application-mode executor test",
            DataMode = dataMode,
            StartDate = start ?? Week[0],
            EndDate = end ?? Week[^1],
            InstrumentUniverseVersion = universe,
            Strategies = (strategies ?? DefaultStrategies).Select(s => new ExperimentStrategyRequest
            {
                StrategyId = s,
                StrategyKind = s == "cash" ? "cash_reference" : s.StartsWith("llm", StringComparison.Ordinal) ? "single_agent" : "quant_policy",
                StrategyConfigId = s + "-config-v1",
            }).ToList(),
        }, "tester");
        Assert.True(definition.Status is ExperimentDefinitionStatus.Created or ExperimentDefinitionStatus.AlreadyExists,
            string.Join("; ", definition.Errors.SelectMany(e => e.Value)));

        var run = await experiments.StartRunAsync(ExperimentId, new StartRunRequest { RunId = runId, RunType = runType }, "tester");
        Assert.Equal(StartRunStatus.Accepted, run.Status);
        if (markRunning)
        {
            Assert.True(await experiments.TryMarkRunningAsync(runId));
        }

        return runId;
    }

    public async Task<RunExecutionResult> ExecuteAsync(string runId, CancellationToken cancellationToken = default)
    {
        using var scope = Provider.CreateScope();
        return await scope.ServiceProvider.GetRequiredService<IFixedIncomeRunExecutor>().ExecuteAsync(runId, cancellationToken);
    }

    public async Task<T> WithRunnerAsync<T>(Func<IFixedIncomeCycleRunner, Task<T>> action)
    {
        using var scope = Provider.CreateScope();
        return await action(scope.ServiceProvider.GetRequiredService<IFixedIncomeCycleRunner>());
    }

    public async Task CancelAsync(string runId)
    {
        using var scope = Provider.CreateScope();
        await scope.ServiceProvider.GetRequiredService<IExperimentService>().CancelRunAsync(runId, "operator");
    }

    /// <summary>Financial footprint used to compare runs (counts and final state hashes).</summary>
    public async Task<RunFootprint> FootprintAsync(string runId)
    {
        await using var db = Db();
        var portfolios = await db.FiPortfolios.AsNoTracking().Where(p => p.RunId == runId).OrderBy(p => p.PortfolioId).ToListAsync();
        var ids = portfolios.Select(p => p.PortfolioId).ToList();
        return new RunFootprint(
            portfolios.ToDictionary(p => p.PortfolioId, p => $"{p.CurrentVersion}:{p.CurrentStateHash}"),
            await db.FiJournals.CountAsync(j => ids.Contains(j.PortfolioId)),
            await db.FiJournalEntries.CountAsync(j => ids.Contains(j.PortfolioId)),
            await db.FiFills.CountAsync(f => ids.Contains(f.PortfolioId)),
            await db.FiSettlements.CountAsync(s => ids.Contains(s.PortfolioId)),
            await db.FiOrderIntents.CountAsync(o => ids.Contains(o.PortfolioId)),
            await db.FiCashFlowEvents.CountAsync(c => ids.Contains(c.PortfolioId)),
            await db.FiValuationSnapshots.CountAsync(v => ids.Contains(v.PortfolioId)),
            await db.FiCommandRecords.CountAsync(c => ids.Contains(c.PortfolioId)),
            await db.FiDecisions.CountAsync(d => d.RunId == runId));
    }

    /// <summary>Every journal is balanced and the ledger of each portfolio balances overall.</summary>
    public async Task AssertJournalsBalanceAsync(string runId)
    {
        await using var db = Db();
        var ids = await db.FiPortfolios.AsNoTracking().Where(p => p.RunId == runId).Select(p => p.PortfolioId).ToListAsync();
        var entries = await db.FiJournalEntries.AsNoTracking().Where(e => ids.Contains(e.PortfolioId)).ToListAsync();
        Assert.NotEmpty(entries);
        foreach (var journal in entries.GroupBy(e => (e.PortfolioId, e.JournalDbId)))
        {
            Assert.Equal(journal.Sum(e => e.DebitUsd), journal.Sum(e => e.CreditUsd));
        }

        foreach (var portfolio in entries.GroupBy(e => e.PortfolioId))
        {
            Assert.Equal(portfolio.Sum(e => e.DebitUsd), portfolio.Sum(e => e.CreditUsd));
        }
    }

    public static string PortfolioId(string runId, string strategyId) => $"pf-{runId}-{strategyId}-r0";
}

public sealed record RunFootprint(
    IReadOnlyDictionary<string, string> States,
    int Journals,
    int JournalEntries,
    int Fills,
    int Settlements,
    int Orders,
    int CashFlows,
    int Valuations,
    int Commands,
    int Decisions)
{
    public bool SameAs(RunFootprint other) =>
        States.Count == other.States.Count && States.All(kv => other.States.TryGetValue(kv.Key, out var v) && v == kv.Value) &&
        (Journals, JournalEntries, Fills, Settlements, Orders, CashFlows, Valuations, Commands, Decisions) ==
        (other.Journals, other.JournalEntries, other.Fills, other.Settlements, other.Orders, other.CashFlows, other.Valuations,
            other.Commands, other.Decisions);
}
