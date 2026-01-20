namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Configuration options for Llama API integration via Groq, Together.ai, or compatible providers.
/// Uses OpenAI-compatible API format for easy integration.
/// </summary>
public sealed class LlamaOptions
{
    public const string SectionName = "Llama";

    /// <summary>
    /// The Llama API provider (Groq, TogetherAI, Replicate, HuggingFace).
    /// </summary>
    public string Provider { get; set; } = "Groq";

    /// <summary>
    /// Base URL for the API endpoint.
    /// Groq: https://api.groq.com/openai/v1
    /// Together.ai: https://api.together.xyz/v1
    /// </summary>
    public string BaseUrl { get; set; } = "https://api.groq.com/openai/v1";

    /// <summary>
    /// API key for authentication.
    /// </summary>
    public string ApiKey { get; set; } = string.Empty;

    /// <summary>
    /// Model name to use.
    /// Groq: llama-3.3-70b-versatile, llama-3.1-8b-instant
    /// Together.ai: meta-llama/Llama-3.1-70B-Instruct-Turbo
    /// </summary>
    public string Model { get; set; } = "llama-3.3-70b-versatile";

    /// <summary>
    /// Temperature for response generation (0.0 = deterministic, 1.0 = creative).
    /// Lower values recommended for trading decisions.
    /// </summary>
    public float Temperature { get; set; } = 0.3f;

    /// <summary>
    /// Maximum tokens in the response.
    /// </summary>
    public int MaxTokens { get; set; } = 500;

    /// <summary>
    /// Timeout in seconds for API calls.
    /// </summary>
    public int TimeoutSeconds { get; set; } = 60;

    /// <summary>
    /// Maximum number of retry attempts for transient failures.
    /// </summary>
    public int MaxRetries { get; set; } = 3;

    /// <summary>
    /// Minimum interval between requests in milliseconds (for rate limiting).
    /// Groq free tier: 60 requests/minute = 1000ms minimum.
    /// </summary>
    public int MinRequestIntervalMs { get; set; } = 1000;
}
