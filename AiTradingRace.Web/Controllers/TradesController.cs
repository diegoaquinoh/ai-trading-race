using AiTradingRace.Infrastructure.Database;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Controller for retrieving trade history.
/// </summary>
[ApiController]
[Route("api/agents/{agentId:guid}/trades")]
public class TradesController : ControllerBase
{
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<TradesController> _logger;

    public TradesController(TradingDbContext dbContext, ILogger<TradesController> logger)
    {
        _dbContext = dbContext;
        _logger = logger;
    }

    /// <summary>
    /// Get trade history for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="limit">Maximum number of trades to return (default: 50, max: 500).</param>
    /// <param name="offset">Number of trades to skip for pagination.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>List of trades ordered by execution time (most recent first).</returns>
    [HttpGet]
    [ProducesResponseType(typeof(TradeHistoryResponse), StatusCodes.Status200OK)]
    public async Task<ActionResult<TradeHistoryResponse>> GetTrades(
        Guid agentId,
        [FromQuery] int limit = 50,
        [FromQuery] int offset = 0,
        CancellationToken ct = default)
    {
        // Clamp limit to reasonable bounds
        limit = Math.Clamp(limit, 1, 500);
        offset = Math.Max(0, offset);

        _logger.LogDebug("Getting trades for agent {AgentId} (limit={Limit}, offset={Offset})", agentId, limit, offset);

        // First get the portfolio for this agent
        var portfolio = await _dbContext.Portfolios
            .AsNoTracking()
            .FirstOrDefaultAsync(p => p.AgentId == agentId, ct);

        if (portfolio == null)
        {
            return Ok(new TradeHistoryResponse(Array.Empty<TradeDto>(), 0, limit, offset));
        }

        // Get total count for pagination
        var totalCount = await _dbContext.Trades
            .Where(t => t.PortfolioId == portfolio.Id)
            .CountAsync(ct);

        // Get paginated trades
        var trades = await _dbContext.Trades
            .AsNoTracking()
            .Include(t => t.MarketAsset)
            .Where(t => t.PortfolioId == portfolio.Id)
            .OrderByDescending(t => t.ExecutedAt)
            .Skip(offset)
            .Take(limit)
            .Select(t => new TradeDto(
                t.Id,
                t.MarketAsset.Symbol,
                t.ExecutedAt,
                t.Quantity,
                t.Price,
                t.Side.ToString(),
                t.Quantity * t.Price))
            .ToListAsync(ct);

        return Ok(new TradeHistoryResponse(trades, totalCount, limit, offset));
    }

    /// <summary>
    /// Get a summary of trading activity for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Summary statistics of trading activity.</returns>
    [HttpGet("summary")]
    [ProducesResponseType(typeof(TradeSummaryDto), StatusCodes.Status200OK)]
    public async Task<ActionResult<TradeSummaryDto>> GetTradeSummary(
        Guid agentId,
        CancellationToken ct)
    {
        var portfolio = await _dbContext.Portfolios
            .AsNoTracking()
            .FirstOrDefaultAsync(p => p.AgentId == agentId, ct);

        if (portfolio == null)
        {
            return Ok(new TradeSummaryDto(0, 0, 0, 0m, null, null));
        }

        var trades = await _dbContext.Trades
            .AsNoTracking()
            .Where(t => t.PortfolioId == portfolio.Id)
            .ToListAsync(ct);

        var totalTrades = trades.Count;
        var buyTrades = trades.Count(t => t.Side == Domain.Entities.TradeSide.Buy);
        var sellTrades = trades.Count(t => t.Side == Domain.Entities.TradeSide.Sell);
        var totalVolume = trades.Sum(t => t.Quantity * t.Price);
        var firstTrade = trades.MinBy(t => t.ExecutedAt)?.ExecutedAt;
        var lastTrade = trades.MaxBy(t => t.ExecutedAt)?.ExecutedAt;

        return Ok(new TradeSummaryDto(
            totalTrades,
            buyTrades,
            sellTrades,
            totalVolume,
            firstTrade,
            lastTrade));
    }
}

/// <summary>
/// Response wrapper for trade history with pagination info.
/// </summary>
public record TradeHistoryResponse(
    IReadOnlyList<TradeDto> Trades,
    int TotalCount,
    int Limit,
    int Offset);

/// <summary>
/// Individual trade DTO.
/// </summary>
public record TradeDto(
    Guid Id,
    string AssetSymbol,
    DateTimeOffset ExecutedAt,
    decimal Quantity,
    decimal Price,
    string Side,
    decimal TotalValue);

/// <summary>
/// Summary of trading activity.
/// </summary>
public record TradeSummaryDto(
    int TotalTrades,
    int BuyTrades,
    int SellTrades,
    decimal TotalVolume,
    DateTimeOffset? FirstTradeAt,
    DateTimeOffset? LastTradeAt);
