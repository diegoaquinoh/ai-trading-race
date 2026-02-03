using System.Net;
using AiTradingRace.Application.Agents;
using AiTradingRace.Infrastructure.Database;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
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

    // NOTE: The timer-triggered agent execution has been removed.
    // Agent decisions are now handled by the MarketCycleOrchestrator (Durable Functions)
    // which runs every 15 minutes as part of the synchronized market cycle.

    /// <summary>
    /// HTTP endpoint to manually trigger agent execution.
    /// POST /api/agents/run
    /// </summary>
    [Function("RunAgentsManual")]
    public async Task<HttpResponseData> RunAgentsManual(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "agents/run")] HttpRequestData req,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation("Manual agent execution triggered via HTTP");

        var activeAgents = await _dbContext.Agents
            .Where(a => a.IsActive)
            .Select(a => new { a.Id, a.Name })
            .ToListAsync(cancellationToken);

        _logger.LogInformation("Found {Count} active agents to run", activeAgents.Count);

        var results = new List<object>();
        var successCount = 0;
        var failureCount = 0;

        foreach (var agent in activeAgents)
        {
            try
            {
                _logger.LogInformation("Running agent {AgentName} ({AgentId})", agent.Name, agent.Id);

                var result = await _agentRunner.RunAgentOnceAsync(agent.Id, cancellationToken);

                successCount++;
                results.Add(new
                {
                    agentId = agent.Id,
                    agentName = agent.Name,
                    status = "success",
                    ordersExecuted = result.Decision.Orders.Count,
                    equity = result.Portfolio.TotalValue
                });

                _logger.LogInformation(
                    "Agent {AgentName} completed. Executed {OrderCount} orders. Equity: {Equity:C}",
                    agent.Name, result.Decision.Orders.Count, result.Portfolio.TotalValue);
            }
            catch (Exception ex)
            {
                failureCount++;
                results.Add(new
                {
                    agentId = agent.Id,
                    agentName = agent.Name,
                    status = "failed",
                    error = ex.Message
                });

                _logger.LogError(ex, "Agent {AgentName} ({AgentId}) failed", agent.Name, agent.Id);
            }
        }

        var response = req.CreateResponse(HttpStatusCode.OK);
        await response.WriteAsJsonAsync(new
        {
            message = "Agent execution completed",
            successCount,
            failureCount,
            results
        }, cancellationToken);

        return response;
    }
}

