using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.Agents;

public interface IAgentModelClient
{
    Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken cancellationToken = default);
}

