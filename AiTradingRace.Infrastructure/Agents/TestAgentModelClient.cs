using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Test implementation of IAgentModelClient that generates aggressive orders
/// to verify risk validation works correctly in E2E testing.
/// </summary>
public sealed class TestAgentModelClient : IAgentModelClient
{
    private readonly ILogger<TestAgentModelClient> _logger;

    public TestAgentModelClient(ILogger<TestAgentModelClient> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Generates test orders that should trigger risk validation:
    /// - Large BTC buy ($50k+ when max trade is $5k)
    /// - ETH buy to test position limits
    /// </summary>
    public Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("TestAgentModelClient generating aggressive test orders for agent {AgentId}",
            context.AgentId);

        // Create orders that WILL trigger risk validation adjustments
        var orders = new List<TradeOrder>
        {
            // Order 1: Try to buy $50k+ worth of BTC (should be capped at $5k max trade)
            // At $42k/BTC, 1.5 BTC = $63k
            new TradeOrder("BTC", TradeSide.Buy, 1.5m),
            
            // Order 2: Try to buy $25k worth of ETH (should be capped by remaining cash after BTC)
            // At $2.5k/ETH, 10 ETH = $25k
            new TradeOrder("ETH", TradeSide.Buy, 10m)
        };

        _logger.LogInformation("TestAgentModelClient proposed {Count} aggressive orders:", orders.Count);
        foreach (var order in orders)
        {
            _logger.LogInformation("  - {Side} {Qty} {Asset}", order.Side, order.Quantity, order.AssetSymbol);
        }

        return Task.FromResult(new AgentDecision(
            context.AgentId,
            DateTimeOffset.UtcNow,
            orders));
    }
}
