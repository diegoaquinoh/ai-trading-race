using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Functions.Functions;
using AiTradingRace.Infrastructure.Database;
using Microsoft.Azure.Functions.Worker;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Functions;

public class RunAgentsFunctionTests
{
    private readonly Mock<IAgentRunner> _agentRunnerMock;
    private readonly Mock<ILogger<RunAgentsFunction>> _loggerMock;

    public RunAgentsFunctionTests()
    {
        _agentRunnerMock = new Mock<IAgentRunner>();
        _loggerMock = new Mock<ILogger<RunAgentsFunction>>();
    }

    private TradingDbContext CreateInMemoryDbContext()
    {
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        return new TradingDbContext(options);
    }

    [Fact]
    public async Task RunAllAgents_WithNoActiveAgents_DoesNotCallAgentRunner()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();
        // No agents added
        var function = new RunAgentsFunction(dbContext, _agentRunnerMock.Object, _loggerMock.Object);
        var timerInfo = CreateTimerInfo();

        // Act
        await function.RunAllAgents(timerInfo, CancellationToken.None);

        // Assert
        _agentRunnerMock.Verify(
            r => r.RunAgentOnceAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunAllAgents_WithActiveAgents_RunsEachAgent()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();

        var agent1 = new Agent { Id = Guid.NewGuid(), Name = "Agent1", IsActive = true };
        var agent2 = new Agent { Id = Guid.NewGuid(), Name = "Agent2", IsActive = true };
        dbContext.Agents.AddRange(agent1, agent2);
        await dbContext.SaveChangesAsync();

        var portfolio = new PortfolioState(
            Guid.NewGuid(), agent1.Id, 10000m,
            Array.Empty<PositionSnapshot>(), DateTimeOffset.UtcNow, 10000m);
        var decision = new AgentDecision(agent1.Id, DateTimeOffset.UtcNow, []);
        var result = new AgentRunResult(agent1.Id, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, portfolio, decision);

        _agentRunnerMock
            .Setup(r => r.RunAgentOnceAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(result);

        var function = new RunAgentsFunction(dbContext, _agentRunnerMock.Object, _loggerMock.Object);
        var timerInfo = CreateTimerInfo();

        // Act
        await function.RunAllAgents(timerInfo, CancellationToken.None);

        // Assert - Should call runner for each active agent
        _agentRunnerMock.Verify(
            r => r.RunAgentOnceAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()),
            Times.Exactly(2));
    }

    [Fact]
    public async Task RunAllAgents_SkipsInactiveAgents()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();

        var activeAgent = new Agent { Id = Guid.NewGuid(), Name = "Active", IsActive = true };
        var inactiveAgent = new Agent { Id = Guid.NewGuid(), Name = "Inactive", IsActive = false };
        dbContext.Agents.AddRange(activeAgent, inactiveAgent);
        await dbContext.SaveChangesAsync();

        var portfolio = new PortfolioState(
            Guid.NewGuid(), activeAgent.Id, 10000m,
            Array.Empty<PositionSnapshot>(), DateTimeOffset.UtcNow, 10000m);
        var decision = new AgentDecision(activeAgent.Id, DateTimeOffset.UtcNow, []);
        var result = new AgentRunResult(activeAgent.Id, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, portfolio, decision);

        _agentRunnerMock
            .Setup(r => r.RunAgentOnceAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(result);

        var function = new RunAgentsFunction(dbContext, _agentRunnerMock.Object, _loggerMock.Object);
        var timerInfo = CreateTimerInfo();

        // Act
        await function.RunAllAgents(timerInfo, CancellationToken.None);

        // Assert - Should only run active agent
        _agentRunnerMock.Verify(
            r => r.RunAgentOnceAsync(activeAgent.Id, It.IsAny<CancellationToken>()),
            Times.Once);
        _agentRunnerMock.Verify(
            r => r.RunAgentOnceAsync(inactiveAgent.Id, It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunAllAgents_WhenOneAgentFails_ContinuesWithOthers()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();

        var agent1 = new Agent { Id = Guid.NewGuid(), Name = "FailingAgent", IsActive = true };
        var agent2 = new Agent { Id = Guid.NewGuid(), Name = "SuccessAgent", IsActive = true };
        dbContext.Agents.AddRange(agent1, agent2);
        await dbContext.SaveChangesAsync();

        var portfolio = new PortfolioState(
            Guid.NewGuid(), agent2.Id, 10000m,
            Array.Empty<PositionSnapshot>(), DateTimeOffset.UtcNow, 10000m);
        var decision = new AgentDecision(agent2.Id, DateTimeOffset.UtcNow, []);
        var result = new AgentRunResult(agent2.Id, DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, portfolio, decision);

        // First agent throws, second succeeds
        _agentRunnerMock
            .Setup(r => r.RunAgentOnceAsync(agent1.Id, It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Agent failed"));

        _agentRunnerMock
            .Setup(r => r.RunAgentOnceAsync(agent2.Id, It.IsAny<CancellationToken>()))
            .ReturnsAsync(result);

        var function = new RunAgentsFunction(dbContext, _agentRunnerMock.Object, _loggerMock.Object);
        var timerInfo = CreateTimerInfo();

        // Act - Should not throw even if one agent fails
        await function.RunAllAgents(timerInfo, CancellationToken.None);

        // Assert - Both agents should be attempted
        _agentRunnerMock.Verify(
            r => r.RunAgentOnceAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()),
            Times.Exactly(2));
    }

    private static TimerInfo CreateTimerInfo()
    {
        return new TimerInfo
        {
            ScheduleStatus = new ScheduleStatus
            {
                Last = DateTime.UtcNow.AddMinutes(-30),
                Next = DateTime.UtcNow.AddMinutes(30),
                LastUpdated = DateTime.UtcNow
            }
        };
    }
}
