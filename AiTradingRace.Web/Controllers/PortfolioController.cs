using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Domain.Entities;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Controller for managing agent portfolios and executing trades.
/// </summary>
[ApiController]
[Route("api/agents/{agentId:guid}")]
public class PortfolioController : ControllerBase
{
    private readonly IPortfolioService _portfolioService;
    private readonly ILogger<PortfolioController> _logger;

    public PortfolioController(IPortfolioService portfolioService, ILogger<PortfolioController> logger)
    {
        _portfolioService = portfolioService;
        _logger = logger;
    }

    /// <summary>
    /// Get the current portfolio state for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Current portfolio with cash, positions, and total value.</returns>
    [HttpGet("portfolio")]
    [ProducesResponseType(typeof(PortfolioState), StatusCodes.Status200OK)]
    public async Task<ActionResult<PortfolioState>> GetPortfolio(
        Guid agentId,
        CancellationToken ct)
    {
        _logger.LogDebug("Getting portfolio for agent {AgentId}", agentId);
        var portfolio = await _portfolioService.GetPortfolioAsync(agentId, ct);
        return Ok(portfolio);
    }

    /// <summary>
    /// Execute trades for an agent (for testing/manual trading).
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="request">Trade orders to execute.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Updated portfolio state after trades.</returns>
    [Authorize(Policy = "RequireOperator")]
    [HttpPost("portfolio/trades")]
    [ProducesResponseType(typeof(PortfolioState), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<PortfolioState>> ExecuteTrades(
        Guid agentId,
        [FromBody] ExecuteTradesRequest request,
        CancellationToken ct)
    {
        if (request?.Orders == null || request.Orders.Count == 0)
        {
            return BadRequest(new { message = "At least one trade order is required" });
        }

        _logger.LogInformation("Executing {Count} trades for agent {AgentId}", request.Orders.Count, agentId);

        try
        {
            var orders = request.Orders.Select(o => new TradeOrder(
                o.AssetSymbol,
                Enum.Parse<TradeSide>(o.Side, ignoreCase: true),
                o.Quantity,
                o.LimitPrice
            )).ToList();

            var decision = new AgentDecision(agentId, DateTimeOffset.UtcNow, orders);
            var result = await _portfolioService.ApplyDecisionAsync(agentId, decision, ct);
            return Ok(result);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(new { message = ex.Message });
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(new { message = ex.Message });
        }
    }
}

/// <summary>
/// Request DTO for executing trades.
/// </summary>
public record ExecuteTradesRequest(IReadOnlyList<TradeOrderRequest> Orders);

/// <summary>
/// Individual trade order in a request.
/// </summary>
public record TradeOrderRequest(
    string AssetSymbol,
    string Side,
    decimal Quantity,
    decimal? LimitPrice = null);
