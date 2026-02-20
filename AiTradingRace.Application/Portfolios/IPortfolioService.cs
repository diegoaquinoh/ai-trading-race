using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.Portfolios;

public interface IPortfolioService
{
    Task<PortfolioState> GetPortfolioAsync(
        Guid agentId,
        CancellationToken cancellationToken = default);

    Task<(PortfolioState State, IReadOnlyList<Guid> CreatedTradeIds)> ApplyDecisionAsync(
        Guid agentId,
        AgentDecision decision,
        CancellationToken cancellationToken = default);

    Task LinkTradesToDecisionAsync(
        IReadOnlyList<Guid> tradeIds,
        int decisionLogId,
        CancellationToken cancellationToken = default);
}

