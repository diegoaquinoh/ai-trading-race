using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using AiTradingRace.Infrastructure.Database;
using Microsoft.AspNetCore.Authentication;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Web.Authentication;

/// <summary>
/// Authentication handler for API key-based authentication.
/// Looks for X-API-Key header and validates against stored keys.
/// </summary>
public class ApiKeyAuthHandler : AuthenticationHandler<ApiKeyAuthOptions>
{
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<ApiKeyAuthHandler> _logger;

    public ApiKeyAuthHandler(
        IOptionsMonitor<ApiKeyAuthOptions> options,
        ILoggerFactory loggerFactory,
        UrlEncoder encoder,
        TradingDbContext dbContext)
        : base(options, loggerFactory, encoder)
    {
        _dbContext = dbContext;
        _logger = loggerFactory.CreateLogger<ApiKeyAuthHandler>();
    }

    protected override async Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        // Check if API key header is present
        if (!Request.Headers.TryGetValue(Options.HeaderName, out var apiKeyHeader))
        {
            return AuthenticateResult.NoResult();
        }

        var providedKey = apiKeyHeader.ToString();
        if (string.IsNullOrWhiteSpace(providedKey))
        {
            return AuthenticateResult.Fail("API key is empty");
        }

        // Find API key by prefix (first 8 characters for efficient lookup)
        var keyPrefix = providedKey.Length >= 8 ? providedKey[..8] : providedKey;
        
        var apiKey = await _dbContext.ApiKeys
            .Include(k => k.User)
            .FirstOrDefaultAsync(k => 
                k.KeyPrefix == keyPrefix && 
                k.IsActive &&
                (k.ExpiresAt == null || k.ExpiresAt > DateTimeOffset.UtcNow));

        if (apiKey == null)
        {
            _logger.LogWarning("API key not found or inactive: {KeyPrefix}...", keyPrefix);
            return AuthenticateResult.Fail("Invalid API key");
        }

        // Verify full key with SHA256 hash comparison
        var providedHash = ComputeSha256Hash(providedKey);
        if (!string.Equals(providedHash, apiKey.KeyHash, StringComparison.OrdinalIgnoreCase))
        {
            _logger.LogWarning("API key verification failed for key ID: {KeyId}", apiKey.Id);
            return AuthenticateResult.Fail("Invalid API key");
        }

        // Update last used timestamp (fire and forget to not slow down request)
        apiKey.LastUsedAt = DateTimeOffset.UtcNow;
        _ = _dbContext.SaveChangesAsync();

        // Build claims from API key
        var claims = new List<Claim>
        {
            new(ClaimTypes.NameIdentifier, apiKey.UserId.ToString()),
            new(ClaimTypes.Name, apiKey.Name),
            new("api_key_id", apiKey.Id.ToString()),
            new(ClaimTypes.Role, apiKey.User.Role.ToString()),
            new(ClaimTypes.AuthenticationMethod, "ApiKey"),
        };

        // Add scopes as claims
        foreach (var scope in apiKey.Scopes.Split(',', StringSplitOptions.RemoveEmptyEntries))
        {
            claims.Add(new Claim("scope", scope.Trim()));
        }

        var identity = new ClaimsIdentity(claims, Scheme.Name);
        var principal = new ClaimsPrincipal(identity);
        var ticket = new AuthenticationTicket(principal, Scheme.Name);

        _logger.LogDebug("API key authenticated: {KeyName} for user {UserId}", 
            apiKey.Name, apiKey.UserId);

        return AuthenticateResult.Success(ticket);
    }

    private static string ComputeSha256Hash(string input)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
