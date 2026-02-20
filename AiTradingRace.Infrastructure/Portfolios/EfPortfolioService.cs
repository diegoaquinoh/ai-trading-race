using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Infrastructure.Portfolios;

public sealed class EfPortfolioService : IPortfolioService
{
    private const decimal DefaultStartingCash = 100_000m;

    private readonly TradingDbContext _dbContext;

    public EfPortfolioService(TradingDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<PortfolioState> GetPortfolioAsync(
        Guid agentId,
        CancellationToken cancellationToken = default)
    {
        var portfolio = await GetOrCreatePortfolioAsync(agentId, cancellationToken);
        return await BuildPortfolioStateAsync(portfolio, captureSnapshot: false, cancellationToken);
    }

    public async Task<(PortfolioState State, IReadOnlyList<Guid> CreatedTradeIds)> ApplyDecisionAsync(
        Guid agentId,
        AgentDecision decision,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(decision);

        var portfolio = await GetOrCreatePortfolioAsync(agentId, cancellationToken);

        await using var transaction = await _dbContext.Database.BeginTransactionAsync(cancellationToken);

        var positions = await _dbContext.Positions
            .Where(p => p.PortfolioId == portfolio.Id)
            .ToDictionaryAsync(p => p.MarketAssetId, cancellationToken);

        var now = DateTimeOffset.UtcNow;
        var cash = portfolio.Cash;
        var createdTradeIds = new List<Guid>();

        foreach (var order in decision.Orders)
        {
            if (order.Quantity <= 0)
            {
                throw new InvalidOperationException($"Order quantity must be positive for {order.AssetSymbol}.");
            }

            var symbol = order.AssetSymbol.ToUpperInvariant();
            var asset = await GetEnabledAssetAsync(symbol, cancellationToken);
            var price = await ResolvePriceAsync(asset.Id, symbol, order.LimitPrice, cancellationToken);
            var notional = order.Quantity * price;

            positions.TryGetValue(asset.Id, out var existingPosition);

            switch (order.Side)
            {
                case TradeSide.Buy:
                    if (notional > cash)
                    {
                        throw new InvalidOperationException($"Insufficient cash ({cash}) to buy {order.Quantity} {symbol} at {price}.");
                    }

                    cash -= notional;

                    if (existingPosition is null)
                    {
                        existingPosition = new Position
                        {
                            Id = Guid.NewGuid(),
                            PortfolioId = portfolio.Id,
                            MarketAssetId = asset.Id,
                            Quantity = order.Quantity,
                            AverageEntryPrice = price
                        };

                        _dbContext.Positions.Add(existingPosition);
                        positions[asset.Id] = existingPosition;
                    }
                    else
                    {
                        existingPosition.AverageEntryPrice = CalculateNewAveragePrice(existingPosition, notional, order.Quantity);
                        existingPosition.Quantity += order.Quantity;
                    }

                    var buyTradeId = Guid.NewGuid();
                    _dbContext.Trades.Add(new Trade
                    {
                        Id = buyTradeId,
                        PortfolioId = portfolio.Id,
                        MarketAssetId = asset.Id,
                        ExecutedAt = now,
                        Quantity = order.Quantity,
                        Price = price,
                        Side = TradeSide.Buy
                    });
                    createdTradeIds.Add(buyTradeId);
                    break;

                case TradeSide.Sell:
                    if (existingPosition is null || existingPosition.Quantity < order.Quantity)
                    {
                        throw new InvalidOperationException($"Cannot sell {order.Quantity} {symbol} without sufficient holdings.");
                    }

                    cash += notional;
                    existingPosition.Quantity -= order.Quantity;

                    if (existingPosition.Quantity <= 0)
                    {
                        _dbContext.Positions.Remove(existingPosition);
                        positions.Remove(asset.Id);
                    }

                    var sellTradeId = Guid.NewGuid();
                    _dbContext.Trades.Add(new Trade
                    {
                        Id = sellTradeId,
                        PortfolioId = portfolio.Id,
                        MarketAssetId = asset.Id,
                        ExecutedAt = now,
                        Quantity = order.Quantity,
                        Price = price,
                        Side = TradeSide.Sell
                    });
                    createdTradeIds.Add(sellTradeId);
                    break;

                case TradeSide.Hold:
                    // No-op: hold does not alter positions or cash.
                    break;

                default:
                    throw new InvalidOperationException($"Unsupported trade side '{order.Side}'.");
            }
        }

        portfolio.Cash = cash;
        portfolio.BaseCurrency ??= "USD";

        await _dbContext.SaveChangesAsync(cancellationToken);

        var state = await BuildPortfolioStateAsync(portfolio, captureSnapshot: true, cancellationToken);

        await transaction.CommitAsync(cancellationToken);
        return (state, createdTradeIds);
    }

    public async Task LinkTradesToDecisionAsync(
        IReadOnlyList<Guid> tradeIds,
        int decisionLogId,
        CancellationToken cancellationToken = default)
    {
        if (tradeIds.Count == 0) return;

        await _dbContext.Trades
            .Where(t => tradeIds.Contains(t.Id))
            .ExecuteUpdateAsync(
                s => s.SetProperty(t => t.DecisionLogId, decisionLogId),
                cancellationToken);
    }

    private async Task<Portfolio> GetOrCreatePortfolioAsync(Guid agentId, CancellationToken cancellationToken)
    {
        var portfolio = await _dbContext.Portfolios
            .Include(p => p.Positions)
            .SingleOrDefaultAsync(p => p.AgentId == agentId, cancellationToken);

        if (portfolio is not null)
        {
            return portfolio;
        }

        portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = agentId,
            Cash = DefaultStartingCash,
            BaseCurrency = "USD",
            Positions = new List<Position>()
        };

        _dbContext.Portfolios.Add(portfolio);
        await _dbContext.SaveChangesAsync(cancellationToken);

        return portfolio;
    }

