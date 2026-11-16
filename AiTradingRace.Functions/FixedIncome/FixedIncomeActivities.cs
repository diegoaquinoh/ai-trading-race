using System.Globalization;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Domain.Entities.FixedIncome;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.FixedIncome;

/// <summary>
/// Durable activities of the fixed income orchestrations. Thin wrappers over the shared
/// <see cref="IFixedIncomeCycleRunner"/> (Infrastructure), which the Web hosted queue uses
/// too. Each invocation gets its own DI scope (DbContext). Activities may run more than
/// once; deterministic command ids guarantee one committed financial effect.
/// </summary>
public sealed class FixedIncomeActivities
{
    private readonly IFixedIncomeCycleRunner _runner;
    private readonly IExperimentService _experiments;
    private readonly ILogger<FixedIncomeActivities> _logger;

    public FixedIncomeActivities(IFixedIncomeCycleRunner runner, IExperimentService experiments, ILogger<FixedIncomeActivities> logger)
    {
        _runner = runner;
        _experiments = experiments;
        _logger = logger;
    }

    [Function(FiActivityNames.PrepareRun)]
    public async Task<FiRunPlan> PrepareRun([ActivityTrigger] string runId, CancellationToken cancellationToken)
    {
        await MarkRunningAsync(runId, cancellationToken);
        return await _runner.PrepareRunAsync(runId, cancellationToken);
    }

    [Function(FiActivityNames.PreparePaperCycle)]
    public async Task<FiRunPlan> PreparePaperCycle([ActivityTrigger] FiPaperCycleInput input, CancellationToken cancellationToken)
    {
        if (!DateOnly.TryParseExact(input.SessionDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var date))
        {
            return new FiRunPlan
            {
                RunId = input.RunId,
                Status = FiPlanStatus.Failed,
                RunType = FiRunType.Forward,
                Reason = $"Invalid session date '{input.SessionDate}'.",
            };
        }

        await MarkRunningAsync(input.RunId, cancellationToken);
        return await _runner.PreparePaperCycleAsync(input.RunId, date, cancellationToken);
    }

    [Function(FiActivityNames.ExecuteCycle)]
    public Task<FiCycleResult> ExecuteCycle([ActivityTrigger] FiCycleActivityInput input, CancellationToken cancellationToken) =>
        _runner.ExecuteCycleAsync(input.RunId, input.CycleId, cancellationToken);

    [Function(FiActivityNames.FinalizeRun)]
    public async Task<bool> FinalizeRun([ActivityTrigger] FiFinalizeInput input, CancellationToken cancellationToken)
    {
        await _runner.FinalizeRunAsync(input.RunId, new FiRunFinalization
        {
            Succeeded = input.Succeeded,
            Cancelled = input.Cancelled,
            KeepRunning = input.KeepRunning,
            Reason = input.Reason,
        }, cancellationToken);
        return true;
    }

    private async Task MarkRunningAsync(string runId, CancellationToken ct)
    {
        if (await _experiments.GetJobStateAsync(runId, ct) == FiJobState.Queued &&
            await _experiments.TryMarkRunningAsync(runId, ct))
        {
            _logger.LogInformation("Fixed income run {RunId} is now running (Functions host)", runId);
        }
    }
}
