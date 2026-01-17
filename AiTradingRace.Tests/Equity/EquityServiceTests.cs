using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Equity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Equity;

/// <summary>
/// Unit tests for EquityService.
/// Uses EF Core InMemory provider for database tests.
/// </summary>
public class EquityServiceTests : IDisposable
{
    private readonly TradingDbContext _dbContext;
    private readonly Mock<ILogger<EquityService>> _loggerMock;
    private readonly EquityService _service;

    private readonly Guid _agentId = Guid.NewGuid();
    private readonly Guid _btcAssetId = Guid.NewGuid();
    private readonly Guid _ethAssetId = Guid.NewGuid();

    public EquityServiceTests()
    {
        var dbOptions = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _dbContext = new TradingDbContext(dbOptions);
        _loggerMock = new Mock<ILogger<EquityService>>();
        _service = new EquityService(_dbContext, _loggerMock.Object);

        SeedData();
    }

    private void SeedData()
    {
        // Seed agent
        _dbContext.Agents.Add(new Agent
        {
            Id = _agentId,
            Name = "TestAgent",
            Strategy = "Test Strategy",
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

        // Seed market candles for price lookup
        _dbContext.MarketCandles.AddRange(
            new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = _btcAssetId,
                TimestampUtc = DateTimeOffset.UtcNow.AddHours(-1),
                Open = 42000m,
                High = 42500m,
                Low = 41800m,
                Close = 42000m,
                Volume = 1000m
            },
            new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = _ethAssetId,
                TimestampUtc = DateTimeOffset.UtcNow.AddHours(-1),
                Open = 3200m,
                High = 3250m,
                Low = 3180m,
                Close = 3200m,
                Volume = 500m
            });

        _dbContext.SaveChanges();
    }

    public void Dispose()
    {
        _dbContext.Dispose();
    }

    #region CaptureSnapshotAsync Tests

    [Fact]
    public async Task CaptureSnapshotAsync_CreatesPortfolioIfNotExists()
    {
        // Act
        var snapshot = await _service.CaptureSnapshotAsync(_agentId);

        // Assert
        Assert.NotNull(snapshot);
        Assert.Equal(_agentId, snapshot.AgentId);
        Assert.Equal(100_000m, snapshot.TotalValue); // Default starting cash
        Assert.Equal(100_000m, snapshot.CashValue);
        Assert.Equal(0m, snapshot.PositionsValue);
        Assert.Equal(0m, snapshot.UnrealizedPnL);

        // Verify portfolio was created
        var portfolio = await _dbContext.Portfolios.FirstOrDefaultAsync(p => p.AgentId == _agentId);
        Assert.NotNull(portfolio);
        Assert.Equal(100_000m, portfolio.Cash);
    }

    [Fact]
    public async Task CaptureSnapshotAsync_CalculatesPositionsValue()
    {
        // Arrange - Create portfolio with positions
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 50_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        _dbContext.Positions.Add(new Position
        {
            Id = Guid.NewGuid(),
            PortfolioId = portfolio.Id,
            MarketAssetId = _btcAssetId,
            Quantity = 1m,
            AverageEntryPrice = 40000m
        });
        await _dbContext.SaveChangesAsync();

        // Act
        var snapshot = await _service.CaptureSnapshotAsync(_agentId);

        // Assert
        Assert.Equal(50_000m, snapshot.CashValue);
        Assert.Equal(42000m, snapshot.PositionsValue); // 1 BTC @ $42,000
        Assert.Equal(92_000m, snapshot.TotalValue); // 50k + 42k
        Assert.Equal(2000m, snapshot.UnrealizedPnL); // Entry 40k, current 42k = +2k
    }

    [Fact]
    public async Task CaptureSnapshotAsync_PersistsToDatabase()
    {
        // Act
        var snapshot = await _service.CaptureSnapshotAsync(_agentId);

        // Assert
        var dbSnapshot = await _dbContext.EquitySnapshots.FirstOrDefaultAsync(s => s.Id == snapshot.Id);
        Assert.NotNull(dbSnapshot);
        Assert.Equal(snapshot.TotalValue, dbSnapshot.TotalValue);
        Assert.Equal(snapshot.CashValue, dbSnapshot.CashValue);
        Assert.Equal(snapshot.PositionsValue, dbSnapshot.PositionsValue);
    }

    #endregion

    #region GetEquityCurveAsync Tests

    [Fact]
    public async Task GetEquityCurveAsync_ReturnsEmptyForNewAgent()
    {
        // Act
        var curve = await _service.GetEquityCurveAsync(Guid.NewGuid());

        // Assert
        Assert.Empty(curve);
    }

