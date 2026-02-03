# Phase 10 — GraphRAG-lite: Explainable AI Decisions & Audit Trail

**Objective:** Implement a lightweight knowledge graph system to enable AI agents to cite explicit rules and constraints in their trading decisions, with full traceability and explainability.

**Status:** 📝 PLANNED  
**Priority:** 🟡 MEDIUM  
**Estimated Effort:** 2-3 weeks  
**Date:** January 21, 2026

---

## 📋 Executive Summary

This phase introduces **GraphRAG-lite** — a lightweight knowledge graph and reasoning system that transforms opaque AI trading decisions into transparent, auditable operations. Instead of black-box predictions, agents will provide structured rationales citing specific rules, market regimes, and risk constraints.

### Problem Statement

**Current State:**
- AI agents make trading decisions without explaining their reasoning
- No way to audit "Why did the agent buy ETH at this timestamp?"
- Difficult to debug poor performance or compliance violations
- No mechanism to enforce rule-based constraints consistently

**Target State:**
- Every decision includes explicit citations to rules and market conditions
- Full audit trail from context → reasoning → decision → execution
- Visual knowledge graph showing which rules influenced each trade
- Post-mortem analysis capabilities for strategy refinement

### Key Features

| Feature | Description | Business Value |
|---------|-------------|----------------|
| **Rule Citations** | Agents cite specific rule IDs in decisions | Compliance & audibility |
| **Market Regime Detection** | Classify market state (volatile/bullish/bearish) | Context-aware trading |
| **Knowledge Graph** | Lightweight graph of rules, regimes, assets | Structured reasoning framework |
| **Decision Audit Trail** | Immutable log of decisions + rationales | Debugging & regulatory compliance |
| **Visual Explainability** | Graph visualization of rule dependencies | Human understanding |
| **Regime-Based Rule Activation** | Rules adapt to market conditions | Dynamic risk management |

---

## 🏗️ Architecture Overview

### Knowledge Graph Structure

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE GRAPH (LITE)                                         │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  NODE TYPES:                                                                           │
│                                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐      │
│  │  RULE NODES                                                                  │      │
│  │  ────────────────────────────────────────────────────────────────────────   │      │
│  │  • Rule:R001 "MaxPositionSize"                                              │      │
│  │    - Description: "No single position > 50% of portfolio"                   │      │
│  │    - Threshold: 0.5                                                         │      │
│  │    - Severity: HIGH                                                         │      │
│  │    - Category: RISK_MANAGEMENT                                              │      │
│  │                                                                              │      │
│  │  • Rule:R002 "MinCashReserve"                                               │      │
│  │    - Description: "Maintain minimum $100 cash buffer"                       │      │
│  │    - Threshold: 100.0                                                       │      │
│  │    - Severity: MEDIUM                                                       │      │
│  │    - Category: LIQUIDITY                                                    │      │
│  │                                                                              │      │
│  │  • Rule:R003 "VolatilityStop"                                               │      │
│  │    - Description: "Reduce exposure when volatility > 5%/day"                │      │
│  │    - Threshold: 0.05                                                        │      │
│  │    - Severity: HIGH                                                         │      │
│  │    - Category: RISK_MANAGEMENT                                              │      │
│  └─────────────────────────────────────────────────────────────────────────────┘      │
│                                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐      │
│  │  REGIME NODES                                                                │      │
│  │  ────────────────────────────────────────────────────────────────────────   │      │
│  │  • Regime:VOLATILE                                                          │      │
│  │    - Condition: "Daily volatility > 5%"                                     │      │
│  │    - Lookback: 7 days                                                       │      │
│  │    - Action: Increase cash reserve to 20%                                   │      │
│  │                                                                              │      │
│  │  • Regime:BULLISH                                                           │      │
│  │    - Condition: "7-day MA > 30-day MA"                                      │      │
│  │    - Lookback: 30 days                                                      │      │
│  │    - Action: Allow higher position sizes (60%)                              │      │
│  │                                                                              │      │
│  │  • Regime:BEARISH                                                           │      │
│  │    - Condition: "7-day MA < 30-day MA"                                      │      │
│  │    - Lookback: 30 days                                                      │      │
│  │    - Action: Reduce max position to 30%                                     │      │
│  │                                                                              │      │
│  │  • Regime:STABLE                                                            │      │
│  │    - Condition: "Daily volatility < 2%"                                     │      │
│  │    - Lookback: 7 days                                                       │      │
│  │    - Action: Standard rules apply                                           │      │
│  └─────────────────────────────────────────────────────────────────────────────┘      │
│                                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐      │
│  │  ASSET NODES                                                                 │      │
│  │  ────────────────────────────────────────────────────────────────────────   │      │
│  │  • Asset:BTC (Bitcoin)                                                      │      │
│  │  • Asset:ETH (Ethereum)                                                     │      │
│  │  • Asset:USD (Cash)                                                         │      │
│  └─────────────────────────────────────────────────────────────────────────────┘      │
│                                                                                        │
│  EDGE TYPES (Relationships):                                                           │
│  ────────────────────────────────────────────────────────────────────────────         │
│                                                                                        │
│  Asset:BTC ───[tradable]──────► Rule:R001 (MaxPositionSize)                           │
│  Asset:ETH ───[tradable]──────► Rule:R001 (MaxPositionSize)                           │
│                                                                                        │
│  Regime:VOLATILE ───[activates]──────► Rule:R003 (VolatilityStop)                     │
│  Regime:VOLATILE ───[increases]──────► Rule:R002 (MinCashReserve, threshold→20%)      │
│                                                                                        │
│  Regime:BULLISH ───[relaxes]──────► Rule:R001 (MaxPositionSize, threshold→60%)        │
│  Regime:BEARISH ───[tightens]─────► Rule:R001 (MaxPositionSize, threshold→30%)        │
│                                                                                        │
│  Asset:BTC ───[subject_to]────────► All Risk Rules                                    │
│  Asset:ETH ───[subject_to]────────► All Risk Rules                                    │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Decision Flow with Rule Citations

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                    EXPLAINABLE AI DECISION FLOW                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Market    │     │   Regime    │     │  Knowledge  │     │   Agent     │
│   Data      │     │  Detector   │     │   Graph     │     │   Runner    │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │                   │
       │ 1. Candles        │                   │                   │
       │   (last 30d)      │                   │                   │
       │──────────────────►│                   │                   │
       │                   │                   │                   │
       │                   │ 2. Detect Regime  │                   │
       │                   │    - Calculate    │                   │
       │                   │      volatility   │                   │
       │                   │    - Check MAs    │                   │
       │                   │    - Classify:    │                   │
       │                   │      VOLATILE     │                   │
       │                   │──────────┐        │                   │
       │                   │          │        │                   │
       │                   │◄─────────┘        │                   │
       │                   │                   │                   │
       │                   │ 3. Get Rules for  │                   │
       │                   │    Regime         │                   │
       │                   │──────────────────►│                   │
       │                   │                   │                   │
       │                   │                   │ 4. Extract        │
       │                   │                   │    Subgraph       │
       │                   │                   │    - R001, R002   │
       │                   │                   │    - R003 (active)│
       │                   │                   │──────────┐        │
       │                   │                   │          │        │
       │                   │ 5. Subgraph JSON  │◄─────────┘        │
       │                   │◄──────────────────│                   │
       │                   │                   │                   │
       │                   │ 6. Build Context  │                   │
       │                   │    - Candles      │                   │
       │                   │    - Portfolio    │                   │
       │                   │    - Regime       │                   │
       │                   │    - Rules graph  │                   │
       │                   │───────────────────────────────────────►│
       │                   │                   │                   │
       │                   │                   │                   │ 7. Call LLM
       │                   │                   │                   │    with graph
       │                   │                   │                   │──────────┐
       │                   │                   │                   │          │
       │                   │                   │    8. LLM Response│◄─────────┘
       │                   │                   │       with citations
       │                   │                   │                   │
       │                   │                   │       {            │
       │                   │                   │         "orders": [{
       │                   │                   │           "action": "SELL",
       │                   │                   │           "asset": "BTC",
       │                   │                   │           "quantity": 0.2,
       │                   │                   │           "rationale": "...",
       │                   │                   │           "cited_rules": [
       │                   │                   │             "R003",
       │                   │                   │             "R002"
       │                   │                   │           ]
       │                   │                   │         }],
       │                   │                   │         "reasoning": "...",
       │                   │                   │         "detected_regime": "VOLATILE"
       │                   │                   │       }
       │                   │                   │                   │
       │                   │                   │  9. Validate      │
       │                   │                   │     citations     │
       │                   │                   │◄──────────────────│
       │                   │                   │                   │
       │                   │                   │ 10. Store Decision│
       │                   │                   │     + Audit Trail │
       │                   │                   │──────────┐        │
       │                   │                   │          │        │
       │                   │                   │◄─────────┘        │
       │                   │                   │                   │
       │                   │ 11. Execute Trades│                   │
       │                   │◄──────────────────────────────────────│
       │                   │                   │                   │

                        DecisionLog Saved:
                        ─────────────────────────────────────────
                        AgentId: 1
                        Timestamp: 2026-01-21T14:30:00Z
                        Action: SELL
                        Asset: BTC
                        Quantity: 0.2
                        Rationale: "High volatility detected..."
                        CitedRules: ["R003", "R002"]
                        DetectedRegime: VOLATILE
                        SubgraphSnapshot: { ... }
                        ─────────────────────────────────────────
