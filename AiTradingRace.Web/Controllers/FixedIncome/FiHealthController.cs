using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>
/// Dependency readiness for the fixed income dashboard (spec 17.5, 18.3): database,
/// research engine capabilities (engine version, allowlist, last ingestion and
/// manifest info as reported by the engine) and run queue counts. The endpoint is anonymous,
/// so failures are reported as short generic messages and the exception details are logged.
/// </summary>
[ApiController]
[Route("api/v1/health/fixed-income")]
public sealed class FiHealthController : FiControllerBase
{
    private readonly IResearchEngineClient _engine;
    private readonly IFixedIncomeQueryService _queries;
    private readonly ResearchEngineOptions _engineOptions;
    private readonly ILogger<FiHealthController> _logger;

    public FiHealthController(
        IResearchEngineClient engine,
        IFixedIncomeQueryService queries,
        IOptions<ResearchEngineOptions> engineOptions,
        ILogger<FiHealthController> logger)
    {
        _engine = engine;
        _queries = queries;
        _engineOptions = engineOptions.Value;
        _logger = logger;
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
            _logger.LogError(ex, "Fixed income health check: database query failed");
            database = new DatabaseHealth(false, "Database query failed.", 0, 0);
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
            _logger.LogWarning(ex, "Fixed income health check: research engine call failed");
            engine = new EngineHealth(false, false, null, false, Array.Empty<string>(), null, DescribeEngineFailure(ex));
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

    /// <summary>Status code and stable problem code only: never the message, body or host.</summary>
    public static string DescribeEngineFailure(ResearchEngineException ex)
    {
        if (ex.StatusCode is null)
        {
            return "Research engine unreachable.";
        }

        return ex.ProblemCode is null
            ? $"Research engine returned HTTP {ex.StatusCode}."
            : $"Research engine returned HTTP {ex.StatusCode} ({ex.ProblemCode}).";
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
