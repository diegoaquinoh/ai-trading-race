namespace AiTradingRace.Domain.Entities.Knowledge;

/// <summary>
/// Types of relationships in the knowledge graph
/// </summary>
public enum EdgeType
{
    /// <summary>
    /// A regime activates or enables a rule
    /// </summary>
    Activates = 0,
    
    /// <summary>
    /// A regime relaxes or loosens a rule's threshold
    /// </summary>
    Relaxes = 1,
    
    /// <summary>
    /// A regime tightens or strengthens a rule's threshold
    /// </summary>
    Tightens = 2,
    
    /// <summary>
    /// An asset can be traded under a rule
    /// </summary>
    Tradable = 3,
    
    /// <summary>
    /// An asset is subject to a rule
    /// </summary>
    SubjectTo = 4,
    
    /// <summary>
    /// A rule depends on another rule
    /// </summary>
    Depends = 5,
    
    /// <summary>
    /// Rules are mutually exclusive
    /// </summary>
    Conflicts = 6
}
