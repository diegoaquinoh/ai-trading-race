using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.MarketData;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;

namespace AiTradingRace.Tests.MarketData;

/// <summary>
/// Unit tests for MarketDataIngestionService.
/// Uses EF Core InMemory provider for database tests.
/// </summary>
public class MarketDataIngestionServiceTests : IDisposable
{
    private readonly TradingDbContext _dbContext;
    private readonly Mock<IExternalMarketDataClient> _externalClientMock;
    private readonly Mock<ILogger<MarketDataIngestionService>> _loggerMock;
    private readonly CoinGeckoOptions _options;
    private readonly MarketDataIngestionService _service;

    private readonly Guid _btcAssetId = Guid.NewGuid();
    private readonly Guid _ethAssetId = Guid.NewGuid();

    public MarketDataIngestionServiceTests()
    {
        // Create unique database name for test isolation
        var dbOptions = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _dbContext = new TradingDbContext(dbOptions);
        _externalClientMock = new Mock<IExternalMarketDataClient>();
        _loggerMock = new Mock<ILogger<MarketDataIngestionService>>();
        _options = new CoinGeckoOptions { DefaultDays = 1 };

        _service = new MarketDataIngestionService(
            _dbContext,
            _externalClientMock.Object,
            Options.Create(_options),
            _loggerMock.Object);

        // Seed test assets
        SeedAssets();
    }

    private void SeedAssets()
    {
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
        _dbContext.SaveChanges();
    }

    public void Dispose()
    {
        _dbContext.Dispose();
    }

    [Fact]
    public async Task IngestLatestCandlesAsync_InsertsNewCandles()
    {
        // Arrange
        var externalCandles = new List<ExternalCandleDto>
        {
            new(DateTimeOffset.UtcNow.AddHours(-2), 42000m, 42500m, 41800m, 42300m),
            new(DateTimeOffset.UtcNow.AddHours(-1), 42300m, 42600m, 42100m, 42400m)
        };

        _externalClientMock
            .Setup(x => x.GetCandlesAsync("bitcoin", "usd", It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(externalCandles);

        // Act
        var insertedCount = await _service.IngestLatestCandlesAsync("BTC");

        // Assert
        Assert.Equal(2, insertedCount);
        Assert.Equal(2, await _dbContext.MarketCandles.CountAsync());
    }

    [Fact]
    public async Task IngestLatestCandlesAsync_SkipsDuplicates()
    {
        // Arrange - Add existing candle
        var existingTimestamp = DateTimeOffset.UtcNow.AddHours(-2);
        _dbContext.MarketCandles.Add(new MarketCandle
        {
            Id = Guid.NewGuid(),
            MarketAssetId = _btcAssetId,
            TimestampUtc = existingTimestamp,
            Open = 41000m,
            High = 41500m,
            Low = 40800m,
            Close = 41300m,
            Volume = 0m
        });
        await _dbContext.SaveChangesAsync();

        var externalCandles = new List<ExternalCandleDto>
        {
            new(existingTimestamp, 42000m, 42500m, 41800m, 42300m), // Duplicate
            new(DateTimeOffset.UtcNow.AddHours(-1), 42300m, 42600m, 42100m, 42400m) // New
        };

        _externalClientMock
            .Setup(x => x.GetCandlesAsync("bitcoin", "usd", It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(externalCandles);

        // Act
        var insertedCount = await _service.IngestLatestCandlesAsync("BTC");

        // Assert
        Assert.Equal(1, insertedCount); // Only 1 new candle inserted
        Assert.Equal(2, await _dbContext.MarketCandles.CountAsync()); // Total 2
    }

    [Fact]
    public async Task IngestLatestCandlesAsync_ReturnsZero_WhenAssetNotFound()
    {
        // Act
        var insertedCount = await _service.IngestLatestCandlesAsync("UNKNOWN");

        // Assert
        Assert.Equal(0, insertedCount);
    }

    [Fact]
    public async Task IngestLatestCandlesAsync_ReturnsZero_WhenNoExternalIdConfigured()
    {
        // Arrange - Add asset without ExternalId
        _dbContext.MarketAssets.Add(new MarketAsset
        {
            Id = Guid.NewGuid(),
            Symbol = "SOL",
            Name = "Solana",
            ExternalId = "", // Empty
            QuoteCurrency = "USD",
            IsEnabled = true
        });
        await _dbContext.SaveChangesAsync();

        // Act
        var insertedCount = await _service.IngestLatestCandlesAsync("SOL");

        // Assert
        Assert.Equal(0, insertedCount);
    }

    [Fact]
    public async Task IngestLatestCandlesAsync_ReturnsZero_WhenExternalApiReturnsEmpty()
    {
        // Arrange
        _externalClientMock
            .Setup(x => x.GetCandlesAsync("bitcoin", "usd", It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new List<ExternalCandleDto>());

        // Act
        var insertedCount = await _service.IngestLatestCandlesAsync("BTC");

        // Assert
        Assert.Equal(0, insertedCount);
    }

    [Fact]
    public async Task IngestAllAssetsAsync_IngestsAllEnabledAssets()
    {
        // Arrange
        var btcCandles = new List<ExternalCandleDto>
        {
            new(DateTimeOffset.UtcNow.AddHours(-1), 42000m, 42500m, 41800m, 42300m)
        };
        var ethCandles = new List<ExternalCandleDto>
        {
            new(DateTimeOffset.UtcNow.AddHours(-1), 3200m, 3250m, 3180m, 3230m)
        };

        _externalClientMock
            .Setup(x => x.GetCandlesAsync("bitcoin", "usd", It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(btcCandles);
        _externalClientMock
            .Setup(x => x.GetCandlesAsync("ethereum", "usd", It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(ethCandles);

        // Act
        var totalInserted = await _service.IngestAllAssetsAsync();

        // Assert
        Assert.Equal(2, totalInserted);
        Assert.Equal(1, await _dbContext.MarketCandles.CountAsync(c => c.MarketAssetId == _btcAssetId));
        Assert.Equal(1, await _dbContext.MarketCandles.CountAsync(c => c.MarketAssetId == _ethAssetId));
    }

    [Fact]
    public async Task IngestAllAssetsAsync_SkipsDisabledAssets()
    {
        // Arrange - Disable ETH
        var eth = await _dbContext.MarketAssets.FirstAsync(a => a.Symbol == "ETH");
        eth.IsEnabled = false;
        await _dbContext.SaveChangesAsync();

        var btcCandles = new List<ExternalCandleDto>
        {
            new(DateTimeOffset.UtcNow.AddHours(-1), 42000m, 42500m, 41800m, 42300m)
        };

        _externalClientMock
            .Setup(x => x.GetCandlesAsync("bitcoin", "usd", It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(btcCandles);

        // Act
        var totalInserted = await _service.IngestAllAssetsAsync();

        // Assert
        Assert.Equal(1, totalInserted);

        // Verify ETH was not called
        _externalClientMock.Verify(
            x => x.GetCandlesAsync("ethereum", It.IsAny<string>(), It.IsAny<int>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task IngestLatestCandlesAsync_IsCaseInsensitive()
    {
        // Arrange
        var externalCandles = new List<ExternalCandleDto>
        {
            new(DateTimeOffset.UtcNow.AddHours(-1), 42000m, 42500m, 41800m, 42300m)
        };

        _externalClientMock
            .Setup(x => x.GetCandlesAsync("bitcoin", "usd", It.IsAny<int>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(externalCandles);

        // Act - Use lowercase symbol
        var insertedCount = await _service.IngestLatestCandlesAsync("btc");

        // Assert
        Assert.Equal(1, insertedCount);
    }
}
