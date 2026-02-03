using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Functions.Activities;
using AiTradingRace.Functions.Models;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Activities;

public class RunAgentDecisionActivityTests
{
    private readonly Mock<IAgentRunner> _agentRunnerMock;
    private readonly Mock<ILogger<RunAgentDecisionActivity>> _loggerMock;

    public RunAgentDecisionActivityTests()
    {
        _agentRunnerMock = new Mock<IAgentRunner>();
        _loggerMock = new Mock<ILogger<RunAgentDecisionActivity>>();
    }

    private TradingDbContext CreateInMemoryDbContext()
    {
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        return new TradingDbContext(options);
    }

    [Fact]
    public async Task Run_WithValidAgent_ReturnsSuccessResult()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();
        var agent = new Agent { Id = Guid.NewGuid(), Name = "TestAgent", IsActive = true };
        dbContext.Agents.Add(agent);
        await dbContext.SaveChangesAsync();

        var portfolio = new PortfolioState(
            Guid.NewGuid(), agent.Id, 10000m,
            Array.Empty<PositionSnapshot>(), DateTimeOffset.UtcNow, 10000m);
        var decision = new AgentDecision(agent.Id, DateTimeOffset.UtcNow, []);
        var runResult = new AgentRunResult(agent.Id, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, portfolio, decision);

        _agentRunnerMock
            .Setup(r => r.RunAgentOnceAsync(agent.Id, It.IsAny<CancellationToken>()))
            .ReturnsAsync(runResult);

        var activity = new RunAgentDecisionActivity(
            _agentRunnerMock.Object, dbContext, _loggerMock.Object);
        var request = new AgentDecisionRequest(agent.Id, Guid.NewGuid(), DateTimeOffset.UtcNow);

        // Act
        var result = await activity.Run(request, CancellationToken.None);

        // Assert
        Assert.True(result.Success);
        Assert.Equal(agent.Id, result.AgentId);
        Assert.Equal(agent.Name, result.AgentName);
        Assert.Null(result.ErrorMessage);
    }

    [Fact]
    public async Task Run_WhenAgentNotFound_ReturnsFailureResult()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();
        var unknownAgentId = Guid.NewGuid();

        var activity = new RunAgentDecisionActivity(
            _agentRunnerMock.Object, dbContext, _loggerMock.Object);
        var request = new AgentDecisionRequest(unknownAgentId, Guid.NewGuid(), DateTimeOffset.UtcNow);

        // Act
        var result = await activity.Run(request, CancellationToken.None);

        // Assert
        Assert.False(result.Success);
        Assert.Equal(unknownAgentId, result.AgentId);
        Assert.Equal("Unknown", result.AgentName);
        Assert.Equal("Agent not found", result.ErrorMessage);
    }

    [Fact]
    public async Task Run_WhenAgentRunnerThrows_ReturnsFailureResult()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();
        var agent = new Agent { Id = Guid.NewGuid(), Name = "FailingAgent", IsActive = true };
        dbContext.Agents.Add(agent);
        await dbContext.SaveChangesAsync();

        _agentRunnerMock
            .Setup(r => r.RunAgentOnceAsync(agent.Id, It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("API timeout"));

        var activity = new RunAgentDecisionActivity(
            _agentRunnerMock.Object, dbContext, _loggerMock.Object);
        var request = new AgentDecisionRequest(agent.Id, Guid.NewGuid(), DateTimeOffset.UtcNow);

        // Act
        var result = await activity.Run(request, CancellationToken.None);

        // Assert
        Assert.False(result.Success);
        Assert.Equal(agent.Id, result.AgentId);
        Assert.Equal(agent.Name, result.AgentName);
        Assert.Contains("API timeout", result.ErrorMessage);
    }
}
