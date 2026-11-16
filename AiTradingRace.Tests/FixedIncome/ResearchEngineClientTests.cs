using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

public class ResearchEngineClientTests
{
    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly HttpStatusCode _status;
        private readonly string _body;

        public StubHandler(HttpStatusCode status, string body)
        {
            _status = status;
            _body = body;
        }

        public List<(HttpRequestMessage Request, string? Body)> Requests { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var body = request.Content is null ? null : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add((request, body));
            return new HttpResponseMessage(_status) { Content = new StringContent(_body, Encoding.UTF8, "application/json") };
        }
    }

    private static (ResearchEngineClient Client, StubHandler Handler, HttpClient Http) Create(HttpStatusCode status, string body, int timeoutSeconds = 120)
    {
        var handler = new StubHandler(status, body);
        var http = new HttpClient(handler);
        var client = new ResearchEngineClient(http, Options.Create(new ResearchEngineOptions
        {
            BaseUrl = "http://engine:8000",
            ApiKey = "internal-test-key",
            TimeoutSeconds = timeoutSeconds,
        }), NullLogger<ResearchEngineClient>.Instance);
        return (client, handler, http);
    }

    private static TransitionRequestDto Request() => new()
    {
        CommandId = "cmd-1",
        CommandType = "capital_flow",
        PortfolioState = JsonDocument.Parse(CanonicalJson.Serialize(Fi.Genesis())).RootElement,
        PortfolioStateHash = CanonicalJson.ContentHash(Fi.Genesis()),
        AdvanceTo = "2025-01-02T00:00:00Z",
        InstrumentUniverseVersion = "universe-synthetic-v1",
        CapitalAmountUsd = "1000000",
    };

    [Fact]
    public async Task ProposeTransition_PostsContractWithApiKey_AndReturnsRawText()
    {
        const string response = "{\"schemaVersion\":\"1.0\",\"proposalId\":\"p\"}";
        var (client, handler, http) = Create(HttpStatusCode.OK, response);

        var raw = await client.ProposeTransitionAsync(Request());

        Assert.Equal(response, raw.Text);
        var (request, body) = Assert.Single(handler.Requests);
        Assert.Equal(HttpMethod.Post, request.Method);
        Assert.Equal("http://engine:8000/internal/v1/simulation/transitions", request.RequestUri!.ToString());
        Assert.Equal("internal-test-key", request.Headers.GetValues("X-API-Key").Single());
        Assert.Equal(TimeSpan.FromSeconds(120), http.Timeout);

        var sent = JsonNode.Parse(body!)!.AsObject();
        Assert.Equal("1000000", sent["capitalAmountUsd"]!.GetValue<string>());
        Assert.Equal(CanonicalJson.Serialize(Fi.Genesis()), CanonicalJson.Serialize(sent["portfolioState"]));
        Assert.False(sent.ContainsKey("decisionId"));
        Assert.Equal("treasury-long-only-v1", sent["riskPolicy"]!["policyId"]!.GetValue<string>());
    }

    [Theory]
    [InlineData(HttpStatusCode.BadRequest, typeof(ResearchEngineValidationException))]
    [InlineData(HttpStatusCode.UnprocessableEntity, typeof(ResearchEngineValidationException))]
    [InlineData(HttpStatusCode.NotFound, typeof(ResearchEngineNotFoundException))]
    [InlineData(HttpStatusCode.Conflict, typeof(ResearchEngineConflictException))]
    [InlineData(HttpStatusCode.TooManyRequests, typeof(ResearchEngineRateLimitedException))]
    [InlineData(HttpStatusCode.ServiceUnavailable, typeof(ResearchEngineUnavailableException))]
    [InlineData(HttpStatusCode.Unauthorized, typeof(ResearchEngineUnavailableException))]
    public async Task ErrorStatuses_MapToTypedExceptions_WithoutRetry(HttpStatusCode status, Type expected)
    {
        var (client, handler, _) = Create(status, "{\"title\":\"problem\"}");

        var ex = await Assert.ThrowsAnyAsync<ResearchEngineException>(() => client.ProposeTransitionAsync(Request()));

        Assert.IsType(expected, ex);
        Assert.Single(handler.Requests);
    }

    /// <summary>
    /// Failure isolation (spec 14.6, 15.3): only "dependency unavailable" (502/503/504), rate limits and
    /// transport failures are transient; 500 and 4xx are deterministic errors of that request.
    /// Before the fix every 5xx (including 500) was classified as unavailable/transient.
    /// </summary>
    [Theory]
    [InlineData(HttpStatusCode.InternalServerError, typeof(ResearchEngineServerException), false)]
    [InlineData(HttpStatusCode.NotImplemented, typeof(ResearchEngineServerException), false)]
    [InlineData(HttpStatusCode.BadGateway, typeof(ResearchEngineUnavailableException), true)]
    [InlineData(HttpStatusCode.ServiceUnavailable, typeof(ResearchEngineUnavailableException), true)]
    [InlineData(HttpStatusCode.GatewayTimeout, typeof(ResearchEngineUnavailableException), true)]
    [InlineData(HttpStatusCode.TooManyRequests, typeof(ResearchEngineRateLimitedException), true)]
    [InlineData(HttpStatusCode.UnprocessableEntity, typeof(ResearchEngineValidationException), false)]
    [InlineData(HttpStatusCode.Conflict, typeof(ResearchEngineConflictException), false)]
    public async Task ServerAndGatewayStatuses_AreClassifiedTransientOnlyWhenRetryable(HttpStatusCode status, Type expected, bool transient)
    {
        var (client, handler, _) = Create(status, "{\"title\":\"problem\",\"code\":\"engine_failure\"}");

        var ex = await Assert.ThrowsAnyAsync<ResearchEngineException>(() => client.ProposeTransitionAsync(Request()));

        Assert.IsType(expected, ex);
        Assert.Equal(transient, ResearchEngineException.IsTransient(ex));
        Assert.Equal((int)status, ex.StatusCode);
        Assert.Single(handler.Requests);
    }

    [Fact]
    public async Task DeterministicRejection_ExposesTheStableProblemCode()
    {
        var (client, _, _) = Create(HttpStatusCode.UnprocessableEntity,
            "{\"type\":\"about:blank\",\"title\":\"Ledger invariant violated\",\"status\":422," +
            "\"code\":\"ledger_invariant_violation\",\"detail\":\"cash mismatch\"}");

        var ex = await Assert.ThrowsAsync<ResearchEngineValidationException>(() => client.ProposeTransitionAsync(Request()));

        Assert.Equal("ledger_invariant_violation", ex.ProblemCode);
        Assert.False(ResearchEngineException.IsTransient(ex));
    }

    [Fact]
    public async Task UnreadableContractPayload_IsANonTransientEngineError()
    {
        var (client, _, _) = Create(HttpStatusCode.OK, "[1,2,3]");

        var ex = await Assert.ThrowsAsync<ResearchEngineServerException>(() => client.ProposeTransitionAsync(Request()));

        Assert.False(ResearchEngineException.IsTransient(ex));
    }

    private sealed class ThrowingHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            throw new HttpRequestException("connection refused");
    }

    [Fact]
    public async Task ConnectionFailure_IsTransient()
    {
        var client = new ResearchEngineClient(new HttpClient(new ThrowingHandler()), Options.Create(new ResearchEngineOptions
        {
            BaseUrl = "http://engine:8000",
        }), NullLogger<ResearchEngineClient>.Instance);

        var ex = await Assert.ThrowsAsync<ResearchEngineUnavailableException>(() => client.ProposeTransitionAsync(Request()));

        Assert.True(ResearchEngineException.IsTransient(ex));
    }

    /// <summary>
    /// Request binding (spec 14.6): the body sent is the canonical JSON whose SHA-256 the caller
    /// passes as ExpectedRequestHash, and it equals what the engine computes from the body it
    /// receives (canonical JSON of the parsed body, nulls omitted by the wire options).
    /// </summary>
    [Fact]
    public async Task ContractRequests_AreSentAsTheCanonicalBodyBehindTheExpectedRequestHash()
    {
        var (client, handler, _) = Create(HttpStatusCode.OK, "{\"schemaVersion\":\"1.0\"}");
        var transition = Request();
        var decision = new DecisionRequestDto
        {
            ExperimentId = "exp-1",
            RunId = "run-1",
            CycleId = "cyc-20250106",
            DecisionId = "dec:run-1:cyc-20250106:llm_rag:0",
            StrategyId = "llm_rag",
            DecisionAsOf = "2025-01-07T00:00:00Z",
            MarketSessionDate = "2025-01-06",
            AvailabilityPolicy = "decision_time_v1",
            DataMode = "synthetic_curve",
            StrategyConfigId = "llm_rag-config-v1",
            RiskPolicyId = Fi.PolicyId,
            PortfolioState = JsonDocument.Parse(CanonicalJson.Serialize(Fi.Genesis())).RootElement,
            SessionContext = new DecisionSessionContextDto(), // null previousSessionDate is omitted on the wire
        };

        await client.ProposeTransitionAsync(transition);
        await client.RequestDecisionAsync(decision);

        var transitionBody = handler.Requests[0].Body!;
        var decisionBody = handler.Requests[1].Body!;
        Assert.Equal(CanonicalJson.Canonicalize(transitionBody), transitionBody);
        Assert.Equal(CanonicalJson.Canonicalize(decisionBody), decisionBody);
        Assert.Equal(FiRequestBody.Hash(transition), CanonicalJson.Sha256(transitionBody));
        Assert.Equal(FiRequestBody.Hash(decision), CanonicalJson.Sha256(decisionBody));
        Assert.Equal(FakeResearchEngine.ReceivedBodyHash(transition), FiRequestBody.Hash(transition));
        Assert.Equal(FakeResearchEngine.ReceivedBodyHash(decision), FiRequestBody.Hash(decision));
        var sentDecision = JsonNode.Parse(decisionBody)!.AsObject();
        Assert.Empty(sentDecision["sessionContext"]!.AsObject());
        Assert.False(sentDecision.ContainsKey("evidenceSnapshotId"));
        Assert.Equal("1000000", JsonNode.Parse(transitionBody)!["capitalAmountUsd"]!.GetValue<string>());
    }

    [Fact]
    public async Task Timeout_NeverBelowDecisionDeadlinePlusMargin()
    {
        var (_, _, http) = Create(HttpStatusCode.OK, "{}", timeoutSeconds: 30);

        Assert.True(http.Timeout > TimeSpan.FromSeconds(90));
        await Task.CompletedTask;
    }

    [Fact]
    public async Task Capabilities_AreParsedAndRawPreserved()
    {
        var (client, handler, _) = Create(HttpStatusCode.OK,
            "{\"engineVersion\":\"research-engine/0.1.0\",\"ready\":true,\"schemaVersions\":[\"1.0\"],\"lastIngestion\":{\"jobId\":\"ing-1\"}}");

        var capabilities = await client.GetCapabilitiesAsync();

        Assert.True(capabilities.Ready);
        Assert.Equal("research-engine/0.1.0", capabilities.EngineVersion);
        Assert.Equal(new[] { "1.0" }, capabilities.SchemaVersions);
        Assert.Equal("ing-1", capabilities.Raw["lastIngestion"]!["jobId"]!.GetValue<string>());
        Assert.Equal(HttpMethod.Get, handler.Requests.Single().Request.Method);
    }

    [Fact]
    public async Task Instruments_PassesPaginationAndFilters()
    {
        var (client, handler, _) = Create(HttpStatusCode.OK, "{\"items\":[]}");

        await client.GetInstrumentsAsync(new InstrumentQuery(AsOf: "2025-01-02", UniverseVersion: "u1", Page: 2, PageSize: 10));

        Assert.Equal("http://engine:8000/internal/v1/instruments?asOf=2025-01-02&universeVersion=u1&page=2&pageSize=10",
            handler.Requests.Single().Request.RequestUri!.ToString());
    }
}
