using AiTradingRace.Application.Knowledge;
using AiTradingRace.Domain.Entities;

namespace AiTradingRace.Application.Common.Models;

public record AgentContext(
    Guid AgentId,
    ModelProvider ModelProvider,
    PortfolioState Portfolio,
    IReadOnlyList<MarketCandleDto> RecentCandles,
    string Instructions,
    string? DeploymentName = null,
    // Phase 10: Knowledge Graph & Regime Detection
    KnowledgeSubgraph? KnowledgeGraph = null,
    MarketRegime? DetectedRegime = null);