```

---

## 📦 Domain Model Changes

### New Entities

#### 1. RuleNode (Knowledge Graph Node)

```csharp
// AiTradingRace.Domain/Entities/Knowledge/RuleNode.cs
public class RuleNode
{
    public string Id { get; set; }              // "R001", "R002"
    public string Name { get; set; }            // "MaxPositionSize"
    public string Description { get; set; }     // "No single position..."
    public RuleCategory Category { get; set; }  // RISK_MANAGEMENT, LIQUIDITY
    public RuleSeverity Severity { get; set; }  // HIGH, MEDIUM, LOW
    public decimal? Threshold { get; set; }     // 0.5, 100.0, null
    public string Unit { get; set; }            // "percentage", "dollars", null
    public bool IsActive { get; set; }          // true/false
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
}

public enum RuleCategory
{
    RiskManagement,
    Liquidity,
    PositionSizing,
    EntryExit,
    StopLoss,
    Compliance
}

public enum RuleSeverity
{
    Critical,    // Must never be violated
    High,        // Should avoid violation
    Medium,      // Warning threshold
    Low          // Informational
}
```

#### 2. RegimeNode (Market Condition Node)

```csharp
// AiTradingRace.Domain/Entities/Knowledge/RegimeNode.cs
public class RegimeNode
{
    public string Id { get; set; }              // "VOLATILE", "BULLISH"
    public string Name { get; set; }            // "Volatile Market"
    public string Description { get; set; }     // "Daily volatility > 5%"
    public string Condition { get; set; }       // SQL-like or JSON condition
    public int LookbackDays { get; set; }       // 7, 30
    public DateTime CreatedAt { get; set; }
}
```

#### 3. RuleEdge (Knowledge Graph Relationship)

```csharp
// AiTradingRace.Domain/Entities/Knowledge/RuleEdge.cs
public class RuleEdge
{
    public int Id { get; set; }
    public string SourceNodeId { get; set; }    // "Regime:VOLATILE"
    public string TargetNodeId { get; set; }    // "Rule:R003"
    public EdgeType Type { get; set; }          // ACTIVATES, RELAXES, TIGHTENS
    public string? Parameters { get; set; }     // JSON: {"threshold": 0.6}
    public DateTime CreatedAt { get; set; }
}

public enum EdgeType
{
    Activates,      // Regime enables a rule
    Relaxes,        // Regime loosens a threshold
    Tightens,       // Regime strengthens a threshold
    Tradable,       // Asset is subject to rule
    SubjectTo,      // Asset must comply with rule
    Depends,        // Rule depends on another
    Conflicts       // Rules are mutually exclusive
}
```

#### 4. DecisionLog (Audit Trail)

```csharp
// AiTradingRace.Domain/Entities/DecisionLog.cs
public class DecisionLog
{
    public int Id { get; set; }
    public int AgentId { get; set; }
    public Agent Agent { get; set; }
    
    public DateTime Timestamp { get; set; }
    public string Action { get; set; }          // "BUY", "SELL", "HOLD"
    public string? Asset { get; set; }          // "BTC", "ETH", null (if HOLD)
    public decimal? Quantity { get; set; }      // 0.5, null
    
    // Explainability
    public string Rationale { get; set; }       // LLM's explanation
    public string CitedRuleIds { get; set; }    // JSON array: ["R001", "R003"]
    public string DetectedRegime { get; set; }  // "VOLATILE"
    public string SubgraphSnapshot { get; set; } // JSON of active rules
    
    // Context
    public decimal PortfolioValueBefore { get; set; }
    public decimal PortfolioValueAfter { get; set; }
    public string MarketConditions { get; set; } // JSON: {"BTC_price": 45000}
    
    // Validation
    public bool WasValidated { get; set; }      // true if passed rule checks
    public string? ValidationErrors { get; set; } // null or JSON array
    
    public DateTime CreatedAt { get; set; }
}
```

#### 5. DetectedRegime (Historical Regime Log)

```csharp
// AiTradingRace.Domain/Entities/DetectedRegime.cs
public class DetectedRegime
{
    public int Id { get; set; }
    public string RegimeId { get; set; }        // "VOLATILE"
    public DateTime DetectedAt { get; set; }
    public DateTime? EndedAt { get; set; }      // null if still active
    
    // Metrics at detection
    public decimal Volatility { get; set; }     // 0.087 (8.7%)
    public decimal? MA7 { get; set; }           // 7-day moving average
    public decimal? MA30 { get; set; }          // 30-day moving average
    public string Asset { get; set; }           // "BTC" or "Market"
    
    public DateTime CreatedAt { get; set; }
}
```

---

## 🔧 Application Layer Changes

### 1. IKnowledgeGraphService

```csharp
// AiTradingRace.Application/Knowledge/IKnowledgeGraphService.cs
public interface IKnowledgeGraphService
{
    // Graph operations
    Task<KnowledgeGraph> LoadGraphAsync();
    Task<KnowledgeSubgraph> GetRelevantSubgraphAsync(
        string regimeId, 
        List<string> assetSymbols);
    
    // Node operations
    Task<RuleNode?> GetRuleAsync(string ruleId);
    Task<List<RuleNode>> GetRulesByCategoryAsync(RuleCategory category);
    Task<List<RuleNode>> GetActiveRulesAsync();
    
