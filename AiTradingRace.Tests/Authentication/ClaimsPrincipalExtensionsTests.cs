using System.Security.Claims;
using AiTradingRace.Web.Controllers;

namespace AiTradingRace.Tests.Authentication;

public class ClaimsPrincipalExtensionsTests
{
    [Fact]
    public void GetUserId_WithNameIdentifierClaim_ReturnsUserId()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString())
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetUserId();

        // Assert
        Assert.Equal(userId, result);
    }

    [Fact]
    public void GetUserId_WithSubClaim_ReturnsUserId()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var claims = new[]
        {
            new Claim("sub", userId.ToString())
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetUserId();

        // Assert
        Assert.Equal(userId, result);
    }

    [Fact]
    public void GetUserId_NoUserIdClaim_ReturnsNull()
    {
        // Arrange
        var claims = new[]
        {
            new Claim(ClaimTypes.Email, "test@example.com")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetUserId();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetRequiredUserId_WithValidUserId_ReturnsUserId()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString())
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetRequiredUserId();

        // Assert
        Assert.Equal(userId, result);
    }

    [Fact]
    public void GetRequiredUserId_NoUserId_ThrowsUnauthorizedAccessException()
    {
        // Arrange
        var claims = new[]
        {
            new Claim(ClaimTypes.Email, "test@example.com")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act & Assert
        Assert.Throws<UnauthorizedAccessException>(() => principal.GetRequiredUserId());
    }

    [Fact]
    public void GetEmail_WithEmailClaim_ReturnsEmail()
    {
        // Arrange
        var email = "test@example.com";
        var claims = new[]
        {
            new Claim(ClaimTypes.Email, email)
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetEmail();

        // Assert
        Assert.Equal(email, result);
    }

    [Fact]
    public void GetEmail_WithLowercaseEmailClaim_ReturnsEmail()
    {
        // Arrange
        var email = "test@example.com";
        var claims = new[]
        {
            new Claim("email", email)
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetEmail();

        // Assert
        Assert.Equal(email, result);
    }

    [Fact]
    public void GetRole_WithRoleClaim_ReturnsRole()
    {
        // Arrange
        var role = "Admin";
        var claims = new[]
        {
            new Claim(ClaimTypes.Role, role)
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetRole();

        // Assert
        Assert.Equal(role, result);
    }

    [Fact]
    public void GetScopes_WithMultipleScopeClaims_ReturnsAllScopes()
    {
        // Arrange
        var claims = new[]
        {
            new Claim("scope", "read"),
            new Claim("scope", "write"),
            new Claim("scp", "admin")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetScopes().ToList();

        // Assert
        Assert.Equal(3, result.Count);
        Assert.Contains("read", result);
        Assert.Contains("write", result);
        Assert.Contains("admin", result);
    }

    [Fact]
    public void GetScopes_WithSpaceSeparatedScopes_SplitsCorrectly()
    {
        // Arrange
        var claims = new[]
        {
            new Claim("scope", "read write admin")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetScopes().ToList();

        // Assert
        Assert.Equal(3, result.Count);
        Assert.Contains("read", result);
        Assert.Contains("write", result);
        Assert.Contains("admin", result);
    }

    [Fact]
    public void HasScope_WithMatchingScope_ReturnsTrue()
    {
        // Arrange
        var claims = new[]
        {
            new Claim("scope", "read"),
            new Claim("scope", "write")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.HasScope("read");

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void HasScope_WithoutMatchingScope_ReturnsFalse()
    {
        // Arrange
        var claims = new[]
        {
            new Claim("scope", "read"),
            new Claim("scope", "write")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.HasScope("admin");

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void HasScope_CaseInsensitive_ReturnsTrue()
    {
        // Arrange
        var claims = new[]
        {
            new Claim("scope", "Read")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.HasScope("read");

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void GetTenantId_WithTenantIdClaim_ReturnsTenantId()
    {
        // Arrange
        var tenantId = "tenant-123";
        var claims = new[]
        {
            new Claim("tenant_id", tenantId)
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.GetTenantId();

        // Assert
        Assert.Equal(tenantId, result);
    }

    [Fact]
    public void ExtractIdentity_WithAllClaims_ReturnsCompleteIdentity()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var email = "test@example.com";
        var displayName = "Test User";
        var role = "Admin";
        var tenantId = "tenant-123";
        
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString()),
            new Claim(ClaimTypes.Email, email),
            new Claim(ClaimTypes.Name, displayName),
            new Claim(ClaimTypes.Role, role),
            new Claim("scope", "read write"),
            new Claim("tenant_id", tenantId)
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.ExtractIdentity();

        // Assert
        Assert.Equal(userId, result.UserId);
        Assert.Equal(email, result.Email);
        Assert.Equal(displayName, result.DisplayName);
        Assert.Equal(role, result.Role);
        Assert.Contains("read", result.Scopes);
        Assert.Contains("write", result.Scopes);
        Assert.Equal(tenantId, result.TenantId);
        Assert.True(result.IsAuthenticated);
    }

    [Fact]
    public void ExtractIdentity_WithMultipleRoles_ReturnsAllRoles()
    {
        // Arrange
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, Guid.NewGuid().ToString()),
            new Claim(ClaimTypes.Role, "Admin"),
            new Claim(ClaimTypes.Role, "Operator")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.ExtractIdentity();

        // Assert
        Assert.Equal(2, result.Roles.Length);
        Assert.Contains("Admin", result.Roles);
        Assert.Contains("Operator", result.Roles);
    }

    [Fact]
    public void ExtractIdentity_NotAuthenticated_ReturnsFalse()
    {
        // Arrange
        var claims = new[]
        {
            new Claim(ClaimTypes.Email, "test@example.com")
        };
        var identity = new ClaimsIdentity(claims); // No authenticationType
        var principal = new ClaimsPrincipal(identity);

        // Act
        var result = principal.ExtractIdentity();

        // Assert
        Assert.False(result.IsAuthenticated);
    }
}
