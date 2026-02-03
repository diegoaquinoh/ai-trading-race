namespace AiTradingRace.Domain.Entities.Knowledge;

/// <summary>
/// Represents a trading rule node in the knowledge graph
/// </summary>
public class RuleNode
{
    /// <summary>
    /// Unique identifier for the rule (e.g., "R001", "R002")
    /// </summary>
    public string Id { get; set; } = string.Empty;
    
    /// <summary>
    /// Name of the rule (e.g., "MaxPositionSize")
    /// </summary>
    public string Name { get; set; } = string.Empty;
    
    /// <summary>
    /// Detailed description of the rule
    /// </summary>
    public string Description { get; set; } = string.Empty;
    
    /// <summary>
    /// Category of the rule
    /// </summary>
    public RuleCategory Category { get; set; }
    
    /// <summary>
    /// Severity level of the rule
    /// </summary>
    public RuleSeverity Severity { get; set; }
    
    /// <summary>
    /// Threshold value for the rule (if applicable)
    /// </summary>
    public decimal? Threshold { get; set; }
    
    /// <summary>
    /// Unit of measurement for the threshold (e.g., "percentage", "dollars")
    /// </summary>
    public string? Unit { get; set; }
    
    /// <summary>
    /// Whether the rule is currently active
    /// </summary>
    public bool IsActive { get; set; } = true;
    
    /// <summary>
    /// Timestamp when the rule was created
    /// </summary>
    public DateTime CreatedAt { get; set; }
    
    /// <summary>
    /// Timestamp when the rule was last updated
    /// </summary>
    public DateTime? UpdatedAt { get; set; }
}
