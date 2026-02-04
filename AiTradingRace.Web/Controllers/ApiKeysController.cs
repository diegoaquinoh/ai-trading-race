using System.ComponentModel.DataAnnotations;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// API key management endpoints. Admin-only access.
/// </summary>
[ApiController]
[Route("api/[controller]")]
[Authorize(Policy = "RequireAdmin")]
public class ApiKeysController : ControllerBase
{
    private readonly TradingDbContext _context;
    private readonly ILogger<ApiKeysController> _logger;

    public ApiKeysController(
        TradingDbContext context,
        ILogger<ApiKeysController> logger)
    {
        _context = context;
        _logger = logger;
    }

    /// <summary>
    /// List all API keys (key values are masked).
    /// </summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<ApiKeyResponse>>> GetAllKeys()
    {
        var keys = await _context.ApiKeys
            .Include(k => k.User)
            .OrderByDescending(k => k.CreatedAt)
            .Select(k => new ApiKeyResponse
            {
                Id = k.Id,
                Name = k.Name,
                KeyPrefix = k.KeyPrefix,
                Scopes = k.Scopes,
                IsActive = k.IsActive,
                CreatedAt = k.CreatedAt,
                ExpiresAt = k.ExpiresAt,
                LastUsedAt = k.LastUsedAt,
                CreatedByEmail = k.User != null ? k.User.Email : null
            })
            .ToListAsync();

        return Ok(keys);
    }

    /// <summary>
    /// Get a specific API key by ID.
    /// </summary>
    [HttpGet("{id:guid}")]
    public async Task<ActionResult<ApiKeyResponse>> GetKey(Guid id)
    {
        var key = await _context.ApiKeys
            .Include(k => k.User)
            .FirstOrDefaultAsync(k => k.Id == id);

        if (key == null)
        {
            return NotFound(new { message = "API key not found." });
        }

        return Ok(new ApiKeyResponse
        {
            Id = key.Id,
            Name = key.Name,
            KeyPrefix = key.KeyPrefix,
            Scopes = key.Scopes,
            IsActive = key.IsActive,
            CreatedAt = key.CreatedAt,
            ExpiresAt = key.ExpiresAt,
            LastUsedAt = key.LastUsedAt,
            CreatedByEmail = key.User?.Email
        });
    }

    /// <summary>
    /// Create a new API key. Returns the key value ONLY ONCE.
    /// </summary>
    [HttpPost]
    public async Task<ActionResult<CreateApiKeyResponse>> CreateKey([FromBody] CreateApiKeyRequest request)
    {
        var userIdClaim = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        if (!Guid.TryParse(userIdClaim, out var userId))
        {
            return Unauthorized(new { message = "Invalid user context." });
        }

        // Generate a secure random key
        var keyBytes = new byte[32];
        using (var rng = RandomNumberGenerator.Create())
        {
            rng.GetBytes(keyBytes);
        }
        var rawKey = Convert.ToBase64String(keyBytes)
            .Replace("+", "-")
            .Replace("/", "_")
            .TrimEnd('=');

        // Prefix for identification (first 8 chars shown)
        var keyPrefix = rawKey[..8];

        // Hash the key for storage using SHA256 (fast lookup, key is already random)
        var keyHash = ComputeSha256Hash(rawKey);

        var apiKey = new ApiKey
        {
            Id = Guid.NewGuid(),
            Name = request.Name.Trim(),
            KeyHash = keyHash,
            KeyPrefix = keyPrefix,
            Scopes = request.Scopes ?? "read",
            IsActive = true,
            CreatedAt = DateTimeOffset.UtcNow,
            ExpiresAt = request.ExpiresInDays.HasValue
                ? DateTimeOffset.UtcNow.AddDays(request.ExpiresInDays.Value)
                : null,
            UserId = userId
        };

        _context.ApiKeys.Add(apiKey);
        await _context.SaveChangesAsync();

        _logger.LogInformation(
            "API key created: {KeyId} ({KeyName}) by user {UserId}",
            apiKey.Id, apiKey.Name, userId);

        // Return the raw key ONLY ONCE - it cannot be retrieved later
        return Ok(new CreateApiKeyResponse
        {
            Id = apiKey.Id,
            Name = apiKey.Name,
            KeyPrefix = apiKey.KeyPrefix,
            Key = rawKey, // Only returned at creation time
            Scopes = apiKey.Scopes,
            ExpiresAt = apiKey.ExpiresAt,
            Message = "Store this key securely. It will not be shown again."
        });
    }

