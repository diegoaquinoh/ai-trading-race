using AiTradingRace.Application.Knowledge;
using AiTradingRace.Domain.Entities.Knowledge;
using AiTradingRace.Infrastructure.Knowledge;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace AiTradingRace.Tests.Knowledge;

/// <summary>
/// Unit tests for InMemoryKnowledgeGraphService
/// Sprint 10.3: Knowledge Graph Service
/// </summary>
public class KnowledgeGraphServiceTests
{
    private readonly InMemoryKnowledgeGraphService _service;
    private readonly Mock<ILogger<InMemoryKnowledgeGraphService>> _loggerMock;

    public KnowledgeGraphServiceTests()
    {
        _loggerMock = new Mock<ILogger<InMemoryKnowledgeGraphService>>();
        _service = new InMemoryKnowledgeGraphService(_loggerMock.Object);
    }

    [Fact]
    public async Task LoadGraphAsync_ReturnsCompleteGraph()
    {
        // Act
        var graph = await _service.LoadGraphAsync();

        // Assert
        Assert.NotNull(graph);
        Assert.NotEmpty(graph.Rules);
        Assert.NotEmpty(graph.Regimes);
        Assert.NotEmpty(graph.Edges);
        
        // Verify expected rules exist
        Assert.Contains(graph.Rules, r => r.Id == "R001"); // MaxPositionSize
        Assert.Contains(graph.Rules, r => r.Id == "R002"); // MinCashReserve
        Assert.Contains(graph.Rules, r => r.Id == "R003"); // VolatilityStop
        Assert.Contains(graph.Rules, r => r.Id == "R004"); // MaxDrawdown
        Assert.Contains(graph.Rules, r => r.Id == "R005"); // MaxOpenPositions
        
        // Verify expected regimes exist
        Assert.Contains(graph.Regimes, r => r.Id == "VOLATILE");
        Assert.Contains(graph.Regimes, r => r.Id == "BULLISH");
        Assert.Contains(graph.Regimes, r => r.Id == "BEARISH");
        Assert.Contains(graph.Regimes, r => r.Id == "STABLE");
    }

    [Fact]
    public async Task GetRelevantSubgraph_VolatileRegime_ActivatesCorrectRules()
    {
        // Arrange
        var regimeId = "VOLATILE";
        var assets = new List<string> { "BTC", "ETH" };

        // Act
        var subgraph = await _service.GetRelevantSubgraphAsync(regimeId, assets);

        // Assert
        Assert.NotNull(subgraph);
        Assert.Equal(regimeId, subgraph.CurrentRegime);
        Assert.NotEmpty(subgraph.ApplicableRules);
        
        // Volatile regime should activate VolatilityStop (R003)
        Assert.Contains(subgraph.ApplicableRules, r => r.Id == "R003");
        
        // Critical rules should always be included
        Assert.Contains(subgraph.ApplicableRules, r => r.Id == "R004" && r.Severity == RuleSeverity.Critical);
    }

    [Fact]
    public async Task GetRelevantSubgraph_BullishRegime_RelaxesPositionSizing()
    {
        // Arrange
        var regimeId = "BULLISH";
        var assets = new List<string> { "BTC" };

        // Act
        var subgraph = await _service.GetRelevantSubgraphAsync(regimeId, assets);

        // Assert
        Assert.NotNull(subgraph);
        Assert.Equal("BULLISH", subgraph.CurrentRegime);
        
        // Bullish regime should affect MaxPositionSize (R001)
        Assert.Contains(subgraph.ApplicableRules, r => r.Id == "R001");
    }

    [Fact]
    public async Task GetRelevantSubgraph_BearishRegime_TightensPositionSizing()
    {
        // Arrange
        var regimeId = "BEARISH";
        var assets = new List<string> { "ETH" };

        // Act
        var subgraph = await _service.GetRelevantSubgraphAsync(regimeId, assets);

        // Assert
        Assert.NotNull(subgraph);
        Assert.Equal("BEARISH", subgraph.CurrentRegime);
        
        // Bearish regime should tighten MaxPositionSize (R001)
        Assert.Contains(subgraph.ApplicableRules, r => r.Id == "R001");
    }

    [Fact]
    public async Task GetRelevantSubgraph_StableRegime_AppliesStandardRules()
    {
        // Arrange
        var regimeId = "STABLE";
        var assets = new List<string> { "BTC", "ETH" };

        // Act
        var subgraph = await _service.GetRelevantSubgraphAsync(regimeId, assets);

        // Assert
        Assert.NotNull(subgraph);
        Assert.Equal("STABLE", subgraph.CurrentRegime);
        Assert.NotEmpty(subgraph.ApplicableRules);
        
        // Should still include critical rules
        var criticalRules = subgraph.ApplicableRules.Where(r => r.Severity == RuleSeverity.Critical).ToList();
        Assert.NotEmpty(criticalRules);
    }

