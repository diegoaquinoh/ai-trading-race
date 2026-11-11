using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Application.FixedIncome;

/// <summary>
/// Client for the Python research-engine internal API (spec 14.3). Authenticated
/// with X-API-Key. POST commands are never retried automatically: a retry is a new
/// logical decision by the caller, protected by command-id idempotency.
/// Errors surface as <see cref="ResearchEngineException"/> subclasses.
/// </summary>
public interface IResearchEngineClient
{
    /// <summary>POST /internal/v1/simulation/transitions → signed TransitionProposal (raw JSON).</summary>
    Task<RawContractJson> ProposeTransitionAsync(TransitionRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/strategies/decisions → signed StrategyResult (raw JSON).</summary>
    Task<RawContractJson> RequestDecisionAsync(DecisionRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/analytics/price.</summary>
    Task<ResearchEngineDocument> PriceAsync(PriceRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/analytics/risk.</summary>
    Task<ResearchEngineDocument> RiskAsync(RiskRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/analytics/performance → evaluation metrics computed by the engine (metrics-v1).</summary>
    Task<ResearchEngineDocument> GetPerformanceAsync(PerformanceRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/instruments/payment-calendar → projected coupons/redemptions of a stored state.</summary>
    Task<ResearchEngineDocument> GetPaymentCalendarAsync(PaymentCalendarRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/evidence/retrieve.</summary>
    Task<ResearchEngineDocument> RetrieveEvidenceAsync(EvidenceRetrieveRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/research-notes (informational only).</summary>
    Task<ResearchEngineDocument> CreateResearchNoteAsync(ResearchNoteRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/capabilities.</summary>
    Task<CapabilitiesDto> GetCapabilitiesAsync(CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/instruments.</summary>
    Task<ResearchEngineDocument> GetInstrumentsAsync(InstrumentQuery query, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/curves/{snapshotId}.</summary>
    Task<ResearchEngineDocument> GetCurveAsync(string snapshotId, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/evidence/bundles/{bundleId}.</summary>
    Task<ResearchEngineDocument> GetEvidenceBundleAsync(string bundleId, PageQuery page, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/admin/ingestions.</summary>
    Task<ResearchEngineDocument> StartIngestionAsync(IngestionRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/admin/index-builds.</summary>
    Task<ResearchEngineDocument> StartIndexBuildAsync(IndexBuildRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/market/sessions?start=&amp;end= → supported sessions with frozen market pointers.</summary>
    Task<MarketSessionsDto> GetMarketSessionsAsync(DateOnly start, DateOnly end, CancellationToken cancellationToken = default);

    /// <summary>POST /internal/v1/simulation/bootstrap-allocation → common bootstrap targets (computed by the engine).</summary>
    Task<BootstrapAllocationDto> GetBootstrapAllocationAsync(BootstrapAllocationRequestDto request, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/evidence/chunks/{chunkId}.</summary>
    Task<ResearchEngineDocument> GetEvidenceChunkAsync(string chunkId, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/evidence/graph?bundleId=.</summary>
    Task<ResearchEngineDocument> GetEvidenceGraphAsync(string bundleId, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/instruments/{securityId}/valuation?date=.</summary>
    Task<ResearchEngineDocument> GetInstrumentValuationAsync(string securityId, DateOnly? date, CancellationToken cancellationToken = default);

    /// <summary>GET /internal/v1/admin/jobs/{jobId}.</summary>
    Task<ResearchEngineDocument> GetAdminJobAsync(string jobId, CancellationToken cancellationToken = default);
}

public sealed record InstrumentQuery(
    string? AsOf = null,
    string? UniverseVersion = null,
    string? SecurityId = null,
    int Page = 1,
    int PageSize = 50);

public sealed record PageQuery(int Page = 1, int PageSize = 50);

/// <summary>Base error for research-engine calls.</summary>
public class ResearchEngineException : Exception
{
    public ResearchEngineException(string message, int? statusCode = null, string? body = null, Exception? inner = null)
        : base(message, inner)
    {
        StatusCode = statusCode;
        Body = body;
        ProblemCode = ReadProblemCode(body);
    }

    /// <summary>HTTP status returned by the engine (null for transport failures).</summary>
    public int? StatusCode { get; }

    /// <summary>Response body (problem details from the engine), if any.</summary>
    public string? Body { get; }

    /// <summary>Stable problem+json <c>code</c> of a deterministic engine rejection (e.g. a ledger invariant violation), if any.</summary>
    public string? ProblemCode { get; }

    /// <summary>
    /// True for failures that may succeed when the same request is repeated later: the engine
    /// unreachable, timed out or answering 502/503/504 (dependency unavailable), or rate limited.
    /// Everything else (4xx, 500, invalid payloads) is a deterministic error of that request.
    /// </summary>
    public static bool IsTransient(Exception? exception) =>
        exception is ResearchEngineUnavailableException or ResearchEngineRateLimitedException;

    private static string? ReadProblemCode(string? body)
    {
        if (string.IsNullOrWhiteSpace(body) || body.TrimStart()[0] != '{')
        {
            return null;
        }

        try
        {
            using var document = System.Text.Json.JsonDocument.Parse(body);
            return document.RootElement.ValueKind == System.Text.Json.JsonValueKind.Object &&
                   document.RootElement.TryGetProperty("code", out var code) &&
                   code.ValueKind == System.Text.Json.JsonValueKind.String
                ? code.GetString()
                : null;
        }
        catch (System.Text.Json.JsonException)
        {
            return null;
        }
    }
}

/// <summary>
/// 500 (or another non-gateway 5xx) from the engine, or a successful response whose contract
/// payload is unreadable: an unexpected engine error for that request. Not transient — the same
/// request is expected to fail the same way, so callers isolate the affected command instead
/// of pausing the whole run.
/// </summary>
public sealed class ResearchEngineServerException : ResearchEngineException
{
    public ResearchEngineServerException(string message, int? statusCode, string? body, Exception? inner = null)
        : base(message, statusCode, body, inner) { }
}

/// <summary>400/422 from the engine: invalid request, unsupported schema/convention/units.</summary>
public sealed class ResearchEngineValidationException : ResearchEngineException
{
    public ResearchEngineValidationException(string message, int statusCode, string? body)
        : base(message, statusCode, body) { }
}

/// <summary>404 from the engine (unknown snapshot, bundle, instrument).</summary>
public sealed class ResearchEngineNotFoundException : ResearchEngineException
{
    public ResearchEngineNotFoundException(string message, string? body)
        : base(message, 404, body) { }
}

/// <summary>409 from the engine (immutable configuration / idempotency mismatch).</summary>
public sealed class ResearchEngineConflictException : ResearchEngineException
{
    public ResearchEngineConflictException(string message, string? body)
        : base(message, 409, body) { }
}

/// <summary>429 from the engine (rate/budget concurrency limit).</summary>
public sealed class ResearchEngineRateLimitedException : ResearchEngineException
{
    public ResearchEngineRateLimitedException(string message, string? body, TimeSpan? retryAfter)
        : base(message, 429, body)
    {
        RetryAfter = retryAfter;
    }

    public TimeSpan? RetryAfter { get; }
}

/// <summary>
/// Transient: engine unreachable, timed out, or answering 502/503/504 (dependency unavailable).
/// Also used for 401/403 (platform credentials misconfigured), which affect every request
/// alike and therefore pause the run rather than isolate one command.
/// </summary>
public sealed class ResearchEngineUnavailableException : ResearchEngineException
{
    public ResearchEngineUnavailableException(string message, int? statusCode = null, string? body = null, Exception? inner = null)
        : base(message, statusCode, body, inner) { }
}
