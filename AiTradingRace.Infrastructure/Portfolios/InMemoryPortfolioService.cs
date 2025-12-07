using System.Collections.Concurrent;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Domain.Entities;

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
                    if (notional > cash)
                    {
                        throw new InvalidOperationException($"Insufficient cash ({cash:C}) to buy {order.Quantity} {asset} at {price}.");
                    }

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
                    if (existingPosition is null || existingPosition.Quantity < order.Quantity)
                    {
                        throw new InvalidOperationException($"Cannot sell {order.Quantity} {asset} without sufficient holdings.");
                    }

                    cash += notional;
                    var remainingQty = Math.Max(0, existingPosition.Quantity - order.Quantity);
                    positions[asset] = existingPosition with
                    {
                        Quantity = remainingQty,
                        CurrentPrice = price
                    };
                    break;

                case TradeSide.Hold:
                    // No changes for hold orders; keep snapshot as-is.
                    if (existingPosition is not null)
                    {
                        positions[asset] = existingPosition with { CurrentPrice = price };
                    }
                    break;

                default:
                    throw new InvalidOperationException($"Unsupported trade side '{order.Side}'.");
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
        // Placeholder prices for demo purposes only.
        return symbol switch
        {
            "ETH" => 3_000m,
            "SOL" => 150m,
            _ => 50_000m
        };
    }

    private static decimal CalculateAveragePrice(PositionSnapshot? existing, decimal notional, decimal quantity)
    {
        if (quantity <= 0)
        {
            return existing?.AveragePrice ?? 0m;
        }

        if (existing is null || existing.Quantity <= 0)
        {
            return notional / quantity;
        }

        var totalCost = (existing.AveragePrice * existing.Quantity) + notional;
        var totalQuantity = existing.Quantity + quantity;

        return totalQuantity <= 0 ? existing.AveragePrice : totalCost / totalQuantity;
    }
}

