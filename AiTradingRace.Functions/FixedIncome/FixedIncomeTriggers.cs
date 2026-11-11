using System.Net;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Functions.FixedIncome;

/// <summary>Deterministic durable instance ids (one replay instance per run, one per paper session).</summary>
public static class FixedIncomeInstanceIds
{
    public static string Run(string runId) => "fi-run-" + runId;

    public static string PaperCycle(string runId, DateOnly sessionDate) =>
        $"fi-paper-{runId}-{sessionDate:yyyy-MM-dd}";
}

/// <summary>
/// HTTP starter for the durable replay of a queued run (used when
/// <c>FixedIncome:Execution:RunExecutionHost=functions</c>; the Web hosted queue is the default).
/// Re-posting for a run whose instance is still active returns the existing instance;
/// posting after a failed instance resumes the run from its last checkpoint.
/// </summary>
public sealed class FixedIncomeRunStarter
{
    private readonly IExperimentService _experiments;
    private readonly ILogger<FixedIncomeRunStarter> _logger;

    public FixedIncomeRunStarter(IExperimentService experiments, ILogger<FixedIncomeRunStarter> logger)
    {
        _experiments = experiments;
        _logger = logger;
    }

    [Function("FixedIncomeRunStarter")]
    public async Task<HttpResponseData> Start(
        [HttpTrigger(AuthorizationLevel.Function, "post", Route = "fi/runs/{runId}/start")] HttpRequestData req,
        string runId,
        [DurableClient] DurableTaskClient client,
        CancellationToken cancellationToken)
    {
        var state = await _experiments.GetJobStateAsync(runId, cancellationToken);
        if (state is null)
        {
            return await Json(req, HttpStatusCode.NotFound, new { runId, error = "run_not_found" });
        }

        if (FiJobState.IsTerminal(state))
        {
            return await Json(req, HttpStatusCode.Conflict, new { runId, jobState = state, error = "run_terminal" });
        }

        var instanceId = FixedIncomeInstanceIds.Run(runId);
        var existing = await client.GetInstanceAsync(instanceId, cancellationToken);
        if (existing is { RuntimeStatus: OrchestrationRuntimeStatus.Running or OrchestrationRuntimeStatus.Pending or OrchestrationRuntimeStatus.Suspended })
        {
            return await Json(req, HttpStatusCode.Accepted, new { runId, instanceId, alreadyRunning = true });
        }

        await client.ScheduleNewOrchestrationInstanceAsync(nameof(FixedIncomeReplayOrchestrator), new FiReplayInput(runId),
            new StartOrchestrationOptions { InstanceId = instanceId }, cancellationToken);
        _logger.LogInformation("Scheduled fixed income replay {InstanceId} for run {RunId}", instanceId, runId);
        return await Json(req, HttpStatusCode.Accepted, new { runId, instanceId, alreadyRunning = false });
    }

    private static async Task<HttpResponseData> Json(HttpRequestData req, HttpStatusCode status, object body)
    {
        var response = req.CreateResponse();
        await response.WriteAsJsonAsync(body);
        response.StatusCode = status;
        return response;
    }
}

/// <summary>Pure trigger decision for the paper-cycle timer (unit-testable without the Functions host).</summary>
public static class PaperCycleTriggerPlanner
{
    public sealed record Decision(bool Trigger, DateOnly SessionDate, string? InstanceId, string Reason);

    public static Decision Plan(DateTimeOffset utcNow, PaperTradingOptions options)
    {
        if (!options.Enabled || string.IsNullOrWhiteSpace(options.ExperimentId) || string.IsNullOrWhiteSpace(options.RunId))
        {
            return new Decision(false, default, null, "paper trading is not configured");
        }

        var zone = FiMarketClock.Resolve(options.TimeZoneId);
        if (!PaperCycleSchedule.ShouldTrigger(utcNow, options.DecisionHour, zone, out var sessionDate))
        {
            return new Decision(false, sessionDate, null,
                $"not the {options.DecisionHour:00}:00 {options.TimeZoneId} decision hour of a weekday");
        }

        return new Decision(true, sessionDate, FixedIncomeInstanceIds.PaperCycle(options.RunId!, sessionDate), "due");
    }
}

/// <summary>
/// Forward paper cycle at 19:00 America/New_York on supported business days (spec 6.4).
/// Time-zone approach: the timer fires hourly in UTC (NCRONTAB <c>0 0 * * * *</c>) and
/// <see cref="PaperCycleSchedule"/> converts to New York local time with the IANA database,
/// so it follows daylight-saving changes without WEBSITE_TIME_ZONE (unsupported on Linux
/// plans). Exchange holidays and incomplete inputs are resolved by the engine's session
/// list: no session ⇒ no cycle; stale inputs ⇒ a skipped cycle with skip decisions.
/// The durable instance id is deterministic per session, so a repeated trigger is a no-op.
/// </summary>
public sealed class FixedIncomePaperCycleTimer
{
    private readonly IExperimentService _experiments;
    private readonly PaperTradingOptions _options;
    private readonly TimeProvider _clock;
    private readonly ILogger<FixedIncomePaperCycleTimer> _logger;

    public FixedIncomePaperCycleTimer(
        IExperimentService experiments,
        IOptions<FixedIncomeOptions> options,
        TimeProvider clock,
        ILogger<FixedIncomePaperCycleTimer> logger)
    {
        _experiments = experiments;
        _options = options.Value.PaperTrading ?? new PaperTradingOptions();
        _clock = clock;
        _logger = logger;
    }

    [Function(nameof(FixedIncomePaperCycleTimer))]
    public async Task Run(
        [TimerTrigger("0 0 * * * *")] TimerInfo timer,
        [DurableClient] DurableTaskClient client,
        CancellationToken cancellationToken)
    {
        var decision = PaperCycleTriggerPlanner.Plan(_clock.GetUtcNow(), _options);
        if (!decision.Trigger)
        {
            _logger.LogDebug("Paper cycle not triggered: {Reason}", decision.Reason);
            return;
        }

        var runId = _options.RunId!;
        var start = await _experiments.StartRunAsync(_options.ExperimentId!, new StartRunRequest
        {
            RunId = runId,
            ExperimentVersion = _options.ExperimentVersion,
            RunType = FiRunType.Forward,
            ResponseMode = _options.ResponseMode,
        }, "paper-cycle-timer", cancellationToken);
        if (start.Status is not (StartRunStatus.Accepted or StartRunStatus.AlreadyExists))
        {
            _logger.LogError("Paper cycle skipped: forward run {RunId} cannot be started ({Status}: {Message})",
                runId, start.Status, start.Message);
            return;
        }

        if (start.JobState is { } jobState && FiJobState.IsTerminal(jobState))
        {
            _logger.LogInformation("Paper cycle skipped: forward run {RunId} is {JobState}", runId, jobState);
            return;
        }

        var existing = await client.GetInstanceAsync(decision.InstanceId!, cancellationToken);
        if (existing is not null)
        {
            _logger.LogInformation("Paper cycle {InstanceId} already scheduled ({Status})", decision.InstanceId, existing.RuntimeStatus);
            return;
        }

        await client.ScheduleNewOrchestrationInstanceAsync(nameof(FixedIncomePaperCycleOrchestrator),
            new FiPaperCycleInput(runId, decision.SessionDate.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture)),
            new StartOrchestrationOptions { InstanceId = decision.InstanceId }, cancellationToken);
        _logger.LogInformation("Scheduled paper cycle {InstanceId} for forward run {RunId}", decision.InstanceId, runId);
    }
}
