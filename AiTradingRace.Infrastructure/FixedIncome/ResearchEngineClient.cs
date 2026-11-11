using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Options;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// HTTP client for the Python research-engine internal API (spec 14.3, 18.4).
/// Sends X-API-Key, uses the configured timeout (default 120 s, above the 90 s
/// decision deadline) and never retries POST commands automatically.
/// Transition and decision requests are sent as canonical JSON (<see cref="FiRequestBody"/>) so the
/// engine's echoed requestHash can be checked against the request that was actually sent.
/// Error classification (spec 14.6): timeouts, connection failures and 502/503/504 are transient
/// (<see cref="ResearchEngineUnavailableException"/>); 400/422, 404, 409, 500 and invalid contract
/// payloads are deterministic errors of the request.
/// </summary>
public sealed class ResearchEngineClient : IResearchEngineClient
{
    public const string ApiKeyHeader = "X-API-Key";

    private readonly HttpClient _http;
    private readonly ILogger<ResearchEngineClient> _logger;

    public ResearchEngineClient(HttpClient http, IOptions<ResearchEngineOptions> options, ILogger<ResearchEngineClient> logger)
    {
        _http = http;
        _logger = logger;
        var value = options.Value;

        _http.BaseAddress ??= BuildBaseAddress(value.BaseUrl);
        _http.Timeout = value.EffectiveTimeout;
        if (!string.IsNullOrEmpty(value.ApiKey) && !_http.DefaultRequestHeaders.Contains(ApiKeyHeader))
        {
            _http.DefaultRequestHeaders.Add(ApiKeyHeader, value.ApiKey);
        }

        _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
    }

    public static Uri BuildBaseAddress(string baseUrl) => new(baseUrl.TrimEnd('/') + "/", UriKind.Absolute);

    public Task<RawContractJson> ProposeTransitionAsync(TransitionRequestDto request, CancellationToken cancellationToken = default) =>
        PostContractAsync("internal/v1/simulation/transitions", FiRequestBody.Create(request).Text, cancellationToken);

    public Task<RawContractJson> RequestDecisionAsync(DecisionRequestDto request, CancellationToken cancellationToken = default) =>
        PostContractAsync("internal/v1/strategies/decisions", FiRequestBody.Create(request).Text, cancellationToken);

