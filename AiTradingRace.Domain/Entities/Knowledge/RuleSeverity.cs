namespace AiTradingRace.Domain.Entities.Knowledge;

/// <summary>
/// Severity levels for trading rules
/// </summary>
public enum RuleSeverity
{
    /// <summary>
    /// Critical rule that must never be violated
    /// </summary>
    Critical = 0,
    
    /// <summary>
    /// High priority rule - violations should be avoided
    /// </summary>
    High = 1,
    
    /// <summary>
    /// Medium priority rule - warning threshold
    /// </summary>
    Medium = 2,
    
    /// <summary>
    /// Low priority rule - informational only
    /// </summary>
    Low = 3
}
