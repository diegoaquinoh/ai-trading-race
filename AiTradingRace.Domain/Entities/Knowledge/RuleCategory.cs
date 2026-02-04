namespace AiTradingRace.Domain.Entities.Knowledge;

/// <summary>
/// Categories of trading rules in the knowledge graph
/// </summary>
public enum RuleCategory
{
    /// <summary>
    /// Rules related to risk management (position sizing, exposure limits)
    /// </summary>
    RiskManagement = 0,
    
    /// <summary>
    /// Rules related to liquidity and cash reserves
    /// </summary>
    Liquidity = 1,
    
    /// <summary>
    /// Rules related to position sizing
    /// </summary>
    PositionSizing = 2,
    
    /// <summary>
    /// Rules related to entry and exit timing
    /// </summary>
    EntryExit = 3,
    
    /// <summary>
    /// Rules related to stop-loss and drawdown limits
    /// </summary>
    StopLoss = 4,
    
    /// <summary>
    /// Rules related to regulatory compliance
    /// </summary>
    Compliance = 5
}
