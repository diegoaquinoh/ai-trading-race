using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Domain.Entities.FixedIncome;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>Run status, cycles, decisions and comparison (spec 14.2, 17.1, 17.5).</summary>
[ApiController]
[Route("api/v1/runs")]
[EnableRateLimiting("per-user")]
public sealed class FiRunsController : FiControllerBase
{
    private readonly IFixedIncomeQueryService _queries;
    private readonly IExperimentService _experiments;

    public FiRunsController(IFixedIncomeQueryService queries, IExperimentService experiments)
    {
        _queries = queries;
        _experiments = experiments;
    }

    [HttpGet]
    public async Task<IActionResult> List(
        [FromQuery] string? experimentId,
        [FromQuery] string? jobState,
        [FromQuery] string? dataMode,
        [FromQuery] string? runType,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        CancellationToken cancellationToken = default)
    {
        var errors = new Dictionary<string, string[]>();
        if (jobState is not null && !FiJobState.All.Contains(jobState))
        {
            errors["jobState"] = new[] { $"jobState must be one of: {string.Join(", ", FiJobState.All)}." };
        }

        if (dataMode is not null && !FiDataMode.All.Contains(dataMode))
        {
            errors["dataMode"] = new[] { $"dataMode must be one of: {string.Join(", ", FiDataMode.All)}." };
        }

        if (runType is not null && !FiRunType.All.Contains(runType))
        {
            errors["runType"] = new[] { "runType must be 'replay' or 'forward'." };
        }

        if (errors.Count > 0)
        {
            return FiValidationProblem(StatusCodes.Status400BadRequest, "Invalid filter.", errors);
        }

        return Ok(await _queries.ListRunsAsync(new RunListFilter(experimentId, jobState, dataMode, runType, page, pageSize), cancellationToken));
    }

    /// <summary>Manifest, progress, outcomes and data-mode labels.</summary>
    [HttpGet("{runId}")]
    public async Task<IActionResult> Get(string runId, CancellationToken cancellationToken)
    {
        var run = await _queries.GetRunAsync(runId, cancellationToken);
        return run is null ? NotFoundProblem($"Run '{runId}'") : Ok(run);
    }

    [HttpGet("{runId}/comparison")]
    public async Task<IActionResult> Comparison(string runId, CancellationToken cancellationToken)
    {
        var comparison = await _queries.GetRunComparisonAsync(runId, cancellationToken);
        return comparison is null ? NotFoundProblem($"Run '{runId}'") : Ok(comparison);
    }

    [HttpGet("{runId}/cycles")]
    public async Task<IActionResult> Cycles(string runId, [FromQuery] int page = 1, [FromQuery] int pageSize = 50,
        CancellationToken cancellationToken = default)
    {
        var cycles = await _queries.GetRunCyclesAsync(runId, page, pageSize, cancellationToken);
        return cycles is null ? NotFoundProblem($"Run '{runId}'") : Ok(cycles);
    }

    [HttpGet("{runId}/decisions")]
    public async Task<IActionResult> Decisions(
        string runId,
        [FromQuery] string? cycleId,
        [FromQuery] string? strategyId,
        [FromQuery] string? outcome,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        CancellationToken cancellationToken = default)
    {
        if (outcome is not null && !FiDecisionOutcome.All.Contains(outcome))
        {
            return FiValidationProblem(StatusCodes.Status400BadRequest, "Invalid filter.",
                new Dictionary<string, string[]> { ["outcome"] = new[] { "Unknown decision outcome." } });
        }

        var decisions = await _queries.ListRunDecisionsAsync(runId,
            new DecisionListFilter(cycleId, strategyId, outcome, page, pageSize), cancellationToken);
        return decisions is null ? NotFoundProblem($"Run '{runId}'") : Ok(decisions);
    }

    /// <summary>Cancel uncommitted work; committed events remain authoritative.</summary>
    [HttpPost("{runId}/cancel")]
    [Authorize(Policy = "RequireOperator")]
    public async Task<IActionResult> Cancel(string runId, CancellationToken cancellationToken)
    {
        var result = await _experiments.CancelRunAsync(runId, Actor, cancellationToken);
        return result.Status switch
        {
            RunStateChangeStatus.Changed => Ok(new { runId, jobState = result.JobState }),
            RunStateChangeStatus.NotFound => NotFoundProblem($"Run '{runId}'"),
            _ => FiProblem(StatusCodes.Status409Conflict, "invalid_job_transition", "The run cannot be cancelled.", result.Message),
        };
    }
}
