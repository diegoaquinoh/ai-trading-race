using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>
/// Dependency readiness for the fixed income dashboard (spec 17.5, 18.3): database,
/// research engine capabilities (engine version, allowlist, last ingestion and
/// manifest info as reported by the engine) and run queue counts.
/// </summary>
[ApiController]
[Route("api/v1/health/fixed-income")]
public sealed class FiHealthController : FiControllerBase
{
    private readonly IResearchEngineClient _engine;
    private readonly IFixedIncomeQueryService _queries;
    private readonly ResearchEngineOptions _engineOptions;

    public FiHealthController(IResearchEngineClient engine, IFixedIncomeQueryService queries, IOptions<ResearchEngineOptions> engineOptions)
    {
        _engine = engine;
        _queries = queries;
        _engineOptions = engineOptions.Value;
    }

    [HttpGet]
    public async Task<IActionResult> Get(CancellationToken cancellationToken)
    {
        DatabaseHealth database;
        try
        {
            var queued = await _queries.ListRunsAsync(new RunListFilter(JobState: FiJobState.Queued, PageSize: 1), cancellationToken);
            var running = await _queries.ListRunsAsync(new RunListFilter(JobState: FiJobState.Running, PageSize: 1), cancellationToken);
            database = new DatabaseHealth(true, null, queued.TotalCount, running.TotalCount);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            database = new DatabaseHealth(false, ex.Message, 0, 0);
        }

        EngineHealth engine;
        try
        {
            var capabilities = await _engine.GetCapabilitiesAsync(cancellationToken);
            engine = new EngineHealth(
                Reachable: true,
                Ready: capabilities.Ready,
                EngineVersion: capabilities.EngineVersion,
                EngineVersionAllowed: _engineOptions.IsEngineVersionAllowed(capabilities.EngineVersion),
                SchemaVersions: capabilities.SchemaVersions,
                Capabilities: capabilities.Raw,
                Error: null);
        }
        catch (ResearchEngineException ex)
        {
            engine = new EngineHealth(false, false, null, false, Array.Empty<string>(), null, ex.Message);
        }

        var status = !database.Ready
            ? "unavailable"
            : engine is { Reachable: true, Ready: true, EngineVersionAllowed: true } ? "ready" : "degraded";

        var report = new FixedIncomeHealthReport(
            status,
            DateTimeOffset.UtcNow,
            database,
            engine,
            SigningKeyConfigured: !string.IsNullOrEmpty(_engineOptions.SigningKey),
            ApiKeyConfigured: !string.IsNullOrEmpty(_engineOptions.ApiKey),
            AllowedEngineVersions: _engineOptions.EffectiveAllowedEngineVersions);

        return database.Ready ? Ok(report) : StatusCode(StatusCodes.Status503ServiceUnavailable, report);
    }
}

public sealed record DatabaseHealth(bool Ready, string? Error, int QueuedRuns, int RunningRuns);

public sealed record EngineHealth(
    bool Reachable,
    bool Ready,
    string? EngineVersion,
    bool EngineVersionAllowed,
    IReadOnlyList<string> SchemaVersions,
    System.Text.Json.Nodes.JsonObject? Capabilities,
    string? Error);

public sealed record FixedIncomeHealthReport(
    string Status,
    DateTimeOffset CheckedAt,
    DatabaseHealth Database,
    EngineHealth ResearchEngine,
    bool SigningKeyConfigured,
    bool ApiKeyConfigured,
    IReadOnlyList<string> AllowedEngineVersions);
