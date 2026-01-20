using System.Net;
using System.Text.Json;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;

namespace AiTradingRace.Tests.Agents;

/// <summary>
/// Unit tests for LlamaAgentModelClient.
/// Uses a mock HttpMessageHandler to simulate Llama API (Groq/Together.ai) responses.
/// </summary>
public class LlamaAgentModelClientTests
{
    private readonly Mock<ILogger<LlamaAgentModelClient>> _loggerMock;
    private readonly LlamaOptions _options;

    public LlamaAgentModelClientTests()
    {
        _loggerMock = new Mock<ILogger<LlamaAgentModelClient>>();
        _options = new LlamaOptions
        {
            Provider = "Groq",
            BaseUrl = "https://api.groq.com/openai/v1",
            ApiKey = "test-api-key",
            Model = "llama-3.3-70b-versatile",
            Temperature = 0.3f,
            MaxTokens = 500,
            TimeoutSeconds = 60
        };
    }

    [Fact]
    public async Task GenerateDecisionAsync_ValidBuyResponse_ReturnsDecisionWithOrder()
    {
        // Arrange
        var llamaResponse = new
        {
            id = "chatcmpl-123",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "BTC showing bullish momentum, RSI indicates oversold",
                            orders = new[]
                            {
                                new { asset = "BTC", side = "BUY", quantity = 0.1m }
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            },
            usage = new
            {
                prompt_tokens = 150,
                completion_tokens = 50,
                total_tokens = 200
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert
        Assert.NotNull(decision);
        Assert.Single(decision.Orders);
        Assert.Equal("BTC", decision.Orders[0].AssetSymbol);
        Assert.Equal(TradeSide.Buy, decision.Orders[0].Side);
        Assert.Equal(0.1m, decision.Orders[0].Quantity);
    }

    [Fact]
    public async Task GenerateDecisionAsync_HoldResponse_ReturnsEmptyOrders()
    {
        // Arrange
        var llamaResponse = new
        {
            id = "chatcmpl-456",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Market conditions uncertain, holding position",
                            orders = Array.Empty<object>()
                        })
                    },
                    finish_reason = "stop"
                }
            },
            usage = new { prompt_tokens = 100, completion_tokens = 30, total_tokens = 130 }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
    }

    [Fact]
    public async Task GenerateDecisionAsync_MultipleOrders_ReturnsAllOrders()
    {
        // Arrange
        var llamaResponse = new
        {
            id = "chatcmpl-789",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Rebalancing portfolio - selling BTC, buying ETH",
                            orders = new[]
                            {
                                new { asset = "BTC", side = "SELL", quantity = 0.05m },
                                new { asset = "ETH", side = "BUY", quantity = 1.0m }
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            },
            usage = new { prompt_tokens = 120, completion_tokens = 60, total_tokens = 180 }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert
        Assert.NotNull(decision);
        Assert.Equal(2, decision.Orders.Count);
        Assert.Equal("BTC", decision.Orders[0].AssetSymbol);
        Assert.Equal(TradeSide.Sell, decision.Orders[0].Side);
        Assert.Equal("ETH", decision.Orders[1].AssetSymbol);
        Assert.Equal(TradeSide.Buy, decision.Orders[1].Side);
    }

    [Fact]
    public async Task GenerateDecisionAsync_RateLimited_ReturnsHoldDecision()
    {
        // Arrange
        var handler = CreateMockHandler(HttpStatusCode.TooManyRequests, new { error = "Rate limit exceeded" });
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - should gracefully degrade to HOLD
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
    }

    [Fact]
    public async Task GenerateDecisionAsync_ServerError_ReturnsHoldDecision()
    {
        // Arrange
        var handler = CreateMockHandler(HttpStatusCode.InternalServerError, new { error = "Server error" });
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - should gracefully degrade to HOLD
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
    }

    [Fact]
    public async Task GenerateDecisionAsync_EmptyChoices_ReturnsHoldDecision()
    {
        // Arrange
        var llamaResponse = new
        {
            id = "chatcmpl-empty",
            choices = Array.Empty<object>(),
            usage = new { prompt_tokens = 100, completion_tokens = 0, total_tokens = 100 }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
    }

    [Fact]
    public async Task GenerateDecisionAsync_InvalidJson_ReturnsHoldDecision()
    {
        // Arrange
        var llamaResponse = new
        {
            id = "chatcmpl-invalid",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = "This is not valid JSON {{{" // Invalid JSON
                    },
                    finish_reason = "stop"
                }
            },
            usage = new { prompt_tokens = 100, completion_tokens = 20, total_tokens = 120 }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - should handle gracefully
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
    }

    [Fact]
    public async Task GenerateDecisionAsync_ZeroQuantity_IgnoresOrder()
    {
        // Arrange
        var llamaResponse = new
        {
            id = "chatcmpl-zero",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Invalid order with zero quantity",
                            orders = new[]
                            {
                                new { asset = "BTC", side = "BUY", quantity = 0m }
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            },
            usage = new { prompt_tokens = 100, completion_tokens = 30, total_tokens = 130 }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - zero quantity should be filtered out
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
    }

    [Fact]
    public async Task GenerateDecisionAsync_MissingReasoningField_ReturnsHoldDecision()
    {
        // Arrange - Response without 'reasoning' field
        var llamaResponse = new
        {
            id = "chatcmpl-validation-1",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            // Missing 'reasoning' field
                            orders = new[]
                            {
                                new { asset = "BTC", side = "BUY", quantity = 0.1m }
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should default to HOLD
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("missing 'reasoning' field")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task GenerateDecisionAsync_MissingOrdersField_ReturnsHoldDecision()
    {
        // Arrange - Response without 'orders' field
        var llamaResponse = new
        {
            id = "chatcmpl-validation-2",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Market analysis complete"
                            // Missing 'orders' field
                        })
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should default to HOLD
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("missing 'orders' field")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task GenerateDecisionAsync_OrdersNotArray_ReturnsHoldDecision()
    {
        // Arrange - 'orders' is not an array
        var llamaResponse = new
        {
            id = "chatcmpl-validation-3",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = "{\"reasoning\": \"test\", \"orders\": \"not-an-array\"}"
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should default to HOLD
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("not an array")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    [Fact]
    public async Task GenerateDecisionAsync_InvalidAsset_SkipsOrder()
    {
        // Arrange - Order with unknown asset
        var llamaResponse = new
        {
            id = "chatcmpl-validation-4",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Diversifying portfolio",
                            orders = new[]
                            {
                                new { asset = "DOGE", side = "BUY", quantity = 100m },  // Invalid asset
                                new { asset = "BTC", side = "BUY", quantity = 0.1m }   // Valid asset
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should skip DOGE order, keep BTC order
        Assert.NotNull(decision);
        Assert.Single(decision.Orders);
        Assert.Equal("BTC", decision.Orders[0].AssetSymbol);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Unknown asset 'DOGE'")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
    }

    [Fact]
    public async Task GenerateDecisionAsync_NegativeQuantity_SkipsOrder()
    {
        // Arrange - Order with negative quantity
        var llamaResponse = new
        {
            id = "chatcmpl-validation-5",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Making trades",
                            orders = new[]
                            {
                                new { asset = "BTC", side = "BUY", quantity = -0.5m }  // Invalid quantity
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should skip order with negative quantity
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Quantity must be positive")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
    }

    [Fact]
    public async Task GenerateDecisionAsync_ExcessiveQuantity_SkipsOrder()
    {
        // Arrange - Order with excessive quantity
        var llamaResponse = new
        {
            id = "chatcmpl-validation-6",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Going all in!",
                            orders = new[]
                            {
                                new { asset = "BTC", side = "BUY", quantity = 10000m }  // Exceeds max 1000
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should skip order with excessive quantity
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("exceeds maximum allowed")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
    }

    [Fact]
    public async Task GenerateDecisionAsync_MissingOrderFields_SkipsOrder()
    {
        // Arrange - Order missing required fields
        var llamaResponse = new
        {
            id = "chatcmpl-validation-7",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Testing validation",
                            orders = new object[]
                            {
                                new { asset = "BTC", quantity = 0.1m },  // Missing 'side'
                                new { side = "BUY", quantity = 0.2m }    // Missing 'asset'
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should skip both incomplete orders
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Missing")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
    }

    [Fact]
    public async Task GenerateDecisionAsync_WrongFieldTypes_SkipsOrder()
    {
        // Arrange - Order with wrong field types
        var llamaResponse = new
        {
            id = "chatcmpl-validation-8",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = "{\"reasoning\": \"test\", \"orders\": [{\"asset\": \"BTC\", \"side\": \"BUY\", \"quantity\": \"not-a-number\"}]}"
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should skip order with wrong types
        Assert.NotNull(decision);
        Assert.Empty(decision.Orders);
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("must be a number")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
    }

    [Fact]
    public async Task GenerateDecisionAsync_MultipleInvalidOrders_LogsSummary()
    {
        // Arrange - Multiple invalid orders
        var llamaResponse = new
        {
            id = "chatcmpl-validation-9",
            choices = new[]
            {
                new
                {
                    index = 0,
                    message = new
                    {
                        role = "assistant",
                        content = JsonSerializer.Serialize(new
                        {
                            reasoning = "Multiple trades",
                            orders = new[]
                            {
                                new { asset = "DOGE", side = "BUY", quantity = 100m },   // Invalid asset
                                new { asset = "BTC", side = "BUY", quantity = -1m },     // Negative quantity
                                new { asset = "ETH", side = "INVALID", quantity = 0.5m }, // Invalid side
                                new { asset = "BTC", side = "BUY", quantity = 0.1m }     // Valid order
                            }
                        })
                    },
                    finish_reason = "stop"
                }
            }
        };

        var handler = CreateMockHandler(HttpStatusCode.OK, llamaResponse);
        var client = CreateClient(handler);
        var context = CreateTestContext();

        // Act
        var decision = await client.GenerateDecisionAsync(context);

        // Assert - Should only keep the valid order
        Assert.NotNull(decision);
        Assert.Single(decision.Orders);
        Assert.Equal("BTC", decision.Orders[0].AssetSymbol);
        
        // Verify summary log
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Rejected 3 invalid orders")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
    }

    #region Helper Methods

    private LlamaAgentModelClient CreateClient(HttpMessageHandler handler)
    {
        var httpClient = new HttpClient(handler)
        {
            BaseAddress = new Uri(_options.BaseUrl)
        };
        
        return new LlamaAgentModelClient(
            httpClient,
            Options.Create(_options),
            _loggerMock.Object);
    }

    private static MockHttpMessageHandler CreateMockHandler(HttpStatusCode statusCode, object response)
    {
        var json = JsonSerializer.Serialize(response, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
        });
        return new MockHttpMessageHandler(statusCode, json);
    }

    private static AgentContext CreateTestContext()
    {
        var portfolio = new PortfolioState(
            PortfolioId: Guid.NewGuid(),
            AgentId: Guid.NewGuid(),
            Cash: 10000m,
            Positions: new List<PositionSnapshot>
            {
                new("BTC", 0.5m, 40000m, 42000m)
            },
            AsOf: DateTimeOffset.UtcNow,
            TotalValue: 31000m);

        var candles = new List<MarketCandleDto>
        {
            new("BTC", DateTimeOffset.UtcNow.AddHours(-1), 41000m, 42500m, 40500m, 42000m, 1000m),
            new("BTC", DateTimeOffset.UtcNow, 42000m, 43000m, 41500m, 42500m, 1200m),
            new("ETH", DateTimeOffset.UtcNow, 2200m, 2300m, 2150m, 2250m, 5000m)
        };

        return new AgentContext(
            Guid.NewGuid(),
            ModelProvider.Llama,
            portfolio,
            candles,
            "You are a conservative trading agent. Focus on long-term gains.");
    }

    #endregion
}