    // Edge operations
    Task<List<RuleEdge>> GetEdgesForRegimeAsync(string regimeId);
    Task<List<RuleEdge>> GetEdgesForAssetAsync(string assetSymbol);
    
    // Validation
    Task<ValidationResult> ValidateCitationsAsync(
        List<string> citedRuleIds, 
        KnowledgeSubgraph subgraph);
}

public class KnowledgeGraph
{
    public List<RuleNode> Rules { get; set; }
    public List<RegimeNode> Regimes { get; set; }
    public List<RuleEdge> Edges { get; set; }
}

public class KnowledgeSubgraph
{
    public List<RuleNode> ApplicableRules { get; set; }
    public string CurrentRegime { get; set; }
    public Dictionary<string, object> Parameters { get; set; }
    
    public string ToJson() => JsonSerializer.Serialize(this);
}
```

### 2. IRegimeDetector

```csharp
// AiTradingRace.Application/Knowledge/IRegimeDetector.cs
public interface IRegimeDetector
{
    Task<MarketRegime> DetectRegimeAsync(
        string assetSymbol, 
        DateTime fromDate, 
        DateTime toDate);
    
    Task<List<DetectedRegime>> GetHistoricalRegimesAsync(
        string assetSymbol, 
        DateTime fromDate);
}

public class MarketRegime
{
    public string RegimeId { get; set; }        // "VOLATILE"
    public string Name { get; set; }            // "Volatile Market"
    public decimal Volatility { get; set; }     // 0.087
    public decimal? MA7 { get; set; }
    public decimal? MA30 { get; set; }
    public DateTime DetectedAt { get; set; }
    public bool IsActive { get; set; }
}
```

### 3. IAgentContextBuilder (Enhanced)

```csharp
// AiTradingRace.Application/Agents/IAgentContextBuilder.cs
public interface IAgentContextBuilder
{
    Task<AgentContext> BuildContextAsync(
        int agentId, 
        DateTime asOfDate,
        bool includeKnowledgeGraph = false);  // NEW
}

// Updated AgentContext
public class AgentContext
{
    // Existing fields
    public Agent Agent { get; set; }
    public List<MarketCandle> RecentCandles { get; set; }
    public Portfolio Portfolio { get; set; }
    public decimal CashBalance { get; set; }
    
    // NEW: Knowledge graph integration
    public KnowledgeSubgraph? KnowledgeGraph { get; set; }
    public MarketRegime? DetectedRegime { get; set; }
    public List<RuleNode>? ActiveRules { get; set; }
}
```

### 4. IDecisionLogService

```csharp
// AiTradingRace.Application/Decisions/IDecisionLogService.cs
public interface IDecisionLogService
{
    Task<DecisionLog> LogDecisionAsync(CreateDecisionLogDto dto);
    Task<List<DecisionLog>> GetDecisionHistoryAsync(
        int agentId, 
        DateTime? fromDate = null, 
        int? limit = null);
    
    Task<DecisionLog?> GetDecisionByIdAsync(int decisionId);
    
    Task<DecisionAnalytics> AnalyzeDecisionsAsync(
        int agentId, 
        DateTime fromDate, 
        DateTime toDate);
}

public class CreateDecisionLogDto
{
    public int AgentId { get; set; }
    public string Action { get; set; }
    public string? Asset { get; set; }
    public decimal? Quantity { get; set; }
    public string Rationale { get; set; }
    public List<string> CitedRuleIds { get; set; }
    public string DetectedRegime { get; set; }
    public KnowledgeSubgraph Subgraph { get; set; }
    public decimal PortfolioValueBefore { get; set; }
    public decimal PortfolioValueAfter { get; set; }
    public Dictionary<string, decimal> MarketConditions { get; set; }
}

public class DecisionAnalytics
{
    public int TotalDecisions { get; set; }
    public int BuyCount { get; set; }
    public int SellCount { get; set; }
    public int HoldCount { get; set; }
    public Dictionary<string, int> RuleCitationCounts { get; set; }
    public Dictionary<string, int> RegimeDistribution { get; set; }
    public decimal AveragePortfolioChange { get; set; }
}
```

---

## 🛠️ Infrastructure Implementation

### 1. InMemoryKnowledgeGraphService

```csharp
// AiTradingRace.Infrastructure/Knowledge/InMemoryKnowledgeGraphService.cs
public class InMemoryKnowledgeGraphService : IKnowledgeGraphService
{
    private readonly KnowledgeGraph _graph;
    
    public InMemoryKnowledgeGraphService()
    {
        _graph = InitializeGraph();
    }
    
    private KnowledgeGraph InitializeGraph()
    {
        // Hardcoded rules for Phase 10 (can be moved to DB later)
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
                IsActive = true
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
                IsActive = true
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
                IsActive = true
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
                IsActive = true
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
                IsActive = true
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
                LookbackDays = 7
            },
            new RegimeNode
            {
                Id = "BULLISH",
                Name = "Bullish Trend",
                Description = "7-day MA > 30-day MA",
                Condition = "ma_7d > ma_30d",
                LookbackDays = 30
            },
            new RegimeNode
            {
                Id = "BEARISH",
                Name = "Bearish Trend",
                Description = "7-day MA < 30-day MA",
                Condition = "ma_7d < ma_30d",
                LookbackDays = 30
            },
            new RegimeNode
            {
                Id = "STABLE",
                Name = "Stable Market",
                Description = "Daily volatility < 2%",
                Condition = "volatility_7d < 0.02",
                LookbackDays = 7
            }
        };
        
        var edges = new List<RuleEdge>
        {
            // Volatile regime activates volatility stop
            new RuleEdge
            {
                SourceNodeId = "VOLATILE",
                TargetNodeId = "R003",
                Type = EdgeType.Activates
            },
            // Volatile regime increases cash reserve requirement
            new RuleEdge
            {
                SourceNodeId = "VOLATILE",
                TargetNodeId = "R002",
                Type = EdgeType.Tightens,
                Parameters = "{\"threshold\": 200.0}"
            },
            // Bullish regime relaxes max position size
            new RuleEdge
            {
                SourceNodeId = "BULLISH",
                TargetNodeId = "R001",
                Type = EdgeType.Relaxes,
                Parameters = "{\"threshold\": 0.6}"
            },
            // Bearish regime tightens max position size
            new RuleEdge
            {
                SourceNodeId = "BEARISH",
                TargetNodeId = "R001",
                Type = EdgeType.Tightens,
                Parameters = "{\"threshold\": 0.3}"
            },
            // Assets subject to position sizing
            new RuleEdge
            {
                SourceNodeId = "Asset:BTC",
                TargetNodeId = "R001",
                Type = EdgeType.SubjectTo
            },
            new RuleEdge
            {
                SourceNodeId = "Asset:ETH",
                TargetNodeId = "R001",
                Type = EdgeType.SubjectTo
            }
        };
        
        return new KnowledgeGraph
        {
            Rules = rules,
            Regimes = regimes,
            Edges = edges
        };
    }
    
    public Task<KnowledgeSubgraph> GetRelevantSubgraphAsync(
        string regimeId, 
        List<string> assetSymbols)
    {
        // Get edges for current regime
        var regimeEdges = _graph.Edges
            .Where(e => e.SourceNodeId == regimeId)
            .ToList();
        
        // Get affected rules
        var affectedRuleIds = regimeEdges.Select(e => e.TargetNodeId).ToList();
        var applicableRules = _graph.Rules
            .Where(r => r.IsActive && (affectedRuleIds.Contains(r.Id) || r.Severity == RuleSeverity.Critical))
            .ToList();
        
        // Apply regime-specific parameter overrides
        foreach (var rule in applicableRules)
        {
            var edge = regimeEdges.FirstOrDefault(e => e.TargetNodeId == rule.Id);
            if (edge?.Parameters != null)
            {
                var parameters = JsonSerializer.Deserialize<Dictionary<string, object>>(edge.Parameters);
                // Apply parameter overrides (e.g., tighter thresholds)
                // This is a simplified version - full implementation would clone rules
            }
        }
        
        var subgraph = new KnowledgeSubgraph
        {
            ApplicableRules = applicableRules,
            CurrentRegime = regimeId,
            Parameters = new Dictionary<string, object>
            {
                { "regime_edges", regimeEdges.Count },
                { "total_active_rules", applicableRules.Count }
            }
        };
        
        return Task.FromResult(subgraph);
    }
    
    // Other methods omitted for brevity
}
```

### 2. VolatilityBasedRegimeDetector

```csharp
// AiTradingRace.Infrastructure/Knowledge/VolatilityBasedRegimeDetector.cs
public class VolatilityBasedRegimeDetector : IRegimeDetector
{
    private readonly IMarketDataProvider _marketDataProvider;
    