    [Fact]
    public async Task GetEquityCurveAsync_ReturnsOrderedSnapshots()
    {
        // Arrange - Create portfolio and snapshots
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 100_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var now = DateTimeOffset.UtcNow;
        _dbContext.EquitySnapshots.AddRange(
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-2),
                TotalValue = 100_000m,
                CashValue = 100_000m,
                PositionsValue = 0m,
                UnrealizedPnL = 0m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-1),
                TotalValue = 105_000m,
                CashValue = 55_000m,
                PositionsValue = 50_000m,
                UnrealizedPnL = 5_000m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now,
                TotalValue = 110_000m,
                CashValue = 60_000m,
                PositionsValue = 50_000m,
                UnrealizedPnL = 10_000m
            });
        await _dbContext.SaveChangesAsync();

        // Act
        var curve = await _service.GetEquityCurveAsync(_agentId);

        // Assert
        Assert.Equal(3, curve.Count);
        Assert.True(curve[0].CapturedAt < curve[1].CapturedAt);
        Assert.True(curve[1].CapturedAt < curve[2].CapturedAt);
    }

    [Fact]
    public async Task GetEquityCurveAsync_FiltersbyDateRange()
    {
        // Arrange
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 100_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var now = DateTimeOffset.UtcNow;
        _dbContext.EquitySnapshots.AddRange(
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-5),
                TotalValue = 100_000m,
                CashValue = 100_000m,
                PositionsValue = 0m,
                UnrealizedPnL = 0m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-2),
                TotalValue = 105_000m,
                CashValue = 100_000m,
                PositionsValue = 5_000m,
                UnrealizedPnL = 5_000m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now,
                TotalValue = 110_000m,
                CashValue = 100_000m,
                PositionsValue = 10_000m,
                UnrealizedPnL = 10_000m
            });
        await _dbContext.SaveChangesAsync();

        // Act - Filter to last 3 days
        var curve = await _service.GetEquityCurveAsync(
            _agentId,
            from: now.AddDays(-3),
            to: now.AddDays(1));

        // Assert
        Assert.Equal(2, curve.Count);
    }

    [Fact]
    public async Task GetEquityCurveAsync_CalculatesPercentChange()
    {
        // Arrange
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 100_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var now = DateTimeOffset.UtcNow;
        _dbContext.EquitySnapshots.AddRange(
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-1),
                TotalValue = 100_000m,
                CashValue = 100_000m,
                PositionsValue = 0m,
                UnrealizedPnL = 0m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now,
                TotalValue = 110_000m,
                CashValue = 100_000m,
                PositionsValue = 10_000m,
                UnrealizedPnL = 10_000m
            });
        await _dbContext.SaveChangesAsync();

        // Act
        var curve = await _service.GetEquityCurveAsync(_agentId);

        // Assert
        Assert.Equal(0m, curve[0].PercentChange); // First snapshot = 0%
        Assert.Equal(10m, curve[1].PercentChange); // 10% gain
    }

    #endregion

    #region GetLatestSnapshotAsync Tests

    [Fact]
    public async Task GetLatestSnapshotAsync_ReturnsNullForNewAgent()
    {
        // Act
        var snapshot = await _service.GetLatestSnapshotAsync(Guid.NewGuid());

        // Assert
        Assert.Null(snapshot);
    }

    [Fact]
    public async Task GetLatestSnapshotAsync_ReturnsMostRecentSnapshot()
    {
        // Arrange
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 100_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var now = DateTimeOffset.UtcNow;
        var latestSnapshotId = Guid.NewGuid();
        _dbContext.EquitySnapshots.AddRange(
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-1),
                TotalValue = 100_000m,
                CashValue = 100_000m,
                PositionsValue = 0m,
                UnrealizedPnL = 0m
            },
            new EquitySnapshot
            {
                Id = latestSnapshotId,
                PortfolioId = portfolio.Id,
                CapturedAt = now,
                TotalValue = 110_000m,
                CashValue = 100_000m,
                PositionsValue = 10_000m,
                UnrealizedPnL = 10_000m
            });
        await _dbContext.SaveChangesAsync();

        // Act
        var snapshot = await _service.GetLatestSnapshotAsync(_agentId);

        // Assert
        Assert.NotNull(snapshot);
        Assert.Equal(latestSnapshotId, snapshot.Id);
        Assert.Equal(110_000m, snapshot.TotalValue);
    }

    #endregion

    #region CalculatePerformanceAsync Tests

    [Fact]
    public async Task CalculatePerformanceAsync_ReturnsDefaultsForNewAgent()
    {
        // Act
        var metrics = await _service.CalculatePerformanceAsync(Guid.NewGuid());

        // Assert
        Assert.Equal(100_000m, metrics.InitialValue);
        Assert.Equal(100_000m, metrics.CurrentValue);
        Assert.Equal(0m, metrics.TotalReturn);
        Assert.Equal(0m, metrics.PercentReturn);
        Assert.Equal(0m, metrics.MaxDrawdown);
        Assert.Equal(0, metrics.TotalTrades);
    }

    [Fact]
    public async Task CalculatePerformanceAsync_CalculatesReturns()
    {
        // Arrange
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 100_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var now = DateTimeOffset.UtcNow;
        _dbContext.EquitySnapshots.AddRange(
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-2),
                TotalValue = 100_000m,
                CashValue = 100_000m,
                PositionsValue = 0m,
                UnrealizedPnL = 0m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now,
                TotalValue = 120_000m,
                CashValue = 70_000m,
                PositionsValue = 50_000m,
                UnrealizedPnL = 20_000m
            });
        await _dbContext.SaveChangesAsync();

        // Act
        var metrics = await _service.CalculatePerformanceAsync(_agentId);

        // Assert
        Assert.Equal(100_000m, metrics.InitialValue);
        Assert.Equal(120_000m, metrics.CurrentValue);
        Assert.Equal(20_000m, metrics.TotalReturn);
        Assert.Equal(20m, metrics.PercentReturn); // 20%
    }

    [Fact]
    public async Task CalculatePerformanceAsync_CalculatesMaxDrawdown()
    {
        // Arrange
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 100_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var now = DateTimeOffset.UtcNow;
        _dbContext.EquitySnapshots.AddRange(
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-3),
                TotalValue = 100_000m, // Initial
                CashValue = 100_000m,
                PositionsValue = 0m,
                UnrealizedPnL = 0m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-2),
                TotalValue = 120_000m, // Peak
                CashValue = 100_000m,
                PositionsValue = 20_000m,
                UnrealizedPnL = 20_000m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now.AddDays(-1),
                TotalValue = 90_000m, // Drawdown (25% from peak)
                CashValue = 100_000m,
                PositionsValue = -10_000m,
                UnrealizedPnL = -10_000m
            },
            new EquitySnapshot
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                CapturedAt = now,
                TotalValue = 110_000m, // Recovery
                CashValue = 100_000m,
                PositionsValue = 10_000m,
                UnrealizedPnL = 10_000m
            });
        await _dbContext.SaveChangesAsync();

        // Act
        var metrics = await _service.CalculatePerformanceAsync(_agentId);

        // Assert
        Assert.Equal(25m, metrics.MaxDrawdown); // 25% drawdown from 120k to 90k
    }

    [Fact]
    public async Task CalculatePerformanceAsync_CalculatesTradeStats()
    {
        // Arrange
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = _agentId,
            Cash = 100_000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var now = DateTimeOffset.UtcNow;
        _dbContext.Trades.AddRange(
            // Buy BTC at 40k
            new Trade
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                MarketAssetId = _btcAssetId,
                ExecutedAt = now.AddDays(-3),
                Quantity = 1m,
                Price = 40_000m,
                Side = TradeSide.Buy
            },
            // Sell BTC at 42k (winning trade)
            new Trade
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                MarketAssetId = _btcAssetId,
                ExecutedAt = now.AddDays(-2),
                Quantity = 0.5m,
                Price = 42_000m,
                Side = TradeSide.Sell
            },
            // Sell remaining BTC at 39k (losing trade)
            new Trade
            {
                Id = Guid.NewGuid(),
                PortfolioId = portfolio.Id,
                MarketAssetId = _btcAssetId,
                ExecutedAt = now.AddDays(-1),
                Quantity = 0.5m,
                Price = 39_000m,
                Side = TradeSide.Sell
            });
        await _dbContext.SaveChangesAsync();

        // Act
        var metrics = await _service.CalculatePerformanceAsync(_agentId);

        // Assert
        Assert.Equal(3, metrics.TotalTrades);
        Assert.Equal(1, metrics.WinningTrades);
        Assert.Equal(1, metrics.LosingTrades);
        // Win rate is calculated as winningTrades / totalTrades * 100
        // 1 winning trade out of 3 total trades = 33.33%
        Assert.True(metrics.WinRate > 33m && metrics.WinRate < 34m);
    }

    #endregion

    #region CaptureAllSnapshotsAsync Tests

    [Fact]
    public async Task CaptureAllSnapshotsAsync_CapturesForAllActiveAgents()
    {
        // Arrange - Add another active agent
        var agent2Id = Guid.NewGuid();
        _dbContext.Agents.Add(new Agent
        {
            Id = agent2Id,
            Name = "TestAgent2",
            Strategy = "Test Strategy 2",
            IsActive = true
        });
        await _dbContext.SaveChangesAsync();

        // Act
        var count = await _service.CaptureAllSnapshotsAsync();

        // Assert
        Assert.Equal(2, count); // Both agents
        Assert.Equal(2, await _dbContext.EquitySnapshots.CountAsync());
    }

    [Fact]
    public async Task CaptureAllSnapshotsAsync_SkipsInactiveAgents()
    {
        // Arrange - Deactivate the agent
        var agent = await _dbContext.Agents.FirstAsync(a => a.Id == _agentId);
        agent.IsActive = false;
        await _dbContext.SaveChangesAsync();

        // Act
        var count = await _service.CaptureAllSnapshotsAsync();

        // Assert
        Assert.Equal(0, count);
        Assert.Equal(0, await _dbContext.EquitySnapshots.CountAsync());
    }

    #endregion
}
