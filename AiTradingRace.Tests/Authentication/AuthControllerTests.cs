using System.Security.Claims;
using AiTradingRace.Web.Controllers;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Authentication;

public class AuthControllerTests
{
    private readonly Mock<ILogger<AuthController>> _loggerMock;
    private readonly AuthController _controller;

    public AuthControllerTests()
    {
        _loggerMock = new Mock<ILogger<AuthController>>();
        _controller = new AuthController(_loggerMock.Object);
    }

    [Fact]
    public void GetCurrentIdentity_WithAuthenticatedUser_ReturnsIdentity()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var email = "test@example.com";
        var role = "User";
        
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString()),
            new Claim(ClaimTypes.Email, email),
            new Claim(ClaimTypes.Name, "Test User"),
            new Claim(ClaimTypes.Role, role),
            new Claim("scope", "read write")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);
        
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext { User = principal }
        };

        // Act
        var result = _controller.GetCurrentIdentity();

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var identityResponse = Assert.IsType<IdentityResponse>(okResult.Value);
        
        Assert.Equal(userId, identityResponse.UserId);
        Assert.Equal(email, identityResponse.Email);
        Assert.Equal(role, identityResponse.Role);
        Assert.True(identityResponse.IsAuthenticated);
        Assert.Contains("read", identityResponse.Scopes);
        Assert.Contains("write", identityResponse.Scopes);
    }

    [Fact]
    public void GetCurrentIdentity_WithUnauthenticatedUser_ReturnsIdentityNotAuthenticated()
    {
        // Arrange
        var claims = Array.Empty<Claim>();
        var identity = new ClaimsIdentity(claims); // No authentication type
        var principal = new ClaimsPrincipal(identity);
        
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext { User = principal }
        };

        // Act
        var result = _controller.GetCurrentIdentity();

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var identityResponse = Assert.IsType<IdentityResponse>(okResult.Value);
        
        Assert.False(identityResponse.IsAuthenticated);
        Assert.Null(identityResponse.UserId);
    }

    [Fact]
    public void ValidateAdmin_WithAdminRole_ReturnsIdentity()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString()),
            new Claim(ClaimTypes.Email, "admin@example.com"),
            new Claim(ClaimTypes.Role, "Admin")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);
        
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext { User = principal }
        };

        // Act
        var result = _controller.ValidateAdmin();

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var identityResponse = Assert.IsType<IdentityResponse>(okResult.Value);
        
        Assert.Equal(userId, identityResponse.UserId);
        Assert.Equal("Admin", identityResponse.Role);
        Assert.True(identityResponse.IsAuthenticated);
    }

    [Fact]
    public void ValidateOperator_WithOperatorRole_ReturnsIdentity()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString()),
            new Claim(ClaimTypes.Email, "operator@example.com"),
            new Claim(ClaimTypes.Role, "Operator")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);
        
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext { User = principal }
        };

        // Act
        var result = _controller.ValidateOperator();

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var identityResponse = Assert.IsType<IdentityResponse>(okResult.Value);
        
        Assert.Equal(userId, identityResponse.UserId);
        Assert.Equal("Operator", identityResponse.Role);
        Assert.True(identityResponse.IsAuthenticated);
    }

    [Fact]
    public void ValidateOperator_WithAdminRole_ReturnsIdentity()
    {
        // Arrange - Admin should also pass Operator validation
        var userId = Guid.NewGuid();
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString()),
            new Claim(ClaimTypes.Email, "admin@example.com"),
            new Claim(ClaimTypes.Role, "Admin")
        };
        var identity = new ClaimsIdentity(claims, "TestAuth");
        var principal = new ClaimsPrincipal(identity);
        
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext { User = principal }
        };

        // Act
        var result = _controller.ValidateOperator();

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var identityResponse = Assert.IsType<IdentityResponse>(okResult.Value);
        
        Assert.Equal(userId, identityResponse.UserId);
        Assert.Equal("Admin", identityResponse.Role);
    }

    [Fact]
    public void Health_Always_ReturnsOk()
    {
        // Act
        var result = _controller.Health();

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result);
        Assert.NotNull(okResult.Value);
        
        // Check that response has status and timestamp
        var response = okResult.Value;
        var statusProperty = response.GetType().GetProperty("status");
        var timestampProperty = response.GetType().GetProperty("timestamp");
        
        Assert.NotNull(statusProperty);
        Assert.NotNull(timestampProperty);
        Assert.Equal("healthy", statusProperty.GetValue(response));
    }

    [Fact]
    public void GetCurrentIdentity_WithApiKeyClaims_ReturnsIdentityWithScopes()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var apiKeyId = Guid.NewGuid();
        
        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, userId.ToString()),
            new Claim(ClaimTypes.Name, "Test API Key"),
            new Claim("api_key_id", apiKeyId.ToString()),
            new Claim(ClaimTypes.Role, "Operator"),
            new Claim("scope", "read"),
            new Claim("scope", "write"),
            new Claim("scope", "admin")
        };
        var identity = new ClaimsIdentity(claims, "ApiKey");
        var principal = new ClaimsPrincipal(identity);
        
        _controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext { User = principal }
        };

        // Act
        var result = _controller.GetCurrentIdentity();

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var identityResponse = Assert.IsType<IdentityResponse>(okResult.Value);
        
        Assert.Equal(userId, identityResponse.UserId);
        Assert.Equal("Operator", identityResponse.Role);
        Assert.True(identityResponse.IsAuthenticated);
        Assert.Equal(3, identityResponse.Scopes.Length);
        Assert.Contains("read", identityResponse.Scopes);
        Assert.Contains("write", identityResponse.Scopes);
        Assert.Contains("admin", identityResponse.Scopes);
    }
}
