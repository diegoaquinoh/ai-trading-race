namespace AiTradingRace.Domain.Entities;

/// <summary>
/// Represents user roles for authorization.
/// </summary>
public enum UserRole
{
    /// <summary>Can view own agents and data.</summary>
    User = 0,
    
    /// <summary>Can run agents and view all data.</summary>
    Operator = 1,
    
    /// <summary>Full administrative access.</summary>
    Admin = 2
}
