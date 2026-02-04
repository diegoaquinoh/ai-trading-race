namespace AiTradingRace.Domain.Entities;

/// <summary>
/// Represents a user/service account in the system.
/// 
/// NOTE: This entity stores user metadata synchronized from an external Identity Provider.
/// Password management and authentication are handled by the IdP, not this system.
/// </summary>
public class User
{
    /// <summary>Unique identifier (matches IdP subject/user ID).</summary>
    public Guid Id { get; set; }
    
    /// <summary>Email address (unique, from IdP).</summary>
    public string Email { get; set; } = string.Empty;
    
    /// <summary>Display name.</summary>
    public string Name { get; set; } = string.Empty;
    
    /// <summary>User role for authorization.</summary>
    public UserRole Role { get; set; } = UserRole.User;
    
    /// <summary>Whether the user account is active.</summary>
    public bool IsActive { get; set; } = true;
    
    /// <summary>When the user was first seen/created.</summary>
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    
    /// <summary>When the user last accessed the system.</summary>
    public DateTimeOffset? LastSeenAt { get; set; }
    
    /// <summary>External IdP subject identifier (for linking).</summary>
    public string? ExternalId { get; set; }
    
    /// <summary>API keys owned by this user.</summary>
    public ICollection<ApiKey> ApiKeys { get; set; } = new List<ApiKey>();
}
