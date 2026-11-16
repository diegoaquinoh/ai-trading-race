using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>Experiment definitions (immutable versions) and run launch (spec 14.2).</summary>
[ApiController]
[Route("api/v1/experiments")]
[EnableRateLimiting("per-user")]
public sealed class FiExperimentsController : FiControllerBase
{
    private readonly IExperimentService _experiments;
    private readonly IFixedIncomeQueryService _queries;
    private readonly IFixedIncomeRunQueue _queue;
    private readonly ILogger<FiExperimentsController> _logger;

    public FiExperimentsController(
        IExperimentService experiments,
        IFixedIncomeQueryService queries,
        IFixedIncomeRunQueue queue,
        ILogger<FiExperimentsController> logger)
    {
        _experiments = experiments;
        _queries = queries;
        _queue = queue;
        _logger = logger;
    }

    /// <summary>Validate and persist an immutable experiment definition.</summary>
    /// <response code="201">Created.</response>
    /// <response code="200">Identical definition already exists (idempotent).</response>
    /// <response code="409">Same id and version with different content.</response>
    /// <response code="422">Invalid definition.</response>
    [HttpPost]
    [Authorize(Policy = "RequireOperator")]
    public async Task<IActionResult> Create([FromBody] CreateExperimentDefinitionRequest request, CancellationToken cancellationToken)
    {
        var result = await _experiments.CreateDefinitionAsync(request, Actor, cancellationToken);
        return result.Status switch
        {
            ExperimentDefinitionStatus.Created => Created(
                $"/api/v1/experiments/{Uri.EscapeDataString(result.Definition!.ExperimentId)}?version={result.Definition.Version}",
                result.Definition),
            ExperimentDefinitionStatus.AlreadyExists => Ok(result.Definition),
            ExperimentDefinitionStatus.Conflict => FiProblem(StatusCodes.Status409Conflict, "immutable_definition_conflict",
                "Experiment definition already exists with different content.", result.Message,
                new Dictionary<string, object?> { ["existingDefinitionHash"] = result.Definition?.DefinitionHash }),
            _ => FiValidationProblem(StatusCodes.Status422UnprocessableEntity, result.Message ?? "Invalid experiment definition.", result.Errors),
        };
    }

    [HttpGet]
    public async Task<IActionResult> List([FromQuery] int page = 1, [FromQuery] int pageSize = 50, CancellationToken cancellationToken = default) =>
        Ok(await _experiments.ListDefinitionsAsync(page, pageSize, cancellationToken));

    [HttpGet("{experimentId}")]
    public async Task<IActionResult> Get(string experimentId, [FromQuery] int? version, CancellationToken cancellationToken)
    {
        var definition = await _experiments.GetDefinitionAsync(experimentId, version, cancellationToken);
        return definition is null ? NotFoundProblem($"Experiment '{experimentId}'") : Ok(definition);
    }

    /// <summary>Comparison of all runs, grouped by compatible data mode / policy / execution model.</summary>
    [HttpGet("{experimentId}/comparison")]
    public async Task<IActionResult> Comparison(string experimentId, CancellationToken cancellationToken)
    {
        var comparison = await _queries.GetExperimentComparisonAsync(experimentId, cancellationToken);
        return comparison is null ? NotFoundProblem($"Experiment '{experimentId}'") : Ok(comparison);
    }

    /// <summary>Start a run; returns 202 with the job id and a status link.</summary>
    [HttpPost("{experimentId}/runs")]
    [Authorize(Policy = "RequireOperator")]
    public async Task<IActionResult> StartRun(string experimentId, [FromBody] StartRunRequest? request, CancellationToken cancellationToken)
    {
        var result = await _experiments.StartRunAsync(experimentId, request ?? new StartRunRequest(), Actor, cancellationToken);
        switch (result.Status)
        {
            case StartRunStatus.Accepted:
            case StartRunStatus.AlreadyExists:
                if (result.Status == StartRunStatus.Accepted && !await _queue.TryEnqueueAsync(result.RunId!, cancellationToken))
                {
                    _logger.LogWarning("Run queue full; run {RunId} stays queued and will be picked up later", result.RunId);
                }

                return RunAccepted(result);
            case StartRunStatus.NotFound:
                return NotFoundProblem($"Experiment '{experimentId}'");
            case StartRunStatus.Conflict:
                return FiProblem(StatusCodes.Status409Conflict, "idempotency_mismatch",
                    "Run id already used with different parameters.", result.Message);
            default:
                return FiValidationProblem(StatusCodes.Status422UnprocessableEntity, result.Message ?? "Invalid run request.", result.Errors);
        }
    }

    internal AcceptedResult RunAccepted(StartRunResult result)
    {
        var statusUrl = $"/api/v1/runs/{Uri.EscapeDataString(result.RunId!)}";
        return Accepted(statusUrl, new RunAcceptedResponse(result.RunId!, result.JobState ?? "queued", statusUrl,
            result.Status == StartRunStatus.AlreadyExists));
    }
}

/// <summary>202 body for run launch.</summary>
public sealed record RunAcceptedResponse(string RunId, string JobState, string StatusUrl, bool AlreadyExisted);
