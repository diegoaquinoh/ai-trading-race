using AiTradingRace.Application.Decisions;
using AiTradingRace.Application.Knowledge;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Domain.Entities.Knowledge;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Decisions;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace AiTradingRace.Tests.Decisions;

/// <summary>
/// Unit tests for DecisionLogService
/// Sprint 10.5: Decision Audit Trail
/// </summary>
public class DecisionLogServiceTests : IDisposable
{
    private readonly TradingDbContext _dbContext;
    private readonly Mock<ILogger<DecisionLogService>> _loggerMock;
    private readonly DecisionLogService _service;
    private readonly Guid _testAgentId = Guid.Parse("11111111-1111-1111-1111-111111111111");

    public DecisionLogServiceTests()
    {
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase($"DecisionLogService_{Guid.NewGuid()}")
            .Options;
        _dbContext = new TradingDbContext(options);
        _loggerMock = new Mock<ILogger<DecisionLogService>>();
        _service = new DecisionLogService(_dbContext, _loggerMock.Object);

        SeedTestData();
    }

    public void Dispose()
    {
        _dbContext.Dispose();
    }

    private void SeedTestData()
    {
        // Add test agent
        _dbContext.Agents.Add(new Agent
        {
            Id = _testAgentId,
            Name = "Test Agent",
            ModelProvider = ModelProvider.Llama,
            Instructions = "Test",
            IsActive = true
        });

        _dbContext.SaveChanges();
    }

    [Fact]
    public async Task LogDecisionAsync_ValidDto_CreatesDecisionLog()
    {
        // Arrange
        var dto = new CreateDecisionLogDto
        {
            AgentId = _testAgentId,
            Action = "BUY",
            Asset = "BTC",
            Quantity = 0.5m,
            Rationale = "Market looks bullish, buying BTC",
            CitedRuleIds = new List<string> { "R001", "R003" },
            DetectedRegime = "BULLISH",
            Subgraph = CreateTestSubgraph(),
            PortfolioValueBefore = 10000m,
            PortfolioValueAfter = 9500m,
            MarketConditions = new Dictionary<string, decimal> { { "BTC_price", 45000m } }
        };

        // Act
        var result = await _service.LogDecisionAsync(dto);

        // Assert
        Assert.NotNull(result);
        Assert.True(result.Id > 0);
        Assert.Equal(_testAgentId, result.AgentId);
        Assert.Equal("BUY", result.Action);
        Assert.Equal("BTC", result.Asset);
        Assert.Equal(0.5m, result.Quantity);
        Assert.Equal("Market looks bullish, buying BTC", result.Rationale);
        Assert.Equal("BULLISH", result.DetectedRegime);
        Assert.Contains("R001", result.CitedRuleIds);
        Assert.True(result.WasValidated);
    }

    [Fact]
    public async Task GetDecisionHistoryAsync_NoFilters_ReturnsAllDecisions()
    {
        // Arrange
        await SeedDecisions(5);

        // Act
        var decisions = await _service.GetDecisionHistoryAsync(_testAgentId);

        // Assert
        Assert.Equal(5, decisions.Count);
        Assert.All(decisions, d => Assert.Equal(_testAgentId, d.AgentId));
        // Should be ordered by timestamp descending
        Assert.True(decisions[0].Timestamp >= decisions[1].Timestamp);
    }

    [Fact]
    public async Task GetDecisionHistoryAsync_WithLimit_ReturnsLimitedResults()
    {
        // Arrange
        await SeedDecisions(10);

        // Act
        var decisions = await _service.GetDecisionHistoryAsync(_testAgentId, limit: 3);

        // Assert
        Assert.Equal(3, decisions.Count);
    }

