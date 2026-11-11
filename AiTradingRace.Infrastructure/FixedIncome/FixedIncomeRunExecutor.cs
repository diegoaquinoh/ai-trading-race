using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// In-process application-mode executor used by the Web hosted run queue. It sequences
/// <see cref="IFixedIncomeCycleRunner"/> calls with one DI scope (and DbContext) per step,
/// checkpointing after each cycle; a later invocation of the same run resumes after the
/// last checkpoint. Transient research-engine outages are retried a bounded number of
/// times, then the run fails as resumable (deterministic command ids make re-execution safe).
/// </summary>
public sealed class FixedIncomeRunExecutor : IFixedIncomeRunExecutor
{
    private readonly IServiceScopeFactory _scopes;
    private readonly FixedIncomeExecutionOptions _options;
    private readonly TimeProvider _clock;
    private readonly ILogger<FixedIncomeRunExecutor> _logger;

    public FixedIncomeRunExecutor(
        IServiceScopeFactory scopes,
        IOptions<FixedIncomeOptions> options,
        ILogger<FixedIncomeRunExecutor> logger,
        TimeProvider? clock = null)
    {
        _scopes = scopes;
        _options = options.Value.Execution ?? new FixedIncomeExecutionOptions();
        _logger = logger;
        _clock = clock ?? TimeProvider.System;
    }

    public async Task<RunExecutionResult> ExecuteAsync(string runId, CancellationToken cancellationToken)
    {
        using var scope = _logger.BeginScope(new Dictionary<string, object?> { ["RunId"] = runId });

        FiRunPlan plan;
        try
        {
            plan = await WithRetryAsync(runner => runner.PrepareRunAsync(runId, cancellationToken), "prepare", cancellationToken);
        }
        catch (FiTransientDependencyException ex)
        {
            return RunExecutionResult.Failure($"{FiErrorScope.Source}: research engine unavailable while preparing the run " +
                                              $"(resumable; no cycle started): {ex.Message}");
        }

        switch (plan.Status)
        {
            case FiPlanStatus.Cancelled:
                return new RunExecutionResult(false, plan.Reason, Cancelled: true);
            case FiPlanStatus.Failed:
                return RunExecutionResult.Failure(plan.Reason ?? "The run could not be prepared.");
            case FiPlanStatus.NothingToDo:
                return plan.RunType == "forward" && !plan.WindowComplete ? RunExecutionResult.Continue() : RunExecutionResult.Success();
        }

        foreach (var cycleId in plan.PendingCycleIds)
        {
            FiCycleResult result;
            try
            {
                result = await WithRetryAsync(runner => runner.ExecuteCycleAsync(runId, cycleId, cancellationToken), cycleId, cancellationToken);
            }
            catch (FiTransientDependencyException ex)
            {
                return RunExecutionResult.Failure($"{FiErrorScope.Source}: research engine unavailable at {cycleId} " +
                                                  $"(resumable from the last checkpoint): {ex.Message}");
            }

            switch (result.Status)
            {
                case FiCycleRunStatus.Cancelled:
                    return new RunExecutionResult(false, result.Reason, Cancelled: true);
                case FiCycleRunStatus.Failed:
                    return RunExecutionResult.Failure(result.Reason ?? $"Cycle {cycleId} failed.");
            }
        }

        return plan.RunType == "forward" && !plan.WindowComplete ? RunExecutionResult.Continue() : RunExecutionResult.Success();
    }

    private async Task<T> WithRetryAsync<T>(Func<IFixedIncomeCycleRunner, Task<T>> step, string label, CancellationToken ct)
    {
        var retries = Math.Max(0, _options.CycleRetryAttempts);
        for (var attempt = 0; ; attempt++)
        {
            try
            {
                using var stepScope = _scopes.CreateScope();
                var runner = stepScope.ServiceProvider.GetRequiredService<IFixedIncomeCycleRunner>();
                return await step(runner);
            }
            catch (FiTransientDependencyException ex) when (attempt < retries)
            {
                var delay = TimeSpan.FromMilliseconds(Math.Max(0, _options.TransientRetryDelayMs) * Math.Pow(2, attempt + 1));
                _logger.LogWarning("Step {Step} hit a transient dependency failure ({Message}); retrying in {Delay}", label, ex.Message, delay);
                if (delay > TimeSpan.Zero)
                {
                    await Task.Delay(delay, _clock, ct);
                }
            }
        }
    }
}
