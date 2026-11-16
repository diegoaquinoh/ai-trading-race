using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>Authoritative portfolio state, valuations, ledger and orders (spec 14.2, 17.3). Read-only.</summary>
[ApiController]
[Route("api/v1/portfolios")]
[EnableRateLimiting("per-user")]
public sealed class FiPortfoliosController : FiControllerBase
{
    private readonly IFixedIncomeQueryService _queries;

    public FiPortfoliosController(IFixedIncomeQueryService queries)
    {
        _queries = queries;
    }

    [HttpGet("{portfolioId}")]
    public async Task<IActionResult> Get(string portfolioId, CancellationToken cancellationToken)
    {
        var portfolio = await _queries.GetPortfolioAsync(portfolioId, cancellationToken);
        return portfolio is null ? NotFoundProblem($"Portfolio '{portfolioId}'") : Ok(portfolio);
    }

    [HttpGet("{portfolioId}/valuations")]
    public async Task<IActionResult> Valuations(string portfolioId, [FromQuery] bool? completeOnly,
        [FromQuery] int page = 1, [FromQuery] int pageSize = 50, CancellationToken cancellationToken = default)
    {
        var valuations = await _queries.GetValuationsAsync(portfolioId, page, pageSize, completeOnly, cancellationToken);
        return valuations is null ? NotFoundProblem($"Portfolio '{portfolioId}'") : Ok(valuations);
    }

    [HttpGet("{portfolioId}/journal")]
    public async Task<IActionResult> Journal(
        string portfolioId,
        [FromQuery] string? account,
        [FromQuery] string? eventType,
        [FromQuery] long? fromVersion,
        [FromQuery] long? toVersion,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        CancellationToken cancellationToken = default)
    {
        var journal = await _queries.GetJournalAsync(portfolioId,
            new JournalFilter(account, eventType, fromVersion, toVersion, page, pageSize), cancellationToken);
        return journal is null ? NotFoundProblem($"Portfolio '{portfolioId}'") : Ok(journal);
    }

    [HttpGet("{portfolioId}/orders")]
    public async Task<IActionResult> Orders(
        string portfolioId,
        [FromQuery] string? status,
        [FromQuery] string? securityId,
        [FromQuery] string? decisionId,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50,
        CancellationToken cancellationToken = default)
    {
        var orders = await _queries.GetOrdersAsync(portfolioId,
            new OrderFilter(status, securityId, decisionId, page, pageSize), cancellationToken);
        return orders is null ? NotFoundProblem($"Portfolio '{portfolioId}'") : Ok(orders);
    }
}
