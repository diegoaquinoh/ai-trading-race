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
        if (!HashesEqual(providedHash, apiKey.KeyHash))
        {
            _logger.LogWarning("API key verification failed for key ID: {KeyId}", apiKey.Id);
            return AuthenticateResult.Fail("Invalid API key");
        }

        // Update last used timestamp. Awaited: the scoped DbContext must not be used concurrently.
        apiKey.LastUsedAt = DateTimeOffset.UtcNow;
        await _dbContext.SaveChangesAsync();

        // Build claims from API key
        var claims = new List<Claim>
        {
            new(ClaimTypes.NameIdentifier, apiKey.UserId.ToString()),
            new(ClaimTypes.Name, apiKey.Name),
            new("api_key_id", apiKey.Id.ToString()),
            new(ClaimTypes.AuthenticationMethod, "ApiKey"),
        };

        // The key acts with the role its scopes grant, never above its owner's role.
        var role = ApiKeyScopes.EffectiveRole(apiKey.User.Role, apiKey.Scopes);
        if (role is not null)
        {
            claims.Add(new Claim(ClaimTypes.Role, role.Value.ToString()));
        }

        // Add scopes as claims
        foreach (var scope in ApiKeyScopes.Parse(apiKey.Scopes))
        {
            claims.Add(new Claim("scope", scope));
        }

        var identity = new ClaimsIdentity(claims, Scheme.Name);
        var principal = new ClaimsPrincipal(identity);
        var ticket = new AuthenticationTicket(principal, Scheme.Name);

        _logger.LogDebug("API key authenticated: {KeyName} for user {UserId}", 
            apiKey.Name, apiKey.UserId);

        return AuthenticateResult.Success(ticket);
    }

    private static bool HashesEqual(string providedHash, string storedHash) =>
        CryptographicOperations.FixedTimeEquals(
            Encoding.ASCII.GetBytes(providedHash),
            Encoding.ASCII.GetBytes(storedHash.ToLowerInvariant()));

    private static string ComputeSha256Hash(string input)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
