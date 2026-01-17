namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Configuration options for Azure OpenAI integration.
/// </summary>
public sealed class AzureOpenAiOptions
{
    public const string SectionName = "AzureOpenAI";

    /// <summary>
    /// Azure OpenAI endpoint URL (e.g., https://your-resource.openai.azure.com/).
    /// </summary>
    public string Endpoint { get; set; } = string.Empty;

    /// <summary>
    /// API key for Azure OpenAI authentication.
    /// </summary>
    public string ApiKey { get; set; } = string.Empty;

    /// <summary>
    /// Deployment name of the model (e.g., gpt-4o, gpt-35-turbo).
    /// </summary>
    public string DeploymentName { get; set; } = "gpt-4o";

    /// <summary>
    /// Temperature for response generation (0.0 = deterministic, 1.0 = creative).
    /// </summary>
    public float Temperature { get; set; } = 0.7f;

    /// <summary>
    /// Maximum tokens in the response.
    /// </summary>
    public int MaxTokens { get; set; } = 500;

    /// <summary>
    /// Timeout in seconds for API calls.
    /// </summary>
    public int TimeoutSeconds { get; set; } = 30;
}