    private async Task<MarketAsset> GetEnabledAssetAsync(string normalizedSymbol, CancellationToken cancellationToken)
    {
        var asset = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled)
            .SingleOrDefaultAsync(a => a.Symbol == normalizedSymbol, cancellationToken);

        if (asset is null)
        {
            throw new InvalidOperationException($"Asset '{normalizedSymbol}' is not enabled or does not exist.");
        }

        return asset;
    }

    private async Task<decimal> ResolvePriceAsync(
        Guid assetId,
        string normalizedSymbol,
        decimal? limitPrice,
        CancellationToken cancellationToken)
    {
        if (limitPrice.HasValue && limitPrice.Value > 0)
        {
            return limitPrice.Value;
        }

        var lastCandle = await _dbContext.MarketCandles
            .AsNoTracking()
            .Where(c => c.MarketAssetId == assetId)
            .OrderByDescending(c => c.TimestampUtc)
            .FirstOrDefaultAsync(cancellationToken);

        if (lastCandle is null)
        {
            throw new InvalidOperationException($"No price available for {normalizedSymbol}. Provide a limit price or ingest market data first.");
        }

        return lastCandle.Close;
    }

    private async Task<PortfolioState> BuildPortfolioStateAsync(
        Portfolio portfolio,
        bool captureSnapshot,
        CancellationToken cancellationToken)
    {
        var positions = await _dbContext.Positions
            .Where(p => p.PortfolioId == portfolio.Id)
            .ToListAsync(cancellationToken);

        var assetIds = positions.Select(p => p.MarketAssetId).Distinct().ToList();

        var assets = await _dbContext.MarketAssets
            .Where(a => assetIds.Contains(a.Id))
            .ToDictionaryAsync(a => a.Id, cancellationToken);

        var latestPrices = await GetLatestPricesAsync(assetIds, cancellationToken);

        var positionSnapshots = new List<PositionSnapshot>();
        decimal unrealizedPnL = 0m;

        foreach (var position in positions)
        {
            assets.TryGetValue(position.MarketAssetId, out var asset);
            var symbol = asset?.Symbol ?? "UNKNOWN";
            var currentPrice = latestPrices.TryGetValue(position.MarketAssetId, out var price)
                ? price
                : position.AverageEntryPrice;

            positionSnapshots.Add(new PositionSnapshot(
                symbol,
                position.Quantity,
                position.AverageEntryPrice,
                currentPrice));

            unrealizedPnL += (currentPrice - position.AverageEntryPrice) * position.Quantity;
        }

        var totalValue = portfolio.Cash + positionSnapshots.Sum(p => p.Quantity * p.CurrentPrice);
        var asOf = DateTimeOffset.UtcNow;

        if (captureSnapshot)
        {
            _dbContext.EquitySnapshots.Add(new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = asOf,
                TotalValue = totalValue,
                UnrealizedPnL = unrealizedPnL
            });

            await _dbContext.SaveChangesAsync(cancellationToken);
        }

        return new PortfolioState(
            portfolio.Id,
            portfolio.AgentId,
            portfolio.Cash,
            positionSnapshots,
            asOf,
            totalValue);
    }

    private async Task<Dictionary<Guid, decimal>> GetLatestPricesAsync(
        IReadOnlyCollection<Guid> assetIds,
        CancellationToken cancellationToken)
    {
        if (assetIds.Count == 0)
        {
            return new Dictionary<Guid, decimal>();
        }

        var latestCandles = await _dbContext.MarketCandles
            .AsNoTracking()
            .Where(c => assetIds.Contains(c.MarketAssetId))
            .OrderByDescending(c => c.TimestampUtc)
            .ToListAsync(cancellationToken);

        return latestCandles
            .GroupBy(c => c.MarketAssetId)
            .ToDictionary(
                g => g.Key,
                g => g.OrderByDescending(c => c.TimestampUtc).First().Close);
    }

    private static decimal CalculateNewAveragePrice(Position existing, decimal newNotional, decimal newQuantity)
    {
        var totalCost = (existing.AverageEntryPrice * existing.Quantity) + newNotional;
        var totalQuantity = existing.Quantity + newQuantity;

        return totalQuantity <= 0 ? existing.AverageEntryPrice : totalCost / totalQuantity;
    }
}