    public VolatilityBasedRegimeDetector(IMarketDataProvider marketDataProvider)
    {
        _marketDataProvider = marketDataProvider;
    }
    
    public async Task<MarketRegime> DetectRegimeAsync(
        string assetSymbol, 
        DateTime fromDate, 
        DateTime toDate)
    {
        var candles = await _marketDataProvider.GetCandlesAsync(
            assetSymbol, 
            fromDate, 
            toDate);
        
        if (candles.Count < 7)
        {
            return new MarketRegime
            {
                RegimeId = "UNKNOWN",
                Name = "Insufficient Data",
                DetectedAt = DateTime.UtcNow,
                IsActive = true
            };
        }
        
        // Calculate volatility (standard deviation of daily returns)
        var returns = new List<decimal>();
        for (int i = 1; i < candles.Count; i++)
        {
            var dailyReturn = (candles[i].Close - candles[i - 1].Close) / candles[i - 1].Close;
            returns.Add(Math.Abs(dailyReturn));
        }
        
        var volatility = CalculateStandardDeviation(returns);
        
        // Calculate moving averages
        var ma7 = candles.TakeLast(7).Average(c => c.Close);
        var ma30 = candles.Count >= 30 
            ? candles.TakeLast(30).Average(c => c.Close) 
            : (decimal?)null;
        
        // Determine regime
        string regimeId;
        string name;
        
        if (volatility > 0.05m)
        {
            regimeId = "VOLATILE";
            name = "Volatile Market";
        }
        else if (ma30.HasValue && ma7 > ma30.Value)
        {
            regimeId = "BULLISH";
            name = "Bullish Trend";
        }
        else if (ma30.HasValue && ma7 < ma30.Value)
        {
            regimeId = "BEARISH";
            name = "Bearish Trend";
        }
        else
        {
            regimeId = "STABLE";
            name = "Stable Market";
        }
        
        return new MarketRegime
        {
            RegimeId = regimeId,
            Name = name,
            Volatility = volatility,
            MA7 = ma7,
            MA30 = ma30,
            DetectedAt = DateTime.UtcNow,
            IsActive = true
        };
    }
    
    private decimal CalculateStandardDeviation(List<decimal> values)
    {
        var average = values.Average();
        var sumOfSquares = values.Sum(v => (v - average) * (v - average));
        return (decimal)Math.Sqrt((double)(sumOfSquares / values.Count));
    }
}
```

### 3. Enhanced LLM Prompt with Knowledge Graph

```csharp
// AiTradingRace.Infrastructure/Agents/LlamaAgentModelClient.cs (modification)
private string BuildPromptWithKnowledgeGraph(AgentContext context)
{
    var prompt = new StringBuilder();
    
    prompt.AppendLine("You are an AI trading agent managing a cryptocurrency portfolio.");
    prompt.AppendLine();
    
    // Include knowledge graph if available
    if (context.KnowledgeGraph != null)
    {
        prompt.AppendLine("=== TRADING RULES & CONSTRAINTS ===");
        prompt.AppendLine($"Current Market Regime: {context.DetectedRegime?.Name ?? "Unknown"}");
        prompt.AppendLine();
        
        foreach (var rule in context.KnowledgeGraph.ApplicableRules.OrderByDescending(r => r.Severity))
        {
            prompt.AppendLine($"[{rule.Id}] {rule.Name} ({rule.Severity})");
            prompt.AppendLine($"    {rule.Description}");
            if (rule.Threshold.HasValue)
            {
                prompt.AppendLine($"    Threshold: {rule.Threshold.Value} {rule.Unit}");
            }
            prompt.AppendLine();
        }
        
        prompt.AppendLine("=== MANDATORY RESPONSE FORMAT ===");
        prompt.AppendLine("You MUST cite rule IDs in your decisions using this format:");
        prompt.AppendLine("{");
        prompt.AppendLine("  \"orders\": [");
        prompt.AppendLine("    {");
        prompt.AppendLine("      \"action\": \"BUY\" | \"SELL\" | \"HOLD\",");
        prompt.AppendLine("      \"asset\": \"BTC\" | \"ETH\",");
        prompt.AppendLine("      \"quantity\": 0.5,");
        prompt.AppendLine("      \"rationale\": \"Explain why...\",");
        prompt.AppendLine("      \"cited_rules\": [\"R001\", \"R003\"]  // REQUIRED");
        prompt.AppendLine("    }");
        prompt.AppendLine("  ],");
        prompt.AppendLine("  \"reasoning\": \"Overall market analysis...\",");
        prompt.AppendLine("  \"detected_regime\": \"VOLATILE\"");
        prompt.AppendLine("}");
        prompt.AppendLine();
    }
    
    // Include market data, portfolio, etc. (existing logic)
    // ...
    
    return prompt.ToString();
}
```

### 4. DecisionLogService

```csharp
// AiTradingRace.Infrastructure/Decisions/DecisionLogService.cs
public class DecisionLogService : IDecisionLogService
{
    private readonly TradingDbContext _context;
    private readonly ILogger<DecisionLogService> _logger;
    
    public async Task<DecisionLog> LogDecisionAsync(CreateDecisionLogDto dto)
    {
        var log = new DecisionLog
        {
            AgentId = dto.AgentId,
            Timestamp = DateTime.UtcNow,
            Action = dto.Action,
            Asset = dto.Asset,
            Quantity = dto.Quantity,
            Rationale = dto.Rationale,
            CitedRuleIds = JsonSerializer.Serialize(dto.CitedRuleIds),
            DetectedRegime = dto.DetectedRegime,
            SubgraphSnapshot = dto.Subgraph.ToJson(),
            PortfolioValueBefore = dto.PortfolioValueBefore,
            PortfolioValueAfter = dto.PortfolioValueAfter,
            MarketConditions = JsonSerializer.Serialize(dto.MarketConditions),
            WasValidated = true,  // Assume validated for now
            CreatedAt = DateTime.UtcNow
        };
        
        _context.DecisionLogs.Add(log);
        await _context.SaveChangesAsync();
        
        _logger.LogInformation(
            "Logged decision {DecisionId} for agent {AgentId}: {Action} {Asset}",
            log.Id, log.AgentId, log.Action, log.Asset);
        
        return log;
    }
    
