using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Authentication endpoints for token validation and identity inspection.
/// 
/// ARCHITECTURE NOTES:
/// ═══════════════════════════════════════════════════════════════════════════
/// This service does NOT implement:
/// - User registration (create account, email verification)
/// - Password hashing or password reset flows
/// - Identity provider functionality
/// 
/// Tokens are issued by an external Identity Provider (IdP) or gateway.
/// This controller validates tokens and extracts claims for authorization.
/// 
/// INTERNAL MICROSERVICES AUTHENTICATION:
/// ═══════════════════════════════════════════════════════════════════════════
/// For service-to-service communication, consider:
/// 
/// 1. mTLS (Mutual TLS):
///    - Both client and server present X.509 certificates
///    - Identity is established by certificate validation
///    - Common in Kubernetes service mesh (Istio, Linkerd)
///    - No tokens needed - identity in certificate CN/SAN
/// 
/// 2. Service Tokens / API Keys:
///    - Pre-shared secrets for internal services
///    - Validated via X-API-Key header (see ApiKeyAuthHandler)
///    - Simpler but requires secure key distribution
/// 
/// 3. Machine-to-Machine OAuth:
///    - Services obtain tokens via client_credentials grant
///    - Same JWT validation as user tokens
///    - Scopes define service permissions
/// </summary>
[ApiController]
[Route("api/[controller]")]
[EnableRateLimiting("auth")]
public class AuthController : ControllerBase
{
    private readonly ILogger<AuthController> _logger;

