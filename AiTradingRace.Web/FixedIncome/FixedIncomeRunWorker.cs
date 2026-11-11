using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Web.FixedIncome;

/// <summary>
/// Background worker: marks runs queued → running, invokes the configured
/// <see cref="IFixedIncomeRunExecutor"/> and records completed/failed. Job states are
/// separate from strategy outcomes (spec 15.2).
/// </summary>
public sealed class FixedIncomeRunWorker : BackgroundService
{
    private readonly FixedIncomeRunQueue _queue;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<FixedIncomeRunWorker> _logger;
    private readonly FixedIncomeExecutionOptions _execution;

    public FixedIncomeRunWorker(
        FixedIncomeRunQueue queue,
        IServiceScopeFactory scopeFactory,
        ILogger<FixedIncomeRunWorker> logger,
        IOptions<FixedIncomeOptions>? options = null)
    {
        _queue = queue;
        _scopeFactory = scopeFactory;
        _logger = logger;
        _execution = options?.Value.Execution ?? new FixedIncomeExecutionOptions();
    }

    /// <summary>False when runs are executed by the Functions durable orchestration instead.</summary>
    private bool ExecutesRuns =>
        !string.Equals(_execution.RunExecutionHost, FixedIncomeExecutionOptions.FunctionsHost, StringComparison.OrdinalIgnoreCase);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!ExecutesRuns)
        {
            _logger.LogInformation("Fixed income runs are executed by Azure Functions (FixedIncome:Execution:RunExecutionHost=functions)");
            return;
        }

        await RecoverQueuedRunsAsync(stoppingToken);

        try
        {
            await foreach (var runId in _queue.Reader.ReadAllAsync(stoppingToken))
            {
                await ProcessAsync(runId, stoppingToken);
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            // Host shutdown.
        }
    }

    /// <summary>Executes one run id (public for tests).</summary>
    public async Task ProcessAsync(string runId, CancellationToken cancellationToken)
    {
        using var scope = _scopeFactory.CreateScope();
        var experiments = scope.ServiceProvider.GetRequiredService<IExperimentService>();

        if (!await experiments.TryMarkRunningAsync(runId, cancellationToken))
        {
            _logger.LogInformation("Run {RunId} is no longer queued; skipping", runId);
            return;
        }

        var executor = scope.ServiceProvider.GetRequiredService<IFixedIncomeRunExecutor>();
        try
        {
            var result = await executor.ExecuteAsync(runId, cancellationToken);
            if (result.Succeeded && result.Continuing)
            {
                _logger.LogInformation("Forward run {RunId} processed its due sessions and stays running", runId);
            }
            else if (result.Succeeded)
            {
                await experiments.MarkCompletedAsync(runId, CancellationToken.None);
            }
            else if (!result.Cancelled)
            {
                await experiments.MarkFailedAsync(runId, result.FailureReason ?? "Run failed without a reason.", CancellationToken.None);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Committed events remain authoritative; the run resumes after its last checkpoint on restart.
            if (!await experiments.TryRequeueAsync(runId,
                    "Interrupted by host shutdown; will resume from the last completed cycle checkpoint.", CancellationToken.None))
            {
                await experiments.MarkFailedAsync(runId, "Interrupted by host shutdown; committed events remain authoritative.", CancellationToken.None);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Fixed income run {RunId} failed", runId);
            await experiments.MarkFailedAsync(runId, $"Executor error: {ex.Message}", CancellationToken.None);
        }
    }

    private async Task RecoverQueuedRunsAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var scope = _scopeFactory.CreateScope();
            var experiments = scope.ServiceProvider.GetRequiredService<IExperimentService>();

            // Single in-process worker: a run still "running" at startup was interrupted by a crash.
            await experiments.RequeueOrphanedRunsAsync(cancellationToken);
            foreach (var runId in await experiments.ListQueuedRunIdsAsync(cancellationToken))
            {
                await _queue.TryEnqueueAsync(runId, cancellationToken);
            }
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            _logger.LogWarning(ex, "Could not recover queued fixed income runs at startup");
        }
    }
}
