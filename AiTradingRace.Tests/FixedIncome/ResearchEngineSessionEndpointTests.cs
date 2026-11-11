using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.FixedIncome;
using AiTradingRace.Web.Controllers.FixedIncome;
using AiTradingRace.Web.FixedIncome;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>New research-engine endpoints (sessions, bootstrap allocation, evidence/valuation/job proxies) and Web wiring.</summary>
public sealed class ResearchEngineSessionEndpointTests
{
    private sealed class RecordingHandler : HttpMessageHandler
    {
        private readonly string _body;

        public RecordingHandler(string body) => _body = body;

        public List<(HttpMethod Method, string Uri, string? Body)> Requests { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var body = request.Content is null ? null : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add((request.Method, request.RequestUri!.PathAndQuery, body));
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(_body, Encoding.UTF8, "application/json") };
        }
    }

    private static (ResearchEngineClient Client, RecordingHandler Handler) Client(string body)
    {
        var handler = new RecordingHandler(body);
        var client = new ResearchEngineClient(new HttpClient(handler), Options.Create(new ResearchEngineOptions
        {
            BaseUrl = "http://engine:8000",
            ApiKey = "k",
        }), NullLogger<ResearchEngineClient>.Instance);
        return (client, handler);
    }

    [Fact]
    public async Task MarketSessions_SendsDateWindow_AndParsesSessions()
    {
        var (client, handler) = Client("""
            {"dataMode":"synthetic_curve","universeVersion":"synthetic-universe-v1","sessions":[
              {"sessionDate":"2024-01-02","marketSnapshotId":"mkt-1","marketSnapshotHash":"sha256:aa","curveSnapshotId":"curve-1",
               "curveStatus":"READY","observedAt":"2024-01-02T20:30:00Z","availableAt":"2024-01-02T23:00:00Z",
               "decisionAsOf":"2024-01-03T00:00:00Z","executionObservationAt":"2024-01-03T20:30:00Z","gap":false,"gapReason":null}]}
            """);

        var sessions = await client.GetMarketSessionsAsync(new DateOnly(2024, 1, 2), new DateOnly(2024, 2, 9));

        Assert.Equal("/internal/v1/market/sessions?start=2024-01-02&end=2024-02-09", handler.Requests.Single().Uri);
        Assert.Equal("synthetic-universe-v1", sessions.UniverseVersion);
        var session = Assert.Single(sessions.Sessions);
        Assert.Equal("READY", session.CurveStatus);
        Assert.Equal("2024-01-03T00:00:00Z", session.DecisionAsOf);
        Assert.False(session.Gap);
    }

    [Fact]
    public async Task BootstrapAllocation_PostsPolicy_AndKeepsTheRawResponse()
    {
        var (client, handler) = Client("""
            {"version":"bootstrap-v1","sessionDate":"2024-01-02","targets":[{"securityId":"SYN-1","weight":"0.94"},{"securityId":"CASH-USD","weight":"0.06"}],
             "buckets":{"short":"0.30"},"extra":"kept"}
            """);

        var allocation = await client.GetBootstrapAllocationAsync(new BootstrapAllocationRequestDto
        {
            SessionDate = "2024-01-02",
            UniverseVersion = "synthetic-universe-v1",
            RiskPolicy = new RiskPolicyOptions().ToWire("treasury-long-only-v1"),
        });

        var request = handler.Requests.Single();
        Assert.Equal(HttpMethod.Post, request.Method);
        Assert.Equal("/internal/v1/simulation/bootstrap-allocation", request.Uri);
        var body = JsonNode.Parse(request.Body!)!;
        Assert.Equal("1.0", (string?)body["schemaVersion"]);
        Assert.Equal("0.05", (string?)body["riskPolicy"]!["minCashRatio"]);
        Assert.Equal(2, allocation.Targets.Count);
        Assert.Equal("0.30", (string?)allocation.Buckets!["short"]);
        Assert.Equal("kept", (string?)allocation.Raw["extra"]);
    }

    [Fact]
    public async Task ProxyEndpoints_UseTheInternalPaths()
    {
        var (client, handler) = Client("{}");

        await client.GetEvidenceChunkAsync("chunk:1/2");
        await client.GetEvidenceGraphAsync("bundle-1");
        await client.GetInstrumentValuationAsync("SYN-USD-NOTE-001", new DateOnly(2024, 1, 5));
        await client.GetAdminJobAsync("job-9");

        Assert.Equal(new[]
        {
            "/internal/v1/evidence/chunks/chunk%3A1%2F2",
            "/internal/v1/evidence/graph?bundleId=bundle-1",
            "/internal/v1/instruments/SYN-USD-NOTE-001/valuation?date=2024-01-05",
            "/internal/v1/admin/jobs/job-9",
        }, handler.Requests.Select(r => r.Uri));
    }

    [Fact]
    public async Task PublicProxies_ReturnEngineBodies_AndValidateDates()
    {
        var engine = new Mock<IResearchEngineClient>();
        engine.Setup(e => e.GetEvidenceChunkAsync("c1", It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ResearchEngineDocument(200, JsonNode.Parse("{\"chunkId\":\"c1\"}")));
        engine.Setup(e => e.GetEvidenceGraphAsync("b1", It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ResearchEngineNotFoundException("missing", null));
        engine.Setup(e => e.GetInstrumentValuationAsync("SYN-1", new DateOnly(2024, 1, 5), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ResearchEngineDocument(200, JsonNode.Parse("{\"securityId\":\"SYN-1\"}")));
        engine.Setup(e => e.GetAdminJobAsync("job-1", It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ResearchEngineDocument(200, JsonNode.Parse("{\"state\":\"running\"}")));
        var research = new FiResearchController(engine.Object) { ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() } };
        var admin = new FiAdminController(engine.Object, Mock.Of<IExperimentService>(), Mock.Of<IFixedIncomeRunQueue>(), Mock.Of<ITransitionCommitService>())
        {
            ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() },
        };

        Assert.IsType<OkObjectResult>(await research.EvidenceChunk("c1", CancellationToken.None));
        Assert.Equal(404, Assert.IsAssignableFrom<ObjectResult>(await research.EvidenceGraph("b1", CancellationToken.None)).StatusCode);
        Assert.IsType<OkObjectResult>(await research.InstrumentValuation("SYN-1", "2024-01-05", CancellationToken.None));
        Assert.Equal(422, Assert.IsAssignableFrom<ObjectResult>(await research.InstrumentValuation("SYN-1", "05/01/2024", CancellationToken.None)).StatusCode);
        Assert.IsType<OkObjectResult>(await admin.Job("job-1", CancellationToken.None));
    }

    [Fact]
    public async Task Worker_KeepsForwardRunsRunning_RequeuesOnShutdown_AndRecoversOrphanedRuns()
    {
        using var database = new FiSqliteDatabase();
        var executor = new Mock<IFixedIncomeRunExecutor>();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddScoped(_ => database.CreateContext());
        services.AddSingleton(Fi.Policies());
        services.AddScoped<IExperimentService>(sp => new ExperimentService(
            sp.GetRequiredService<TradingDbContext>(), sp.GetRequiredService<IRiskPolicyProvider>(), NullLogger<ExperimentService>.Instance));
        services.AddSingleton(executor.Object);
        await using var provider = services.BuildServiceProvider();
        using (var scope = provider.CreateScope())
        {
            var experiments = scope.ServiceProvider.GetRequiredService<IExperimentService>();
            await experiments.CreateDefinitionAsync(ExperimentServiceTests.Definition(), null);
            await experiments.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-fwd", RunType = "forward" }, null);
            await experiments.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-int" }, null);
            await experiments.StartRunAsync("exp-demo", new StartRunRequest { RunId = "run-orphan" }, null);
            Assert.True(await experiments.TryMarkRunningAsync("run-orphan"));
        }

        using var shutdown = new CancellationTokenSource();
        executor.Setup(e => e.ExecuteAsync("run-fwd", It.IsAny<CancellationToken>())).ReturnsAsync(RunExecutionResult.Continue());
        executor.Setup(e => e.ExecuteAsync("run-int", It.IsAny<CancellationToken>()))
            .Returns<string, CancellationToken>((_, _) =>
            {
                shutdown.Cancel();
                return Task.FromException<RunExecutionResult>(new OperationCanceledException(shutdown.Token));
            });
        var queue = new FixedIncomeRunQueue(Options.Create(new FixedIncomeOptions()));
        var worker = new FixedIncomeRunWorker(queue, provider.GetRequiredService<IServiceScopeFactory>(),
            NullLogger<FixedIncomeRunWorker>.Instance);

        await worker.ProcessAsync("run-fwd", CancellationToken.None);
        await worker.ProcessAsync("run-int", shutdown.Token);

        await using var db = database.CreateContext();
        Assert.Equal(FiJobState.Running, (await db.FiExperimentRuns.SingleAsync(r => r.RunId == "run-fwd")).JobState);
        var interrupted = await db.FiExperimentRuns.SingleAsync(r => r.RunId == "run-int");
        Assert.Equal(FiJobState.Queued, interrupted.JobState);
        Assert.StartsWith("Interrupted by host shutdown", interrupted.StatusReason);

        using (var scope = provider.CreateScope())
        {
            var experiments = scope.ServiceProvider.GetRequiredService<IExperimentService>();
            Assert.True(await experiments.TryRequeueAsync("run-fwd", "test requeue"));
            Assert.False(await experiments.TryRequeueAsync("run-fwd", "already queued"));
            var orphans = await experiments.RequeueOrphanedRunsAsync();
            Assert.Contains("run-orphan", orphans);
        }

        await using var check = database.CreateContext();
        Assert.Equal(FiJobState.Queued, (await check.FiExperimentRuns.SingleAsync(r => r.RunId == "run-orphan")).JobState);
        Assert.StartsWith("Interrupted", (await check.FiExperimentRuns.SingleAsync(r => r.RunId == "run-orphan")).StatusReason);
    }

    [Fact]
    public void DependencyInjection_RegistersTheRealExecutor()
    {
        var configuration = new Microsoft.Extensions.Configuration.ConfigurationBuilder().Build();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddDbContext<TradingDbContext>(o => o.UseInMemoryDatabase("fi-di"));
        Infrastructure.DependencyInjection.FixedIncomeServiceCollectionExtensions.AddFixedIncomeServices(services, configuration);
        using var provider = services.BuildServiceProvider();
        using var scope = provider.CreateScope();

        Assert.IsType<FixedIncomeRunExecutor>(scope.ServiceProvider.GetRequiredService<IFixedIncomeRunExecutor>());
        Assert.IsType<FixedIncomeCycleRunner>(scope.ServiceProvider.GetRequiredService<IFixedIncomeCycleRunner>());
        Assert.Same(provider.GetRequiredService<FixedIncomeMetrics>(), provider.GetRequiredService<FixedIncomeMetrics>());
    }
}
