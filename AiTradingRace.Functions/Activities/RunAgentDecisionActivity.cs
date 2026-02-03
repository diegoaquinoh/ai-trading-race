using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Functions.Models;
using AiTradingRace.Infrastructure.Database;
using Microsoft.Azure.Functions.Worker;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Activities;

/// <summary>
/// Activity function to run a single agent's decision logic.
/// </summary>
public sealed class RunAgentDecisionActivity
{
    private readonly IAgentRunner _agentRunner;
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<RunAgentDecisionActivity> _logger;

    public RunAgentDecisionActivity(
        IAgentRunner agentRunner,
        TradingDbContext dbContext,
        ILogger<RunAgentDecisionActivity> logger)
    {
        _agentRunner = agentRunner;
        _dbContext = dbContext;
        _logger = logger;
    }

    [Function(nameof(RunAgentDecisionActivity))]
    public async Task<AgentDecisionResult> Run(
        [ActivityTrigger] AgentDecisionRequest request,
        CancellationToken ct)
    {
        var agent = await _dbContext.Agents
            .AsNoTracking()
            .Where(a => a.Id == request.AgentId)
            .Select(a => new { a.Id, a.Name })
            .FirstOrDefaultAsync(ct);

        if (agent is null)
        {
            _logger.LogWarning("Agent {AgentId} not found", request.AgentId);
            return new AgentDecisionResult(
                request.AgentId,
                "Unknown",
                CreateEmptyDecision(request.AgentId),
                0m,
                false,
                "Agent not found");
        }

        _logger.LogInformation(
            "Running agent {AgentName} ({AgentId}) for batch {BatchId}",
            agent.Name, agent.Id, request.BatchId);

        try
        {
            var result = await _agentRunner.RunAgentOnceAsync(agent.Id, ct);

            _logger.LogInformation(
                "Agent {AgentName} completed. Orders: {OrderCount}, Equity: {Equity:C}",
                agent.Name, result.Decision.Orders.Count, result.Portfolio.TotalValue);

            return new AgentDecisionResult(
                agent.Id,
                agent.Name,
                result.Decision,
                result.Portfolio.TotalValue,
                true);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Agent {AgentName} ({AgentId}) failed", agent.Name, agent.Id);
            
            return new AgentDecisionResult(
                agent.Id,
                agent.Name,
                CreateEmptyDecision(agent.Id, ex.Message),
                0m,
                false,
                ex.Message);
        }
    }

    private static AgentDecision CreateEmptyDecision(Guid agentId, string? rationale = null)
    {
        return new AgentDecision(
            agentId,
            DateTimeOffset.UtcNow,
            Array.Empty<TradeOrder>(),
            null,
            rationale ?? "No decision made");
    }
}
