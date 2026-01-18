using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;

namespace AiTradingRace.Tests.Agents;

/// <summary>
/// Integration tests for CustomMlAgentModelClient.
/// Uses a mock HttpMessageHandler to simulate Python service responses.
/// </summary>
public class CustomMlAgentModelClientTests
{
    private readonly Mock<ILogger<CustomMlAgentModelClient>> _loggerMock;
    private readonly CustomMlAgentOptions _options;

    public CustomMlAgentModelClientTests()
    {
        _loggerMock = new Mock<ILogger<CustomMlAgentModelClient>>();
        _options = new CustomMlAgentOptions
        {
            BaseUrl = "http://localhost:8000",
            TimeoutSeconds = 30,
            ApiKey = "test-api-key"
        };
    }

    [Fact]
    public async Task GenerateDecisionAsync_ValidResponse_ReturnsDecision()
    {
        // Arrange
        var expectedResponse = new
        {
            schemaVersion = "1.0",
            modelVersion = "1.0.0",
            requestId = Guid.NewGuid().ToString(),
            agentId = Guid.NewGuid().ToString(),
            createdAt = DateTimeOffset.UtcNow,
            orders = new[]
            {
                new
                {
                    assetSymbol = "BTC",
                    side = "BUY",
                    quantity = 0.01m,
                    limitPrice = (decimal?)null
                }
            },
            signals = new[]
            {
                new
                {
                    feature = "rsi_14",
                    value = 27.3,
                    rule = "<30 = oversold",
                    fired = true,
                    contribution = "bullish"
                }
            },
            reasoning = "RSI oversold signal"
        };

        var handler = new MockHttpMessageHandler(
            HttpStatusCode.OK,
            JsonSerializer.Serialize(expectedResponse, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));

        var httpClient = new HttpClient(handler);
        var optionsMock = Options.Create(_options);

        var client = new CustomMlAgentModelClient(httpClient, optionsMock, _loggerMock.Object);

        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert
        Assert.NotNull(decision);
        Assert.Single(decision.Orders);
        Assert.Equal("BTC", decision.Orders[0].AssetSymbol);
        Assert.Equal(TradeSide.Buy, decision.Orders[0].Side);
    }

    [Fact]
    public async Task GenerateDecisionAsync_EmptyOrders_ReturnsEmptyDecision()
    {
        // Arrange
        var responseWithNoOrders = new
        {
            schemaVersion = "1.0",
            modelVersion = "1.0.0",
            requestId = Guid.NewGuid().ToString(),
            agentId = Guid.NewGuid().ToString(),
            createdAt = DateTimeOffset.UtcNow,
            orders = Array.Empty<object>(),
            signals = Array.Empty<object>(),
            reasoning = "HOLD - no signals"
        };

        var handler = new MockHttpMessageHandler(
            HttpStatusCode.OK,
            JsonSerializer.Serialize(responseWithNoOrders, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));

        var httpClient = new HttpClient(handler);
        var client = new CustomMlAgentModelClient(httpClient, Options.Create(_options), _loggerMock.Object);

        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
    }

    [Fact]
    public async Task GenerateDecisionAsync_ApiError_ThrowsException()
    {
        // Arrange
        var handler = new MockHttpMessageHandler(HttpStatusCode.InternalServerError, "Server error");
        var httpClient = new HttpClient(handler);
        var client = new CustomMlAgentModelClient(httpClient, Options.Create(_options), _loggerMock.Object);

        var context = CreateTestContext();

        // Act & Assert
        await Assert.ThrowsAsync<HttpRequestException>(() =>
            client.GenerateDecisionAsync(context));
    }

    [Fact]
    public async Task GenerateDecisionAsync_SendsApiKeyHeader()
    {
        // Arrange
        var response = new
        {
            schemaVersion = "1.0",
            modelVersion = "1.0.0",
            requestId = Guid.NewGuid().ToString(),
            agentId = Guid.NewGuid().ToString(),
            createdAt = DateTimeOffset.UtcNow,
            orders = Array.Empty<object>(),
            signals = Array.Empty<object>(),
            reasoning = "HOLD"
        };

        var handler = new MockHttpMessageHandler(
            HttpStatusCode.OK,
            JsonSerializer.Serialize(response, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));

        var httpClient = new HttpClient(handler);
        var client = new CustomMlAgentModelClient(httpClient, Options.Create(_options), _loggerMock.Object);

        var context = CreateTestContext();

        // Act
        await client.GenerateDecisionAsync(context);

        // Assert - verify API key was sent
        Assert.True(handler.LastRequest?.Headers.Contains("X-API-Key"));
        Assert.Equal("test-api-key", handler.LastRequest?.Headers.GetValues("X-API-Key").First());
    }

    private static AgentContext CreateTestContext()
    {
        var portfolio = new PortfolioState(
            PortfolioId: Guid.NewGuid(),
            AgentId: Guid.NewGuid(),
            Cash: 10000m,
            Positions: new List<PositionSnapshot>(),
            AsOf: DateTimeOffset.UtcNow,
            TotalValue: 10000m);

        var candles = new List<MarketCandleDto>
        {
            new("BTC", DateTimeOffset.UtcNow, 42000m, 42500m, 41500m, 42200m, 1000m)
        };

        return new AgentContext(
            Guid.NewGuid(),
            ModelProvider.CustomML,
            portfolio,
            candles,
            "Test instructions");
    }
}

/// <summary>
/// Mock HTTP handler for testing HTTP clients.
/// </summary>
internal class MockHttpMessageHandler : HttpMessageHandler
{
    private readonly HttpStatusCode _statusCode;
    private readonly string _responseContent;

    public HttpRequestMessage? LastRequest { get; private set; }

    public MockHttpMessageHandler(HttpStatusCode statusCode, string responseContent)
    {
        _statusCode = statusCode;
        _responseContent = responseContent;
    }

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        LastRequest = request;

        return Task.FromResult(new HttpResponseMessage
        {
            StatusCode = _statusCode,
            Content = new StringContent(_responseContent, System.Text.Encoding.UTF8, "application/json")
        });
    }
}
