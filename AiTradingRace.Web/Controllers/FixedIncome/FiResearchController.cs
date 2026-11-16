using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>
/// Research-engine proxies: instruments, curves, evidence bundles and informational
/// research notes (spec 14.2). Research notes carry no order authority.
/// </summary>
[ApiController]
[Route("api/v1")]
[EnableRateLimiting("per-user")]
public sealed class FiResearchController : FiControllerBase
{
    private readonly IResearchEngineClient _engine;

    public FiResearchController(IResearchEngineClient engine)
    {
        _engine = engine;
    }

    /// <summary>Admitted securities and term versions.</summary>
    [HttpGet("instruments")]
    public Task<IActionResult> Instruments(
        [FromQuery] string? asOf,
        [FromQuery] string? universeVersion,
        [FromQuery] string? securityId,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        CancellationToken cancellationToken = default) =>
        EngineCallAsync(async () =>
        {
            var (p, s) = Application.FixedIncome.Models.PagedResult<object>.Normalize(page, pageSize);
            var document = await _engine.GetInstrumentsAsync(new InstrumentQuery(asOf, universeVersion, securityId, p, s), cancellationToken);
            return Ok(document.Body);
        });

    /// <summary>Curve inputs, specification, diagnostics and nodes.</summary>
    [HttpGet("curves/{snapshotId}")]
    public Task<IActionResult> Curve(string snapshotId, CancellationToken cancellationToken) =>
        EngineCallAsync(async () => Ok((await _engine.GetCurveAsync(snapshotId, cancellationToken)).Body));

    /// <summary>Delivered passages and graph provenance (permission-scoped, paginated).</summary>
    [HttpGet("evidence/{bundleId}")]
    [Authorize(Policy = "RequireUser")]
    public Task<IActionResult> Evidence(string bundleId, [FromQuery] int page = 1, [FromQuery] int pageSize = 50,
        CancellationToken cancellationToken = default) =>
        EngineCallAsync(async () =>
        {
            var (p, s) = Application.FixedIncome.Models.PagedResult<object>.Normalize(page, pageSize);
            return Ok((await _engine.GetEvidenceBundleAsync(bundleId, new PageQuery(p, s), cancellationToken)).Body);
        });

    /// <summary>Exact source passage of one evidence chunk (citation drill-down, spec 17.4).</summary>
    [HttpGet("evidence/chunks/{chunkId}")]
    [Authorize(Policy = "RequireUser")]
    public Task<IActionResult> EvidenceChunk(string chunkId, CancellationToken cancellationToken) =>
        EngineCallAsync(async () => Ok((await _engine.GetEvidenceChunkAsync(chunkId, cancellationToken)).Body));

    /// <summary>Bounded graph view (relevant nodes/edges with supporting assertions) of an evidence bundle.</summary>
    [HttpGet("evidence/{bundleId}/graph")]
    [Authorize(Policy = "RequireUser")]
    public Task<IActionResult> EvidenceGraph(string bundleId, CancellationToken cancellationToken) =>
        EngineCallAsync(async () => Ok((await _engine.GetEvidenceGraphAsync(bundleId, cancellationToken)).Body));

    /// <summary>Model/observed values, accrued, cash flows and risk of one instrument on a date (computed by the engine).</summary>
    [HttpGet("instruments/{securityId}/valuation")]
    public Task<IActionResult> InstrumentValuation(string securityId, [FromQuery] string? date, CancellationToken cancellationToken)
    {
        DateOnly? parsed = null;
        if (!string.IsNullOrEmpty(date))
        {
            if (!DateOnly.TryParseExact(date, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture,
                    System.Globalization.DateTimeStyles.None, out var value))
            {
                return Task.FromResult<IActionResult>(FiValidationProblem(StatusCodes.Status422UnprocessableEntity, "Invalid date.",
                    new Dictionary<string, string[]> { ["date"] = new[] { "date must be YYYY-MM-DD." } }));
            }

            parsed = value;
        }

        return EngineCallAsync(async () =>
            Ok((await _engine.GetInstrumentValuationAsync(securityId, parsed, cancellationToken)).Body));
    }

    /// <summary>Start an informational research query. The response never carries order authority.</summary>
    [HttpPost("research-notes")]
    [Authorize(Policy = "RequireUser")]
    public Task<IActionResult> ResearchNote([FromBody] ResearchNoteQuery query, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(query.Question) || query.Question.Length > 4000)
        {
            return Task.FromResult<IActionResult>(FiValidationProblem(StatusCodes.Status422UnprocessableEntity, "Invalid research query.",
                new Dictionary<string, string[]> { ["question"] = new[] { "question is required (at most 4000 characters)." } }));
        }

        if (query.ResponseMode is not ("recorded_replay" or "fresh_inference"))
        {
            return Task.FromResult<IActionResult>(FiValidationProblem(StatusCodes.Status422UnprocessableEntity, "Invalid research query.",
                new Dictionary<string, string[]> { ["responseMode"] = new[] { "responseMode must be 'recorded_replay' or 'fresh_inference'." } }));
        }

        return EngineCallAsync(async () =>
        {
            var document = await _engine.CreateResearchNoteAsync(new ResearchNoteRequestDto
            {
                RequestId = "rn-" + Guid.NewGuid().ToString("N")[..20],
                Question = query.Question,
                AsOf = query.AsOf,
                EvidenceSnapshotId = query.EvidenceSnapshotId,
                IndexBuildId = query.IndexBuildId,
                RetrievalMode = query.RetrievalMode ?? "hybrid_rag_v1",
                ResponseMode = query.ResponseMode,
                RequestedBy = Actor,
            }, cancellationToken);

            return StatusCode(document.StatusCode == StatusCodes.Status202Accepted ? 202 : 200,
                new ResearchNoteResponse(OrderAuthority: false, Note: document.Body));
        });
    }
}

public sealed record ResearchNoteQuery
{
    public string Question { get; init; } = string.Empty;
    public string? AsOf { get; init; }
    public string? EvidenceSnapshotId { get; init; }
    public string? IndexBuildId { get; init; }
    public string? RetrievalMode { get; init; }
    public string ResponseMode { get; init; } = "recorded_replay";
}

/// <summary>Research note envelope. <see cref="OrderAuthority"/> is always false.</summary>
public sealed record ResearchNoteResponse(bool OrderAuthority, System.Text.Json.Nodes.JsonNode? Note);
