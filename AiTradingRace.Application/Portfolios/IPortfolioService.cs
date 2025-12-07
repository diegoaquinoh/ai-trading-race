using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.Portfolios;

public interface IPortfolioService
{
    Task<PortfolioState> GetPortfolioAsync(
        Guid agentId,
        CancellationToken cancellationToken = default);

    Task<PortfolioState> ApplyDecisionAsync(
        Guid agentId,
        AgentDecision decision,
        CancellationToken cancellationToken = default);
}

