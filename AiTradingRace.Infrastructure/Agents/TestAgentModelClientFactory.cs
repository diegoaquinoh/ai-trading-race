using AiTradingRace.Application.Agents;
using AiTradingRace.Domain.Entities;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Factory that always returns TestAgentModelClient regardless of the agent's model provider.
/// Use this for development/testing when no AI API keys are configured.
/// </summary>
public sealed class TestAgentModelClientFactory : IAgentModelClientFactory
{
    private readonly TestAgentModelClient _testClient;
    private readonly ILogger<TestAgentModelClientFactory> _logger;

    public TestAgentModelClientFactory(
        TestAgentModelClient testClient,
        ILogger<TestAgentModelClientFactory> logger)
    {
        _testClient = testClient;
        _logger = logger;
    }

    public IAgentModelClient GetClient(ModelProvider provider)
    {
        _logger.LogDebug(
            "TestAgentModelClientFactory: Ignoring provider {Provider}, returning TestAgentModelClient",
            provider);

        return _testClient;
    }
}
