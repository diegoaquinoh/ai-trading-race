namespace AiTradingRace.Application.FixedIncome.Options;

/// <summary>Configuration of the Python research-engine internal API (section "ResearchEngine").</summary>
public sealed class ResearchEngineOptions
{
    public const string SectionName = "ResearchEngine";

    /// <summary>Default engine allowlist used when none is configured.</summary>
    public static readonly IReadOnlyList<string> DefaultAllowedEngineVersions = new[] { "research-engine/0.1.*" };

    public string BaseUrl { get; set; } = "http://localhost:8000";

    /// <summary>Sent as X-API-Key on every internal call.</summary>
    public string ApiKey { get; set; } = string.Empty;

    /// <summary>Shared HMAC-SHA256 key used to verify proposal/result signatures (UTF-8 bytes).</summary>
    public string SigningKey { get; set; } = string.Empty;

    /// <summary>
    /// HTTP timeout. Must exceed the 90 second decision deadline plus transport
    /// margin (spec 14.3); values below <see cref="MinimumTimeoutSeconds"/> are raised.
    /// </summary>
    public int TimeoutSeconds { get; set; } = 120;

    public const int MinimumTimeoutSeconds = 100;

    /// <summary>
    /// Accepted engine versions. Exact strings or a trailing "*" prefix wildcard
    /// (e.g. "research-engine/0.1.*"). Empty means <see cref="DefaultAllowedEngineVersions"/>.
    /// </summary>
    public List<string> AllowedEngineVersions { get; set; } = new();

    public IReadOnlyList<string> EffectiveAllowedEngineVersions =>
        AllowedEngineVersions.Count == 0 ? DefaultAllowedEngineVersions : AllowedEngineVersions;

    public TimeSpan EffectiveTimeout =>
        TimeSpan.FromSeconds(Math.Max(TimeoutSeconds, MinimumTimeoutSeconds));

    public bool IsEngineVersionAllowed(string? engineVersion)
    {
        if (string.IsNullOrWhiteSpace(engineVersion))
        {
            return false;
        }

        foreach (var allowed in EffectiveAllowedEngineVersions)
        {
            if (string.IsNullOrWhiteSpace(allowed))
            {
                continue;
            }

            if (allowed.EndsWith('*'))
            {
                if (engineVersion.StartsWith(allowed[..^1], StringComparison.Ordinal))
                {
                    return true;
                }
            }
            else if (string.Equals(allowed, engineVersion, StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }
}
