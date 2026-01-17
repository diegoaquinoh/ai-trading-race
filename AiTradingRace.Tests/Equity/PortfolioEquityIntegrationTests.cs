using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Equity;
using AiTradingRace.Infrastructure.Portfolios;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Equity;

/// <summary>
/// Integration tests for portfolio and equity operations.
/// Tests the full flow from portfolio creation through trade execution to equity snapshots.
/// </summary>
public class PortfolioEquityIntegrationTests : IDisposable
{
    private readonly TradingDbContext _dbContext;
    private readonly EfPortfolioService _portfolioService;
    private readonly EquityService _equityService;

    private readonly Guid _agentId = Guid.NewGuid();
    private readonly Guid _btcAssetId = Guid.NewGuid();
    private readonly Guid _ethAssetId = Guid.NewGuid();

    public PortfolioEquityIntegrationTests()
    {
        var dbOptions = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .ConfigureWarnings(w => w.Ignore(InMemoryEventId.TransactionIgnoredWarning))
            .Options;

        _dbContext = new TradingDbContext(dbOptions);
        _portfolioService = new EfPortfolioService(_dbContext);
        _equityService = new EquityService(
            _dbContext,
            new Mock<ILogger<EquityService>>().Object);

        SeedData();
    }

    private void SeedData()
    {
        // Seed agent
        _dbContext.Agents.Add(new Agent
        {
            Id = _agentId,
            Name = "IntegrationTestAgent",
            Provider = "Test",
            IsActive = true
        });

        // Seed market assets
        _dbContext.MarketAssets.AddRange(
            new MarketAsset
            {
                Id = _btcAssetId,
                Symbol = "BTC",
                Name = "Bitcoin",
                ExternalId = "bitcoin",
                QuoteCurrency = "USD",
                IsEnabled = true
            },
            new MarketAsset
            {
                Id = _ethAssetId,
                Symbol = "ETH",
                Name = "Ethereum",
                ExternalId = "ethereum",
                QuoteCurrency = "USD",
                IsEnabled = true
            });

        // Seed market candles for price lookup (multiple to ensure latest is used)
        _dbContext.MarketCandles.AddRange(
            new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = _btcAssetId,
                TimestampUtc = DateTimeOffset.UtcNow.AddHours(-2),
                Open = 41000m,
                High = 41500m,
                Low = 40800m,
                Close = 41000m,
                Volume = 1000m
            },
            new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = _btcAssetId,
                TimestampUtc = DateTimeOffset.UtcNow.AddHours(-1),
                Open = 41000m,
                High = 42500m,
                Low = 41000m,
                Close = 42000m, // Latest BTC price
                Volume = 1500m
            },
            new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = _ethAssetId,
                TimestampUtc = DateTimeOffset.UtcNow.AddHours(-1),
                Open = 3100m,
                High = 3250m,
                Low = 3100m,
                Close = 3200m, // Latest ETH price
                Volume = 500m
            });

        _dbContext.SaveChanges();
    }

    public void Dispose()
    {
        _dbContext.Dispose();
    }

    [Fact]
    public async Task FullFlow_CreatePortfolio_ExecuteTrades_CaptureSnapshot()
    {
        // Step 1: Get initial portfolio (should auto-create)
        var initialPortfolio = await _portfolioService.GetPortfolioAsync(_agentId);
        Assert.Equal(100_000m, initialPortfolio.Cash);
        Assert.Empty(initialPortfolio.Positions);

        // Step 2: Execute buy trade
        var buyDecision = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 1m, 42000m)
            });

        var afterBuy = await _portfolioService.ApplyDecisionAsync(_agentId, buyDecision);

        Assert.Equal(58_000m, afterBuy.Cash); // 100k - 42k
        Assert.Single(afterBuy.Positions);
        Assert.Equal(1m, afterBuy.Positions[0].Quantity);
        Assert.Equal("BTC", afterBuy.Positions[0].AssetSymbol);

        // Step 3: Capture equity snapshot
        var snapshot = await _equityService.CaptureSnapshotAsync(_agentId);

        Assert.Equal(58_000m, snapshot.CashValue);
        Assert.Equal(42_000m, snapshot.PositionsValue); // 1 BTC @ $42k
        Assert.Equal(100_000m, snapshot.TotalValue); // Total unchanged (bought at current price)
        Assert.Equal(0m, snapshot.UnrealizedPnL); // No gain/loss yet
    }

    [Fact]
    public async Task TradeExecution_PositivePnL_ReflectedInSnapshot()
    {
        // Step 1: Buy BTC at a lower price (using limit)
        var buyDecision = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 1m, 40000m) // Buy below market
            });

        await _portfolioService.ApplyDecisionAsync(_agentId, buyDecision);

        // Step 2: Capture snapshot (current market price is $42k)
        var snapshot = await _equityService.CaptureSnapshotAsync(_agentId);

        // BTC position now worth $42k (bought at $40k)
        Assert.Equal(42_000m, snapshot.PositionsValue);
        Assert.Equal(2_000m, snapshot.UnrealizedPnL); // +$2k profit
        Assert.Equal(102_000m, snapshot.TotalValue); // 60k cash + 42k positions
    }

    [Fact]
    public async Task TradeExecution_NegativePnL_ReflectedInSnapshot()
    {
        // Step 1: Buy BTC at a higher price (using limit)
        var buyDecision = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 1m, 44000m) // Buy above market
            });

        await _portfolioService.ApplyDecisionAsync(_agentId, buyDecision);

        // Step 2: Capture snapshot (current market price is $42k)
        var snapshot = await _equityService.CaptureSnapshotAsync(_agentId);

        // BTC position now worth $42k (bought at $44k)
        Assert.Equal(42_000m, snapshot.PositionsValue);
        Assert.Equal(-2_000m, snapshot.UnrealizedPnL); // -$2k loss
        Assert.Equal(98_000m, snapshot.TotalValue); // 56k cash + 42k positions
    }

    [Fact]
    public async Task MultipleTrades_PositionAveraging_CorrectPnL()
    {
        // Step 1: Buy BTC in two tranches
        var buy1 = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.5m, 40000m)
            });
        await _portfolioService.ApplyDecisionAsync(_agentId, buy1);

        var buy2 = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.5m, 44000m)
            });
        await _portfolioService.ApplyDecisionAsync(_agentId, buy2);

        // Average entry: (0.5 * 40k + 0.5 * 44k) / 1 = $42k
        // Step 2: Check portfolio
        var portfolio = await _portfolioService.GetPortfolioAsync(_agentId);
        Assert.Single(portfolio.Positions);
        Assert.Equal(1m, portfolio.Positions[0].Quantity);
        Assert.Equal(42000m, portfolio.Positions[0].AveragePrice);

        // Step 3: Snapshot should show 0 PnL (avg = market)
        var snapshot = await _equityService.CaptureSnapshotAsync(_agentId);
        Assert.Equal(0m, snapshot.UnrealizedPnL);
    }

    [Fact]
    public async Task SellTrade_ReducesPosition_UpdatesSnapshot()
    {
        // Step 1: Buy 2 BTC
        var buy = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 2m, 40000m)
            });
        await _portfolioService.ApplyDecisionAsync(_agentId, buy);

        // Step 2: Sell 1 BTC at profit
        var sell = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Sell, 1m, 42000m) // Sell at market
            });
        var afterSell = await _portfolioService.ApplyDecisionAsync(_agentId, sell);

        Assert.Equal(62_000m, afterSell.Cash); // 100k - 80k (buy 2 BTC) + 42k (sell 1 BTC)
        Assert.Equal(1m, afterSell.Positions[0].Quantity); // 1 BTC remaining

        // Step 3: Capture snapshot
        var snapshot = await _equityService.CaptureSnapshotAsync(_agentId);
        Assert.Equal(62_000m, snapshot.CashValue);
        Assert.Equal(42_000m, snapshot.PositionsValue); // 1 BTC @ market
        Assert.Equal(104_000m, snapshot.TotalValue); // 62k + 42k
        Assert.Equal(2_000m, snapshot.UnrealizedPnL); // Remaining BTC has $2k profit
    }

    [Fact]
    public async Task EquityCurve_TracksPortfolioOverTime()
    {
        // Step 1: Initial snapshot
        await _equityService.CaptureSnapshotAsync(_agentId);

        // Step 2: Execute profitable trade
        var buy = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 1m, 40000m)
            });
        await _portfolioService.ApplyDecisionAsync(_agentId, buy);

        // Step 3: Second snapshot (with profit)
        await _equityService.CaptureSnapshotAsync(_agentId);

        // Step 4: Get equity curve
        // Note: ApplyDecisionAsync also captures a snapshot, so we have 3 total
        var curve = await _equityService.GetEquityCurveAsync(_agentId);

        Assert.Equal(3, curve.Count);
        Assert.Equal(100_000m, curve[0].TotalValue); // Initial
        Assert.Equal(102_000m, curve[2].TotalValue); // +$2k profit
    }

    [Fact]
    public async Task MultipleAssets_Portfolio_CorrectValuation()
    {
        // Buy both BTC and ETH
        var decision = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 1m, 42000m),
                new("ETH", TradeSide.Buy, 10m, 3200m)
            });

        var portfolio = await _portfolioService.ApplyDecisionAsync(_agentId, decision);

        // Cash: 100k - 42k - 32k = 26k
        Assert.Equal(26_000m, portfolio.Cash);
        Assert.Equal(2, portfolio.Positions.Count);

        // Snapshot
        var snapshot = await _equityService.CaptureSnapshotAsync(_agentId);

        // Positions: 1 BTC @ 42k + 10 ETH @ 3.2k = 42k + 32k = 74k
        Assert.Equal(74_000m, snapshot.PositionsValue);
        Assert.Equal(100_000m, snapshot.TotalValue); // 26k + 74k
        Assert.Equal(0m, snapshot.UnrealizedPnL); // Bought at current prices
    }

    [Fact]
    public async Task InsufficientFunds_ThrowsException()
    {
        var decision = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 10m, 42000m) // $420k > $100k
            });

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => _portfolioService.ApplyDecisionAsync(_agentId, decision));
    }

    [Fact]
    public async Task InsufficientPosition_ThrowsException()
    {
        // Try to sell without owning
        var decision = new AgentDecision(
            _agentId,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Sell, 1m, null)
            });

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => _portfolioService.ApplyDecisionAsync(_agentId, decision));
    }

    [Fact]
    public async Task Performance_CalculatesAfterMultipleTrades()
    {
        // Execute several trades
        var buy1 = new AgentDecision(_agentId, DateTimeOffset.UtcNow,
            new List<TradeOrder> { new("BTC", TradeSide.Buy, 1m, 40000m) });
        await _portfolioService.ApplyDecisionAsync(_agentId, buy1);

        var sell1 = new AgentDecision(_agentId, DateTimeOffset.UtcNow,
            new List<TradeOrder> { new("BTC", TradeSide.Sell, 0.5m, 42000m) });
        await _portfolioService.ApplyDecisionAsync(_agentId, sell1);

        // Capture snapshot with profit
        await _equityService.CaptureSnapshotAsync(_agentId);

        // Get performance
        var metrics = await _equityService.CalculatePerformanceAsync(_agentId);

        Assert.Equal(2, metrics.TotalTrades);
        Assert.Equal(1, metrics.WinningTrades); // Sold above entry
        Assert.True(metrics.CurrentValue > 100_000m); // Made profit
    }
}
