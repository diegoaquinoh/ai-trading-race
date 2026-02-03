using AiTradingRace.Domain.Entities.Knowledge;

namespace AiTradingRace.Application.Knowledge;

/// <summary>
/// Service for querying and managing the knowledge graph of trading rules
/// </summary>
public interface IKnowledgeGraphService
{
    /// <summary>
    /// Load the complete knowledge graph
    /// </summary>
    Task<KnowledgeGraph> LoadGraphAsync();
    
    /// <summary>
    /// Get a relevant subgraph based on current regime and assets
    /// </summary>
    Task<KnowledgeSubgraph> GetRelevantSubgraphAsync(string regimeId, List<string> assetSymbols);
    
    /// <summary>
    /// Get a specific rule by ID
    /// </summary>
    Task<RuleNode?> GetRuleAsync(string ruleId);
    
    /// <summary>
    /// Get all rules in a specific category
    /// </summary>
    Task<List<RuleNode>> GetRulesByCategoryAsync(RuleCategory category);
    
    /// <summary>
    /// Get all active rules
    /// </summary>
    Task<List<RuleNode>> GetActiveRulesAsync();
    
    /// <summary>
    /// Get all edges (relationships) for a specific regime
    /// </summary>
    Task<List<RuleEdge>> GetEdgesForRegimeAsync(string regimeId);
    
    /// <summary>
    /// Get all edges for a specific asset
    /// </summary>
    Task<List<RuleEdge>> GetEdgesForAssetAsync(string assetSymbol);
    
    /// <summary>
    /// Validate that cited rule IDs exist in the subgraph
    /// </summary>
    Task<ValidationResult> ValidateCitationsAsync(List<string> citedRuleIds, KnowledgeSubgraph subgraph);
}

/// <summary>
/// Complete knowledge graph with all nodes and edges
/// </summary>
public class KnowledgeGraph
{
    public List<RuleNode> Rules { get; set; } = new();
    public List<RegimeNode> Regimes { get; set; } = new();
    public List<RuleEdge> Edges { get; set; } = new();
}

/// <summary>
/// Subgraph containing only applicable rules for current context
/// </summary>
public class KnowledgeSubgraph
{
    public List<RuleNode> ApplicableRules { get; set; } = new();
    public string CurrentRegime { get; set; } = string.Empty;
    public Dictionary<string, object> Parameters { get; set; } = new();
    
    public string ToJson() => System.Text.Json.JsonSerializer.Serialize(this);
}

/// <summary>
/// Result of validating rule citations
/// </summary>
public class ValidationResult
{
    public bool IsValid { get; set; }
    public List<string> Errors { get; set; } = new();
}
