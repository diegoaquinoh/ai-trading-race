using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>
/// Operator-triggered administrative work (spec 14.2). Requires Operator/Admin;
/// read-only viewers cannot launch it. Long operations return job status links.
/// </summary>
[ApiController]
[Route("api/v1/admin")]
[Authorize(Policy = "RequireOperator")]
[EnableRateLimiting("per-user")]
public sealed class FiAdminController : FiControllerBase
{
    private readonly IResearchEngineClient _engine;
    private readonly IExperimentService _experiments;
    private readonly IFixedIncomeRunQueue _queue;
    private readonly ITransitionCommitService _commits;

    public FiAdminController(
        IResearchEngineClient engine,
        IExperimentService experiments,
        IFixedIncomeRunQueue queue,
        ITransitionCommitService commits)
    {
        _engine = engine;
        _experiments = experiments;
        _queue = queue;
        _commits = commits;
    }

    /// <summary>Operator-triggered source refresh (runs in the research engine, never inside a decision).</summary>
    [HttpPost("ingestions")]
    public Task<IActionResult> StartIngestion([FromBody] IngestionCommand? command, CancellationToken cancellationToken) =>
        EngineCallAsync(async () =>
        {
            var document = await _engine.StartIngestionAsync(new IngestionRequestDto
            {
                RequestId = "ing-" + Guid.NewGuid().ToString("N")[..20],
                SourceIds = command?.SourceIds ?? new List<string>(),
                Reason = command?.Reason,
                RequestedBy = Actor,
            }, cancellationToken);
            return StatusCode(StatusCodes.Status202Accepted, document.Body);
        });

    /// <summary>Rebuild/validate an index; never mutates an existing manifest.</summary>
    [HttpPost("index-builds")]
    public Task<IActionResult> StartIndexBuild([FromBody] IndexBuildCommand? command, CancellationToken cancellationToken) =>
        EngineCallAsync(async () =>
        {
            var document = await _engine.StartIndexBuildAsync(new IndexBuildRequestDto
            {
                RequestId = "idx-" + Guid.NewGuid().ToString("N")[..20],
                EvidenceSnapshotId = command?.EvidenceSnapshotId,
                BaseIndexBuildId = command?.BaseIndexBuildId,
                ValidateOnly = command?.ValidateOnly ?? false,
                Reason = command?.Reason,
                RequestedBy = Actor,
            }, cancellationToken);
            return StatusCode(StatusCodes.Status202Accepted, document.Body);
        });

    /// <summary>Status of an engine-side administrative job (ingestion, index build).</summary>
    [HttpGet("jobs/{jobId}")]
    public Task<IActionResult> Job(string jobId, CancellationToken cancellationToken) =>
        EngineCallAsync(async () => Ok((await _engine.GetAdminJobAsync(jobId, cancellationToken)).Body));

    /// <summary>Trigger a configured forward (paper) cycle as a queued forward run.</summary>
    [HttpPost("paper-cycles")]
    public async Task<IActionResult> TriggerPaperCycle([FromBody] PaperCycleCommand command, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(command.ExperimentId))
        {
            return FiValidationProblem(StatusCodes.Status422UnprocessableEntity, "Invalid paper-cycle request.",
                new Dictionary<string, string[]> { ["experimentId"] = new[] { "experimentId is required." } });
        }

        var result = await _experiments.StartRunAsync(command.ExperimentId, new StartRunRequest
        {
            RunId = command.RunId,
            ExperimentVersion = command.ExperimentVersion,
            RunType = "forward",
            ResponseMode = command.ResponseMode ?? "recorded_replay",
        }, Actor, cancellationToken);

        switch (result.Status)
        {
            case StartRunStatus.Accepted:
                await _queue.TryEnqueueAsync(result.RunId!, cancellationToken);
                goto case StartRunStatus.AlreadyExists;
            case StartRunStatus.AlreadyExists:
                var statusUrl = $"/api/v1/runs/{Uri.EscapeDataString(result.RunId!)}";
                return Accepted(statusUrl, new RunAcceptedResponse(result.RunId!, result.JobState ?? "queued", statusUrl,
                    result.Status == StartRunStatus.AlreadyExists));
            case StartRunStatus.NotFound:
                return NotFoundProblem($"Experiment '{command.ExperimentId}'");
            case StartRunStatus.Conflict:
                return FiProblem(StatusCodes.Status409Conflict, "idempotency_mismatch", "Run id already used with different parameters.", result.Message);
            default:
                return FiValidationProblem(StatusCodes.Status422UnprocessableEntity, result.Message ?? "Invalid paper-cycle request.", result.Errors);
        }
    }

    /// <summary>Operator action clearing a reconciliation block (Admin only).</summary>
    [HttpPost("portfolios/{portfolioId}/unblock")]
    [Authorize(Policy = "RequireAdmin")]
    public async Task<IActionResult> Unblock(string portfolioId, [FromBody] UnblockCommand command, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(command.Reason))
        {
            return FiValidationProblem(StatusCodes.Status422UnprocessableEntity, "A reason is required.",
                new Dictionary<string, string[]> { ["reason"] = new[] { "Explain the operator investigation." } });
        }

        return await _commits.UnblockAsync(portfolioId, Actor, command.Reason, cancellationToken)
            ? Ok(new { portfolioId, blocked = false })
            : NotFoundProblem($"Portfolio '{portfolioId}'");
    }
}

public sealed record IngestionCommand(List<string>? SourceIds, string? Reason);

public sealed record IndexBuildCommand(string? EvidenceSnapshotId, string? BaseIndexBuildId, bool ValidateOnly, string? Reason);

public sealed record PaperCycleCommand(string ExperimentId, int? ExperimentVersion, string? RunId, string? ResponseMode);

public sealed record UnblockCommand(string Reason);
