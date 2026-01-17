using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Agents;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Agents;

/// <summary>
/// Unit tests for AgentContextBuilder.
/// </summary>
public class AgentContextBuilderTests : IDisposable
{
    private readonly TradingDbContext _dbContext;
    private readonly Mock<IPortfolioService> _portfolioServiceMock;
    private readonly Mock<IMarketDataProvider> _marketDataProviderMock;
    private readonly Mock<ILogger<AgentContextBuilder>> _loggerMock;
    private readonly Guid _activeAgentId = Guid.Parse("11111111-1111-1111-1111-111111111111");
    private readonly Guid _inactiveAgentId = Guid.Parse("22222222-2222-2222-2222-222222222222");

    public AgentContextBuilderTests()
    {
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase($"ContextBuilder_{Guid.NewGuid()}")
            .Options;
        _dbContext = new TradingDbContext(options);
        _portfolioServiceMock = new Mock<IPortfolioService>();
        _marketDataProviderMock = new Mock<IMarketDataProvider>();
        _loggerMock = new Mock<ILogger<AgentContextBuilder>>();

        SeedData();
        SetupMocks();
    }

    public void Dispose()
    {
        _dbContext.Dispose();
    }

    private void SeedData()
    {
        _dbContext.Agents.AddRange(
            new Agent
            {
                Id = _activeAgentId,
                Name = "Active Agent",
                Strategy = "Test strategy",
                Instructions = "Test instructions",
                ModelProvider = ModelProvider.Mock,
                IsActive = true,
                CreatedAt = DateTimeOffset.UtcNow
            },
            new Agent
            {
                Id = _inactiveAgentId,
                Name = "Inactive Agent",
                Strategy = "Test strategy",
                Instructions = "Test instructions",
                ModelProvider = ModelProvider.Mock,
                IsActive = false,
                CreatedAt = DateTimeOffset.UtcNow
            });

        _dbContext.MarketAssets.Add(new MarketAsset
        {
            Id = Guid.NewGuid(),
            Symbol = "BTC",
            Name = "Bitcoin",
            ExternalId = "bitcoin",
            IsEnabled = true
        });

        _dbContext.SaveChanges();
    }

    private void SetupMocks()
    {
        _portfolioServiceMock
            .Setup(x => x.GetPortfolioAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new PortfolioState(
                Guid.NewGuid(),
                _activeAgentId,
                100_000m,
                new List<PositionSnapshot>(),
                DateTimeOffset.UtcNow,
                100_000m));

        _marketDataProviderMock
            .Setup(x => x.GetLatestCandlesAsync(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new List<MarketCandleDto>
            {
                new("BTC", DateTimeOffset.UtcNow, 42000m, 43000m, 41000m, 42000m, 1000m)
            });
    }

    private AgentContextBuilder CreateBuilder()
    {
        return new AgentContextBuilder(
            _dbContext,
            _portfolioServiceMock.Object,
            _marketDataProviderMock.Object,
            _loggerMock.Object);
    }

    [Fact]
    public async Task BuildContext_ReturnsContextForActiveAgent()
    {
        var builder = CreateBuilder();

        var context = await builder.BuildContextAsync(_activeAgentId);

        Assert.NotNull(context);
        Assert.Equal(_activeAgentId, context.AgentId);
        Assert.Equal("Test instructions", context.Instructions);
        Assert.NotNull(context.Portfolio);
        Assert.NotNull(context.RecentCandles);
    }

    [Fact]
    public async Task BuildContext_ThrowsForNonExistentAgent()
    {
        var builder = CreateBuilder();
        var nonExistentId = Guid.NewGuid();

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => builder.BuildContextAsync(nonExistentId));
    }

    [Fact]
    public async Task BuildContext_ThrowsForInactiveAgent()
    {
        var builder = CreateBuilder();

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => builder.BuildContextAsync(_inactiveAgentId));
    }

    [Fact]
    public async Task BuildContext_IncludesPortfolioState()
    {
        var builder = CreateBuilder();

        var context = await builder.BuildContextAsync(_activeAgentId);

        Assert.Equal(100_000m, context.Portfolio.Cash);
        Assert.Equal(100_000m, context.Portfolio.TotalValue);
        _portfolioServiceMock.Verify(
            x => x.GetPortfolioAsync(_activeAgentId, It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task BuildContext_IncludesMarketCandles()
    {
        var builder = CreateBuilder();

        var context = await builder.BuildContextAsync(_activeAgentId, candleCount: 24);

        Assert.NotEmpty(context.RecentCandles);
        _marketDataProviderMock.Verify(
            x => x.GetLatestCandlesAsync("BTC", 24, It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task BuildContext_HandlesMarketDataFailureGracefully()
    {
        _marketDataProviderMock
            .Setup(x => x.GetLatestCandlesAsync(It.IsAny<string>(), It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new Exception("API Error"));

        var builder = CreateBuilder();

        // Should not throw, just return empty candles
        var context = await builder.BuildContextAsync(_activeAgentId);

        Assert.NotNull(context);
        Assert.Empty(context.RecentCandles);
    }
}
