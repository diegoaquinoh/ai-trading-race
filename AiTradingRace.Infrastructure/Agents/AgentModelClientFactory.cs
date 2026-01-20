using AiTradingRace.Application.Agents;
using AiTradingRace.Domain.Entities;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Factory that creates the appropriate IAgentModelClient based on the agent's model provider.
/// Uses IServiceProvider to resolve named implementations.
/// </summary>
public sealed class AgentModelClientFactory : IAgentModelClientFactory
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<AgentModelClientFactory> _logger;

    public AgentModelClientFactory(
        IServiceProvider serviceProvider,
        ILogger<AgentModelClientFactory> logger)
    {
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    public IAgentModelClient GetClient(ModelProvider provider)
    {
        _logger.LogDebug("Resolving AI client for provider {Provider}", provider);

        IAgentModelClient client = provider switch
        {
            ModelProvider.Llama => _serviceProvider.GetRequiredService<LlamaAgentModelClient>(),
            ModelProvider.AzureOpenAI => _serviceProvider.GetRequiredService<AzureOpenAiAgentModelClient>(),
            ModelProvider.OpenAI => _serviceProvider.GetRequiredService<AzureOpenAiAgentModelClient>(), // Reuse for now
            ModelProvider.CustomML => _serviceProvider.GetRequiredService<CustomMlAgentModelClient>(),
            ModelProvider.Mock => _serviceProvider.GetRequiredService<TestAgentModelClient>(),
            _ => throw new NotSupportedException($"Model provider {provider} is not supported")
        };

        _logger.LogDebug("Resolved {ClientType} for provider {Provider}", client.GetType().Name, provider);

        return client;
    }
}
