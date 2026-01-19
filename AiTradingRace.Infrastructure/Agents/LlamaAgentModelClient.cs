using System.Net;
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
/// Implementation of IAgentModelClient using Llama API (Groq, Together.ai, etc.)
/// with OpenAI-compatible chat completions endpoint.
/// </summary>
public sealed class LlamaAgentModelClient : IAgentModelClient
{
    private readonly HttpClient _httpClient;
    private readonly LlamaOptions _options;
    private readonly ILogger<LlamaAgentModelClient> _logger;

    public LlamaAgentModelClient(
        HttpClient httpClient,
        IOptions<LlamaOptions> options,
        ILogger<LlamaAgentModelClient> logger)
    {
        _httpClient = httpClient;
        _options = options.Value;
        _logger = logger;
    }

    /// <inheritdoc />
    public async Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken cancellationToken = default)
    {
        _logger.LogDebug(
            "Generating decision for agent {AgentId} using Llama ({Provider}/{Model})",
            context.AgentId, _options.Provider, _options.Model);

        var systemPrompt = BuildSystemPrompt(context.Instructions);
        var userPrompt = BuildUserPrompt(context);

        var request = new LlamaChatRequest
        {
            Model = _options.Model,
            Messages = new[]
            {
                new LlamaChatMessage { Role = "system", Content = systemPrompt },
                new LlamaChatMessage { Role = "user", Content = userPrompt }
            },
            Temperature = _options.Temperature,
            MaxTokens = _options.MaxTokens,
            ResponseFormat = new LlamaResponseFormat { Type = "json_object" }
        };

        try
        {
            var response = await _httpClient.PostAsJsonAsync(
                "/chat/completions",
                request,
                LlamaJsonContext.Default.LlamaChatRequest,
                cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                var errorBody = await response.Content.ReadAsStringAsync(cancellationToken);
                _logger.LogError(
                    "Llama API error: {StatusCode} - {Error}",
                    response.StatusCode, errorBody);

                if (response.StatusCode == HttpStatusCode.TooManyRequests)
                {
                    _logger.LogWarning("Rate limited by Llama API, returning HOLD decision");
                    return CreateHoldDecision(context.AgentId, "Rate limited - holding position");
                }

                return CreateHoldDecision(context.AgentId, $"API error {response.StatusCode}");
            }

            var chatResponse = await response.Content.ReadFromJsonAsync(
                LlamaJsonContext.Default.LlamaChatResponse,
                cancellationToken);

            if (chatResponse?.Choices == null || chatResponse.Choices.Length == 0)
            {
                _logger.LogWarning("Empty response from Llama API");
                return CreateHoldDecision(context.AgentId, "Empty API response");
            }

            var content = chatResponse.Choices[0].Message?.Content ?? "{}";
            _logger.LogDebug("Llama response: {Content}", content);

            // Log token usage
            if (chatResponse.Usage != null)
            {
                _logger.LogInformation(
                    "Llama API usage - Prompt: {PromptTokens}, Completion: {CompletionTokens}, Total: {TotalTokens}",
                    chatResponse.Usage.PromptTokens,
                    chatResponse.Usage.CompletionTokens,
                    chatResponse.Usage.TotalTokens);
            }

            return ParseDecision(context.AgentId, content);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "HTTP error calling Llama API for agent {AgentId}", context.AgentId);
            return CreateHoldDecision(context.AgentId, "Network error - defaulting to HOLD");
        }
        catch (TaskCanceledException ex) when (ex.InnerException is TimeoutException)
        {
            _logger.LogWarning("Llama API timeout for agent {AgentId}", context.AgentId);
            return CreateHoldDecision(context.AgentId, "Request timeout - defaulting to HOLD");
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Failed to parse Llama response for agent {AgentId}", context.AgentId);
            return CreateHoldDecision(context.AgentId, "Invalid response format - defaulting to HOLD");
        }
    }

    private static string BuildSystemPrompt(string instructions)
    {
        return $$"""
            You are an AI trading agent managing a cryptocurrency portfolio.
            
            ## Your Instructions
            {{instructions}}
            
            ## Trading Rules
            1. You can only trade BTC and ETH
            2. Always respond with valid JSON
            3. Use "BUY", "SELL", or "HOLD" for side
            4. Quantity must be positive
            5. Be conservative - don't trade if uncertain
            6. Never invest more than 50% of cash in a single trade
            7. Always keep a minimum cash reserve
            
            ## Response Format
            You MUST respond with a JSON object in this exact format:
            {
              "reasoning": "Brief explanation of your decision",
              "orders": [
                {
                  "asset": "BTC",
                  "side": "BUY",
                  "quantity": 0.1
                }
              ]
            }
            
            If you decide to hold (no trades), return:
            {
              "reasoning": "Explanation",
              "orders": []
            }
            """;
    }

    private static string BuildUserPrompt(AgentContext context)
    {
        var portfolio = context.Portfolio;
        var positions = string.Join("\n", portfolio.Positions.Select(p =>
            $"  - {p.AssetSymbol}: {p.Quantity:F8} @ avg ${p.AveragePrice:F2} (current: ${p.CurrentPrice:F2})"));

        if (string.IsNullOrEmpty(positions))
        {
            positions = "  (no positions)";
        }

        var recentPrices = context.RecentCandles
            .GroupBy(c => c.AssetSymbol)
            .Select(g =>
            {
                var latest = g.OrderByDescending(c => c.TimestampUtc).First();
                var oldest = g.OrderByDescending(c => c.TimestampUtc).Last();
                var change = oldest.Close > 0
                    ? ((latest.Close - oldest.Close) / oldest.Close * 100)
                    : 0;
                return $"  - {g.Key}: ${latest.Close:F2} ({change:+0.00;-0.00}% over {g.Count()} candles)";
            });

        var pricesText = string.Join("\n", recentPrices);
        if (string.IsNullOrEmpty(pricesText))
        {
            pricesText = "  (no market data available)";
        }

        return $"""
            ## Current Portfolio State
            - Cash: ${portfolio.Cash:F2}
            - Total Value: ${portfolio.TotalValue:F2}
            - Positions:
            {positions}
            
            ## Recent Market Data
            {pricesText}
            
            ## Task
            Based on the above, decide your next trading action(s).
            Respond with JSON only.
            """;
    }

    private AgentDecision ParseDecision(Guid agentId, string jsonContent)
    {
        using var doc = JsonDocument.Parse(jsonContent);
        var root = doc.RootElement;

        if (root.TryGetProperty("reasoning", out var reasoningElement))
        {
            _logger.LogInformation("Agent {AgentId} reasoning: {Reasoning}",
                agentId, reasoningElement.GetString());
        }

        var orders = new List<TradeOrder>();

        if (root.TryGetProperty("orders", out var ordersElement) &&
            ordersElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var orderElement in ordersElement.EnumerateArray())
            {
                var asset = orderElement.GetProperty("asset").GetString()?.ToUpperInvariant() ?? "BTC";
                var sideStr = orderElement.GetProperty("side").GetString()?.ToUpperInvariant() ?? "HOLD";
                var quantity = orderElement.GetProperty("quantity").GetDecimal();

                if (quantity <= 0 || sideStr == "HOLD")
                {
                    continue;
                }

                var side = sideStr switch
                {
                    "BUY" => TradeSide.Buy,
                    "SELL" => TradeSide.Sell,
                    _ => TradeSide.Hold
                };

                if (side != TradeSide.Hold)
                {
                    orders.Add(new TradeOrder(asset, side, quantity));
                }
            }
        }

        _logger.LogInformation("Agent {AgentId} generated {OrderCount} orders", agentId, orders.Count);

        return new AgentDecision(agentId, DateTimeOffset.UtcNow, orders);
    }

    private AgentDecision CreateHoldDecision(Guid agentId, string reason)
    {
        _logger.LogWarning("Agent {AgentId}: {Reason}", agentId, reason);
        return new AgentDecision(agentId, DateTimeOffset.UtcNow, Array.Empty<TradeOrder>());
    }
}

