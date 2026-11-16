using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.FixedIncome;
using AiTradingRace.Web.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

public sealed class FixedIncomeRunWorkerTests : IDisposable
{
    private readonly FiSqliteDatabase _database = new();

    public void Dispose() => _database.Dispose();

    private ServiceProvider Provider(IFixedIncomeRunExecutor? executor = null)
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddScoped(_ => _database.CreateContext());
        services.AddSingleton(Fi.Policies());
        services.AddScoped<IExperimentService>(sp => new ExperimentService(
            sp.GetRequiredService<TradingDbContext>(), sp.GetRequiredService<IRiskPolicyProvider>(),
            NullLogger<ExperimentService>.Instance));
        if (executor is null)
        {
            services.AddScoped<IFixedIncomeRunExecutor, NotConfiguredRunExecutor>();
        }
        else
        {
            services.AddSingleton(executor);
        }

        return services.BuildServiceProvider();
    }

    private async Task QueueRunAsync(ServiceProvider provider, string runId)
    {
        using var scope = provider.CreateScope();
        var experiments = scope.ServiceProvider.GetRequiredService<IExperimentService>();
        await experiments.CreateDefinitionAsync(ExperimentServiceTests.Definition(), null);
        await experiments.StartRunAsync("exp-demo", new StartRunRequest { RunId = runId }, null);
    }

    private static FixedIncomeRunWorker Worker(ServiceProvider provider) => new(
        new FixedIncomeRunQueue(Options.Create(new FixedIncomeOptions())),
        provider.GetRequiredService<IServiceScopeFactory>(),
        NullLogger<FixedIncomeRunWorker>.Instance);

    [Fact]
    public async Task StubExecutor_FailsRunWithExplicitReason()
    {
        await using var provider = Provider();
        await QueueRunAsync(provider, "run-w1");

        await Worker(provider).ProcessAsync("run-w1", CancellationToken.None);

        await using var db = _database.CreateContext();
        var run = await db.FiExperimentRuns.SingleAsync();
        Assert.Equal(FiJobState.Failed, run.JobState);
        Assert.StartsWith("executor not configured", run.StatusReason);
        Assert.NotNull(run.StartedAt);
        Assert.NotNull(run.CompletedAt);
        Assert.Equal(0, (await db.FiPortfolios.FirstAsync()).CurrentVersion);
    }

    [Fact]
    public async Task SuccessfulExecutor_CompletesRun_AndNonQueuedRunsAreSkipped()
    {
        var executor = new CountingExecutor();
        await using var provider = Provider(executor);
        await QueueRunAsync(provider, "run-w2");
        var worker = Worker(provider);

        await worker.ProcessAsync("run-w2", CancellationToken.None);
        await worker.ProcessAsync("run-w2", CancellationToken.None);

        await using var db = _database.CreateContext();
        Assert.Equal(FiJobState.Completed, (await db.FiExperimentRuns.SingleAsync()).JobState);
        Assert.Equal(1, executor.Calls);
    }

    [Fact]
    public async Task Queue_IsBoundedAndReportsFullness()
    {
        var queue = new FixedIncomeRunQueue(Options.Create(new FixedIncomeOptions { RunQueueCapacity = 1 }));

        Assert.True(await queue.TryEnqueueAsync("run-1"));
        Assert.False(await queue.TryEnqueueAsync("run-2"));
        Assert.True(queue.Reader.TryRead(out var first));
        Assert.Equal("run-1", first);
    }

    [Fact]
    public async Task FailedRun_IsMarkedFailed_EvenWhenAnotherScopeUpdatedTheRunRow()
    {
        // Regression: the cycle runner writes run errors/progress from its own scope, which
        // rotates the run's concurrency stamp. The worker's context still tracked the copy it
        // loaded when marking the run running; the terminal update must not be lost.
        var executor = new ConcurrentlyUpdatingFailingExecutor(_database);
        await using var provider = Provider(executor);
        await QueueRunAsync(provider, "run-w-stale");

        await Worker(provider).ProcessAsync("run-w-stale", CancellationToken.None);

        await using var db = _database.CreateContext();
        var run = await db.FiExperimentRuns.SingleAsync(r => r.RunId == "run-w-stale");
        Assert.Equal(FiJobState.Failed, run.JobState);
        Assert.Equal("source: sessions_invalid", run.StatusReason);
        Assert.NotNull(run.CompletedAt);
    }

    private sealed class ConcurrentlyUpdatingFailingExecutor(FiSqliteDatabase database) : IFixedIncomeRunExecutor
    {
        public async Task<RunExecutionResult> ExecuteAsync(string runId, CancellationToken cancellationToken)
        {
            await using var other = database.CreateContext();
            var run = await other.FiExperimentRuns.SingleAsync(r => r.RunId == runId, cancellationToken);
            run.StatusReason = "error recorded by the cycle runner";
            run.ConcurrencyStamp = Guid.NewGuid();
            await other.SaveChangesAsync(cancellationToken);
            return RunExecutionResult.Failure("source: sessions_invalid");
        }
    }

    private sealed class CountingExecutor : IFixedIncomeRunExecutor
    {
        public int Calls { get; private set; }

        public Task<RunExecutionResult> ExecuteAsync(string runId, CancellationToken cancellationToken)
        {
            Calls++;
            return Task.FromResult(RunExecutionResult.Success());
        }
    }
}
