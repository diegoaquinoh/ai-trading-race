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

        var systemPrompt = BuildSystemPrompt(context.Instructions, context);
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

    private static string BuildSystemPrompt(string instructions, AgentContext context)
    {
        var sb = new System.Text.StringBuilder();
        
        sb.AppendLine("You are an AI trading agent managing a cryptocurrency portfolio.");
        sb.AppendLine();
        sb.AppendLine("## Your Instructions");
        sb.AppendLine(instructions);
        sb.AppendLine();
        sb.AppendLine("## Trading Rules");
        sb.AppendLine("1. You can only trade BTC and ETH");
        sb.AppendLine("2. Always respond with valid JSON");
        sb.AppendLine("3. Use \"BUY\", \"SELL\", or \"HOLD\" for side");
        sb.AppendLine("4. Quantity must be positive");
        sb.AppendLine("5. Be conservative - don't trade if uncertain");

        // Phase 10: Add knowledge graph rules if available
        if (context.KnowledgeGraph != null && context.DetectedRegime != null)
        {
            sb.AppendLine();
            sb.AppendLine("## ACTIVE TRADING CONSTRAINTS");
            sb.AppendLine($"Current Market Regime: {context.DetectedRegime.Name} (Volatility: {context.DetectedRegime.Volatility:P2})");
            sb.AppendLine();
            
            foreach (var rule in context.KnowledgeGraph.ApplicableRules.OrderByDescending(r => r.Severity))
            {
                sb.AppendLine($"[{rule.Id}] {rule.Name} - {rule.Severity}");
                sb.AppendLine($"    {rule.Description}");
                if (rule.Threshold.HasValue)
                {
                    sb.AppendLine($"    Threshold: {rule.Threshold.Value} {rule.Unit}");
                }
                sb.AppendLine();
            }
            
            sb.AppendLine("⚠️ IMPORTANT: You MUST cite which rule IDs influenced your decision in the 'cited_rules' field.");
        }

        sb.AppendLine();
        sb.AppendLine("## Response Format");
        sb.AppendLine("You MUST respond with a JSON object in this exact format:");
        sb.AppendLine("{");
        sb.AppendLine("  \"reasoning\": \"Brief explanation of your decision\",");
        sb.AppendLine("  \"orders\": [");
        sb.AppendLine("    {");
        sb.AppendLine("      \"asset\": \"BTC\",");
        sb.AppendLine("      \"side\": \"BUY\",");
        sb.AppendLine("      \"quantity\": 0.1");
        sb.AppendLine("    }");
        sb.Append("  ]");
        
        // Add cited_rules field if knowledge graph is enabled
        if (context.KnowledgeGraph != null)
        {
            sb.AppendLine(",");
            sb.AppendLine("  \"cited_rules\": [\"R001\", \"R003\"]");
        }
        else
        {
            sb.AppendLine();
        }
        
        sb.AppendLine("}");
        sb.AppendLine();
        sb.AppendLine("If you decide to hold (no trades), return:");
        sb.AppendLine("{");
        sb.AppendLine("  \"reasoning\": \"Explanation\",");
        sb.Append("  \"orders\": []");
        
        if (context.KnowledgeGraph != null)
        {
            sb.AppendLine(",");
            sb.AppendLine("  \"cited_rules\": []");
        }
        else
        {
            sb.AppendLine();
        }
        
        sb.AppendLine("}");

        return sb.ToString();
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

        // Validate required fields exist
        if (!root.TryGetProperty("reasoning", out var reasoningElement))
        {
            _logger.LogWarning("LLM response missing 'reasoning' field for agent {AgentId}", agentId);
            return CreateHoldDecision(agentId, "Invalid response: missing reasoning field");
        }

        if (!root.TryGetProperty("orders", out var ordersElement))
        {
            _logger.LogWarning("LLM response missing 'orders' field for agent {AgentId}", agentId);
            return CreateHoldDecision(agentId, "Invalid response: missing orders field");
        }

        // Validate field types
        if (ordersElement.ValueKind != JsonValueKind.Array)
        {
            _logger.LogWarning(
                "LLM response 'orders' is not an array (got {Type}) for agent {AgentId}",
                ordersElement.ValueKind, agentId);
            return CreateHoldDecision(agentId, "Invalid response: orders must be an array");
        }

        var reasoning = reasoningElement.GetString();
        if (string.IsNullOrWhiteSpace(reasoning))
        {
            _logger.LogWarning("LLM response has empty reasoning for agent {AgentId}", agentId);
            return CreateHoldDecision(agentId, "Invalid response: empty reasoning");
        }

        _logger.LogInformation("Agent {AgentId} reasoning: {Reasoning}", agentId, reasoning);

        // Phase 10: Extract cited rules if present
        List<string>? citedRuleIds = null;
        if (root.TryGetProperty("cited_rules", out var citedRulesElement))
        {
            if (citedRulesElement.ValueKind == JsonValueKind.Array)
            {
                citedRuleIds = new List<string>();
                foreach (var ruleElement in citedRulesElement.EnumerateArray())
                {
                    if (ruleElement.ValueKind == JsonValueKind.String)
                    {
                        var ruleId = ruleElement.GetString();
                        if (!string.IsNullOrWhiteSpace(ruleId))
                        {
                            citedRuleIds.Add(ruleId);
                        }
                    }
                }
                
                if (citedRuleIds.Count > 0)
                {
                    _logger.LogInformation(
                        "Agent {AgentId} cited rules: {Rules}",
                        agentId, string.Join(", ", citedRuleIds));
                }
            }
        }

        var orders = new List<TradeOrder>();
        var validationErrors = new List<string>();

        foreach (var orderElement in ordersElement.EnumerateArray())
        {
            // Validate individual order
            var validationResult = ValidateOrder(orderElement);
            if (!validationResult.IsValid)
            {
                validationErrors.Add(validationResult.Error!);
                _logger.LogWarning(
                    "Agent {AgentId}: Skipping invalid order - {Error}",
                    agentId, validationResult.Error);
                continue;  // Skip this order but process others
            }

            var asset = orderElement.GetProperty("asset").GetString()!.ToUpperInvariant();
            var sideStr = orderElement.GetProperty("side").GetString()!.ToUpperInvariant();
            var quantity = orderElement.GetProperty("quantity").GetDecimal();

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

        // Log validation summary
        if (validationErrors.Count > 0)
        {
            _logger.LogWarning(
                "Agent {AgentId}: Rejected {Count} invalid orders. Errors: {Errors}",
                agentId, validationErrors.Count, string.Join("; ", validationErrors));
        }

        _logger.LogInformation("Agent {AgentId} generated {OrderCount} valid orders", agentId, orders.Count);

        return new AgentDecision(
            agentId, 
            DateTimeOffset.UtcNow, 
            orders,
            CitedRuleIds: citedRuleIds,
            Rationale: reasoning);
    }

    /// <summary>
    /// Validates an individual order element from the LLM response.
    /// </summary>
    private OrderValidationResult ValidateOrder(JsonElement orderElement)
    {
        // Check required fields exist
        if (!orderElement.TryGetProperty("asset", out var assetElement))
            return OrderValidationResult.Fail("Missing 'asset' field");

        if (!orderElement.TryGetProperty("side", out var sideElement))
            return OrderValidationResult.Fail("Missing 'side' field");

        if (!orderElement.TryGetProperty("quantity", out var quantityElement))
            return OrderValidationResult.Fail("Missing 'quantity' field");

        // Validate field types
        if (assetElement.ValueKind != JsonValueKind.String)
            return OrderValidationResult.Fail($"'asset' must be a string, got {assetElement.ValueKind}");

        if (sideElement.ValueKind != JsonValueKind.String)
            return OrderValidationResult.Fail($"'side' must be a string, got {sideElement.ValueKind}");

        if (quantityElement.ValueKind != JsonValueKind.Number)
            return OrderValidationResult.Fail($"'quantity' must be a number, got {quantityElement.ValueKind}");

        // Validate values
        var asset = assetElement.GetString();
        if (string.IsNullOrWhiteSpace(asset))
            return OrderValidationResult.Fail("'asset' cannot be empty");

        var allowedAssets = new[] { "BTC", "ETH" };
        if (!allowedAssets.Contains(asset.ToUpperInvariant()))
            return OrderValidationResult.Fail($"Unknown asset '{asset}'. Allowed: BTC, ETH");

        var side = sideElement.GetString()?.ToUpperInvariant();
        var allowedSides = new[] { "BUY", "SELL", "HOLD" };
        if (string.IsNullOrWhiteSpace(side) || !allowedSides.Contains(side))
            return OrderValidationResult.Fail($"Invalid side '{side}'. Allowed: BUY, SELL, HOLD");

        var quantity = quantityElement.GetDecimal();
        if (quantity <= 0)
            return OrderValidationResult.Fail($"Quantity must be positive, got {quantity}");

        // Sanity check: no single order > 1000 units
        if (quantity > 1000)
            return OrderValidationResult.Fail($"Quantity {quantity} exceeds maximum allowed (1000)");

        return OrderValidationResult.Success();
    }

    private AgentDecision CreateHoldDecision(Guid agentId, string reason)
    {
        _logger.LogWarning("Agent {AgentId}: {Reason}", agentId, reason);
        return new AgentDecision(
            agentId, 
            DateTimeOffset.UtcNow, 
            Array.Empty<TradeOrder>(),
            CitedRuleIds: null,
            Rationale: reason);
    }
}
