using System.Reflection;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Web.Controllers.FixedIncome;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace AiTradingRace.Tests.FixedIncome;

public class FixedIncomeControllerTests
{
    private static T WithContext<T>(T controller) where T : ControllerBase
    {
        controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        return controller;
    }

    private static (FiExperimentsController Controller, Mock<IExperimentService> Experiments, Mock<IFixedIncomeRunQueue> Queue) Experiments()
    {
        var experiments = new Mock<IExperimentService>();
        var queue = new Mock<IFixedIncomeRunQueue>();
        queue.Setup(q => q.TryEnqueueAsync(It.IsAny<string>(), It.IsAny<CancellationToken>())).ReturnsAsync(true);
        var controller = WithContext(new FiExperimentsController(experiments.Object, Mock.Of<IFixedIncomeQueryService>(),
            queue.Object, NullLogger<FiExperimentsController>.Instance));
        return (controller, experiments, queue);
    }

    private static ProblemDetails AssertProblem(IActionResult result, int status)
    {
        var objectResult = Assert.IsAssignableFrom<ObjectResult>(result);
        Assert.Equal(status, objectResult.StatusCode);
        Assert.Contains("application/problem+json", objectResult.ContentTypes);
        var problem = Assert.IsAssignableFrom<ProblemDetails>(objectResult.Value);
        Assert.Equal(status, problem.Status);
        return problem;
    }

