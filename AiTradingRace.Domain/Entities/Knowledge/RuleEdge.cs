namespace AiTradingRace.Domain.Entities.Knowledge;

/// <summary>
/// Represents a relationship between nodes in the knowledge graph
/// </summary>
public class RuleEdge
{
    /// <summary>
    /// Unique identifier for the edge
    /// </summary>
    public int Id { get; set; }
    
    /// <summary>
    /// ID of the source node (e.g., "Regime:VOLATILE", "Asset:BTC")
    /// </summary>
    public string SourceNodeId { get; set; } = string.Empty;
    
    /// <summary>
    /// ID of the target node (e.g., "Rule:R003")
    /// </summary>
    public string TargetNodeId { get; set; } = string.Empty;
    
    /// <summary>
    /// Type of relationship
    /// </summary>
    public EdgeType Type { get; set; }
    
    /// <summary>
    /// Optional parameters for the relationship (JSON format)
    /// e.g., {"threshold": 0.6} for modified thresholds
    /// </summary>
    public string? Parameters { get; set; }
    
    /// <summary>
    /// Timestamp when the edge was created
    /// </summary>
    public DateTime CreatedAt { get; set; }
}
