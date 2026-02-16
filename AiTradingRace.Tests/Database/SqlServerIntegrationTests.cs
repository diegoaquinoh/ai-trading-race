using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Equity;
using AiTradingRace.Infrastructure.Portfolios;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using Testcontainers.MsSql;

namespace AiTradingRace.Tests.Database;

/// <summary>
/// Integration tests that run against a real SQL Server instance in Docker.
/// These tests verify that migrations apply correctly and the schema matches entity definitions.
/// </summary>
/// <remarks>
/// These tests require Docker to be running. They use Testcontainers to spin up
/// an ephemeral SQL Server container for each test class run.
/// </remarks>
public class SqlServerIntegrationTests : IAsyncLifetime
{
    private readonly MsSqlContainer _sqlContainer;
    private TradingDbContext _dbContext = null!;

    public SqlServerIntegrationTests()
    {
        _sqlContainer = new MsSqlBuilder()
            .WithImage("mcr.microsoft.com/mssql/server:2022-latest")
            .Build();
    }

    public async Task InitializeAsync()
    {
        await _sqlContainer.StartAsync();

        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseSqlServer(_sqlContainer.GetConnectionString())
            .Options;

        _dbContext = new TradingDbContext(options);

        // Apply migrations - this is the key test!
        await _dbContext.Database.MigrateAsync();
    }

    public async Task DisposeAsync()
    {
        await _dbContext.DisposeAsync();
        await _sqlContainer.DisposeAsync();
    }

    #region Migration Verification Tests

    [Fact]
    public void Migrations_ApplySuccessfully()
    {
        // If we get here, InitializeAsync succeeded which means migrations applied
        Assert.True(true);
    }

    [Fact]
    public async Task SeedData_AgentsAreCreated()
    {
        var agents = await _dbContext.Agents.ToListAsync();

        Assert.True(agents.Count >= 3, $"Expected at least 3 agents, got {agents.Count}");
        Assert.Contains(agents, a => a.Name == "Llama-70B");
        Assert.Contains(agents, a => a.Name == "Claude");
        Assert.Contains(agents, a => a.Name == "Grok");
    }

    [Fact]
    public async Task SeedData_MarketAssetsAreCreated()
    {
        var assets = await _dbContext.MarketAssets.ToListAsync();

        Assert.Equal(2, assets.Count);
        Assert.Contains(assets, a => a.Symbol == "BTC" && a.ExternalId == "bitcoin");
        Assert.Contains(assets, a => a.Symbol == "ETH" && a.ExternalId == "ethereum");
    }

    #endregion

    #region Schema Verification Tests

    [Fact]
    public async Task EquitySnapshots_HasAllRequiredColumns()
    {
        // Create a portfolio first (required for FK)
        var agent = await _dbContext.Agents.FirstAsync();
        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = agent.Id,
            Cash = 100000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);
        await _dbContext.SaveChangesAsync();

        // Create an equity snapshot with ALL fields
        var snapshot = new EquitySnapshot
        {
            Id = Guid.NewGuid(),
            PortfolioId = portfolio.Id,
            CapturedAt = DateTimeOffset.UtcNow,
            TotalValue = 100000m,
            CashValue = 80000m,
            PositionsValue = 20000m,
            UnrealizedPnL = 500m
        };

        _dbContext.EquitySnapshots.Add(snapshot);
        await _dbContext.SaveChangesAsync();

        // Read it back to verify all columns work
        var retrieved = await _dbContext.EquitySnapshots
            .FirstOrDefaultAsync(s => s.Id == snapshot.Id);

        Assert.NotNull(retrieved);
        Assert.Equal(100000m, retrieved.TotalValue);
        Assert.Equal(80000m, retrieved.CashValue);
        Assert.Equal(20000m, retrieved.PositionsValue);
        Assert.Equal(500m, retrieved.UnrealizedPnL);
    }

    [Fact]
    public async Task Trades_CanBeCreatedAndQueried()
    {
        var agent = await _dbContext.Agents.FirstAsync();
        var asset = await _dbContext.MarketAssets.FirstAsync(a => a.Symbol == "BTC");

        var portfolio = new Portfolio
        {
            Id = Guid.NewGuid(),
            AgentId = agent.Id,
            Cash = 100000m,
            BaseCurrency = "USD"
        };
        _dbContext.Portfolios.Add(portfolio);

        var trade = new Trade
        {
            Id = Guid.NewGuid(),
            PortfolioId = portfolio.Id,
            MarketAssetId = asset.Id,
            Side = TradeSide.Buy,
            Quantity = 1m,
            Price = 42000m,
            ExecutedAt = DateTimeOffset.UtcNow
        };
        _dbContext.Trades.Add(trade);

        await _dbContext.SaveChangesAsync();

        var retrieved = await _dbContext.Trades
            .Include(t => t.MarketAsset)
            .FirstOrDefaultAsync(t => t.Id == trade.Id);

        Assert.NotNull(retrieved);
        Assert.Equal(TradeSide.Buy, retrieved.Side);
        Assert.Equal(1m, retrieved.Quantity);
        Assert.Equal("BTC", retrieved.MarketAsset.Symbol);
    }

    #endregion

    #region Service Integration Tests

    [Fact]
    public async Task EquityService_CapturesSnapshot_WithRealDatabase()
    {
        var agent = await _dbContext.Agents.FirstAsync();
        var equityService = new EquityService(
            _dbContext,
            new Mock<ILogger<EquityService>>().Object);

        var snapshot = await equityService.CaptureSnapshotAsync(agent.Id);

        Assert.NotNull(snapshot);
        Assert.Equal(100000m, snapshot.TotalValue);
        Assert.Equal(100000m, snapshot.CashValue);
        Assert.Equal(0m, snapshot.PositionsValue);
    }

    [Fact]
    public async Task PortfolioService_ExecutesTrade_WithRealDatabase()
    {
        var agent = await _dbContext.Agents.FirstAsync();
        var asset = await _dbContext.MarketAssets.FirstAsync(a => a.Symbol == "BTC");

        // Add market data for price lookup
        _dbContext.MarketCandles.Add(new MarketCandle
        {
            Id = Guid.NewGuid(),
            MarketAssetId = asset.Id,
            TimestampUtc = DateTimeOffset.UtcNow,
            Open = 42000m,
            High = 43000m,
            Low = 41000m,
            Close = 42000m,
            Volume = 1000m
        });
        await _dbContext.SaveChangesAsync();

        var portfolioService = new EfPortfolioService(_dbContext);

        // Execute a buy trade
        var decision = new AgentDecision(
            agent.Id,
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.5m, 42000m)
            });

        var portfolio = await portfolioService.ApplyDecisionAsync(agent.Id, decision);

        Assert.Equal(79000m, portfolio.Cash); // 100k - (0.5 * 42k)
        Assert.Single(portfolio.Positions);
        Assert.Equal(0.5m, portfolio.Positions[0].Quantity);
    }

    #endregion
}
