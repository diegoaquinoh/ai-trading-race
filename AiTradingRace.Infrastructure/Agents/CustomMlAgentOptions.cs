namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Configuration options for the Custom ML Agent service.
/// </summary>
public class CustomMlAgentOptions
{
    /// <summary>
    /// Configuration section name in appsettings.json.
    /// </summary>
    public const string SectionName = "CustomMlAgent";

    /// <summary>
    /// Base URL of the Python FastAPI service.
    /// </summary>
    public string BaseUrl { get; set; } = "http://localhost:8000";

    /// <summary>
    /// Request timeout in seconds.
    /// </summary>
    public int TimeoutSeconds { get; set; } = 30;

    /// <summary>
    /// Number of retry attempts on transient failures.
    /// </summary>
    public int MaxRetries { get; set; } = 2;

    /// <summary>
    /// API key for service-to-service authentication.
    /// Sent as X-API-Key header.
    /// </summary>
    public string ApiKey { get; set; } = "";
}
