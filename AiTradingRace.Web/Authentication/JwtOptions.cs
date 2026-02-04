namespace AiTradingRace.Web.Authentication;

/// <summary>
/// Configuration options for JWT authentication.
/// </summary>
public class JwtOptions
{
    /// <summary>Configuration section name.</summary>
    public const string SectionName = "Authentication:Jwt";
    
    /// <summary>Token issuer (who created the token).</summary>
    public string Issuer { get; set; } = "ai-trading-race";
    
    /// <summary>Token audience (who the token is intended for).</summary>
    public string Audience { get; set; } = "ai-trading-race-api";
    
    /// <summary>
    /// Secret key for signing tokens (minimum 32 characters).
    /// Set via user-secrets or environment variable.
    /// </summary>
    public string SecretKey { get; set; } = string.Empty;
    
    /// <summary>Access token expiration in minutes.</summary>
    public int AccessTokenExpirationMinutes { get; set; } = 60;
    
    /// <summary>Refresh token expiration in days.</summary>
    public int RefreshTokenExpirationDays { get; set; } = 7;
}