#region JSON DTOs

internal sealed class LlamaChatRequest
{
    [JsonPropertyName("model")]
    public string Model { get; set; } = string.Empty;

    [JsonPropertyName("messages")]
    public LlamaChatMessage[] Messages { get; set; } = Array.Empty<LlamaChatMessage>();

    [JsonPropertyName("temperature")]
    public float Temperature { get; set; }

    [JsonPropertyName("max_tokens")]
    public int MaxTokens { get; set; }

    [JsonPropertyName("response_format")]
    public LlamaResponseFormat? ResponseFormat { get; set; }
}

internal sealed class LlamaChatMessage
{
    [JsonPropertyName("role")]
    public string Role { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;
}

internal sealed class LlamaResponseFormat
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = "json_object";
}

internal sealed class LlamaChatResponse
{
    [JsonPropertyName("id")]
    public string? Id { get; set; }

    [JsonPropertyName("choices")]
    public LlamaChatChoice[]? Choices { get; set; }

    [JsonPropertyName("usage")]
    public LlamaUsage? Usage { get; set; }
}

internal sealed class LlamaChatChoice
{
    [JsonPropertyName("index")]
    public int Index { get; set; }

    [JsonPropertyName("message")]
    public LlamaChatMessage? Message { get; set; }

    [JsonPropertyName("finish_reason")]
    public string? FinishReason { get; set; }
}

internal sealed class LlamaUsage
{
    [JsonPropertyName("prompt_tokens")]
    public int PromptTokens { get; set; }

    [JsonPropertyName("completion_tokens")]
    public int CompletionTokens { get; set; }

    [JsonPropertyName("total_tokens")]
    public int TotalTokens { get; set; }
}

/// <summary>
/// JSON source generator context for Llama API DTOs.
/// </summary>
[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(LlamaChatRequest))]
[JsonSerializable(typeof(LlamaChatResponse))]
internal partial class LlamaJsonContext : JsonSerializerContext
{
}

#endregion
