namespace AiTradingRace.Domain.Entities;

/// <summary>
/// Represents an audit log of an AI agent's trading decision with explainability
/// </summary>
public class DecisionLog
{
    /// <summary>
    /// Unique identifier for the decision log entry
    /// </summary>
    public int Id { get; set; }
    
    /// <summary>
    /// ID of the agent that made the decision
    /// </summary>
    public Guid AgentId { get; set; }
    
    /// <summary>
    /// Navigation property to the agent
    /// </summary>
    public Agent Agent { get; set; } = null!;
    
    /// <summary>
    /// Timestamp when the decision was made
    /// </summary>
    public DateTime Timestamp { get; set; }
    
    /// <summary>
    /// Action taken (BUY, SELL, HOLD)
    /// </summary>
    public string Action { get; set; } = string.Empty;
    
    /// <summary>
    /// Asset symbol if applicable (BTC, ETH, or null for HOLD)
    /// </summary>
    public string? Asset { get; set; }
    
    /// <summary>
    /// Quantity of the order (null for HOLD)
    /// </summary>
    public decimal? Quantity { get; set; }
    
    /// <summary>
    /// LLM's explanation for the decision
    /// </summary>
    public string Rationale { get; set; } = string.Empty;
    
    /// <summary>
    /// JSON array of cited rule IDs (e.g., ["R001", "R003"])
    /// </summary>
    public string CitedRuleIds { get; set; } = string.Empty;
    
    /// <summary>
    /// Detected market regime at decision time (e.g., "VOLATILE")
    /// </summary>
    public string DetectedRegime { get; set; } = string.Empty;
    
    /// <summary>
    /// JSON snapshot of the active knowledge subgraph
    /// </summary>
    public string SubgraphSnapshot { get; set; } = string.Empty;
    
    /// <summary>
    /// Portfolio value before the decision
    /// </summary>
    public decimal PortfolioValueBefore { get; set; }
    
    /// <summary>
    /// Portfolio value after the decision
    /// </summary>
    public decimal PortfolioValueAfter { get; set; }
    
    /// <summary>
    /// JSON object with market conditions at decision time (prices, volatility, etc.)
    /// </summary>
    public string MarketConditions { get; set; } = string.Empty;
    
    /// <summary>
    /// Whether the decision passed validation checks
    /// </summary>
    public bool WasValidated { get; set; }
    
    /// <summary>
    /// JSON array of validation errors (null if none)
    /// </summary>
    public string? ValidationErrors { get; set; }
    
    /// <summary>
    /// Timestamp when the log was created
    /// </summary>
    public DateTime CreatedAt { get; set; }
}