    public Task<ResearchEngineDocument> PriceAsync(PriceRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/analytics/price", request, cancellationToken);

    public Task<ResearchEngineDocument> RiskAsync(RiskRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/analytics/risk", request, cancellationToken);

    public Task<ResearchEngineDocument> GetPerformanceAsync(PerformanceRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/analytics/performance", request, cancellationToken);

    public Task<ResearchEngineDocument> GetPaymentCalendarAsync(PaymentCalendarRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/instruments/payment-calendar", request, cancellationToken);

    public Task<ResearchEngineDocument> RetrieveEvidenceAsync(EvidenceRetrieveRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/evidence/retrieve", request, cancellationToken);

    public Task<ResearchEngineDocument> CreateResearchNoteAsync(ResearchNoteRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/research-notes", request, cancellationToken);

    public Task<ResearchEngineDocument> StartIngestionAsync(IngestionRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/admin/ingestions", request, cancellationToken);

    public Task<ResearchEngineDocument> StartIndexBuildAsync(IndexBuildRequestDto request, CancellationToken cancellationToken = default) =>
        PostDocumentAsync("internal/v1/admin/index-builds", request, cancellationToken);

    public async Task<CapabilitiesDto> GetCapabilitiesAsync(CancellationToken cancellationToken = default)
    {
        var document = await SendAsync(HttpMethod.Get, "internal/v1/capabilities", null, cancellationToken);
        if (document.Body is not JsonObject body)
        {
            throw new ResearchEngineUnavailableException("Research engine capabilities response is not a JSON object.");
        }

        var engineVersion = body["engineVersion"] is JsonValue ev && ev.TryGetValue<string>(out var e) ? e : string.Empty;
        var ready = body["ready"] is JsonValue rv && rv.GetValueKind() is JsonValueKind.True;
        var schemas = body["schemaVersions"] is JsonArray array
            ? array.Select(n => n is JsonValue v && v.TryGetValue<string>(out var x) ? x : null)
                .Where(x => x is not null).Select(x => x!).ToList()
            : new List<string>();

        return new CapabilitiesDto { EngineVersion = engineVersion, Ready = ready, SchemaVersions = schemas, Raw = body };
    }

    public Task<ResearchEngineDocument> GetInstrumentsAsync(InstrumentQuery query, CancellationToken cancellationToken = default)
    {
        var parameters = new List<(string, string?)>
        {
            ("asOf", query.AsOf),
            ("universeVersion", query.UniverseVersion),
            ("securityId", query.SecurityId),
            ("page", query.Page.ToString(CultureInfo.InvariantCulture)),
            ("pageSize", query.PageSize.ToString(CultureInfo.InvariantCulture)),
        };
        return SendAsync(HttpMethod.Get, "internal/v1/instruments" + QueryString(parameters), null, cancellationToken);
    }

    public Task<ResearchEngineDocument> GetCurveAsync(string snapshotId, CancellationToken cancellationToken = default) =>
        SendAsync(HttpMethod.Get, "internal/v1/curves/" + Uri.EscapeDataString(snapshotId), null, cancellationToken);

    public Task<ResearchEngineDocument> GetEvidenceBundleAsync(string bundleId, PageQuery page, CancellationToken cancellationToken = default)
    {
        var parameters = new List<(string, string?)>
        {
            ("page", page.Page.ToString(CultureInfo.InvariantCulture)),
            ("pageSize", page.PageSize.ToString(CultureInfo.InvariantCulture)),
        };
        return SendAsync(HttpMethod.Get,
            "internal/v1/evidence/bundles/" + Uri.EscapeDataString(bundleId) + QueryString(parameters), null, cancellationToken);
    }

    public async Task<MarketSessionsDto> GetMarketSessionsAsync(DateOnly start, DateOnly end, CancellationToken cancellationToken = default)
    {
        var parameters = new List<(string, string?)>
        {
            ("start", FiWire.FormatDate(start)),
            ("end", FiWire.FormatDate(end)),
        };
        const string path = "internal/v1/market/sessions";
        var document = await SendAsync(HttpMethod.Get, path + QueryString(parameters), null, cancellationToken);
        if (document.Body is not JsonObject body)
        {
            throw new ResearchEngineUnavailableException("Research engine market sessions response is not a JSON object.", document.StatusCode);
        }

        try
        {
            return FiWire.Deserialize<MarketSessionsDto>(body);
        }
        catch (Exception ex) when (ex is JsonException or FormatException or InvalidOperationException)
        {
            throw new ResearchEngineUnavailableException(
                $"Research engine returned an invalid market sessions payload: {ex.Message}", document.StatusCode, inner: ex);
        }
    }

    public async Task<BootstrapAllocationDto> GetBootstrapAllocationAsync(BootstrapAllocationRequestDto request, CancellationToken cancellationToken = default)
    {
        const string path = "internal/v1/simulation/bootstrap-allocation";
        var document = await SendAsync(HttpMethod.Post, path, request, cancellationToken);
        if (document.Body is not JsonObject body)
        {
            throw new ResearchEngineUnavailableException("Research engine bootstrap allocation response is not a JSON object.", document.StatusCode);
        }

        try
        {
            var parsed = FiWire.Deserialize<BootstrapAllocationDto>(body);
            return parsed with { Buckets = body["buckets"]?.DeepClone(), Raw = (JsonObject)body.DeepClone() };
        }
        catch (Exception ex) when (ex is JsonException or FormatException or InvalidOperationException)
        {
            throw new ResearchEngineUnavailableException(
                $"Research engine returned an invalid bootstrap allocation payload: {ex.Message}", document.StatusCode, inner: ex);
        }
    }

    public Task<ResearchEngineDocument> GetEvidenceChunkAsync(string chunkId, CancellationToken cancellationToken = default) =>
        SendAsync(HttpMethod.Get, "internal/v1/evidence/chunks/" + Uri.EscapeDataString(chunkId), null, cancellationToken);

    public Task<ResearchEngineDocument> GetEvidenceGraphAsync(string bundleId, CancellationToken cancellationToken = default) =>
        SendAsync(HttpMethod.Get,
            "internal/v1/evidence/graph" + QueryString(new List<(string, string?)> { ("bundleId", bundleId) }), null, cancellationToken);

    public Task<ResearchEngineDocument> GetInstrumentValuationAsync(string securityId, DateOnly? date, CancellationToken cancellationToken = default) =>
        SendAsync(HttpMethod.Get,
            "internal/v1/instruments/" + Uri.EscapeDataString(securityId) + "/valuation" +
            QueryString(new List<(string, string?)> { ("date", date is { } d ? FiWire.FormatDate(d) : null) }),
            null, cancellationToken);

    public Task<ResearchEngineDocument> GetAdminJobAsync(string jobId, CancellationToken cancellationToken = default) =>
        SendAsync(HttpMethod.Get, "internal/v1/admin/jobs/" + Uri.EscapeDataString(jobId), null, cancellationToken);

    /// <summary>Posts the exact canonical body text (hashed by the caller) and returns the raw signed contract.</summary>
    private async Task<RawContractJson> PostContractAsync(string path, string canonicalBody, CancellationToken ct)
    {
        var (status, text) = await SendRawAsync(HttpMethod.Post, path, canonicalBody, ct);
        try
        {
            return RawContractJson.Parse(text);
        }
        catch (FormatException ex)
        {
            // A successful status with an unreadable contract is an engine defect, not an outage.
            throw new ResearchEngineServerException(
                $"Research engine returned an invalid contract payload from {path}: {ex.Message}", status, text, ex);
        }
    }

    private Task<ResearchEngineDocument> PostDocumentAsync<T>(string path, T request, CancellationToken ct) =>
        SendAsync(HttpMethod.Post, path, request, ct);

    private async Task<ResearchEngineDocument> SendAsync(HttpMethod method, string path, object? body, CancellationToken ct)
    {
        var (status, text) = await SendRawAsync(method, path, body, ct);
        if (string.IsNullOrWhiteSpace(text))
        {
            return new ResearchEngineDocument(status, null);
        }

        try
        {
            return new ResearchEngineDocument(status, JsonNode.Parse(text));
        }
        catch (JsonException ex)
        {
            throw new ResearchEngineUnavailableException($"Research engine returned invalid JSON from {path}.", status, text, ex);
        }
    }

    private async Task<(int Status, string Text)> SendRawAsync(HttpMethod method, string path, object? body, CancellationToken ct)
    {
        using var message = new HttpRequestMessage(method, path);
        if (body is not null)
        {
            // A pre-serialized string body is sent verbatim (canonical contract requests).
            var json = body as string ?? JsonSerializer.Serialize(body, body.GetType(), FiContract.WireOptions);
            message.Content = new StringContent(json, Encoding.UTF8, "application/json");
        }

        HttpResponseMessage response;
        try
        {
            response = await _http.SendAsync(message, HttpCompletionOption.ResponseContentRead, ct);
        }
        catch (TaskCanceledException ex) when (!ct.IsCancellationRequested)
        {
            throw new ResearchEngineUnavailableException(
                $"Research engine call {method} {path} timed out after {_http.Timeout.TotalSeconds:0} s.", inner: ex);
        }
        catch (HttpRequestException ex)
        {
            throw new ResearchEngineUnavailableException($"Research engine is unreachable ({method} {path}): {ex.Message}", inner: ex);
        }

        using (response)
        {
            var text = await response.Content.ReadAsStringAsync(ct);
            var status = (int)response.StatusCode;
            if (response.IsSuccessStatusCode)
            {
                return (status, text);
            }

            _logger.LogWarning("Research engine {Method} {Path} returned {Status}", method, path, status);
            throw response.StatusCode switch
            {
                HttpStatusCode.BadRequest or HttpStatusCode.UnprocessableEntity =>
                    new ResearchEngineValidationException($"Research engine rejected the request ({status}).", status, text),
                HttpStatusCode.NotFound => new ResearchEngineNotFoundException("Research engine resource not found.", text),
                HttpStatusCode.Conflict => new ResearchEngineConflictException("Research engine reported a conflict.", text),
                HttpStatusCode.TooManyRequests => new ResearchEngineRateLimitedException(
                    "Research engine rate or budget limit reached.", text, response.Headers.RetryAfter?.Delta),
                HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden => new ResearchEngineUnavailableException(
                    "Research engine rejected the platform credentials; check ResearchEngine:ApiKey.", status, text),
                HttpStatusCode.BadGateway or HttpStatusCode.ServiceUnavailable or HttpStatusCode.GatewayTimeout =>
                    new ResearchEngineUnavailableException($"Research engine dependency unavailable ({status}).", status, text),
                _ when status >= 500 => new ResearchEngineServerException(
                    $"Research engine failed to process the request ({status}).", status, text),
                _ => new ResearchEngineException($"Unexpected research engine status {status}.", status, text),
            };
        }
    }

    private static string QueryString(IEnumerable<(string Key, string? Value)> parameters)
    {
        var parts = parameters
            .Where(p => !string.IsNullOrEmpty(p.Value))
            .Select(p => Uri.EscapeDataString(p.Key) + "=" + Uri.EscapeDataString(p.Value!))
            .ToList();
        return parts.Count == 0 ? string.Empty : "?" + string.Join("&", parts);
    }
}
