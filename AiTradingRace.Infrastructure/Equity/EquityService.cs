using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Equity;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.Equity;

/// <summary>
/// EF Core implementation of IEquityService for managing equity snapshots and performance metrics.
/// </summary>
public sealed class EquityService : IEquityService
{
    private const decimal DefaultStartingValue = 100_000m;

    private readonly TradingDbContext _dbContext;
    private readonly ILogger<EquityService> _logger;

    public EquityService(TradingDbContext dbContext, ILogger<EquityService> logger)
    {
        _dbContext = dbContext;
        _logger = logger;
    }

    /// <inheritdoc />
    public async Task<EquitySnapshotDto> CaptureSnapshotAsync(
        Guid agentId,
        CancellationToken ct = default)
    {
        var portfolio = await _dbContext.Portfolios
            .Include(p => p.Positions)
            .FirstOrDefaultAsync(p => p.AgentId == agentId, ct);

        if (portfolio is null)
        {
            _logger.LogWarning("No portfolio found for agent {AgentId}, creating one with default cash", agentId);
            portfolio = await CreatePortfolioAsync(agentId, ct);
        }

        var latestPrices = await GetLatestPricesAsync(ct);

        decimal positionsValue = 0m;
        decimal unrealizedPnL = 0m;

        foreach (var position in portfolio.Positions)
        {
            if (latestPrices.TryGetValue(position.MarketAssetId, out var price))
            {
                var posValue = position.Quantity * price;
                positionsValue += posValue;
                unrealizedPnL += (price - position.AverageEntryPrice) * position.Quantity;
            }
            else
            {
                // Use average entry price if no market data available
                positionsValue += position.Quantity * position.AverageEntryPrice;
            }
        }

        var totalValue = portfolio.Cash + positionsValue;

        var snapshot = new EquitySnapshot
        {
            Id = Guid.NewGuid(),
            PortfolioId = portfolio.Id,
            CapturedAt = DateTimeOffset.UtcNow,
            TotalValue = totalValue,
            CashValue = portfolio.Cash,
            PositionsValue = positionsValue,
            UnrealizedPnL = unrealizedPnL
        };

        _dbContext.EquitySnapshots.Add(snapshot);
        await _dbContext.SaveChangesAsync(ct);

        _logger.LogInformation(
            "Captured equity snapshot for agent {AgentId}: Total={TotalValue}, Cash={Cash}, Positions={Positions}",
            agentId, totalValue, portfolio.Cash, positionsValue);

        // Calculate percent change from first snapshot
        var firstSnapshot = await _dbContext.EquitySnapshots
            .Where(s => s.PortfolioId == portfolio.Id)
            .OrderBy(s => s.CapturedAt)
            .FirstOrDefaultAsync(ct);

        decimal? percentChange = firstSnapshot is not null && firstSnapshot.TotalValue > 0
            ? (totalValue - firstSnapshot.TotalValue) / firstSnapshot.TotalValue * 100
            : null;

        return new EquitySnapshotDto(
            snapshot.Id,
            snapshot.PortfolioId,
            agentId,
            snapshot.CapturedAt,
            snapshot.TotalValue,
            snapshot.CashValue,
            snapshot.PositionsValue,
            snapshot.UnrealizedPnL,
            percentChange);
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<EquitySnapshotDto>> GetEquityCurveAsync(
        Guid agentId,
        DateTimeOffset? from = null,
        DateTimeOffset? to = null,
        CancellationToken ct = default)
    {
        var portfolio = await _dbContext.Portfolios
            .AsNoTracking()
            .FirstOrDefaultAsync(p => p.AgentId == agentId, ct);

        if (portfolio is null)
        {
            return Array.Empty<EquitySnapshotDto>();
        }

        var query = _dbContext.EquitySnapshots
            .AsNoTracking()
            .Where(s => s.PortfolioId == portfolio.Id);

        if (from.HasValue)
            query = query.Where(s => s.CapturedAt >= from.Value);

        if (to.HasValue)
            query = query.Where(s => s.CapturedAt <= to.Value);

        var snapshots = await query
            .OrderBy(s => s.CapturedAt)
            .ToListAsync(ct);

        if (snapshots.Count == 0)
        {
            return Array.Empty<EquitySnapshotDto>();
        }

        var firstValue = snapshots[0].TotalValue;

        return snapshots.Select(s => new EquitySnapshotDto(
            s.Id,
            s.PortfolioId,
            agentId,
            s.CapturedAt,
            s.TotalValue,
            s.CashValue,
            s.PositionsValue,
            s.UnrealizedPnL,
            firstValue > 0 ? (s.TotalValue - firstValue) / firstValue * 100 : null
        )).ToList();
    }

    /// <inheritdoc />
    public async Task<EquitySnapshotDto?> GetLatestSnapshotAsync(
        Guid agentId,
        CancellationToken ct = default)
    {
        var portfolio = await _dbContext.Portfolios
            .AsNoTracking()
            .FirstOrDefaultAsync(p => p.AgentId == agentId, ct);

        if (portfolio is null)
        {
            return null;
        }

        var latestSnapshot = await _dbContext.EquitySnapshots
            .AsNoTracking()
            .Where(s => s.PortfolioId == portfolio.Id)
            .OrderByDescending(s => s.CapturedAt)
            .FirstOrDefaultAsync(ct);

        if (latestSnapshot is null)
        {
            return null;
        }

        // Get first snapshot for percent change calculation
        var firstSnapshot = await _dbContext.EquitySnapshots
            .AsNoTracking()
            .Where(s => s.PortfolioId == portfolio.Id)
            .OrderBy(s => s.CapturedAt)
            .FirstOrDefaultAsync(ct);

        decimal? percentChange = firstSnapshot is not null && firstSnapshot.TotalValue > 0
            ? (latestSnapshot.TotalValue - firstSnapshot.TotalValue) / firstSnapshot.TotalValue * 100
            : null;

        return new EquitySnapshotDto(
            latestSnapshot.Id,
            latestSnapshot.PortfolioId,
            agentId,
            latestSnapshot.CapturedAt,
            latestSnapshot.TotalValue,
            latestSnapshot.CashValue,
            latestSnapshot.PositionsValue,
            latestSnapshot.UnrealizedPnL,
            percentChange);
    }

    /// <inheritdoc />
    public async Task<PerformanceMetrics> CalculatePerformanceAsync(
        Guid agentId,
        CancellationToken ct = default)
    {
        var portfolio = await _dbContext.Portfolios
            .AsNoTracking()
            .FirstOrDefaultAsync(p => p.AgentId == agentId, ct);

        if (portfolio is null)
        {
            return CreateDefaultMetrics(agentId);
        }

        // Get all snapshots for this portfolio
        var snapshots = await _dbContext.EquitySnapshots
            .AsNoTracking()
            .Where(s => s.PortfolioId == portfolio.Id)
            .OrderBy(s => s.CapturedAt)
            .ToListAsync(ct);

        // Get all trades for this portfolio
        var trades = await _dbContext.Trades
            .AsNoTracking()
            .Where(t => t.PortfolioId == portfolio.Id)
            .ToListAsync(ct);

        var initialValue = snapshots.Count > 0 ? snapshots[0].TotalValue : DefaultStartingValue;
        var currentValue = snapshots.Count > 0 ? snapshots[^1].TotalValue : DefaultStartingValue;

        var totalReturn = currentValue - initialValue;
        var percentReturn = initialValue > 0 ? totalReturn / initialValue * 100 : 0;

        var maxDrawdown = CalculateMaxDrawdown(snapshots);

        // Calculate win rate based on sell trades that realized profit
        var (winningTrades, losingTrades) = CalculateTradeOutcomes(trades);

        var totalTrades = trades.Count;
        var winRate = totalTrades > 0 ? (decimal)winningTrades / totalTrades * 100 : 0;

        return new PerformanceMetrics(
            agentId,
            initialValue,
            currentValue,
            totalReturn,
            percentReturn,
            maxDrawdown,
            null, // Sharpe ratio requires more complex calculation with risk-free rate
            totalTrades,
            winningTrades,
            losingTrades,
            winRate,
            DateTimeOffset.UtcNow);
    }

    /// <inheritdoc />
    public async Task<int> CaptureAllSnapshotsAsync(CancellationToken ct = default)
    {
        // Delegate to the batch version with generated values
        return await CaptureAllSnapshotsAsync(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            ct);
    }

    /// <inheritdoc />
    public async Task<int> CaptureAllSnapshotsAsync(
        Guid batchId,
        DateTimeOffset timestamp,
        CancellationToken ct = default)
    {
        var agents = await _dbContext.Agents
            .AsNoTracking()
            .Where(a => a.IsActive)
            .Select(a => a.Id)
            .ToListAsync(ct);

        // Get latest prices once for all agents
        var latestPrices = await GetLatestPricesAsync(ct);

        var count = 0;
        foreach (var agentId in agents)
        {
            try
            {
                await CaptureSnapshotInternalAsync(agentId, batchId, timestamp, latestPrices, ct);
                count++;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to capture snapshot for agent {AgentId}", agentId);
            }
        }

        _logger.LogInformation(
            "Captured {Count} equity snapshots for {Total} active agents. BatchId: {BatchId}, Timestamp: {Timestamp}",
            count, agents.Count, batchId, timestamp);
        return count;
    }

    /// <summary>
    /// Internal method to capture a snapshot with explicit batch and timestamp.
    /// </summary>
    private async Task CaptureSnapshotInternalAsync(
        Guid agentId,
        Guid batchId,
        DateTimeOffset timestamp,
        Dictionary<Guid, decimal> latestPrices,
        CancellationToken ct)
    {
        var portfolio = await _dbContext.Portfolios
            .Include(p => p.Positions)
            .FirstOrDefaultAsync(p => p.AgentId == agentId, ct);

        if (portfolio is null)
        {
            _logger.LogWarning("No portfolio found for agent {AgentId}, creating one with default cash", agentId);
            portfolio = await CreatePortfolioAsync(agentId, ct);
        }

        decimal positionsValue = 0m;
        decimal unrealizedPnL = 0m;

        foreach (var position in portfolio.Positions)
        {
            if (latestPrices.TryGetValue(position.MarketAssetId, out var price))
            {
                var posValue = position.Quantity * price;
                positionsValue += posValue;
                unrealizedPnL += (price - position.AverageEntryPrice) * position.Quantity;
            }
            else
            {
                // Use average entry price if no market data available
                positionsValue += position.Quantity * position.AverageEntryPrice;
            }
        }

        var totalValue = portfolio.Cash + positionsValue;

        var snapshot = new EquitySnapshot
        {
            Id = Guid.NewGuid(),
            PortfolioId = portfolio.Id,
            CapturedAt = timestamp,  // Use provided timestamp, not DateTimeOffset.UtcNow
            TotalValue = totalValue,
            CashValue = portfolio.Cash,
            PositionsValue = positionsValue,
            UnrealizedPnL = unrealizedPnL,
            BatchId = batchId  // Correlate with market data batch
        };

        _dbContext.EquitySnapshots.Add(snapshot);
        await _dbContext.SaveChangesAsync(ct);

        _logger.LogDebug(
            "Captured equity snapshot for agent {AgentId}: Total={TotalValue}, Cash={Cash}, Positions={Positions}, BatchId={BatchId}",
            agentId, totalValue, portfolio.Cash, positionsValue, batchId);
    }

    private async Task<Portfolio> CreatePortfolioAsync(Guid agentId, CancellationToken ct)
    {
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = agentId,
            Cash = DefaultStartingValue,
            BaseCurrency = "USD",
            Positions = new List<Position>()
        };

        _dbContext.Portfolios.Add(portfolio);
        await _dbContext.SaveChangesAsync(ct);

        return portfolio;
    }

