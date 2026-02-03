using AiTradingRace.Application.Knowledge;
using AiTradingRace.Domain.Entities.Knowledge;
using Microsoft.Extensions.Logging;
using System.Text.Json;

namespace AiTradingRace.Infrastructure.Knowledge;

/// <summary>
/// In-memory implementation of knowledge graph service
/// </summary>
public class InMemoryKnowledgeGraphService : IKnowledgeGraphService
{
    private readonly KnowledgeGraph _graph;
    private readonly ILogger<InMemoryKnowledgeGraphService> _logger;

    public InMemoryKnowledgeGraphService(ILogger<InMemoryKnowledgeGraphService> logger)
    {
        _logger = logger;
        _graph = InitializeGraph();
    }

    public Task<KnowledgeGraph> LoadGraphAsync()
    {
        return Task.FromResult(_graph);
    }

    public Task<KnowledgeSubgraph> GetRelevantSubgraphAsync(string regimeId, List<string> assetSymbols)
    {
        _logger.LogDebug("Getting subgraph for regime {Regime} and assets {Assets}", regimeId, string.Join(", ", assetSymbols));

        // Get edges for current regime
        var regimeEdges = _graph.Edges
            .Where(e => e.SourceNodeId == regimeId)
            .ToList();

        // Get affected rules
        var affectedRuleIds = regimeEdges.Select(e => e.TargetNodeId).ToList();
        
        // Include all active rules that are either affected by regime or are critical
        var applicableRules = _graph.Rules
            .Where(r => r.IsActive && (affectedRuleIds.Contains(r.Id) || r.Severity == RuleSeverity.Critical))
            .ToList();

        // Apply regime-specific parameter overrides (simplified - in production would clone rules)
        var parameters = new Dictionary<string, object>
        {
            { "regime_edges", regimeEdges.Count },
            { "total_active_rules", applicableRules.Count },
            { "regime_id", regimeId }
        };

        // Add parameter overrides from edges
        foreach (var edge in regimeEdges.Where(e => !string.IsNullOrEmpty(e.Parameters)))
        {
            try
            {
                var edgeParams = JsonSerializer.Deserialize<Dictionary<string, object>>(edge.Parameters!);
                if (edgeParams != null)
                {
                    parameters[$"{edge.TargetNodeId}_override"] = edgeParams;
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to parse parameters for edge {EdgeId}", edge.Id);
            }
        }

        var subgraph = new KnowledgeSubgraph
        {
            ApplicableRules = applicableRules,
            CurrentRegime = regimeId,
            Parameters = parameters
        };

        _logger.LogInformation(
            "Generated subgraph for regime {Regime}: {RuleCount} rules applicable",
            regimeId, applicableRules.Count);

        return Task.FromResult(subgraph);
    }

    public Task<RuleNode?> GetRuleAsync(string ruleId)
    {
        var rule = _graph.Rules.FirstOrDefault(r => r.Id == ruleId);
        return Task.FromResult(rule);
    }

    public Task<List<RuleNode>> GetRulesByCategoryAsync(RuleCategory category)
    {
        var rules = _graph.Rules.Where(r => r.Category == category).ToList();
        return Task.FromResult(rules);
    }

    public Task<List<RuleNode>> GetActiveRulesAsync()
    {
        var rules = _graph.Rules.Where(r => r.IsActive).ToList();
        return Task.FromResult(rules);
    }

    public Task<List<RuleEdge>> GetEdgesForRegimeAsync(string regimeId)
    {
        var edges = _graph.Edges.Where(e => e.SourceNodeId == regimeId).ToList();
        return Task.FromResult(edges);
    }

    public Task<List<RuleEdge>> GetEdgesForAssetAsync(string assetSymbol)
    {
        var assetNodeId = $"Asset:{assetSymbol}";
        var edges = _graph.Edges.Where(e => e.SourceNodeId == assetNodeId).ToList();
        return Task.FromResult(edges);
    }

    public Task<ValidationResult> ValidateCitationsAsync(List<string> citedRuleIds, KnowledgeSubgraph subgraph)
    {
        var result = new ValidationResult { IsValid = true };
        var availableRuleIds = subgraph.ApplicableRules.Select(r => r.Id).ToHashSet();

        foreach (var citedId in citedRuleIds)
        {
            if (!availableRuleIds.Contains(citedId))
            {
                result.IsValid = false;
                result.Errors.Add($"Rule {citedId} was cited but is not in the applicable subgraph");
            }
        }

        return Task.FromResult(result);
    }

    /// <summary>
    /// Initialize the knowledge graph with hardcoded rules and regimes
    /// </summary>
    private KnowledgeGraph InitializeGraph()
    {
        var now = DateTime.UtcNow;

        var rules = new List<RuleNode>
        {
            new RuleNode
            {
                Id = "R001",
                Name = "MaxPositionSize",
                Description = "No single position should exceed 50% of total portfolio value",
                Category = RuleCategory.RiskManagement,
                Severity = RuleSeverity.High,
                Threshold = 0.5m,
                Unit = "percentage",
                IsActive = true,
                CreatedAt = now
            },
            new RuleNode
            {
                Id = "R002",
                Name = "MinCashReserve",
                Description = "Maintain minimum $100 cash buffer for trading costs",
                Category = RuleCategory.Liquidity,
                Severity = RuleSeverity.Medium,
                Threshold = 100.0m,
                Unit = "dollars",
                IsActive = true,
                CreatedAt = now
            },
            new RuleNode
            {
                Id = "R003",
                Name = "VolatilityStop",
                Description = "Reduce exposure when daily volatility exceeds 5%",
                Category = RuleCategory.RiskManagement,
                Severity = RuleSeverity.High,
                Threshold = 0.05m,
                Unit = "percentage",
                IsActive = true,
                CreatedAt = now
            },
            new RuleNode
            {
                Id = "R004",
                Name = "MaxDrawdown",
                Description = "Exit all positions if portfolio drops 20% from peak",
                Category = RuleCategory.StopLoss,
                Severity = RuleSeverity.Critical,
                Threshold = 0.2m,
                Unit = "percentage",
                IsActive = true,
                CreatedAt = now
            },
            new RuleNode
            {
                Id = "R005",
                Name = "DiversificationRule",
                Description = "Hold at least 2 different assets when invested",
                Category = RuleCategory.PositionSizing,
                Severity = RuleSeverity.Medium,
                Threshold = 2.0m,
                Unit = "count",
                IsActive = true,
                CreatedAt = now
            }
        };

        var regimes = new List<RegimeNode>
        {
            new RegimeNode
            {
                Id = "VOLATILE",
                Name = "Volatile Market",
                Description = "Daily volatility > 5%",
                Condition = "volatility_7d > 0.05",
                LookbackDays = 7,
                CreatedAt = now
            },
            new RegimeNode
            {
                Id = "BULLISH",
                Name = "Bullish Trend",
                Description = "7-day MA > 30-day MA",
                Condition = "ma_7d > ma_30d",
                LookbackDays = 30,
                CreatedAt = now
            },
            new RegimeNode
            {
                Id = "BEARISH",
                Name = "Bearish Trend",
                Description = "7-day MA < 30-day MA",
                Condition = "ma_7d < ma_30d",
                LookbackDays = 30,
                CreatedAt = now
            },
            new RegimeNode
            {
                Id = "STABLE",
                Name = "Stable Market",
                Description = "Daily volatility < 2%",
                Condition = "volatility_7d < 0.02",
                LookbackDays = 7,
                CreatedAt = now
            }
        };

        var edges = new List<RuleEdge>
        {
            // Volatile regime activates volatility stop
            new RuleEdge
            {
                Id = 1,
                SourceNodeId = "VOLATILE",
                TargetNodeId = "R003",
                Type = EdgeType.Activates,
                CreatedAt = now
            },
            // Volatile regime increases cash reserve requirement
            new RuleEdge
            {
                Id = 2,
                SourceNodeId = "VOLATILE",
                TargetNodeId = "R002",
                Type = EdgeType.Tightens,
                Parameters = "{\"threshold\": 200.0}",
                CreatedAt = now
            },
            // Bullish regime relaxes max position size
            new RuleEdge
            {
                Id = 3,
                SourceNodeId = "BULLISH",
                TargetNodeId = "R001",
                Type = EdgeType.Relaxes,
                Parameters = "{\"threshold\": 0.6}",
                CreatedAt = now
            },
            // Bearish regime tightens max position size
            new RuleEdge
            {
                Id = 4,
                SourceNodeId = "BEARISH",
                TargetNodeId = "R001",
                Type = EdgeType.Tightens,
                Parameters = "{\"threshold\": 0.3}",
                CreatedAt = now
            },
            // Assets subject to position sizing
            new RuleEdge
            {
                Id = 5,
                SourceNodeId = "Asset:BTC",
                TargetNodeId = "R001",
                Type = EdgeType.SubjectTo,
                CreatedAt = now
            },
            new RuleEdge
            {
                Id = 6,
                SourceNodeId = "Asset:ETH",
                TargetNodeId = "R001",
                Type = EdgeType.SubjectTo,
                CreatedAt = now
            }
        };

        _logger.LogInformation(
            "Initialized knowledge graph: {RuleCount} rules, {RegimeCount} regimes, {EdgeCount} edges",
            rules.Count, regimes.Count, edges.Count);

        return new KnowledgeGraph
        {
            Rules = rules,
            Regimes = regimes,
            Edges = edges
        };
    }
}
