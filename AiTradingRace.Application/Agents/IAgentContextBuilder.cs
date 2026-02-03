using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.Agents;

/// <summary>
/// Builds the context needed for an AI agent to make trading decisions.
/// Gathers portfolio state, recent market data, and agent instructions.
/// </summary>
public interface IAgentContextBuilder
{
    /// <summary>
    /// Builds a complete context for the specified agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="candleCount">Number of recent candles to include per asset.</param>
    /// <param name="includeKnowledgeGraph">Whether to include knowledge graph and regime detection (Phase 10).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The agent context with portfolio, market data, instructions, and optionally knowledge graph.</returns>
    /// <exception cref="InvalidOperationException">Thrown if agent not found or inactive.</exception>
    Task<AgentContext> BuildContextAsync(
        Guid agentId,
        int candleCount = 24,
        bool includeKnowledgeGraph = false,
        CancellationToken cancellationToken = default);
}