    /// <summary>
    /// Update an API key (name, scopes, active status).
    /// </summary>
    [HttpPatch("{id:guid}")]
    public async Task<ActionResult<ApiKeyResponse>> UpdateKey(Guid id, [FromBody] UpdateApiKeyRequest request)
    {
        var key = await _context.ApiKeys.FindAsync(id);
        if (key == null)
        {
            return NotFound(new { message = "API key not found." });
        }

        if (!string.IsNullOrWhiteSpace(request.Name))
        {
            key.Name = request.Name.Trim();
        }

        if (!string.IsNullOrWhiteSpace(request.Scopes))
        {
            key.Scopes = request.Scopes;
        }

        if (request.IsActive.HasValue)
        {
            key.IsActive = request.IsActive.Value;
        }

        await _context.SaveChangesAsync();

        _logger.LogInformation("API key updated: {KeyId}", id);

        return Ok(new ApiKeyResponse
        {
            Id = key.Id,
            Name = key.Name,
            KeyPrefix = key.KeyPrefix,
            Scopes = key.Scopes,
            IsActive = key.IsActive,
            CreatedAt = key.CreatedAt,
            ExpiresAt = key.ExpiresAt,
            LastUsedAt = key.LastUsedAt
        });
    }

    /// <summary>
    /// Revoke (soft delete) an API key.
    /// </summary>
    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> RevokeKey(Guid id)
    {
        var key = await _context.ApiKeys.FindAsync(id);
        if (key == null)
        {
            return NotFound(new { message = "API key not found." });
        }

        // Soft delete - mark as inactive
        key.IsActive = false;
        await _context.SaveChangesAsync();

        _logger.LogInformation("API key revoked: {KeyId}", id);

        return Ok(new { message = "API key revoked successfully." });
    }

    /// <summary>
    /// Permanently delete an API key.
    /// </summary>
    [HttpDelete("{id:guid}/permanent")]
    public async Task<IActionResult> DeleteKey(Guid id)
    {
        var key = await _context.ApiKeys.FindAsync(id);
        if (key == null)
        {
            return NotFound(new { message = "API key not found." });
        }

        _context.ApiKeys.Remove(key);
        await _context.SaveChangesAsync();

        _logger.LogInformation("API key permanently deleted: {KeyId}", id);

        return Ok(new { message = "API key permanently deleted." });
    }

    /// <summary>
    /// Compute SHA256 hash of a string (for API key storage).
    /// </summary>
    private static string ComputeSha256Hash(string input)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Request/Response DTOs
// ═══════════════════════════════════════════════════════════════════════════

public class CreateApiKeyRequest
{
    [Required]
    [StringLength(100, MinimumLength = 1)]
    public required string Name { get; set; }

    /// <summary>
    /// Comma-separated scopes: read, write, admin
    /// </summary>
    [StringLength(200)]
    public string? Scopes { get; set; }

    /// <summary>
    /// Number of days until expiration. Null = never expires.
    /// </summary>
    [Range(1, 365)]
    public int? ExpiresInDays { get; set; }
}

public class UpdateApiKeyRequest
{
    [StringLength(100)]
    public string? Name { get; set; }

    [StringLength(200)]
    public string? Scopes { get; set; }

    public bool? IsActive { get; set; }
}

public class ApiKeyResponse
{
    public Guid Id { get; set; }
    public required string Name { get; set; }
    public required string KeyPrefix { get; set; }
    public required string Scopes { get; set; }
    public bool IsActive { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset? ExpiresAt { get; set; }
    public DateTimeOffset? LastUsedAt { get; set; }
    public string? CreatedByEmail { get; set; }
}

public class CreateApiKeyResponse
{
    public Guid Id { get; set; }
    public required string Name { get; set; }
    public required string KeyPrefix { get; set; }
    public required string Key { get; set; } // Only shown at creation
    public required string Scopes { get; set; }
    public DateTimeOffset? ExpiresAt { get; set; }
    public required string Message { get; set; }
}
