using AiTradingRace.Application.MarketData;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Knowledge;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace AiTradingRace.Tests.Knowledge;

public class RegimeDetectorTests : IDisposable
{
    private readonly TradingDbContext _context;
    private readonly Mock<IMarketDataProvider> _mockMarketDataProvider;
    private readonly Mock<ILogger<VolatilityBasedRegimeDetector>> _mockLogger;
    private readonly VolatilityBasedRegimeDetector _detector;
    private readonly Guid _btcAssetId = Guid.NewGuid();

    public RegimeDetectorTests()
    {
        // Setup in-memory database
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TradingDbContext(options);

        // Seed test data
        SeedTestData();

        _mockMarketDataProvider = new Mock<IMarketDataProvider>();
        _mockLogger = new Mock<ILogger<VolatilityBasedRegimeDetector>>();

        _detector = new VolatilityBasedRegimeDetector(
            _mockMarketDataProvider.Object,
            _context,
            _mockLogger.Object);
    }

    private void SeedTestData()
    {
        var btc = new MarketAsset
        {
            Id = _btcAssetId,
            Symbol = "BTC",
            Name = "Bitcoin",
            ExternalId = "bitcoin",
            QuoteCurrency = "USD",
            IsEnabled = true
        };

        _context.MarketAssets.Add(btc);
        _context.SaveChanges();
    }

