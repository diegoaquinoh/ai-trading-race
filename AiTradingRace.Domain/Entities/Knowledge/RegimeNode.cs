namespace AiTradingRace.Domain.Entities.Knowledge;

/// <summary>
/// Represents a market regime node in the knowledge graph
/// </summary>
public class RegimeNode
{
    /// <summary>
    /// Unique identifier for the regime (e.g., "VOLATILE", "BULLISH")
    /// </summary>
    public string Id { get; set; } = string.Empty;
    
    /// <summary>
    /// Human-readable name of the regime
    /// </summary>
    public string Name { get; set; } = string.Empty;
    
    /// <summary>
    /// Description of the regime
    /// </summary>
    public string Description { get; set; } = string.Empty;
    
    /// <summary>
    /// Condition that defines when this regime is active (e.g., "volatility_7d > 0.05")
    /// </summary>
    public string Condition { get; set; } = string.Empty;
    
    /// <summary>
    /// Number of days to look back when evaluating the regime
    /// </summary>
    public int LookbackDays { get; set; }
    
    /// <summary>
    /// Timestamp when the regime was defined
    /// </summary>
    public DateTime CreatedAt { get; set; }
}