    public async Task<DecisionAnalytics> AnalyzeDecisionsAsync(
        int agentId, 
        DateTime fromDate, 
        DateTime toDate)
    {
        var decisions = await _context.DecisionLogs
            .Where(d => d.AgentId == agentId 
                && d.Timestamp >= fromDate 
                && d.Timestamp <= toDate)
            .ToListAsync();
        
        var ruleCitationCounts = new Dictionary<string, int>();
        var regimeDistribution = new Dictionary<string, int>();
        
        foreach (var decision in decisions)
        {
            // Count rule citations
            var citedRules = JsonSerializer.Deserialize<List<string>>(decision.CitedRuleIds);
            foreach (var ruleId in citedRules)
            {
                ruleCitationCounts[ruleId] = ruleCitationCounts.GetValueOrDefault(ruleId, 0) + 1;
            }
            
            // Count regime occurrences
            var regime = decision.DetectedRegime;
            regimeDistribution[regime] = regimeDistribution.GetValueOrDefault(regime, 0) + 1;
        }
        
        return new DecisionAnalytics
        {
            TotalDecisions = decisions.Count,
            BuyCount = decisions.Count(d => d.Action == "BUY"),
            SellCount = decisions.Count(d => d.Action == "SELL"),
            HoldCount = decisions.Count(d => d.Action == "HOLD"),
            RuleCitationCounts = ruleCitationCounts,
            RegimeDistribution = regimeDistribution,
            AveragePortfolioChange = decisions.Average(d => d.PortfolioValueAfter - d.PortfolioValueBefore)
        };
    }
}
```

---

## 🌐 API Endpoints

### New Controllers

#### 1. KnowledgeGraphController

```csharp
// AiTradingRace.Web/Controllers/KnowledgeGraphController.cs
[ApiController]
[Route("api/knowledge")]
public class KnowledgeGraphController : ControllerBase
{
    private readonly IKnowledgeGraphService _graphService;
    
    [HttpGet("graph")]
    public async Task<ActionResult<KnowledgeGraph>> GetGraph()
    {
        var graph = await _graphService.LoadGraphAsync();
        return Ok(graph);
    }
    
    [HttpGet("rules")]
    public async Task<ActionResult<List<RuleNode>>> GetRules(
        [FromQuery] RuleCategory? category = null)
    {
        var rules = category.HasValue
            ? await _graphService.GetRulesByCategoryAsync(category.Value)
            : await _graphService.GetActiveRulesAsync();
        return Ok(rules);
    }
    
    [HttpGet("rules/{ruleId}")]
    public async Task<ActionResult<RuleNode>> GetRule(string ruleId)
    {
        var rule = await _graphService.GetRuleAsync(ruleId);
        if (rule == null) return NotFound();
        return Ok(rule);
    }
}
```

#### 2. DecisionLogsController

```csharp
// AiTradingRace.Web/Controllers/DecisionLogsController.cs
[ApiController]
[Route("api/agents/{agentId}/decisions")]
public class DecisionLogsController : ControllerBase
{
    private readonly IDecisionLogService _decisionLogService;
    
    [HttpGet]
    public async Task<ActionResult<List<DecisionLog>>> GetDecisions(
        int agentId,
        [FromQuery] DateTime? fromDate = null,
        [FromQuery] int? limit = 50)
    {
        var decisions = await _decisionLogService.GetDecisionHistoryAsync(
            agentId, 
            fromDate, 
            limit);
        return Ok(decisions);
    }
    
    [HttpGet("{decisionId}")]
    public async Task<ActionResult<DecisionLog>> GetDecision(
        int agentId, 
        int decisionId)
    {
        var decision = await _decisionLogService.GetDecisionByIdAsync(decisionId);
        if (decision == null || decision.AgentId != agentId)
            return NotFound();
        return Ok(decision);
    }
    
    [HttpGet("analytics")]
    public async Task<ActionResult<DecisionAnalytics>> GetAnalytics(
        int agentId,
        [FromQuery] DateTime fromDate,
        [FromQuery] DateTime? toDate = null)
    {
        var analytics = await _decisionLogService.AnalyzeDecisionsAsync(
            agentId, 
            fromDate, 
            toDate ?? DateTime.UtcNow);
        return Ok(analytics);
    }
}
```

#### 3. RegimeController

```csharp
// AiTradingRace.Web/Controllers/RegimeController.cs
[ApiController]
[Route("api/regime")]
public class RegimeController : ControllerBase
{
    private readonly IRegimeDetector _regimeDetector;
    
    [HttpGet("current/{assetSymbol}")]
    public async Task<ActionResult<MarketRegime>> GetCurrentRegime(
        string assetSymbol)
    {
        var toDate = DateTime.UtcNow;
        var fromDate = toDate.AddDays(-30);
        
        var regime = await _regimeDetector.DetectRegimeAsync(
            assetSymbol, 
            fromDate, 
            toDate);
        
        return Ok(regime);
    }
    
    [HttpGet("history/{assetSymbol}")]
    public async Task<ActionResult<List<DetectedRegime>>> GetRegimeHistory(
        string assetSymbol,
        [FromQuery] DateTime? fromDate = null)
    {
        var history = await _regimeDetector.GetHistoricalRegimesAsync(
            assetSymbol, 
            fromDate ?? DateTime.UtcNow.AddDays(-90));
        
        return Ok(history);
    }
}
```

---

## 🎨 Frontend Changes

### 1. Decision History Component

```typescript
// ai-trading-race-web/src/components/DecisionHistory.tsx
interface Decision {
  id: number;
  timestamp: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  asset: string | null;
  quantity: number | null;
  rationale: string;
  citedRuleIds: string[];
  detectedRegime: string;
  portfolioValueBefore: number;
  portfolioValueAfter: number;
}