    [Fact]
    public async Task DetectRegime_HighVolatility_ReturnsVolatileRegime()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-10);
        var toDate = DateTime.UtcNow;

        // Generate candles with high volatility (price swings ±8%)
        var candles = GenerateVolatileCandles(_btcAssetId, fromDate, 10, basePrice: 50000m, volatility: 0.08m);
        _context.MarketCandles.AddRange(candles);
        await _context.SaveChangesAsync();

        // Act
        var regime = await _detector.DetectRegimeAsync("BTC", fromDate, toDate);

        // Assert
        Assert.Equal("VOLATILE", regime.RegimeId);
        Assert.Equal("Volatile Market", regime.Name);
        Assert.True(regime.Volatility > 0.05m);
        Assert.True(regime.IsActive);
    }

    [Fact]
    public async Task DetectRegime_LowVolatility_ReturnsStableRegime()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-10);
        var toDate = DateTime.UtcNow;

        // Generate candles with low volatility (price swings ±1%)
        var candles = GenerateVolatileCandles(_btcAssetId, fromDate, 10, basePrice: 50000m, volatility: 0.01m);
        _context.MarketCandles.AddRange(candles);
        await _context.SaveChangesAsync();

        // Act
        var regime = await _detector.DetectRegimeAsync("BTC", fromDate, toDate);

        // Assert
        Assert.Equal("STABLE", regime.RegimeId);
        Assert.Equal("Stable Market", regime.Name);
        Assert.True(regime.Volatility < 0.05m);
    }

    [Fact]
    public async Task DetectRegime_UpwardTrend_ReturnsBullishRegime()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-35);
        var toDate = DateTime.UtcNow;

        // Generate 35 candles with upward trend
        var candles = GenerateTrendingCandles(_btcAssetId, fromDate, 35, startPrice: 40000m, dailyChange: 0.02m);
        _context.MarketCandles.AddRange(candles);
        await _context.SaveChangesAsync();

        // Act
        var regime = await _detector.DetectRegimeAsync("BTC", fromDate, toDate);

        // Assert
        Assert.Equal("BULLISH", regime.RegimeId);
        Assert.Equal("Bullish Trend", regime.Name);
        Assert.NotNull(regime.MA7);
        Assert.NotNull(regime.MA30);
        Assert.True(regime.MA7 > regime.MA30);
    }

    [Fact]
    public async Task DetectRegime_DownwardTrend_ReturnsBearishRegime()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-35);
        var toDate = DateTime.UtcNow;

        // Generate 35 candles with downward trend
        var candles = GenerateTrendingCandles(_btcAssetId, fromDate, 35, startPrice: 60000m, dailyChange: -0.02m);
        _context.MarketCandles.AddRange(candles);
        await _context.SaveChangesAsync();

        // Act
        var regime = await _detector.DetectRegimeAsync("BTC", fromDate, toDate);

        // Assert
        Assert.Equal("BEARISH", regime.RegimeId);
        Assert.Equal("Bearish Trend", regime.Name);
        Assert.NotNull(regime.MA7);
        Assert.NotNull(regime.MA30);
        Assert.True(regime.MA7 < regime.MA30);
    }

    [Fact]
    public async Task DetectRegime_InsufficientData_ReturnsUnknownRegime()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-3);
        var toDate = DateTime.UtcNow;

        // Generate only 3 candles (less than required 7)
        var candles = GenerateVolatileCandles(_btcAssetId, fromDate, 3, basePrice: 50000m, volatility: 0.01m);
        _context.MarketCandles.AddRange(candles);
        await _context.SaveChangesAsync();

        // Act
        var regime = await _detector.DetectRegimeAsync("BTC", fromDate, toDate);

        // Assert
        Assert.Equal("UNKNOWN", regime.RegimeId);
        Assert.Equal("Insufficient Data", regime.Name);
    }

    [Fact]
    public async Task DetectRegime_UnknownAsset_ReturnsUnknownRegime()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-10);
        var toDate = DateTime.UtcNow;

        // Act
        var regime = await _detector.DetectRegimeAsync("UNKNOWN", fromDate, toDate);

        // Assert
        Assert.Equal("UNKNOWN", regime.RegimeId);
        Assert.Equal("Unknown Asset", regime.Name);
        Assert.False(regime.IsActive);
    }

    [Fact]
    public async Task DetectRegime_SavesDetectedRegimeToDatabase()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-10);
        var toDate = DateTime.UtcNow;

        var candles = GenerateVolatileCandles(_btcAssetId, fromDate, 10, basePrice: 50000m, volatility: 0.08m);
        _context.MarketCandles.AddRange(candles);
        await _context.SaveChangesAsync();

        // Act
        await _detector.DetectRegimeAsync("BTC", fromDate, toDate);

        // Assert
        var savedRegime = await _context.DetectedRegimes
            .Where(r => r.Asset == "BTC")
            .OrderByDescending(r => r.DetectedAt)
            .FirstOrDefaultAsync();

        Assert.NotNull(savedRegime);
        Assert.Equal("VOLATILE", savedRegime.RegimeId);
        Assert.True(savedRegime.Volatility > 0.05m);
    }

    [Fact]
    public async Task GetHistoricalRegimes_ReturnsOrderedHistory()
    {
        // Arrange
        var now = DateTime.UtcNow;
        var regimes = new[]
        {
            new DetectedRegime
            {
                RegimeId = "VOLATILE",
                Asset = "BTC",
                DetectedAt = now.AddDays(-3),
                Volatility = 0.08m,
                CreatedAt = now.AddDays(-3)
            },
            new DetectedRegime
            {
                RegimeId = "STABLE",
                Asset = "BTC",
                DetectedAt = now.AddDays(-2),
                Volatility = 0.02m,
                CreatedAt = now.AddDays(-2)
            },
            new DetectedRegime
            {
                RegimeId = "BULLISH",
                Asset = "BTC",
                DetectedAt = now.AddDays(-1),
                Volatility = 0.03m,
                MA7 = 51000m,
                MA30 = 49000m,
                CreatedAt = now.AddDays(-1)
            }
        };

        _context.DetectedRegimes.AddRange(regimes);
        await _context.SaveChangesAsync();

        // Act
        var history = await _detector.GetHistoricalRegimesAsync("BTC", now.AddDays(-4));

        // Assert
        Assert.Equal(3, history.Count);
        Assert.Equal("BULLISH", history[0].RegimeId); // Most recent first
        Assert.Equal("STABLE", history[1].RegimeId);
        Assert.Equal("VOLATILE", history[2].RegimeId);
    }

    // Helper methods
    private List<MarketCandle> GenerateVolatileCandles(
        Guid assetId,
        DateTime startDate,
        int count,
        decimal basePrice,
        decimal volatility)
    {
        var candles = new List<MarketCandle>();
        var random = new Random(42); // Fixed seed for reproducibility
        var currentPrice = basePrice;

        for (int i = 0; i < count; i++)
        {
            // Generate alternating large swings to ensure high volatility
            var change = (i % 2 == 0 ? 1 : -1) * volatility;
            currentPrice *= (1 + change);

            candles.Add(new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = assetId,
                TimestampUtc = startDate.AddDays(i),
                Open = currentPrice,
                High = currentPrice * 1.01m,
                Low = currentPrice * 0.99m,
                Close = currentPrice,
                Volume = 1000m
            });
        }

        return candles;
    }

    private List<MarketCandle> GenerateTrendingCandles(
        Guid assetId,
        DateTime startDate,
        int count,
        decimal startPrice,
        decimal dailyChange)
    {
        var candles = new List<MarketCandle>();
        var currentPrice = startPrice;

        for (int i = 0; i < count; i++)
        {
            currentPrice *= (1 + dailyChange);

            candles.Add(new MarketCandle
            {
                Id = Guid.NewGuid(),
                MarketAssetId = assetId,
                TimestampUtc = startDate.AddDays(i),
                Open = currentPrice,
                High = currentPrice * 1.005m,
                Low = currentPrice * 0.995m,
                Close = currentPrice,
                Volume = 1000m
            });
        }

        return candles;
    }

    public void Dispose()
    {
        _context?.Dispose();
    }
}
