namespace AiTradingRace.Domain.Entities;

/// <summary>
/// Represents an API key for service-to-service authentication.
/// </summary>
public class ApiKey
{
    /// <summary>Unique identifier.</summary>
    public Guid Id { get; set; }
    
    /// <summary>BCrypt hash of the full API key.</summary>
    public string KeyHash { get; set; } = string.Empty;
    
    /// <summary>First 8 characters of the key for lookup.</summary>
    public string KeyPrefix { get; set; } = string.Empty;
    
    /// <summary>Descriptive name (e.g., "ML Service Key", "CI/CD Key").</summary>
    public string Name { get; set; } = string.Empty;
    
    /// <summary>User who owns this API key.</summary>
    public Guid UserId { get; set; }
    
    /// <summary>Comma-separated list of scopes (e.g., "read,write,admin").</summary>
    public string Scopes { get; set; } = string.Empty;
    
    /// <summary>Whether the API key is active.</summary>
    public bool IsActive { get; set; } = true;
    
    /// <summary>When the API key was created.</summary>
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    
    /// <summary>When the API key expires (null = never).</summary>
    public DateTimeOffset? ExpiresAt { get; set; }
    
    /// <summary>When the API key was last used.</summary>
    public DateTimeOffset? LastUsedAt { get; set; }
    
    /// <summary>Navigation property to the owning user.</summary>
    public User User { get; set; } = null!;
}
