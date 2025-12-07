using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.Agents;

public interface IAgentRunner
{
    Task<AgentRunResult> RunAgentOnceAsync(
        Guid agentId,
        CancellationToken cancellationToken = default);
}

