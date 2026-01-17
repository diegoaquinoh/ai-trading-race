using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Agents;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;

namespace AiTradingRace.Tests.Agents;

/// <summary>
/// Unit tests for RiskValidator server-side risk enforcement.
/// </summary>
public class RiskValidatorTests : IDisposable
{
    private readonly TradingDbContext _dbContext;
    private readonly Mock<ILogger<RiskValidator>> _loggerMock;
    private readonly RiskValidatorOptions _defaultOptions;

    public RiskValidatorTests()
    {
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase($"RiskValidator_{Guid.NewGuid()}")
            .Options;
        _dbContext = new TradingDbContext(options);
        _loggerMock = new Mock<ILogger<RiskValidator>>();
        _defaultOptions = new RiskValidatorOptions
        {
            MaxPositionSizePercent = 0.50m,
            MinCashReserve = 100m,
            MaxSingleTradeValue = 5_000m,
            MinOrderValue = 10m,
            AllowedAssets = new List<string> { "BTC", "ETH" },
            MaxOrdersPerCycle = 5,
            AllowLeverage = false
        };

        SeedMarketData();
    }

    public void Dispose()
    {
        _dbContext.Dispose();
    }

    private void SeedMarketData()
    {
        var btc = new MarketAsset
        {
            Id = Guid.NewGuid(),
            Symbol = "BTC",
            Name = "Bitcoin",
            ExternalId = "bitcoin",
            IsEnabled = true
        };
        var eth = new MarketAsset
        {
            Id = Guid.NewGuid(),
            Symbol = "ETH",
            Name = "Ethereum",
            ExternalId = "ethereum",
            IsEnabled = true
        };

        _dbContext.MarketAssets.AddRange(btc, eth);

        // Add price data
        _dbContext.MarketCandles.Add(new MarketCandle
        {
            Id = Guid.NewGuid(),
            MarketAssetId = btc.Id,
            TimestampUtc = DateTimeOffset.UtcNow,
            Open = 42000m,
            High = 43000m,
            Low = 41000m,
            Close = 42000m,
            Volume = 1000m
        });
        _dbContext.MarketCandles.Add(new MarketCandle
        {
            Id = Guid.NewGuid(),
            MarketAssetId = eth.Id,
            TimestampUtc = DateTimeOffset.UtcNow,
            Open = 2500m,
            High = 2600m,
            Low = 2400m,
            Close = 2500m,
            Volume = 5000m
        });

        _dbContext.SaveChanges();
    }

    private RiskValidator CreateValidator(RiskValidatorOptions? options = null)
    {
        return new RiskValidator(
            Options.Create(options ?? _defaultOptions),
            _dbContext,
            _loggerMock.Object);
    }

    private PortfolioState CreatePortfolio(
        decimal cash = 100_000m,
        List<PositionSnapshot>? positions = null)
    {
        positions ??= new List<PositionSnapshot>();
        var totalValue = cash + positions.Sum(p => p.Quantity * p.CurrentPrice);
        return new PortfolioState(
            Guid.NewGuid(),
            Guid.NewGuid(),
            cash,
            positions,
            DateTimeOffset.UtcNow,
            totalValue);
    }

    #region Allowed Assets Tests

