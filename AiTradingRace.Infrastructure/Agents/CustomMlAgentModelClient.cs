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
        
        // Add API key header for authentication (Task 12)
        if (!string.IsNullOrEmpty(_options.ApiKey))
        {
            httpRequest.Headers.Add("X-API-Key", _options.ApiKey);
        }
        
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

    private static AgentDecision MapToDecision(Guid agentId, MlDecisionResponse response)
    {
        var orders = response.Orders.Select(o => new TradeOrder(
            AssetSymbol: o.AssetSymbol,
            Side: ParseSide(o.Side),
            Quantity: o.Quantity,
            LimitPrice: o.LimitPrice
        )).ToList();

        return new AgentDecision(agentId, DateTimeOffset.UtcNow, orders);
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
