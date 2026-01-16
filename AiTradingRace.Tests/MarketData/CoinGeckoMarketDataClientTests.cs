using System.Net;
using System.Text;
using AiTradingRace.Infrastructure.MarketData;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using Moq.Protected;

namespace AiTradingRace.Tests.MarketData;

/// <summary>
/// Unit tests for CoinGeckoMarketDataClient.
/// Tests HTTP interactions using mocked HttpMessageHandler.
/// </summary>
public class CoinGeckoMarketDataClientTests
{
    private readonly Mock<ILogger<CoinGeckoMarketDataClient>> _loggerMock;
    private readonly CoinGeckoOptions _options;

    public CoinGeckoMarketDataClientTests()
    {
        _loggerMock = new Mock<ILogger<CoinGeckoMarketDataClient>>();
        _options = new CoinGeckoOptions
        {
            BaseUrl = "https://api.coingecko.com/api/v3/",
            TimeoutSeconds = 30,
            DefaultDays = 1
        };
    }

    private CoinGeckoMarketDataClient CreateClient(HttpMessageHandler handler)
    {
        var httpClient = new HttpClient(handler);
        return new CoinGeckoMarketDataClient(
            httpClient,
            Options.Create(_options),
            _loggerMock.Object);
    }

    [Fact]
    public async Task GetCandlesAsync_ReturnsCandles_WhenApiReturnsValidData()
    {
        // Arrange
        var jsonResponse = @"[
            [1704067200000, 42000.5, 42500.0, 41800.0, 42300.0],
            [1704070800000, 42300.0, 42600.0, 42100.0, 42400.0]
        ]";

        var handlerMock = new Mock<HttpMessageHandler>();
        handlerMock.Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.OK,
                Content = new StringContent(jsonResponse, Encoding.UTF8, "application/json")
            });

        var client = CreateClient(handlerMock.Object);

        // Act
        var candles = await client.GetCandlesAsync("bitcoin", "usd", 1);

        // Assert
        Assert.Equal(2, candles.Count);
        Assert.Equal(42000.5m, candles[0].Open);
        Assert.Equal(42300.0m, candles[0].Close);
        Assert.Equal(42300.0m, candles[1].Open);
        Assert.Equal(42400.0m, candles[1].Close);
    }

    [Fact]
    public async Task GetCandlesAsync_ReturnsEmpty_WhenApiReturns403()
    {
        // Arrange
        var handlerMock = new Mock<HttpMessageHandler>();
        handlerMock.Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.Forbidden,
                Content = new StringContent("{\"error\":\"Rate limited\"}")
            });

        var client = CreateClient(handlerMock.Object);

        // Act
        var candles = await client.GetCandlesAsync("bitcoin", "usd", 1);

        // Assert
        Assert.Empty(candles);
    }

    [Fact]
    public async Task GetCandlesAsync_ReturnsEmpty_WhenApiReturns429RateLimited()
    {
        // Arrange
        var handlerMock = new Mock<HttpMessageHandler>();
        handlerMock.Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.TooManyRequests,
                Content = new StringContent("{\"error\":\"Too many requests\"}")
            });

        var client = CreateClient(handlerMock.Object);

        // Act
        var candles = await client.GetCandlesAsync("bitcoin", "usd", 1);

        // Assert
        Assert.Empty(candles);
    }

    [Fact]
    public async Task GetCandlesAsync_ReturnsEmpty_WhenApiReturnsEmptyArray()
    {
        // Arrange
        var handlerMock = new Mock<HttpMessageHandler>();
        handlerMock.Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.OK,
                Content = new StringContent("[]", Encoding.UTF8, "application/json")
            });

        var client = CreateClient(handlerMock.Object);

        // Act
        var candles = await client.GetCandlesAsync("bitcoin", "usd", 1);

        // Assert
        Assert.Empty(candles);
    }

    [Fact]
    public async Task GetCandlesAsync_ParsesTimestampCorrectly()
    {
        // Arrange - timestamp 1704067200000 = 2024-01-01 00:00:00 UTC
        var jsonResponse = @"[[1704067200000, 42000.0, 42500.0, 41800.0, 42300.0]]";

        var handlerMock = new Mock<HttpMessageHandler>();
        handlerMock.Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.OK,
                Content = new StringContent(jsonResponse, Encoding.UTF8, "application/json")
            });

        var client = CreateClient(handlerMock.Object);

        // Act
        var candles = await client.GetCandlesAsync("bitcoin", "usd", 1);

        // Assert
        Assert.Single(candles);
        Assert.Equal(new DateTimeOffset(2024, 1, 1, 0, 0, 0, TimeSpan.Zero), candles[0].TimestampUtc);
    }

    [Fact]
    public void GetCandlesAsync_ThrowsArgumentException_WhenCoinIdIsEmpty()
    {
        // Arrange
        var handlerMock = new Mock<HttpMessageHandler>();
        var client = CreateClient(handlerMock.Object);

        // Act & Assert
        Assert.ThrowsAsync<ArgumentException>(() => client.GetCandlesAsync("", "usd", 1));
    }

    [Fact]
    public void GetCandlesAsync_ThrowsArgumentOutOfRange_WhenDaysIsZeroOrNegative()
    {
        // Arrange
        var handlerMock = new Mock<HttpMessageHandler>();
        var client = CreateClient(handlerMock.Object);

        // Act & Assert
        Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => client.GetCandlesAsync("bitcoin", "usd", 0));
        Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => client.GetCandlesAsync("bitcoin", "usd", -1));
    }

    [Fact]
    public async Task GetCandlesAsync_SetsUserAgentHeader()
    {
        // Arrange
        HttpRequestMessage? capturedRequest = null;
        var handlerMock = new Mock<HttpMessageHandler>();
        handlerMock.Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<HttpRequestMessage, CancellationToken>((request, _) => capturedRequest = request)
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.OK,
                Content = new StringContent("[]", Encoding.UTF8, "application/json")
            });

        var client = CreateClient(handlerMock.Object);

        // Act
        await client.GetCandlesAsync("bitcoin", "usd", 1);

        // Assert
        Assert.NotNull(capturedRequest);
        Assert.True(capturedRequest.Headers.UserAgent.Count > 0);
    }
}
