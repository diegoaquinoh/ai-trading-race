using System.Text.Json;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Web.Controllers.FixedIncome;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Moq;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// The fixed income health endpoint is anonymous: failures must not echo exception messages,
/// which can carry database hosts, login names or engine URLs.
/// </summary>
public class FiHealthControllerTests
{
    private static FiHealthController Controller(Mock<IResearchEngineClient> engine, Mock<IFixedIncomeQueryService> queries)
    {
        var controller = new FiHealthController(
            engine.Object,
            queries.Object,
            Options.Create(new ResearchEngineOptions()),
            NullLogger<FiHealthController>.Instance);
        controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        return controller;
    }

    [Fact]
    public async Task Failures_AreReportedWithoutExceptionDetails()
    {
        var queries = new Mock<IFixedIncomeQueryService>();
        queries.Setup(q => q.ListRunsAsync(It.IsAny<RunListFilter>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Login failed for user 'sqladmin' on server secret-db.internal"));
        var engine = new Mock<IResearchEngineClient>();
        engine.Setup(e => e.GetCapabilitiesAsync(It.IsAny<CancellationToken>()))
            .ThrowsAsync(new ResearchEngineException("Connection refused (ml.secret-host.internal:8000)"));

        var result = await Controller(engine, queries).Get(CancellationToken.None);

        var body = JsonSerializer.Serialize(Assert.IsType<ObjectResult>(result).Value);
        Assert.DoesNotContain("sqladmin", body);
        Assert.DoesNotContain("secret-db", body);
        Assert.DoesNotContain("secret-host", body);
        Assert.Contains("Database query failed.", body);
        Assert.Contains("Research engine unreachable.", body);
    }

    [Theory]
    [InlineData(null, null, "Research engine unreachable.")]
    [InlineData(503, null, "Research engine returned HTTP 503.")]
    [InlineData(401, "{\"code\":\"invalid_api_key\",\"detail\":\"key abc123 rejected\"}", "Research engine returned HTTP 401 (invalid_api_key).")]
    public void EngineFailure_IsDescribedByStatusAndProblemCodeOnly(int? status, string? body, string expected)
    {
        var description = FiHealthController.DescribeEngineFailure(
            new ResearchEngineException("raw message with http://10.0.0.5:8000", status, body));

        Assert.Equal(expected, description);
    }
}
