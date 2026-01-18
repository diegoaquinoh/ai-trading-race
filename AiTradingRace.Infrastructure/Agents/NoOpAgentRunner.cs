using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Domain.Entities;

namespace AiTradingRace.Infrastructure.Agents;

public sealed class NoOpAgentRunner : IAgentRunner
{
    private readonly IAgentModelClient _modelClient;
    private readonly IPortfolioService _portfolioService;
    private readonly IMarketDataProvider _marketDataProvider;

    public NoOpAgentRunner(
        IAgentModelClient modelClient,
        IPortfolioService portfolioService,
        IMarketDataProvider marketDataProvider)
    {
        _modelClient = modelClient;
        _portfolioService = portfolioService;
        _marketDataProvider = marketDataProvider;
    }

    public async Task<AgentRunResult> RunAgentOnceAsync(
        Guid agentId,
        CancellationToken cancellationToken = default)
    {
        var startedAt = DateTimeOffset.UtcNow;
        var portfolio = await _portfolioService.GetPortfolioAsync(agentId, cancellationToken);
        var candles = await _marketDataProvider.GetLatestCandlesAsync("BTC", 10, cancellationToken);
        var context = new AgentContext(agentId, ModelProvider.Mock, portfolio, candles, "Bootstrap cycle");

        var decision = await _modelClient.GenerateDecisionAsync(context, cancellationToken);
        portfolio = await _portfolioService.ApplyDecisionAsync(agentId, decision, cancellationToken);

        var completedAt = DateTimeOffset.UtcNow;
        return new AgentRunResult(agentId, startedAt, completedAt, portfolio, decision);
    }
}

