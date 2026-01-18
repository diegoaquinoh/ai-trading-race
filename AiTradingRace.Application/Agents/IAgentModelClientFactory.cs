using AiTradingRace.Domain.Entities;

namespace AiTradingRace.Application.Agents;

/// <summary>
/// Factory for creating the appropriate IAgentModelClient based on the agent's model provider.
/// </summary>
public interface IAgentModelClientFactory
{
    /// <summary>
    /// Gets the appropriate client for the specified model provider.
    /// </summary>
    /// <param name="provider">The model provider (AzureOpenAI, CustomML, Mock, etc.)</param>
    /// <returns>The appropriate IAgentModelClient implementation.</returns>
    IAgentModelClient GetClient(ModelProvider provider);
}
