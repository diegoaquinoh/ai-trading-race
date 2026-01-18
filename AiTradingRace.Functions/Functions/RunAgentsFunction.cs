using AiTradingRace.Application.Agents;
using AiTradingRace.Infrastructure.Database;
using Microsoft.Azure.Functions.Worker;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

/// <summary>
/// Timer-triggered function to execute all active trading agents.
/// </summary>
public sealed class RunAgentsFunction
{
    private readonly TradingDbContext _dbContext;
    private readonly IAgentRunner _agentRunner;
    private readonly ILogger<RunAgentsFunction> _logger;

    public RunAgentsFunction(
        TradingDbContext dbContext,
        IAgentRunner agentRunner,
        ILogger<RunAgentsFunction> logger)
    {
        _dbContext = dbContext;
        _agentRunner = agentRunner;
        _logger = logger;
    }

    /// <summary>
    /// Run all active agents every 30 minutes.
    /// CRON: 0 */30 * * * * (at minute 0 and 30 of every hour)
    /// </summary>
    [Function(nameof(RunAllAgents))]
    public async Task RunAllAgents(
        [TimerTrigger("0 */30 * * * *")] TimerInfo timer,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Agent execution cycle started at {Time}. Next run at {NextRun}",
            DateTime.UtcNow,
            timer.ScheduleStatus?.Next);

        var activeAgents = await _dbContext.Agents
            .Where(a => a.IsActive)
            .Select(a => new { a.Id, a.Name })
            .ToListAsync(cancellationToken);

        _logger.LogInformation("Found {Count} active agents to run", activeAgents.Count);

        var successCount = 0;
        var failureCount = 0;

        foreach (var agent in activeAgents)
        {
            try
            {
                _logger.LogInformation(
                    "Running agent {AgentName} ({AgentId})",
                    agent.Name, agent.Id);

                var result = await _agentRunner.RunAgentOnceAsync(agent.Id, cancellationToken);

                successCount++;
                _logger.LogInformation(
                    "Agent {AgentName} completed. Executed {OrderCount} orders. Equity: {Equity:C}",
                    agent.Name,
                    result.Decision.Orders.Count,
                    result.Portfolio.TotalValue);
            }
            catch (Exception ex)
            {
                failureCount++;
                _logger.LogError(ex, "Agent {AgentName} ({AgentId}) failed", agent.Name, agent.Id);
                // Continue with next agent, don't fail entire batch
            }
        }

        _logger.LogInformation(
            "Agent execution cycle completed. Success: {Success}, Failures: {Failures}",
            successCount, failureCount);
    }
}

