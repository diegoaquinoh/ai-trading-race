using AiTradingRace.Domain.Entities;
using AiTradingRace.Functions.Activities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Activities;

public class GetActiveAgentsActivityTests
{
    private readonly Mock<ILogger<GetActiveAgentsActivity>> _loggerMock;

    public GetActiveAgentsActivityTests()
    {
        _loggerMock = new Mock<ILogger<GetActiveAgentsActivity>>();
    }

    private TradingDbContext CreateInMemoryDbContext()
    {
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        return new TradingDbContext(options);
    }

    [Fact]
    public async Task Run_WithNoAgents_ReturnsEmptyList()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();
        var activity = new GetActiveAgentsActivity(dbContext, _loggerMock.Object);

        // Act
        var result = await activity.Run(new object(), CancellationToken.None);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public async Task Run_WithActiveAgents_ReturnsOnlyActiveAgentIds()
    {
        // Arrange
        using var dbContext = CreateInMemoryDbContext();
        var activeAgent1 = new Agent { Id = Guid.NewGuid(), Name = "Active1", IsActive = true };
        var activeAgent2 = new Agent { Id = Guid.NewGuid(), Name = "Active2", IsActive = true };
        var inactiveAgent = new Agent { Id = Guid.NewGuid(), Name = "Inactive", IsActive = false };
        
        dbContext.Agents.AddRange(activeAgent1, activeAgent2, inactiveAgent);
        await dbContext.SaveChangesAsync();

        var activity = new GetActiveAgentsActivity(dbContext, _loggerMock.Object);

        // Act
        var result = await activity.Run(new object(), CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Contains(activeAgent1.Id, result);
        Assert.Contains(activeAgent2.Id, result);
        Assert.DoesNotContain(inactiveAgent.Id, result);
    }
}
