using Microsoft.AspNetCore.Authentication;

namespace AiTradingRace.Web.Authentication;

/// <summary>
/// Configuration options for API key authentication.
/// </summary>
public class ApiKeyAuthOptions : AuthenticationSchemeOptions
{
    /// <summary>Authentication scheme name.</summary>
    public const string SchemeName = "ApiKey";
    
    /// <summary>HTTP header name for the API key.</summary>
    public string HeaderName { get; set; } = "X-API-Key";
}
