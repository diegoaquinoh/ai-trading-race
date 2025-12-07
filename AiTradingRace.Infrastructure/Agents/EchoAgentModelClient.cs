using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Infrastructure.Agents;

public sealed class EchoAgentModelClient : IAgentModelClient
{
    public Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken cancellationToken = default)
    {
        var holdOrder = new TradeOrder(
            AssetSymbol: "BTC",
            Side: TradeSide.Hold,
            Quantity: 0m);

        var decision = new AgentDecision(
            context.AgentId,
            DateTimeOffset.UtcNow,
            new[] { holdOrder });

        return Task.FromResult(decision);
    }
}

