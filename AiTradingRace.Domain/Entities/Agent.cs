namespace AiTradingRace.Domain.Entities;

public class Agent
{
    public Guid Id { get; init; }

    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Description of the agent's trading strategy (for display/reference).
    /// </summary>
    public string Strategy { get; set; } = string.Empty;

    /// <summary>
    /// System prompt / instructions for the AI model.
    /// Contains trading rules, risk preferences, and behavioral guidelines.
    /// </summary>
    public string Instructions { get; set; } = string.Empty;

    /// <summary>
    /// The AI model provider to use for this agent.
    /// </summary>
    public ModelProvider ModelProvider { get; set; } = ModelProvider.AzureOpenAI;

    /// <summary>
    /// Key that maps to a deployment name in configuration (e.g., "GPT4oMini", "GPT41Nano").
    /// Only used for providers that support multiple deployments (AzureOpenAI).
    /// </summary>
    public string? DeploymentKey { get; set; }

    public bool IsActive { get; set; } = true;

    public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;

    // Navigation property
    public Portfolio? Portfolio { get; set; }
}