    [Fact]
    public async Task GetDecisionHistoryAsync_WithFromDate_FiltersCorrectly()
    {
        // Arrange
        var cutoffDate = DateTime.UtcNow.AddDays(-5);
        await SeedDecisions(5, startDaysAgo: 10); // Older decisions
        await SeedDecisions(3, startDaysAgo: 2);  // Recent decisions

        // Act
        var decisions = await _service.GetDecisionHistoryAsync(_testAgentId, fromDate: cutoffDate);

        // Assert
        Assert.Equal(3, decisions.Count);
        Assert.All(decisions, d => Assert.True(d.Timestamp >= cutoffDate));
    }

    [Fact]
    public async Task GetDecisionByIdAsync_ExistingId_ReturnsDecision()
    {
        // Arrange
        var decisions = await SeedDecisions(1);
        var decisionId = decisions[0].Id;

        // Act
        var result = await _service.GetDecisionByIdAsync(decisionId);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(decisionId, result.Id);
        Assert.NotNull(result.Agent);
    }

    [Fact]
    public async Task GetDecisionByIdAsync_NonExistentId_ReturnsNull()
    {
        // Act
        var result = await _service.GetDecisionByIdAsync(99999);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task AnalyzeDecisionsAsync_NoDecisions_ReturnsZeroAnalytics()
    {
        // Arrange
        var fromDate = DateTime.UtcNow.AddDays(-30);
        var toDate = DateTime.UtcNow;

        // Act
        var analytics = await _service.AnalyzeDecisionsAsync(_testAgentId, fromDate, toDate);

        // Assert
        Assert.Equal(0, analytics.TotalDecisions);
        Assert.Equal(0, analytics.BuyCount);
        Assert.Equal(0, analytics.SellCount);
        Assert.Equal(0, analytics.HoldCount);
        Assert.Empty(analytics.RuleCitationCounts);
        Assert.Empty(analytics.RegimeDistribution);
        Assert.Equal(0m, analytics.AveragePortfolioChange);
    }

    [Fact]
    public async Task AnalyzeDecisionsAsync_WithDecisions_ComputesCorrectAnalytics()
    {
        // Arrange
        await _dbContext.DecisionLogs.AddRangeAsync(
            CreateDecisionLog("BUY", "R001", "BULLISH", 100m, 105m),
            CreateDecisionLog("SELL", "R002", "VOLATILE", 105m, 110m),
            CreateDecisionLog("BUY", "R001", "BULLISH", 110m, 108m),
            CreateDecisionLog("HOLD", "R003", "STABLE", 108m, 108m)
        );
        await _dbContext.SaveChangesAsync();

        var fromDate = DateTime.UtcNow.AddDays(-1);
        var toDate = DateTime.UtcNow.AddDays(1);

        // Act
        var analytics = await _service.AnalyzeDecisionsAsync(_testAgentId, fromDate, toDate);

        // Assert
        Assert.Equal(4, analytics.TotalDecisions);
        Assert.Equal(2, analytics.BuyCount);
        Assert.Equal(1, analytics.SellCount);
        Assert.Equal(1, analytics.HoldCount);
        
        // Check rule citations
        Assert.Equal(2, analytics.RuleCitationCounts["R001"]); // Cited twice
        Assert.Equal(1, analytics.RuleCitationCounts["R002"]);
        Assert.Equal(1, analytics.RuleCitationCounts["R003"]);
        
        // Check regime distribution
        Assert.Equal(2, analytics.RegimeDistribution["BULLISH"]);
        Assert.Equal(1, analytics.RegimeDistribution["VOLATILE"]);
        Assert.Equal(1, analytics.RegimeDistribution["STABLE"]);
        
        // Average change: (5 + 5 + (-2) + 0) / 4 = 2
        Assert.Equal(2m, analytics.AveragePortfolioChange);
    }

    [Fact]
    public async Task AnalyzeDecisionsAsync_DateRangeFilter_OnlyIncludesCorrectDecisions()
    {
        // Arrange
        var baseDate = new DateTime(2026, 1, 1, 12, 0, 0, DateTimeKind.Utc);
        
        // Decision outside range (older)
        var oldDecision = CreateDecisionLog("BUY", "R001", "BULLISH", 100m, 105m);
        oldDecision.Timestamp = baseDate.AddDays(-10);
        
        // Decisions inside range
        var decision1 = CreateDecisionLog("SELL", "R002", "VOLATILE", 105m, 110m);
        decision1.Timestamp = baseDate.AddDays(5);
        
        var decision2 = CreateDecisionLog("BUY", "R001", "BULLISH", 110m, 115m);
        decision2.Timestamp = baseDate.AddDays(10);
        
        // Decision outside range (newer)
        var newDecision = CreateDecisionLog("HOLD", "R003", "STABLE", 115m, 115m);
        newDecision.Timestamp = baseDate.AddDays(25);
        
        await _dbContext.DecisionLogs.AddRangeAsync(oldDecision, decision1, decision2, newDecision);
        await _dbContext.SaveChangesAsync();

        var fromDate = baseDate;
        var toDate = baseDate.AddDays(15);

        // Act
        var analytics = await _service.AnalyzeDecisionsAsync(_testAgentId, fromDate, toDate);

        // Assert
        Assert.Equal(2, analytics.TotalDecisions); // Only the 2 decisions in range
        Assert.Equal(1, analytics.BuyCount);
        Assert.Equal(1, analytics.SellCount);
        Assert.Equal(0, analytics.HoldCount);
    }

    // Helper methods

    private async Task<List<DecisionLog>> SeedDecisions(int count, int startDaysAgo = 10)
    {
        var decisions = new List<DecisionLog>();
        for (int i = 0; i < count; i++)
        {
            var decision = CreateDecisionLog(
                i % 3 == 0 ? "BUY" : (i % 3 == 1 ? "SELL" : "HOLD"),
                $"R00{(i % 3) + 1}",
                i % 2 == 0 ? "BULLISH" : "VOLATILE",
                1000m + i * 10,
                1000m + i * 10 + 5);
            
            decision.Timestamp = DateTime.UtcNow.AddDays(-startDaysAgo + i);
            decisions.Add(decision);
        }

        await _dbContext.DecisionLogs.AddRangeAsync(decisions);
        await _dbContext.SaveChangesAsync();
        return decisions;
    }

    private DecisionLog CreateDecisionLog(
        string action,
        string ruleId,
        string regime,
        decimal valueBefore,
        decimal valueAfter)
    {
        return new DecisionLog
        {
            AgentId = _testAgentId,
            Timestamp = DateTime.UtcNow,
            Action = action,
            Asset = action == "HOLD" ? null : "BTC",
            Quantity = action == "HOLD" ? null : 0.5m,
            Rationale = $"Test rationale for {action}",
            CitedRuleIds = System.Text.Json.JsonSerializer.Serialize(new List<string> { ruleId }),
            DetectedRegime = regime,
            SubgraphSnapshot = CreateTestSubgraph().ToJson(),
            PortfolioValueBefore = valueBefore,
            PortfolioValueAfter = valueAfter,
            MarketConditions = System.Text.Json.JsonSerializer.Serialize(
                new Dictionary<string, decimal> { { "BTC_price", 45000m } }),
            WasValidated = true,
            CreatedAt = DateTime.UtcNow
        };
    }

    private KnowledgeSubgraph CreateTestSubgraph()
    {
        return new KnowledgeSubgraph
        {
            ApplicableRules = new List<RuleNode>
            {
                new RuleNode
                {
                    Id = "R001",
                    Name = "MaxPositionSize",
                    Description = "Test rule",
                    Category = RuleCategory.RiskManagement,
                    Severity = RuleSeverity.High,
                    IsActive = true,
                    CreatedAt = DateTime.UtcNow
                }
            },
            CurrentRegime = "BULLISH",
            Parameters = new Dictionary<string, object> { { "test", "value" } }
        };
    }
}