    private async Task<Dictionary<Guid, decimal>> GetLatestPricesAsync(CancellationToken ct)
    {
        var latestCandles = await _dbContext.MarketCandles
            .AsNoTracking()
            .GroupBy(c => c.MarketAssetId)
            .Select(g => new
            {
                AssetId = g.Key,
                Price = g.OrderByDescending(c => c.TimestampUtc).First().Close
            })
            .ToListAsync(ct);

        return latestCandles.ToDictionary(x => x.AssetId, x => x.Price);
    }

    private static decimal CalculateMaxDrawdown(IReadOnlyList<EquitySnapshot> snapshots)
    {
        if (snapshots.Count < 2) return 0;

        decimal peak = snapshots[0].TotalValue;
        decimal maxDrawdown = 0;

        foreach (var snapshot in snapshots)
        {
            if (snapshot.TotalValue > peak)
                peak = snapshot.TotalValue;

            if (peak > 0)
            {
                var drawdown = (peak - snapshot.TotalValue) / peak;
                if (drawdown > maxDrawdown)
                    maxDrawdown = drawdown;
            }
        }

        return maxDrawdown * 100; // Return as percentage
    }

    private static (int winning, int losing) CalculateTradeOutcomes(
        IReadOnlyList<Trade> trades)
    {
        // Simple heuristic: count sell trades that executed above average entry price as winning
        var positionsAtTime = new Dictionary<Guid, (decimal qty, decimal avgPrice)>();
        int winning = 0;
        int losing = 0;

        // Get historical positions to track average entry prices
        var orderedTrades = trades.OrderBy(t => t.ExecutedAt).ToList();

        foreach (var trade in orderedTrades)
        {
            if (trade.Side == TradeSide.Buy)
            {
                if (positionsAtTime.TryGetValue(trade.MarketAssetId, out var pos))
                {
                    var newQty = pos.qty + trade.Quantity;
                    var newAvg = (pos.qty * pos.avgPrice + trade.Quantity * trade.Price) / newQty;
                    positionsAtTime[trade.MarketAssetId] = (newQty, newAvg);
                }
                else
                {
                    positionsAtTime[trade.MarketAssetId] = (trade.Quantity, trade.Price);
                }
            }
            else if (trade.Side == TradeSide.Sell)
            {
                if (positionsAtTime.TryGetValue(trade.MarketAssetId, out var pos))
                {
                    if (trade.Price > pos.avgPrice)
                        winning++;
                    else
                        losing++;

                    var newQty = pos.qty - trade.Quantity;
                    if (newQty > 0)
                        positionsAtTime[trade.MarketAssetId] = (newQty, pos.avgPrice);
                    else
                        positionsAtTime.Remove(trade.MarketAssetId);
                }
            }
        }

        return (winning, losing);
    }

    private static PerformanceMetrics CreateDefaultMetrics(Guid agentId)
    {
        return new PerformanceMetrics(
            agentId,
            DefaultStartingValue,
            DefaultStartingValue,
            0m,
            0m,
            0m,
            null,
            0,
            0,
            0,
            0m,
            DateTimeOffset.UtcNow);
    }
}
