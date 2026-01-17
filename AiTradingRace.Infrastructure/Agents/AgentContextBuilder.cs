using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Builds the context needed for an AI agent to make trading decisions.
/// Gathers portfolio state, recent market data, and agent instructions.
/// </summary>
public sealed class AgentContextBuilder : IAgentContextBuilder
{
    private readonly TradingDbContext _dbContext;
    private readonly IPortfolioService _portfolioService;
    private readonly IMarketDataProvider _marketDataProvider;
    private readonly ILogger<AgentContextBuilder> _logger;

    public AgentContextBuilder(
        TradingDbContext dbContext,
        IPortfolioService portfolioService,
        IMarketDataProvider marketDataProvider,
        ILogger<AgentContextBuilder> logger)
    {
        _dbContext = dbContext;
        _portfolioService = portfolioService;
        _marketDataProvider = marketDataProvider;
        _logger = logger;
    }

    /// <inheritdoc />
    public async Task<AgentContext> BuildContextAsync(
        Guid agentId,
        int candleCount = 24,
        CancellationToken cancellationToken = default)
    {
        _logger.LogDebug("Building context for agent {AgentId} with {CandleCount} candles", agentId, candleCount);

        // 1. Load and validate agent
        var agent = await _dbContext.Agents
            .AsNoTracking()
            .FirstOrDefaultAsync(a => a.Id == agentId, cancellationToken);

        if (agent is null)
        {
            throw new InvalidOperationException($"Agent {agentId} not found.");
        }

        if (!agent.IsActive)
        {
            throw new InvalidOperationException($"Agent {agentId} is not active.");
        }

        // 2. Get portfolio state
        var portfolio = await _portfolioService.GetPortfolioAsync(agentId, cancellationToken);

        // 3. Get recent market candles for all enabled assets
        var candles = await GetRecentCandlesAsync(candleCount, cancellationToken);

        _logger.LogDebug(
            "Built context: Portfolio ${TotalValue:N2}, {PositionCount} positions, {CandleCount} candles",
            portfolio.TotalValue,
            portfolio.Positions.Count,
            candles.Count);

        return new AgentContext(
            agentId,
            portfolio,
            candles,
            agent.Instructions);
    }

    private async Task<IReadOnlyList<MarketCandleDto>> GetRecentCandlesAsync(
        int limit,
        CancellationToken cancellationToken)
    {
        // Get all enabled asset symbols
        var enabledAssets = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled)
            .Select(a => a.Symbol)
            .ToListAsync(cancellationToken);

        if (enabledAssets.Count == 0)
        {
            _logger.LogWarning("No enabled assets found for market data");
            return Array.Empty<MarketCandleDto>();
        }

        var allCandles = new List<MarketCandleDto>();

        foreach (var symbol in enabledAssets)
        {
            try
            {
                var candles = await _marketDataProvider.GetLatestCandlesAsync(
                    symbol,
                    limit,
                    cancellationToken);

                allCandles.AddRange(candles);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to get candles for {Symbol}", symbol);
                // Continue with other assets
            }
        }

        // Order by timestamp descending so most recent are first
        return allCandles
            .OrderByDescending(c => c.TimestampUtc)
            .ToList();
    }
}
