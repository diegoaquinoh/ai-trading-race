using System.ClientModel;
using System.Text.Json;
using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using Azure.AI.OpenAI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using OpenAI.Chat;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Implementation of IAgentModelClient using Azure OpenAI to generate trading decisions.
/// </summary>
public sealed class AzureOpenAiAgentModelClient : IAgentModelClient
{
    private readonly ChatClient _chatClient;
    private readonly AzureOpenAiOptions _options;
    private readonly ILogger<AzureOpenAiAgentModelClient> _logger;

    public AzureOpenAiAgentModelClient(
        AzureOpenAIClient openAIClient,
        IOptions<AzureOpenAiOptions> options,
        ILogger<AzureOpenAiAgentModelClient> logger)
    {
        _options = options.Value;
        _logger = logger;
        _chatClient = openAIClient.GetChatClient(_options.DeploymentName);
    }

    /// <inheritdoc />
    public async Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken cancellationToken = default)
    {
        _logger.LogDebug("Generating decision for agent {AgentId}", context.AgentId);

        var systemPrompt = BuildSystemPrompt(context.Instructions);
        var userPrompt = BuildUserPrompt(context);

        var chatMessages = new List<ChatMessage>
        {
            new SystemChatMessage(systemPrompt),
            new UserChatMessage(userPrompt)
        };

        var chatOptions = new ChatCompletionOptions
        {
            Temperature = _options.Temperature,
            MaxOutputTokenCount = _options.MaxTokens,
            ResponseFormat = ChatResponseFormat.CreateJsonObjectFormat()
        };

        try
        {
            var response = await _chatClient.CompleteChatAsync(
                chatMessages,
                chatOptions,
                cancellationToken);

            var content = response.Value.Content[0].Text;
            _logger.LogDebug("LLM Response: {Content}", content);

            return ParseDecision(context.AgentId, content);
        }
        catch (ClientResultException ex)
        {
            _logger.LogError(ex, "Azure OpenAI API error for agent {AgentId}", context.AgentId);
            return CreateHoldDecision(context.AgentId, "API error - defaulting to HOLD");
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Failed to parse LLM response for agent {AgentId}", context.AgentId);
            return CreateHoldDecision(context.AgentId, "Invalid JSON response - defaulting to HOLD");
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
