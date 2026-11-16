using AiTradingRace.Application.FixedIncome;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>Decision audit: proposal, claims, tools, gates and resulting orders (spec 14.2, 17.3).</summary>
[ApiController]
[Route("api/v1/decisions")]
[EnableRateLimiting("per-user")]
public sealed class FiDecisionsController : FiControllerBase
{
    private readonly IFixedIncomeQueryService _queries;

    public FiDecisionsController(IFixedIncomeQueryService queries)
    {
        _queries = queries;
    }

    [HttpGet("{decisionId}")]
    public async Task<IActionResult> Get(string decisionId, CancellationToken cancellationToken)
    {
        var decision = await _queries.GetDecisionAsync(decisionId, cancellationToken);
        return decision is null ? NotFoundProblem($"Decision '{decisionId}'") : Ok(decision);
    }
}