    [Fact]
    public async Task ValidateDecision_RejectsUnknownAsset()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("DOGE", TradeSide.Buy, 100m)
            });
        var portfolio = CreatePortfolio();

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.True(result.HasWarnings);
        Assert.Empty(result.ValidatedDecision.Orders);
        Assert.Single(result.RejectedOrders);
        Assert.Contains("not in allowed list", result.RejectedOrders[0].Reason);
    }

    [Fact]
    public async Task ValidateDecision_AcceptsAllowedAssets()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.05m),
                new("ETH", TradeSide.Buy, 0.5m)
            });
        var portfolio = CreatePortfolio();

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.Equal(2, result.ValidatedDecision.Orders.Count);
        Assert.Empty(result.RejectedOrders);
    }

    #endregion

    #region Cash Reserve Tests

    [Fact]
    public async Task ValidateDecision_RejectsWhenCashBelowReserve()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 2.5m) // 2.5 * 42000 = $105,000 (more than $100k - $100 reserve)
            });
        var portfolio = CreatePortfolio(cash: 100m); // Only $100 cash (equal to reserve)

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.True(result.HasWarnings);
        Assert.Empty(result.ValidatedDecision.Orders);
        Assert.Contains("cash", result.RejectedOrders[0].Reason.ToLower());
    }

    [Fact]
    public async Task ValidateDecision_AdjustsOrderToRespectCashReserve()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 2.5m) // 2.5 * 42000 = $105,000
            });
        var portfolio = CreatePortfolio(cash: 50_000m); // $50k cash, $100 reserve = $49,900 usable

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        // Order should be adjusted to fit available cash
        Assert.Single(result.ValidatedDecision.Orders);
        var order = result.ValidatedDecision.Orders[0];
        Assert.True(order.Quantity < 2.5m); // Should be reduced
        Assert.True(order.Quantity * 42000m <= 49_900m); // Should respect cash limit
    }

    #endregion

    #region Max Trade Value Tests

    [Fact]
    public async Task ValidateDecision_AdjustsOrderExceedingMaxTradeValue()
    {
        var options = new RiskValidatorOptions
        {
            MaxSingleTradeValue = 5_000m,
            AllowedAssets = new List<string> { "BTC", "ETH" },
            MinOrderValue = 10m,
            MinCashReserve = 100m
        };
        var validator = CreateValidator(options);
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.5m) // 0.5 * 42000 = $21,000 > $5,000 max
            });
        var portfolio = CreatePortfolio();

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.Single(result.ValidatedDecision.Orders);
        var order = result.ValidatedDecision.Orders[0];
        Assert.True(order.Quantity * 42000m <= 5_000m); // Adjusted to max trade value
    }

    #endregion

    #region Minimum Order Value Tests

    [Fact]
    public async Task ValidateDecision_RejectsDustOrder()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.0001m) // 0.0001 * 42000 = $4.20 < $10 minimum
            });
        var portfolio = CreatePortfolio();

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.True(result.HasWarnings);
        Assert.Empty(result.ValidatedDecision.Orders);
        Assert.Contains("minimum", result.RejectedOrders[0].Reason.ToLower());
    }

    #endregion

    #region Sell Order Tests

    [Fact]
    public async Task ValidateDecision_RejectsSellWithoutPosition()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Sell, 1m)
            });
        var portfolio = CreatePortfolio(); // No positions

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.True(result.HasWarnings);
        Assert.Empty(result.ValidatedDecision.Orders);
        Assert.Contains("No BTC position", result.RejectedOrders[0].Reason);
    }

    [Fact]
    public async Task ValidateDecision_AdjustsSellToAvailablePosition()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Sell, 2m) // Trying to sell 2 BTC
            });
        var portfolio = CreatePortfolio(positions: new List<PositionSnapshot>
        {
            new("BTC", 1m, 40_000m, 42_000m) // Only have 1 BTC
        });

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.Single(result.ValidatedDecision.Orders);
        Assert.Equal(1m, result.ValidatedDecision.Orders[0].Quantity); // Adjusted to available
    }

    #endregion

    #region Order Limit Tests

    [Fact]
    public async Task ValidateDecision_TruncatesExcessOrders()
    {
        var options = new RiskValidatorOptions
        {
            MaxOrdersPerCycle = 2,
            AllowedAssets = new List<string> { "BTC", "ETH" },
            MinOrderValue = 1m,
            MinCashReserve = 100m
        };
        var validator = CreateValidator(options);
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.01m),
                new("ETH", TradeSide.Buy, 0.1m),
                new("BTC", TradeSide.Buy, 0.02m), // This should be truncated
                new("ETH", TradeSide.Buy, 0.2m)  // This should be truncated
            });
        var portfolio = CreatePortfolio();

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        // Only first 2 orders should be processed
        Assert.True(result.ValidatedDecision.Orders.Count <= 2);
    }

    #endregion

    #region Position Size Limit Tests

    [Fact]
    public async Task ValidateDecision_RejectsWhenPositionLimitReached()
    {
        var options = new RiskValidatorOptions
        {
            MaxPositionSizePercent = 0.50m, // 50% max
            AllowedAssets = new List<string> { "BTC", "ETH" },
            MinOrderValue = 10m,
            MinCashReserve = 100m
        };
        var validator = CreateValidator(options);

        // Portfolio: $100k total, already 50% in BTC
        var portfolio = CreatePortfolio(
            cash: 50_000m,
            positions: new List<PositionSnapshot>
            {
                new("BTC", 1.19m, 40_000m, 42_000m) // ~$50k in BTC = 50% of $100k
            });

        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>
            {
                new("BTC", TradeSide.Buy, 0.5m) // Trying to buy more BTC
            });

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        // Should reject or significantly adjust since position limit is reached
        Assert.True(result.HasWarnings || result.ValidatedDecision.Orders[0].Quantity < 0.5m);
    }

    #endregion

    #region Empty Decision Tests

    [Fact]
    public async Task ValidateDecision_AcceptsEmptyOrderList()
    {
        var validator = CreateValidator();
        var decision = new AgentDecision(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow,
            new List<TradeOrder>()); // HOLD - no orders
        var portfolio = CreatePortfolio();

        var result = await validator.ValidateDecisionAsync(decision, portfolio);

        Assert.False(result.HasWarnings);
        Assert.Empty(result.ValidatedDecision.Orders);
        Assert.Empty(result.RejectedOrders);
    }

    #endregion
}
