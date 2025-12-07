using System.Collections.Concurrent;
using System.Linq;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Portfolios;

namespace AiTradingRace.Infrastructure.Portfolios;

public sealed class InMemoryPortfolioService : IPortfolioService
{
    private readonly ConcurrentDictionary<Guid, PortfolioState> _store = new();

    public Task<PortfolioState> GetPortfolioAsync(
        Guid agentId,
        CancellationToken cancellationToken = default)
    {
        var state = _store.GetOrAdd(agentId, CreateDefaultPortfolio);
        return Task.FromResult(state);
    }

    public Task<PortfolioState> ApplyDecisionAsync(
        Guid agentId,
        AgentDecision decision,
        CancellationToken cancellationToken = default)
    {
        var state = _store.AddOrUpdate(agentId,
            _ => CreateDefaultPortfolio(agentId),
            (_, current) => ApplyOrders(current, decision));

        return Task.FromResult(state);
    }

    private static PortfolioState CreateDefaultPortfolio(Guid agentId)
    {
        var portfolioId = Guid.NewGuid();
        return new PortfolioState(
            portfolioId,
            agentId,
            Cash: 100_000m,
            Positions: Array.Empty<PositionSnapshot>(),
            AsOf: DateTimeOffset.UtcNow,
            TotalValue: 100_000m);
    }

    private static PortfolioState ApplyOrders(PortfolioState current, AgentDecision decision)
    {
        var cash = current.Cash;
        var positions = current.Positions
            .ToDictionary(position => position.AssetSymbol, position => position);

        foreach (var order in decision.Orders)
        {
            var asset = order.AssetSymbol.ToUpperInvariant();
            var price = order.LimitPrice ?? EstimatePrice(order.AssetSymbol);
            var notional = order.Quantity * price;

            positions.TryGetValue(asset, out var existingPosition);

            switch (order.Side)
            {
                case TradeSide.Buy:
                    cash -= notional;
                    var newQuantity = (existingPosition?.Quantity ?? 0m) + order.Quantity;
                    var averagePrice = CalculateAveragePrice(existingPosition, notional, order.Quantity);
                    positions[asset] = new PositionSnapshot(
                        asset,
                        newQuantity,
                        averagePrice,
                        price);
                    break;

                case TradeSide.Sell:
                    cash += notional;
                    if (existingPosition is not null)
                    {
                        var remainingQty = Math.Max(0, existingPosition.Quantity - order.Quantity);
                        positions[asset] = existingPosition with
                        {
                            Quantity = remainingQty,
                            CurrentPrice = price
                        };
                    }
                    break;

                default:
                    positions[asset] = existingPosition ?? new PositionSnapshot(asset, 0m, price, price);
                    break;
            }
        }

        // Remove empty positions to keep the snapshot clean.
        var cleanedPositions = positions.Values
            .Where(position => position.Quantity > 0)
            .OrderBy(position => position.AssetSymbol, StringComparer.Ordinal)
            .ToList();

        var totalValue = cash + cleanedPositions.Sum(position => position.Quantity * position.CurrentPrice);

        return new PortfolioState(
            current.PortfolioId,
            current.AgentId,
            cash,
            cleanedPositions,
            DateTimeOffset.UtcNow,
            totalValue);
    }

    private static decimal EstimatePrice(string assetSymbol)
    {
        var symbol = assetSymbol.ToUpperInvariant();
        return symbol switch
        {
            "ETH" => 3_000m,
            "SOL" => 150m,
            _ => 50_000m
        };
    }

    private static decimal CalculateAveragePrice(PositionSnapshot? existing, decimal notional, decimal quantity)
    {
        if (existing is null || existing.Quantity <= 0)
        {
            return quantity <= 0 ? 0m : notional / quantity;
        }

        var totalCost = (existing.AveragePrice * existing.Quantity) + notional;
        var totalQuantity = existing.Quantity + quantity;

        return totalQuantity <= 0 ? existing.AveragePrice : totalCost / totalQuantity;
    }
}