    [Fact]
    public async Task GetRuleAsync_ValidRuleId_ReturnsRule()
    {
        // Act
        var rule = await _service.GetRuleAsync("R001");

        // Assert
        Assert.NotNull(rule);
        Assert.Equal("R001", rule.Id);
        Assert.Equal("MaxPositionSize", rule.Name);
        Assert.True(rule.IsActive);
    }

    [Fact]
    public async Task GetRuleAsync_InvalidRuleId_ReturnsNull()
    {
        // Act
        var rule = await _service.GetRuleAsync("R999");

        // Assert
        Assert.Null(rule);
    }

    [Fact]
    public async Task GetRulesByCategoryAsync_RiskManagement_ReturnsCorrectRules()
    {
        // Act
        var rules = await _service.GetRulesByCategoryAsync(RuleCategory.RiskManagement);

        // Assert
        Assert.NotEmpty(rules);
        Assert.All(rules, r => Assert.Equal(RuleCategory.RiskManagement, r.Category));
        
        // Should include R001 (MaxPositionSize) and R003 (VolatilityStop)
        Assert.Contains(rules, r => r.Id == "R001");
        Assert.Contains(rules, r => r.Id == "R003");
    }

    [Fact]
    public async Task GetActiveRulesAsync_ReturnsOnlyActiveRules()
    {
        // Act
        var rules = await _service.GetActiveRulesAsync();

        // Assert
        Assert.NotEmpty(rules);
        Assert.All(rules, r => Assert.True(r.IsActive));
    }

    [Fact]
    public async Task GetEdgesForRegimeAsync_VolatileRegime_ReturnsCorrectEdges()
    {
        // Act
        var edges = await _service.GetEdgesForRegimeAsync("VOLATILE");

        // Assert
        Assert.NotEmpty(edges);
        Assert.All(edges, e => Assert.Equal("VOLATILE", e.SourceNodeId));
        
        // Should have edges to R003 (activates) and R002 (tightens)
        Assert.Contains(edges, e => e.TargetNodeId == "R003" && e.Type == EdgeType.Activates);
        Assert.Contains(edges, e => e.TargetNodeId == "R002" && e.Type == EdgeType.Tightens);
    }

    [Fact]
    public async Task ValidateCitationsAsync_ValidRuleIds_ReturnsSuccess()
    {
        // Arrange
        var subgraph = await _service.GetRelevantSubgraphAsync("VOLATILE", new List<string> { "BTC" });
        // Cite rules that are actually in the VOLATILE subgraph: R003 (activated) and R004 (critical)
        var applicableRuleIds = subgraph.ApplicableRules.Select(r => r.Id).Take(2).ToList();

        // Act
        var result = await _service.ValidateCitationsAsync(applicableRuleIds, subgraph);

        // Assert
        Assert.True(result.IsValid, $"Validation failed. Errors: {string.Join(", ", result.Errors)}");
        Assert.Empty(result.Errors);
    }

    [Fact]
    public async Task ValidateCitationsAsync_InvalidRuleIds_ReturnsErrors()
    {
        // Arrange
        var subgraph = await _service.GetRelevantSubgraphAsync("STABLE", new List<string> { "BTC" });
        var citedRuleIds = new List<string> { "R999", "R888" };

        // Act
        var result = await _service.ValidateCitationsAsync(citedRuleIds, subgraph);

        // Assert
        Assert.False(result.IsValid);
        Assert.NotEmpty(result.Errors);
        Assert.Contains("R999", result.Errors[0]);
    }

    [Fact]
    public async Task ValidateCitationsAsync_MixedValidInvalid_ReturnsPartialErrors()
    {
        // Arrange
        var subgraph = await _service.GetRelevantSubgraphAsync("BULLISH", new List<string> { "ETH" });
        var citedRuleIds = new List<string> { "R001", "R999" }; // One valid, one invalid

        // Act
        var result = await _service.ValidateCitationsAsync(citedRuleIds, subgraph);

        // Assert
        Assert.False(result.IsValid);
        Assert.Single(result.Errors);
        Assert.Contains("R999", result.Errors[0]);
    }

    [Fact]
    public async Task KnowledgeSubgraph_ToJson_ReturnsValidJson()
    {
        // Arrange
        var subgraph = await _service.GetRelevantSubgraphAsync("VOLATILE", new List<string> { "BTC" });

        // Act
        var json = subgraph.ToJson();

        // Assert
        Assert.NotNull(json);
        Assert.NotEmpty(json);
        Assert.Contains("VOLATILE", json);
        Assert.Contains("ApplicableRules", json);
    }
}