export function DecisionHistory({ agentId }: { agentId: number }) {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  
  useEffect(() => {
    fetch(`/api/agents/${agentId}/decisions?limit=20`)
      .then(res => res.json())
      .then(data => setDecisions(data));
  }, [agentId]);
  
  return (
    <div className="decision-history">
      <h2>Decision History</h2>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Action</th>
            <th>Asset</th>
            <th>Regime</th>
            <th>Rules Cited</th>
            <th>P/L</th>
          </tr>
        </thead>
        <tbody>
          {decisions.map(decision => {
            const pnl = decision.portfolioValueAfter - decision.portfolioValueBefore;
            const pnlClass = pnl >= 0 ? 'positive' : 'negative';
            
            return (
              <tr 
                key={decision.id} 
                onClick={() => setSelectedDecision(decision)}
                className="clickable"
              >
                <td>{new Date(decision.timestamp).toLocaleString()}</td>
                <td>
                  <Badge variant={decision.action === 'BUY' ? 'success' : 'warning'}>
                    {decision.action}
                  </Badge>
                </td>
                <td>{decision.asset || '-'}</td>
                <td>
                  <Badge variant="info">{decision.detectedRegime}</Badge>
                </td>
                <td>
                  <div className="rule-badges">
                    {decision.citedRuleIds.map(ruleId => (
                      <Badge key={ruleId} variant="secondary" size="sm">
                        {ruleId}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td className={pnlClass}>
                  ${pnl.toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      
      {selectedDecision && (
        <DecisionDetailModal 
          decision={selectedDecision} 
          onClose={() => setSelectedDecision(null)} 
        />
      )}
    </div>
  );
}
```

### 2. Knowledge Graph Visualization

```typescript
// ai-trading-race-web/src/components/KnowledgeGraphVisualization.tsx
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface GraphNode {
  id: string;
  name: string;
  type: 'rule' | 'regime' | 'asset';
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export function KnowledgeGraphVisualization({ 
  decisionId 
}: { 
  decisionId: number 
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  
  useEffect(() => {
    fetch(`/api/agents/decisions/${decisionId}`)
      .then(res => res.json())
      .then(decision => {
        const subgraph = JSON.parse(decision.subgraphSnapshot);
        renderGraph(subgraph);
      });
  }, [decisionId]);
  
  const renderGraph = (subgraph: any) => {
    if (!svgRef.current) return;
    
    // D3.js force-directed graph rendering
    const width = 800;
    const height = 600;
    
    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height);
    
    // Clear previous content
    svg.selectAll('*').remove();
    
    // Transform data for D3
    const nodes: GraphNode[] = subgraph.applicableRules.map((rule: any) => ({
      id: rule.id,
      name: rule.name,
      type: 'rule'
    }));
    
    nodes.push({
      id: subgraph.currentRegime,
      name: subgraph.currentRegime,
      type: 'regime'
    });
    
    // Create links (simplified)
    const links: GraphEdge[] = subgraph.applicableRules.map((rule: any) => ({
      source: subgraph.currentRegime,
      target: rule.id,
      type: 'activates'
    }));
    
    // Force simulation
    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links).id((d: any) => d.id))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2));
    
    // Draw links
    const link = svg.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#999')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2);
    
    // Draw nodes
    const node = svg.append('g')
      .selectAll('circle')
      .data(nodes)
      .join('circle')
      .attr('r', (d: GraphNode) => d.type === 'regime' ? 20 : 15)
      .attr('fill', (d: GraphNode) => 
        d.type === 'regime' ? '#ff7f0e' : '#1f77b4')
      .call(d3.drag() as any);
    
    // Draw labels
    const labels = svg.append('g')
      .selectAll('text')
      .data(nodes)
      .join('text')
      .text((d: GraphNode) => d.name)
      .attr('font-size', 12)
      .attr('dx', 20)
      .attr('dy', 4);
    
    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);
      
      node
        .attr('cx', (d: any) => d.x)
        .attr('cy', (d: any) => d.y);
      
      labels
        .attr('x', (d: any) => d.x)
        .attr('y', (d: any) => d.y);
    });
  };
  
  return (
    <div className="knowledge-graph">
      <h3>Rule Citations Graph</h3>
      <svg ref={svgRef}></svg>
    </div>
  );
}
```

### 3. Decision Analytics Dashboard

```typescript
// ai-trading-race-web/src/components/DecisionAnalytics.tsx
export function DecisionAnalytics({ agentId }: { agentId: number }) {
  const [analytics, setAnalytics] = useState<any>(null);
  
  useEffect(() => {
    const fromDate = new Date();
    fromDate.setMonth(fromDate.getMonth() - 1);
    
    fetch(`/api/agents/${agentId}/decisions/analytics?fromDate=${fromDate.toISOString()}`)
      .then(res => res.json())
      .then(data => setAnalytics(data));
  }, [agentId]);
  
  if (!analytics) return <Loading />;
  
  return (
    <div className="decision-analytics">
      <h2>Decision Analytics (Last 30 Days)</h2>
      
      <div className="stats-grid">
        <StatCard title="Total Decisions" value={analytics.totalDecisions} />
        <StatCard title="Buy Orders" value={analytics.buyCount} color="green" />
        <StatCard title="Sell Orders" value={analytics.sellCount} color="red" />
        <StatCard title="Hold Decisions" value={analytics.holdCount} color="gray" />
      </div>
      
      <div className="charts-row">
        <div className="chart-container">
          <h3>Rule Citation Frequency</h3>
          <BarChart 
            data={Object.entries(analytics.ruleCitationCounts).map(([rule, count]) => ({
              rule,
              count
            }))}
            xKey="rule"
            yKey="count"
          />
        </div>
        
        <div className="chart-container">
          <h3>Market Regime Distribution</h3>
          <PieChart 
            data={Object.entries(analytics.regimeDistribution).map(([regime, count]) => ({
              regime,
              count
            }))}
            labelKey="regime"
            valueKey="count"
          />
        </div>
      </div>
      
      <div className="avg-pnl">
        <h3>Average Portfolio Change per Decision</h3>
        <div className={analytics.averagePortfolioChange >= 0 ? 'positive' : 'negative'}>
          ${analytics.averagePortfolioChange.toFixed(2)}
        </div>
      </div>
    </div>
  );
}
```

---

## 🧪 Testing Strategy

### Unit Tests

```csharp
// AiTradingRace.Tests/Knowledge/KnowledgeGraphServiceTests.cs
public class KnowledgeGraphServiceTests
{
    [Fact]
    public async Task GetRelevantSubgraph_VolatileRegime_ActivatesCorrectRules()
    {
        // Arrange
        var service = new InMemoryKnowledgeGraphService();
        
        // Act
        var subgraph = await service.GetRelevantSubgraphAsync(
            "VOLATILE", 
            new List<string> { "BTC", "ETH" });
        
        // Assert
        Assert.Contains(subgraph.ApplicableRules, r => r.Id == "R003"); // VolatilityStop
        Assert.Contains(subgraph.ApplicableRules, r => r.Id == "R004"); // MaxDrawdown (critical)
        Assert.Equal("VOLATILE", subgraph.CurrentRegime);
    }
    
    [Fact]
    public async Task ValidateCitations_ValidRuleIds_ReturnsSuccess()
    {
        // Arrange
        var service = new InMemoryKnowledgeGraphService();
        var subgraph = await service.GetRelevantSubgraphAsync("VOLATILE", new List<string> { "BTC" });
        
        // Act
        var result = await service.ValidateCitationsAsync(
            new List<string> { "R001", "R003" }, 
            subgraph);
        
        // Assert
        Assert.True(result.IsValid);
        Assert.Empty(result.Errors);
    }
}
```

```csharp
// AiTradingRace.Tests/Knowledge/RegimeDetectorTests.cs
public class RegimeDetectorTests
{
    [Fact]
    public async Task DetectRegime_HighVolatility_ReturnsVolatileRegime()
    {
        // Arrange
        var mockProvider = new Mock<IMarketDataProvider>();
        mockProvider.Setup(p => p.GetCandlesAsync(It.IsAny<string>(), It.IsAny<DateTime>(), It.IsAny<DateTime>()))
            .ReturnsAsync(GenerateVolatileCandles());
        
        var detector = new VolatilityBasedRegimeDetector(mockProvider.Object);
        
        // Act
        var regime = await detector.DetectRegimeAsync("BTC", DateTime.UtcNow.AddDays(-7), DateTime.UtcNow);
        
        // Assert
        Assert.Equal("VOLATILE", regime.RegimeId);
        Assert.True(regime.Volatility > 0.05m);
    }
    
    private List<MarketCandle> GenerateVolatileCandles()
    {
        // Generate synthetic candles with high volatility
        var candles = new List<MarketCandle>();
        decimal price = 50000m;
        for (int i = 0; i < 10; i++)
        {
            var change = (decimal)(new Random().NextDouble() * 0.1 - 0.05); // ±10%
            price *= (1 + change);
            candles.Add(new MarketCandle
            {
                Timestamp = DateTime.UtcNow.AddDays(-10 + i),
                Close = price
            });
        }
        return candles;
    }
}
```

### Integration Tests

```csharp
// AiTradingRace.Tests/Integration/ExplainableDecisionFlowTests.cs
public class ExplainableDecisionFlowTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;
    
    public ExplainableDecisionFlowTests(WebApplicationFactory<Program> factory)
    {
        _client = factory.CreateClient();
    }
    
    [Fact]
    public async Task AgentRunner_WithKnowledgeGraph_LogsDecisionWithCitations()
    {
        // Arrange
        var agentId = 1;
        
        // Act
        var response = await _client.PostAsync($"/api/agents/{agentId}/run", null);
        
        // Assert
        response.EnsureSuccessStatusCode();
        
        // Verify decision log was created with citations
        var decisionsResponse = await _client.GetAsync($"/api/agents/{agentId}/decisions?limit=1");
        var decisions = await decisionsResponse.Content.ReadFromJsonAsync<List<DecisionLog>>();
        
        Assert.NotEmpty(decisions);
        var latestDecision = decisions[0];
        Assert.NotNull(latestDecision.CitedRuleIds);
        Assert.NotEmpty(JsonSerializer.Deserialize<List<string>>(latestDecision.CitedRuleIds));
        Assert.NotNull(latestDecision.DetectedRegime);
        Assert.NotNull(latestDecision.SubgraphSnapshot);
    }
    
    [Fact]
    public async Task KnowledgeGraphEndpoint_ReturnsCompleteGraph()
    {
        // Act
        var response = await _client.GetAsync("/api/knowledge/graph");
        
        // Assert
        response.EnsureSuccessStatusCode();
        var graph = await response.Content.ReadFromJsonAsync<KnowledgeGraph>();
        
        Assert.NotNull(graph);
        Assert.NotEmpty(graph.Rules);
        Assert.NotEmpty(graph.Regimes);
        Assert.NotEmpty(graph.Edges);
    }
}
```

---

## 📊 Database Migration

```sql
-- Add tables for Phase 10
CREATE TABLE RuleNodes (
    Id NVARCHAR(50) PRIMARY KEY,
    Name NVARCHAR(200) NOT NULL,
    Description NVARCHAR(1000) NOT NULL,
    Category INT NOT NULL,
    Severity INT NOT NULL,
    Threshold DECIMAL(18, 8) NULL,
    Unit NVARCHAR(50) NULL,
    IsActive BIT NOT NULL DEFAULT 1,
    CreatedAt DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
    UpdatedAt DATETIME2 NULL
);

CREATE TABLE RegimeNodes (
    Id NVARCHAR(50) PRIMARY KEY,
    Name NVARCHAR(200) NOT NULL,
    Description NVARCHAR(1000) NOT NULL,
    Condition NVARCHAR(500) NOT NULL,
    LookbackDays INT NOT NULL,
    CreatedAt DATETIME2 NOT NULL DEFAULT GETUTCDATE()
);

CREATE TABLE RuleEdges (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    SourceNodeId NVARCHAR(50) NOT NULL,
    TargetNodeId NVARCHAR(50) NOT NULL,
    Type INT NOT NULL,
    Parameters NVARCHAR(MAX) NULL,
    CreatedAt DATETIME2 NOT NULL DEFAULT GETUTCDATE()
);

CREATE TABLE DecisionLogs (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    AgentId INT NOT NULL,
    Timestamp DATETIME2 NOT NULL,
    Action NVARCHAR(20) NOT NULL,
    Asset NVARCHAR(20) NULL,
    Quantity DECIMAL(18, 8) NULL,
    Rationale NVARCHAR(MAX) NOT NULL,
    CitedRuleIds NVARCHAR(500) NOT NULL,
    DetectedRegime NVARCHAR(50) NOT NULL,
    SubgraphSnapshot NVARCHAR(MAX) NOT NULL,
    PortfolioValueBefore DECIMAL(18, 2) NOT NULL,
    PortfolioValueAfter DECIMAL(18, 2) NOT NULL,
    MarketConditions NVARCHAR(MAX) NOT NULL,
    WasValidated BIT NOT NULL DEFAULT 1,
    ValidationErrors NVARCHAR(MAX) NULL,
    CreatedAt DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT FK_DecisionLogs_Agents FOREIGN KEY (AgentId) REFERENCES Agents(Id)
);

CREATE TABLE DetectedRegimes (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    RegimeId NVARCHAR(50) NOT NULL,
    DetectedAt DATETIME2 NOT NULL,
    EndedAt DATETIME2 NULL,
    Volatility DECIMAL(18, 8) NOT NULL,
    MA7 DECIMAL(18, 2) NULL,
    MA30 DECIMAL(18, 2) NULL,
    Asset NVARCHAR(20) NOT NULL,
    CreatedAt DATETIME2 NOT NULL DEFAULT GETUTCDATE()
);

-- Indexes
CREATE INDEX IX_DecisionLogs_AgentId_Timestamp ON DecisionLogs(AgentId, Timestamp DESC);
CREATE INDEX IX_DecisionLogs_DetectedRegime ON DecisionLogs(DetectedRegime);
CREATE INDEX IX_DetectedRegimes_Asset_DetectedAt ON DetectedRegimes(Asset, DetectedAt DESC);
```

---

## 📝 Implementation Sprints

### Sprint 10.1: Domain & Knowledge Graph (3 days)

**Goal:** Establish the knowledge graph foundation

- [ ] Create domain entities (RuleNode, RegimeNode, RuleEdge, DecisionLog, DetectedRegime)
- [ ] Add enums (RuleCategory, RuleSeverity, EdgeType)
- [ ] Define interfaces (IKnowledgeGraphService, IRegimeDetector, IDecisionLogService)
- [ ] Database migration
- [ ] Seed initial rules and regimes

**Deliverables:**
- ✅ Domain models compile
- ✅ Migration applied successfully
- ✅ Test data seeded

---

### Sprint 10.2: Regime Detection (2 days)

**Goal:** Implement market regime classification

- [ ] Implement VolatilityBasedRegimeDetector
- [ ] Add volatility calculation (standard deviation of returns)
- [ ] Add moving average calculations (7-day, 30-day)
- [ ] Create RegimeController with endpoints
- [ ] Unit tests for regime detection

**Deliverables:**
- ✅ Regime detector returns correct classifications
- ✅ API endpoints return current regime
- ✅ 5+ unit tests passing

---

### Sprint 10.3: Knowledge Graph Service (3 days)

**Goal:** Build the graph query and subgraph extraction logic

- [ ] Implement InMemoryKnowledgeGraphService
- [ ] Add GetRelevantSubgraphAsync logic
- [ ] Implement regime-based rule activation
- [ ] Add parameter override logic (tighter/relaxed thresholds)
- [ ] Create KnowledgeGraphController
- [ ] Unit tests for subgraph extraction

**Deliverables:**
- ✅ Subgraphs correctly filter rules based on regime
- ✅ Parameter overrides apply correctly
- ✅ API returns full graph and subgraphs
- ✅ 8+ unit tests passing

---

### Sprint 10.4: Enhanced Agent Context (2 days)

**Goal:** Integrate knowledge graph into agent decision flow

- [ ] Extend AgentContext to include KnowledgeGraph and DetectedRegime
- [ ] Update IAgentContextBuilder to fetch regime and subgraph
- [ ] Modify LLM prompt builder to include rules
- [ ] Add citation parsing logic (extract rule IDs from LLM response)
- [ ] Update AgentRunner to log decisions with citations

**Deliverables:**
- ✅ Agent receives knowledge graph in context
- ✅ LLM responses include rule citations
- ✅ Citations are validated

---

### Sprint 10.5: Decision Audit Trail (3 days)

**Goal:** Implement comprehensive decision logging

- [ ] Implement DecisionLogService
- [ ] Create DecisionLogsController
- [ ] Add LogDecisionAsync method
- [ ] Implement decision analytics (AnalyzeDecisionsAsync)
- [ ] Integration tests for decision logging
- [ ] API tests for decision endpoints

**Deliverables:**
- ✅ Every agent decision is logged with full context
- ✅ Analytics endpoint returns aggregated statistics
- ✅ Decision history endpoint works
- ✅ 6+ tests passing

---

### Sprint 10.6: Frontend Explainability (4 days)

**Goal:** Visualize decisions and knowledge graph in React

- [ ] Create DecisionHistory component
- [ ] Create DecisionDetailModal component
- [ ] Implement KnowledgeGraphVisualization (D3.js)
- [ ] Create DecisionAnalytics dashboard
- [ ] Add rule citation badges
- [ ] Add regime indicator badges
- [ ] Responsive design for mobile

**Deliverables:**
- ✅ Users can view decision history with citations
- ✅ Knowledge graph is visualized
- ✅ Analytics dashboard displays trends
- ✅ UI is intuitive and polished

---

### Sprint 10.7: Testing & Documentation (2 days)

**Goal:** Comprehensive testing and documentation

- [ ] Add 20+ unit tests across all services
- [ ] Add 5+ integration tests for full decision flow
- [ ] Update API documentation (Swagger annotations)
- [ ] Create PHASE10_TECHNICAL_DOCS.md
- [ ] Update README.md with Phase 10 features
- [ ] Record demo video of explainable decisions

**Deliverables:**
- ✅ Test coverage > 80%
- ✅ All tests passing
- ✅ Documentation complete
- ✅ Demo ready for presentation

---

## 🎯 Success Criteria

### Functional Requirements

- [ ] Every agent decision includes explicit rule citations
- [ ] Market regime is detected and influences rule activation
- [ ] Knowledge graph can be queried via API
- [ ] Decision logs include full audit trail (rationale, citations, regime, subgraph)
- [ ] Frontend displays decision history with rule citations
- [ ] Knowledge graph is visualized in the UI
- [ ] Analytics dashboard shows rule citation frequency and regime distribution

### Non-Functional Requirements

- [ ] Response time < 2 seconds for agent decisions (including regime detection)
- [ ] Knowledge graph operations < 100ms
- [ ] Decision logging does not block agent execution
- [ ] Test coverage > 80%
- [ ] Zero breaking changes to existing agent functionality

### Business Requirements

- [ ] Compliance auditors can trace every decision to explicit rules
- [ ] Post-mortem analysis shows which rules influenced performance
- [ ] Regime-based rule adaptation demonstrably improves risk management
- [ ] Non-technical stakeholders can understand agent reasoning

---

## 📚 Technical Documentation

### API Documentation

All new endpoints will be documented with Swagger annotations:

```csharp
/// <summary>
/// Get the knowledge graph of trading rules and market regimes
/// </summary>
/// <returns>Complete knowledge graph with nodes and edges</returns>
[HttpGet("graph")]
[ProducesResponseType(typeof(KnowledgeGraph), StatusCodes.Status200OK)]
public async Task<ActionResult<KnowledgeGraph>> GetGraph() { ... }
```

### Architecture Decision Records (ADRs)

**ADR-010: Lightweight Knowledge Graph (In-Memory)**

- **Status:** Accepted
- **Context:** Need to store and query trading rules without adding database complexity
- **Decision:** Implement in-memory graph with ~20-30 nodes, hardcoded initialization
- **Consequences:** Fast queries, easy to modify, sufficient for MVP, may need database for scale

**ADR-011: Regime Detection Algorithm**

- **Status:** Accepted
- **Context:** Need to classify market conditions for rule activation
- **Decision:** Use volatility (stddev of returns) + moving averages (7d/30d MA)
- **Consequences:** Simple, interpretable, computationally cheap, may need ML-based classifier later

**ADR-012: Citation Format**

- **Status:** Accepted
- **Context:** LLMs must cite rules in structured format
- **Decision:** Require JSON array of rule IDs in `cited_rules` field
- **Consequences:** Machine-parseable, validation possible, clear audit trail

---

## 🚀 Deployment Considerations

### Database Migration

```bash
# Generate migration
dotnet ef migrations add Phase10_KnowledgeGraph --project AiTradingRace.Infrastructure

# Apply migration
dotnet ef database update --project AiTradingRace.Web
```

### Configuration

```json
// appsettings.json
{
  "KnowledgeGraph": {
    "Enabled": true,
    "DefaultRegime": "STABLE",
    "MaxCitedRules": 5
  },
  "RegimeDetection": {
    "LookbackDays": 30,
    "VolatilityThreshold": 0.05,
    "UpdateIntervalMinutes": 60
  }
}
```

### Feature Flag

```csharp
// Program.cs
var knowledgeGraphEnabled = builder.Configuration.GetValue<bool>("KnowledgeGraph:Enabled");

if (knowledgeGraphEnabled)
{
    builder.Services.AddScoped<IKnowledgeGraphService, InMemoryKnowledgeGraphService>();
    builder.Services.AddScoped<IRegimeDetector, VolatilityBasedRegimeDetector>();
    builder.Services.AddScoped<IDecisionLogService, DecisionLogService>();
}
```

---

## 🔗 Dependencies

### NuGet Packages

- None (uses existing packages)

### NPM Packages

```json
{
  "d3": "^7.8.5",
  "@types/d3": "^7.4.0"
}
```

---

## 📖 References

- [GraphRAG: Retrieval-Augmented Generation with Knowledge Graphs](https://arxiv.org/abs/2404.16130)
- [Explainable AI (XAI) in Finance](https://www.oreilly.com/library/view/explainable-ai-for/9781098119126/)
- [D3.js Force-Directed Graphs](https://d3js.org/d3-force)
- [ASP.NET Core Logging Best Practices](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/logging/)

---

## 🎓 Learning Outcomes

By completing Phase 10, the team will gain expertise in:

- Knowledge graph design and querying
- Explainable AI patterns
- Regime detection algorithms
- Audit trail implementation
- Advanced D3.js visualization
- Structured reasoning frameworks

---

## 📞 Support & Questions

For questions or issues during implementation:

1. Check existing tests for usage examples
2. Review ADRs for architectural context
3. Consult API documentation (Swagger)
4. Refer to similar patterns in Phase 8/9 code

---

**Phase 10 Status:** 📝 PLANNED  
**Next Phase:** Phase 11 - Advanced ML Models & AutoML Pipeline

**Last Updated:** January 21, 2026  
**Document Version:** 1.0
