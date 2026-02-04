using AiTradingRace.Application.Knowledge;
using AiTradingRace.Domain.Entities;

namespace AiTradingRace.Application.Decisions;

/// <summary>
/// Service for logging and analyzing AI trading decisions
/// </summary>
public interface IDecisionLogService
{
    /// <summary>
    /// Log a new decision with full context
    /// </summary>
    Task<DecisionLog> LogDecisionAsync(CreateDecisionLogDto dto);
    
    /// <summary>
    /// Get decision history for an agent
    /// </summary>
    Task<List<DecisionLog>> GetDecisionHistoryAsync(Guid agentId, DateTime? fromDate = null, int? limit = null);
    
    /// <summary>
    /// Get a specific decision by ID
    /// </summary>
    Task<DecisionLog?> GetDecisionByIdAsync(int decisionId);
    
    /// <summary>
    /// Analyze decisions for an agent over a time period
    /// </summary>
    Task<DecisionAnalytics> AnalyzeDecisionsAsync(Guid agentId, DateTime fromDate, DateTime toDate);
}

/// <summary>
/// DTO for creating a decision log
/// </summary>
public class CreateDecisionLogDto
{
    public Guid AgentId { get; set; }
    public string Action { get; set; } = string.Empty;
    public string? Asset { get; set; }
    public decimal? Quantity { get; set; }
    public string Rationale { get; set; } = string.Empty;
    public List<string> CitedRuleIds { get; set; } = new();
    public string DetectedRegime { get; set; } = string.Empty;
    public KnowledgeSubgraph Subgraph { get; set; } = null!;
    public decimal PortfolioValueBefore { get; set; }
    public decimal PortfolioValueAfter { get; set; }
    public Dictionary<string, decimal> MarketConditions { get; set; } = new();
}

/// <summary>
/// Analytics about an agent's decisions
/// </summary>
public class DecisionAnalytics
{
    public int TotalDecisions { get; set; }
    public int BuyCount { get; set; }
    public int SellCount { get; set; }
    public int HoldCount { get; set; }
    public Dictionary<string, int> RuleCitationCounts { get; set; } = new();
    public Dictionary<string, int> RegimeDistribution { get; set; } = new();
    public decimal AveragePortfolioChange { get; set; }
}