    public AuthController(ILogger<AuthController> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Validate token and return current identity.
    /// 
    /// Requires: Authorization: Bearer {token} header
    /// Returns: 401 Unauthorized if no/invalid token
    /// Returns: 200 OK with identity claims if valid
    /// </summary>
    [HttpGet("me")]
    [Authorize]
    [ProducesResponseType(typeof(IdentityResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public ActionResult<IdentityResponse> GetCurrentIdentity()
    {
        var identity = User.ExtractIdentity();
        
        _logger.LogDebug(
            "Identity validated: UserId={UserId}, Role={Role}", 
            identity.UserId, identity.Role);

        return Ok(identity);
    }

    /// <summary>
    /// Validate token with Admin role requirement.
    /// 
    /// Returns: 401 Unauthorized if no/invalid token
    /// Returns: 403 Forbidden if valid token but not Admin role
    /// Returns: 200 OK if valid Admin token
    /// </summary>
    [HttpGet("validate/admin")]
    [Authorize(Policy = "RequireAdmin")]
    [ProducesResponseType(typeof(IdentityResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    public ActionResult<IdentityResponse> ValidateAdmin()
    {
        return Ok(User.ExtractIdentity());
    }

    /// <summary>
    /// Validate token with Operator role requirement.
    /// 
    /// Returns: 401 Unauthorized if no/invalid token
    /// Returns: 403 Forbidden if valid token but not Operator/Admin role
    /// Returns: 200 OK if valid Operator or Admin token
    /// </summary>
    [HttpGet("validate/operator")]
    [Authorize(Policy = "RequireOperator")]
    [ProducesResponseType(typeof(IdentityResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    public ActionResult<IdentityResponse> ValidateOperator()
    {
        return Ok(User.ExtractIdentity());
    }

    /// <summary>
    /// Health check endpoint - no authentication required.
    /// Useful for load balancers and monitoring.
    /// </summary>
    [HttpGet("health")]
    [AllowAnonymous]
    public IActionResult Health()
    {
        return Ok(new { status = "healthy", timestamp = DateTimeOffset.UtcNow });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// CLAIMS EXTRACTION EXTENSIONS
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Extension methods for extracting identity information from ClaimsPrincipal.
/// Use these throughout the application to get user context from validated tokens.
/// 
/// Example usage in a controller:
/// <code>
/// [Authorize]
/// public async Task<IActionResult> GetMyData()
/// {
///     var userId = User.GetRequiredUserId();
///     var data = await _service.GetDataForUser(userId);
///     return Ok(data);
/// }
/// </code>
/// </summary>
public static class ClaimsPrincipalExtensions
{
    /// <summary>
    /// Extract the user/service ID from the token.
    /// Returns null if not authenticated or claim missing.
    /// </summary>
    public static Guid? GetUserId(this ClaimsPrincipal principal)
    {
        var claim = principal.FindFirst(ClaimTypes.NameIdentifier) 
                    ?? principal.FindFirst("sub");
        
        return Guid.TryParse(claim?.Value, out var id) ? id : null;
    }

    /// <summary>
    /// Extract the user/service ID from the token.
    /// Throws UnauthorizedAccessException if not authenticated or claim missing.
    /// </summary>
    public static Guid GetRequiredUserId(this ClaimsPrincipal principal)
    {
        return principal.GetUserId() 
               ?? throw new UnauthorizedAccessException("User ID claim not found in token.");
    }

    /// <summary>
    /// Extract email from the token.
    /// Supports both standard ClaimTypes.Email and "email" claim.
    /// </summary>
    public static string? GetEmail(this ClaimsPrincipal principal)
    {
        return principal.FindFirst(ClaimTypes.Email)?.Value 
               ?? principal.FindFirst("email")?.Value;
    }

    /// <summary>
    /// Extract display name from the token.
    /// </summary>
    public static string? GetDisplayName(this ClaimsPrincipal principal)
    {
        return principal.FindFirst(ClaimTypes.Name)?.Value 
               ?? principal.FindFirst("name")?.Value;
    }

    /// <summary>
    /// Extract primary role from the token.
    /// </summary>
    public static string? GetRole(this ClaimsPrincipal principal)
    {
        return principal.FindFirst(ClaimTypes.Role)?.Value 
               ?? principal.FindFirst("role")?.Value;
    }

    /// <summary>
    /// Extract all roles from the token (supports multiple role claims).
    /// Some IdPs emit multiple "role" claims for users with multiple roles.
    /// </summary>
    public static IEnumerable<string> GetRoles(this ClaimsPrincipal principal)
    {
        return principal.FindAll(ClaimTypes.Role)
            .Concat(principal.FindAll("role"))
            .Select(c => c.Value)
            .Distinct();
    }

    /// <summary>
    /// Extract scopes from the token (for API authorization).
    /// Handles both space-separated format (OAuth2 standard) and multiple claims.
    /// 
    /// Examples:
    /// - Single claim: scope="read write admin" -> ["read", "write", "admin"]
    /// - Multiple claims: scp="read", scp="write" -> ["read", "write"]
    /// </summary>
    public static IEnumerable<string> GetScopes(this ClaimsPrincipal principal)
    {
        var scopeClaims = principal.FindAll("scope")
            .Concat(principal.FindAll("scp"));
        
        return scopeClaims
            .SelectMany(c => c.Value.Split(' ', StringSplitOptions.RemoveEmptyEntries))
            .Distinct();
    }

    /// <summary>
    /// Check if the user has a specific scope.
    /// </summary>
    public static bool HasScope(this ClaimsPrincipal principal, string scope)
    {
        return principal.GetScopes().Contains(scope, StringComparer.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Check if the user has a specific role.
    /// Uses both IsInRole() and manual claim checking.
    /// </summary>
    public static bool HasRole(this ClaimsPrincipal principal, string role)
    {
        return principal.IsInRole(role) || 
               principal.GetRoles().Contains(role, StringComparer.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Extract tenant/workspace ID if present (for multi-tenant systems).
    /// Common claim names: tenant_id, tid (Azure AD), org_id
    /// </summary>
    public static string? GetTenantId(this ClaimsPrincipal principal)
    {
        return principal.FindFirst("tenant_id")?.Value 
               ?? principal.FindFirst("tid")?.Value
               ?? principal.FindFirst("org_id")?.Value;
    }

    /// <summary>
    /// Extract full identity information into a response object.
    /// Useful for debugging and returning identity info to clients.
    /// </summary>
    public static IdentityResponse ExtractIdentity(this ClaimsPrincipal principal)
    {
        return new IdentityResponse
        {
            UserId = principal.GetUserId(),
            Email = principal.GetEmail(),
            DisplayName = principal.GetDisplayName(),
            Role = principal.GetRole(),
            Roles = principal.GetRoles().ToArray(),
            Scopes = principal.GetScopes().ToArray(),
            TenantId = principal.GetTenantId(),
            IsAuthenticated = principal.Identity?.IsAuthenticated ?? false
        };
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// RESPONSE DTOs
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Identity information extracted from a validated token.
/// </summary>
public class IdentityResponse
{
    /// <summary>User or service account ID (from 'sub' or NameIdentifier claim).</summary>
    public Guid? UserId { get; set; }
    
    /// <summary>Email address (if present in token).</summary>
    public string? Email { get; set; }
    
    /// <summary>Display name (if present in token).</summary>
    public string? DisplayName { get; set; }
    
    /// <summary>Primary role.</summary>
    public string? Role { get; set; }
    
    /// <summary>All roles (for systems with multiple role claims).</summary>
    public string[] Roles { get; set; } = [];
    
    /// <summary>Authorized scopes (e.g., "read", "write", "admin").</summary>
    public string[] Scopes { get; set; } = [];
    
    /// <summary>Tenant/workspace ID for multi-tenant systems.</summary>
    public string? TenantId { get; set; }
    
    /// <summary>Whether the token was successfully validated.</summary>
    public bool IsAuthenticated { get; set; }
}