    [Fact]
    public async Task StartRun_Returns202WithJobIdAndStatusLink_AndEnqueues()
    {
        var (controller, experiments, queue) = Experiments();
        experiments.Setup(e => e.StartRunAsync("exp-demo", It.IsAny<StartRunRequest>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new StartRunResult { Status = StartRunStatus.Accepted, RunId = "run-1", JobState = "queued" });

        var result = await controller.StartRun("exp-demo", new StartRunRequest(), CancellationToken.None);

        var accepted = Assert.IsType<AcceptedResult>(result);
        Assert.Equal("/api/v1/runs/run-1", accepted.Location);
        var body = Assert.IsType<RunAcceptedResponse>(accepted.Value);
        Assert.Equal("run-1", body.RunId);
        Assert.Equal("queued", body.JobState);
        queue.Verify(q => q.TryEnqueueAsync("run-1", It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task StartRun_IdempotentRetry_Returns202WithoutReenqueue()
    {
        var (controller, experiments, queue) = Experiments();
        experiments.Setup(e => e.StartRunAsync(It.IsAny<string>(), It.IsAny<StartRunRequest>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new StartRunResult { Status = StartRunStatus.AlreadyExists, RunId = "run-1", JobState = "running" });

        var result = await controller.StartRun("exp-demo", new StartRunRequest { RunId = "run-1" }, CancellationToken.None);

        var body = Assert.IsType<RunAcceptedResponse>(Assert.IsType<AcceptedResult>(result).Value);
        Assert.True(body.AlreadyExisted);
        queue.Verify(q => q.TryEnqueueAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task StartRun_IdempotencyMismatch_Returns409()
    {
        var (controller, experiments, _) = Experiments();
        experiments.Setup(e => e.StartRunAsync(It.IsAny<string>(), It.IsAny<StartRunRequest>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new StartRunResult { Status = StartRunStatus.Conflict, RunId = "run-1", Message = "different" });

        var problem = AssertProblem(await controller.StartRun("exp-demo", new StartRunRequest(), CancellationToken.None), 409);

        Assert.Equal("idempotency_mismatch", problem.Extensions["code"]);
    }

    [Fact]
    public async Task StartRun_InvalidRequest_Returns422_AndUnknownExperiment404()
    {
        var (controller, experiments, _) = Experiments();
        experiments.Setup(e => e.StartRunAsync("bad", It.IsAny<StartRunRequest>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new StartRunResult
            {
                Status = StartRunStatus.Invalid,
                Errors = new Dictionary<string, string[]> { ["runType"] = new[] { "invalid" } },
            });
        experiments.Setup(e => e.StartRunAsync("missing", It.IsAny<StartRunRequest>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new StartRunResult { Status = StartRunStatus.NotFound });

        var invalid = AssertProblem(await controller.StartRun("bad", new StartRunRequest(), CancellationToken.None), 422);
        AssertProblem(await controller.StartRun("missing", new StartRunRequest(), CancellationToken.None), 404);

        Assert.Contains("runType", Assert.IsType<ValidationProblemDetails>(invalid).Errors.Keys);
    }

    [Fact]
    public async Task CreateExperiment_MapsCreatedIdempotentConflictAndInvalid()
    {
        var view = new ExperimentDefinitionView("exp-demo", 1, "n", null, "synthetic_curve", "treasury-long-only-v1",
            "synthetic-half-spread-0.02-v1", "u1", new DateOnly(2025, 1, 2), new DateOnly(2025, 2, 2), 1, "sha256:" + new string('a', 64),
            null, DateTimeOffset.UtcNow);
        var (controller, experiments, _) = Experiments();
        experiments.SetupSequence(e => e.CreateDefinitionAsync(It.IsAny<CreateExperimentDefinitionRequest>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ExperimentDefinitionResult { Status = ExperimentDefinitionStatus.Created, Definition = view })
            .ReturnsAsync(new ExperimentDefinitionResult { Status = ExperimentDefinitionStatus.AlreadyExists, Definition = view })
            .ReturnsAsync(new ExperimentDefinitionResult { Status = ExperimentDefinitionStatus.Conflict, Definition = view, Message = "immutable" })
            .ReturnsAsync(new ExperimentDefinitionResult
            {
                Status = ExperimentDefinitionStatus.Invalid,
                Errors = new Dictionary<string, string[]> { ["dataMode"] = new[] { "bad" } },
            });
        var request = new CreateExperimentDefinitionRequest();

        Assert.IsType<CreatedResult>(await controller.Create(request, CancellationToken.None));
        Assert.IsType<OkObjectResult>(await controller.Create(request, CancellationToken.None));
        AssertProblem(await controller.Create(request, CancellationToken.None), 409);
        AssertProblem(await controller.Create(request, CancellationToken.None), 422);
    }

    [Fact]
    public async Task StartRun_EndToEnd_WithRealService_Returns202ThenConflictOnChangedParameters()
    {
        using var database = new FiSqliteDatabase();
        await using var db = database.CreateContext();
        var service = ExperimentServiceTests.Service(db);
        await service.CreateDefinitionAsync(ExperimentServiceTests.Definition(), null);
        var queue = new Mock<IFixedIncomeRunQueue>();
        queue.Setup(q => q.TryEnqueueAsync(It.IsAny<string>(), It.IsAny<CancellationToken>())).ReturnsAsync(true);
        var controller = WithContext(new FiExperimentsController(service, Mock.Of<IFixedIncomeQueryService>(), queue.Object,
            NullLogger<FiExperimentsController>.Instance));

        var accepted = await controller.StartRun("exp-demo", new StartRunRequest { RunId = "run-e2e" }, CancellationToken.None);
        var conflict = await controller.StartRun("exp-demo", new StartRunRequest { RunId = "run-e2e", RunType = "forward" }, CancellationToken.None);
        var invalid = await controller.StartRun("exp-demo", new StartRunRequest { RunType = "intraday" }, CancellationToken.None);

        Assert.Equal(StatusCodes.Status202Accepted, Assert.IsType<AcceptedResult>(accepted).StatusCode);
        AssertProblem(conflict, 409);
        AssertProblem(invalid, 422);
    }

    [Fact]
    public async Task ResearchProxy_MapsEngineFailuresTo503And429()
    {
        var engine = new Mock<IResearchEngineClient>();
        engine.Setup(e => e.GetCurveAsync("curve-1", It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ResearchEngineUnavailableException("down"));
        engine.Setup(e => e.GetCurveAsync("curve-2", It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ResearchEngineRateLimitedException("slow down", null, TimeSpan.FromSeconds(5)));
        engine.Setup(e => e.GetCurveAsync("curve-3", It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ResearchEngineNotFoundException("missing", null));
        engine.Setup(e => e.GetCurveAsync("curve-4", It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ResearchEngineValidationException("bad units", 422, null));
        var controller = WithContext(new FiResearchController(engine.Object));

        AssertProblem(await controller.Curve("curve-1", CancellationToken.None), 503);
        AssertProblem(await controller.Curve("curve-2", CancellationToken.None), 429);
        Assert.Equal("5", controller.Response.Headers.RetryAfter.ToString());
        AssertProblem(await controller.Curve("curve-3", CancellationToken.None), 404);
        AssertProblem(await controller.Curve("curve-4", CancellationToken.None), 422);
    }

    [Fact]
    public async Task ResearchNote_NeverCarriesOrderAuthority()
    {
        var engine = new Mock<IResearchEngineClient>();
        engine.Setup(e => e.CreateResearchNoteAsync(It.IsAny<ResearchNoteRequestDto>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ResearchEngineDocument(200, System.Text.Json.Nodes.JsonNode.Parse("{\"status\":\"supported\"}")));
        var controller = WithContext(new FiResearchController(engine.Object));

        var result = await controller.ResearchNote(new ResearchNoteQuery { Question = "What did the Fed say?" }, CancellationToken.None);
        var empty = await controller.ResearchNote(new ResearchNoteQuery { Question = " " }, CancellationToken.None);

        var body = Assert.IsType<ResearchNoteResponse>(Assert.IsType<ObjectResult>(result).Value);
        Assert.False(body.OrderAuthority);
        AssertProblem(empty, 422);
    }

    [Fact]
    public async Task Portfolio_UnknownId_Returns404Problem()
    {
        var controller = WithContext(new FiPortfoliosController(Mock.Of<IFixedIncomeQueryService>()));

        AssertProblem(await controller.Get("pf-missing", CancellationToken.None), 404);
        AssertProblem(await controller.Journal("pf-missing", null, null, null, null, 1, 50, CancellationToken.None), 404);
    }

    [Fact]
    public async Task Runs_InvalidFilter_Returns400()
    {
        var controller = WithContext(new FiRunsController(Mock.Of<IFixedIncomeQueryService>(), Mock.Of<IExperimentService>()));

        AssertProblem(await controller.List(null, "exploded", null, null, 1, 50, CancellationToken.None), 400);
    }

    [Theory]
    [InlineData(typeof(FiExperimentsController), nameof(FiExperimentsController.Create))]
    [InlineData(typeof(FiExperimentsController), nameof(FiExperimentsController.StartRun))]
    [InlineData(typeof(FiRunsController), nameof(FiRunsController.Cancel))]
    public void LaunchingWork_RequiresOperator(Type controller, string action)
    {
        var attribute = controller.GetMethod(action)!.GetCustomAttribute<AuthorizeAttribute>();

        Assert.Equal("RequireOperator", attribute?.Policy);
    }

    [Fact]
    public void AdminEndpoints_RequireOperatorAndUnblockRequiresAdmin()
    {
        Assert.Equal("RequireOperator", typeof(FiAdminController).GetCustomAttribute<AuthorizeAttribute>()?.Policy);
        Assert.Equal("RequireAdmin",
            typeof(FiAdminController).GetMethod(nameof(FiAdminController.Unblock))!.GetCustomAttribute<AuthorizeAttribute>()?.Policy);
    }

    [Fact]
    public void Routes_ExposeTheV1Surface()
    {
        var routes = typeof(FiControllerBase).Assembly.GetTypes()
            .Where(t => typeof(FiControllerBase).IsAssignableFrom(t) && !t.IsAbstract)
            .SelectMany(t =>
            {
                var prefix = t.GetCustomAttribute<RouteAttribute>()!.Template;
                return t.GetMethods().SelectMany(m => m.GetCustomAttributes<Microsoft.AspNetCore.Mvc.Routing.HttpMethodAttribute>()
                    .Select(a => $"{a.HttpMethods.Single()} /{prefix}{(string.IsNullOrEmpty(a.Template) ? "" : "/" + a.Template)}"));
            })
            .ToHashSet();

        foreach (var expected in new[]
        {
            "GET /api/v1/instruments", "GET /api/v1/curves/{snapshotId}", "GET /api/v1/portfolios/{portfolioId}",
            "GET /api/v1/portfolios/{portfolioId}/valuations", "POST /api/v1/experiments", "POST /api/v1/experiments/{experimentId}/runs",
            "GET /api/v1/runs/{runId}", "GET /api/v1/runs/{runId}/comparison", "GET /api/v1/decisions/{decisionId}",
            "GET /api/v1/evidence/{bundleId}", "POST /api/v1/research-notes", "POST /api/v1/admin/ingestions",
            "POST /api/v1/admin/index-builds", "POST /api/v1/admin/paper-cycles", "GET /api/v1/runs",
            "GET /api/v1/runs/{runId}/cycles", "GET /api/v1/portfolios/{portfolioId}/journal",
            "GET /api/v1/portfolios/{portfolioId}/orders", "GET /api/v1/health/fixed-income",
        })
        {
            Assert.Contains(expected, routes);
        }
    }
}
