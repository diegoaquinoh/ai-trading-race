using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Client for the Custom ML service (Python FastAPI).
/// Implements IAgentModelClient to generate trading decisions using the ML model.
/// </summary>
public sealed class CustomMlAgentModelClient : IAgentModelClient
{
    private readonly HttpClient _httpClient;
    private readonly CustomMlAgentOptions _options;
    private readonly ILogger<CustomMlAgentModelClient> _logger;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public CustomMlAgentModelClient(
        HttpClient httpClient,
        IOptions<CustomMlAgentOptions> options,
        ILogger<CustomMlAgentModelClient> logger)
    {
        _httpClient = httpClient;
        _options = options.Value;
        _logger = logger;

        _httpClient.BaseAddress = new Uri(_options.BaseUrl);
        _httpClient.Timeout = TimeSpan.FromSeconds(_options.TimeoutSeconds);
    }

    public async Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken cancellationToken = default)
    {
        var request = MapToRequest(context);

        _logger.LogDebug(
            "Calling ML service for agent {AgentId} with {CandleCount} candles",
            context.AgentId, context.RecentCandles.Count);

        // Create request with API key header
        using var httpRequest = new HttpRequestMessage(HttpMethod.Post, "/predict");
        
        // Add API key header for authentication
        if (!string.IsNullOrEmpty(_options.ApiKey))
        {
            httpRequest.Headers.Add("X-API-Key", _options.ApiKey);
        }
        
        // Add idempotency key for Redis caching (Sprint 8.5)
        // Key format: agentId-timestamp to allow retries within same time window
        var idempotencyKey = GenerateIdempotencyKey(context);
        httpRequest.Headers.Add("Idempotency-Key", idempotencyKey);
        
        _logger.LogDebug("Using idempotency key: {IdempotencyKey}", idempotencyKey);
        
        httpRequest.Content = JsonContent.Create(request, options: JsonOptions);

        var response = await _httpClient.SendAsync(httpRequest, cancellationToken);
        response.EnsureSuccessStatusCode();

        var mlResponse = await response.Content.ReadFromJsonAsync<MlDecisionResponse>(
            JsonOptions, cancellationToken);

        if (mlResponse is null)
        {
            throw new InvalidOperationException("ML service returned null response");
        }

        _logger.LogDebug(
            "ML service returned {OrderCount} orders for agent {AgentId}. Reasoning: {Reasoning}",
            mlResponse.Orders.Count, context.AgentId, mlResponse.Reasoning);

        return MapToDecision(context.AgentId, mlResponse);
    }

    /// <summary>
    /// Generate idempotency key for request caching.
    /// Format: {agentId}-{roundedTimestamp}
    /// This allows the same request within a 5-minute window to be cached.
    /// </summary>
    private static string GenerateIdempotencyKey(AgentContext context)
    {
        // Round timestamp to nearest 5 minutes to group requests
        var now = DateTimeOffset.UtcNow;
        var roundedMinutes = (now.Minute / 5) * 5;
        var roundedTime = new DateTimeOffset(
            now.Year, now.Month, now.Day, 
            now.Hour, roundedMinutes, 0, 
            TimeSpan.Zero);
        
        // Include agent ID and last candle timestamp for uniqueness
        var lastCandleTime = context.RecentCandles.Count > 0 
            ? context.RecentCandles.Max(c => c.TimestampUtc).ToString("yyyyMMddHHmm")
            : "nocandles";
            
        return $"{context.AgentId}-{lastCandleTime}";
    }

    private static MlContextRequest MapToRequest(AgentContext context)
    {
        return new MlContextRequest
        {
            RequestId = Guid.NewGuid().ToString(),
            AgentId = context.AgentId.ToString(),
            Portfolio = new MlPortfolioState
            {
                Cash = context.Portfolio.Cash,
                TotalValue = context.Portfolio.TotalValue,
                Positions = context.Portfolio.Positions.Select(p => new MlPosition
                {
                    Symbol = p.AssetSymbol,
                    Quantity = p.Quantity,
                    AveragePrice = p.AveragePrice
                }).ToList()
            },
            Candles = context.RecentCandles.Select(c => new MlCandle
            {
                Symbol = c.AssetSymbol,
                Timestamp = c.TimestampUtc,
                Open = c.Open,
                High = c.High,
                Low = c.Low,
                Close = c.Close,
                Volume = c.Volume
            }).ToList(),
            Instructions = context.Instructions
        };
    }

    private AgentDecision MapToDecision(Guid agentId, MlDecisionResponse response)
    {
        var orders = new List<TradeOrder>();
        var validationErrors = new List<string>();

        foreach (var mlOrder in response.Orders)
        {
            // Validate individual order
            var validationResult = ValidateMlOrder(mlOrder);
            if (!validationResult.IsValid)
            {
                validationErrors.Add(validationResult.Error!);
                _logger.LogWarning(
                    "Agent {AgentId}: Skipping invalid ML order - {Error}",
                    agentId, validationResult.Error);
                continue;  // Skip this order but process others
            }

            var side = ParseSide(mlOrder.Side);
            if (side != TradeSide.Hold)
            {
                orders.Add(new TradeOrder(
                    AssetSymbol: mlOrder.AssetSymbol,
                    Side: side,
                    Quantity: mlOrder.Quantity,
                    LimitPrice: mlOrder.LimitPrice));
            }
        }

        // Log validation summary
        if (validationErrors.Count > 0)
        {
            _logger.LogWarning(
                "Agent {AgentId}: Rejected {Count} invalid ML orders. Errors: {Errors}",
                agentId, validationErrors.Count, string.Join("; ", validationErrors));
        }

        _logger.LogInformation("Agent {AgentId} generated {OrderCount} valid ML orders", agentId, orders.Count);

        return new AgentDecision(agentId, DateTimeOffset.UtcNow, orders);
    }

    /// <summary>
    /// Validates an individual order from the ML service response.
    /// </summary>
    private OrderValidationResult ValidateMlOrder(MlOrder order)
    {
        // Validate asset
        if (string.IsNullOrWhiteSpace(order.AssetSymbol))
            return OrderValidationResult.Fail("AssetSymbol cannot be empty");

        var allowedAssets = new[] { "BTC", "ETH" };
        if (!allowedAssets.Contains(order.AssetSymbol.ToUpperInvariant()))
            return OrderValidationResult.Fail($"Unknown asset '{order.AssetSymbol}'. Allowed: BTC, ETH");

        // Validate side
        if (string.IsNullOrWhiteSpace(order.Side))
            return OrderValidationResult.Fail("Side cannot be empty");

        var allowedSides = new[] { "BUY", "SELL", "HOLD" };
        if (!allowedSides.Contains(order.Side.ToUpperInvariant()))
            return OrderValidationResult.Fail($"Invalid side '{order.Side}'. Allowed: BUY, SELL, HOLD");

        // Validate quantity
        if (order.Quantity <= 0)
            return OrderValidationResult.Fail($"Quantity must be positive, got {order.Quantity}");

        // Sanity check: no single order > 1000 units
        if (order.Quantity > 1000)
            return OrderValidationResult.Fail($"Quantity {order.Quantity} exceeds maximum allowed (1000)");

        // Validate limit price if provided
        if (order.LimitPrice.HasValue && order.LimitPrice.Value <= 0)
            return OrderValidationResult.Fail($"LimitPrice must be positive if provided, got {order.LimitPrice.Value}");

        return OrderValidationResult.Success();
    }

    private static TradeSide ParseSide(string side) => side.ToUpperInvariant() switch
    {
        "BUY" => TradeSide.Buy,
        "SELL" => TradeSide.Sell,
        _ => TradeSide.Hold
    };

    #region DTOs for Python API

    private record MlContextRequest
    {
        public string SchemaVersion { get; init; } = "1.0";
        public required string RequestId { get; init; }
        public required string AgentId { get; init; }
        public required MlPortfolioState Portfolio { get; init; }
        public required List<MlCandle> Candles { get; init; }
        public string Instructions { get; init; } = "";
    }

    private record MlPortfolioState
    {
        public decimal Cash { get; init; }
        public decimal TotalValue { get; init; }
        public required List<MlPosition> Positions { get; init; }
    }

    private record MlPosition
    {
        public required string Symbol { get; init; }
        public decimal Quantity { get; init; }
        public decimal AveragePrice { get; init; }
    }

    private record MlCandle
    {
        public required string Symbol { get; init; }
        public DateTimeOffset Timestamp { get; init; }
        public decimal Open { get; init; }
        public decimal High { get; init; }
        public decimal Low { get; init; }
        public decimal Close { get; init; }
        public decimal Volume { get; init; }
    }

    private record MlDecisionResponse
    {
        public string SchemaVersion { get; init; } = "1.0";
        public required string ModelVersion { get; init; }
        public required string RequestId { get; init; }
        public required string AgentId { get; init; }
        public DateTimeOffset CreatedAt { get; init; }
        public required List<MlOrder> Orders { get; init; }
        public List<MlExplanationSignal> Signals { get; init; } = [];
        public string Reasoning { get; init; } = "";
    }

    private record MlOrder
    {
        public required string AssetSymbol { get; init; }
        public required string Side { get; init; }
        public decimal Quantity { get; init; }
        public decimal? LimitPrice { get; init; }
    }

    private record MlExplanationSignal
    {
        public required string Feature { get; init; }
        public double Value { get; init; }
        public required string Rule { get; init; }
        public bool Fired { get; init; }
        public required string Contribution { get; init; }
    }

    #endregion
}
