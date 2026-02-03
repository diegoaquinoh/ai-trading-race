using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Web.Authentication;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;

namespace AiTradingRace.Tests.Authentication;

public class ApiKeyAuthHandlerTests : IDisposable
{
    private readonly TradingDbContext _dbContext;
    private readonly Mock<IOptionsMonitor<ApiKeyAuthOptions>> _optionsMock;
    private readonly Mock<ILoggerFactory> _loggerFactoryMock;
    private readonly Mock<UrlEncoder> _encoderMock;
    private readonly ApiKeyAuthHandler _handler;
    private readonly DefaultHttpContext _httpContext;

    public ApiKeyAuthHandlerTests()
    {
        // Setup in-memory database
        var options = new DbContextOptionsBuilder<TradingDbContext>()
            .UseInMemoryDatabase(databaseName: $"TestDb_{Guid.NewGuid()}")
            .Options;
        _dbContext = new TradingDbContext(options);

        // Setup mocks
        _optionsMock = new Mock<IOptionsMonitor<ApiKeyAuthOptions>>();
        _optionsMock.Setup(o => o.Get(It.IsAny<string>()))
            .Returns(new ApiKeyAuthOptions { HeaderName = "X-API-Key" });

        _loggerFactoryMock = new Mock<ILoggerFactory>();
        _loggerFactoryMock.Setup(f => f.CreateLogger(It.IsAny<string>()))
            .Returns(Mock.Of<ILogger>());

        _encoderMock = new Mock<UrlEncoder>();

        // Setup HTTP context
        _httpContext = new DefaultHttpContext();

        // Create handler
        _handler = new ApiKeyAuthHandler(
            _optionsMock.Object,
            _loggerFactoryMock.Object,
            _encoderMock.Object,
            _dbContext);

        // Initialize handler with scheme
        var scheme = new AuthenticationScheme(
            ApiKeyAuthOptions.SchemeName,
            ApiKeyAuthOptions.SchemeName,
            typeof(ApiKeyAuthHandler));

        _handler.InitializeAsync(scheme, _httpContext).Wait();
    }

    [Fact]
    public async Task HandleAuthenticateAsync_NoApiKeyHeader_ReturnsNoResult()
    {
        // Arrange - no X-API-Key header

        // Act
        var result = await _handler.AuthenticateAsync();

        // Assert
        Assert.False(result.Succeeded);
        Assert.True(result.None);
    }

    [Fact]
    public async Task HandleAuthenticateAsync_EmptyApiKey_ReturnsFail()
    {
        // Arrange
        _httpContext.Request.Headers["X-API-Key"] = "";

        // Act
        var result = await _handler.AuthenticateAsync();

        // Assert
        Assert.False(result.Succeeded);
        Assert.NotNull(result.Failure);
        Assert.Contains("empty", result.Failure.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task HandleAuthenticateAsync_ValidApiKey_ReturnsSuccess()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var user = new User
        {
            Id = userId,
            Email = "test@example.com",
            Name = "Test User",
            Role = UserRole.Operator
        };

        var rawKey = GenerateRandomKey();
        var apiKey = new ApiKey
        {
            Id = Guid.NewGuid(),
            KeyHash = ComputeSha256Hash(rawKey),
            KeyPrefix = rawKey[..8],
            Name = "Test Key",
            UserId = userId,
            User = user,
            Scopes = "read,write",
            IsActive = true,
            CreatedAt = DateTimeOffset.UtcNow
        };

        _dbContext.Users.Add(user);
        _dbContext.ApiKeys.Add(apiKey);
        await _dbContext.SaveChangesAsync();

        _httpContext.Request.Headers["X-API-Key"] = rawKey;

        // Act
        var result = await _handler.AuthenticateAsync();

        // Assert
        Assert.True(result.Succeeded);
        Assert.NotNull(result.Ticket);
        Assert.NotNull(result.Principal);
        Assert.Equal(userId.ToString(), result.Principal.FindFirst(ClaimTypes.NameIdentifier)?.Value);
        Assert.Equal("Operator", result.Principal.FindFirst(ClaimTypes.Role)?.Value);
        
        var scopeClaims = result.Principal.FindAll("scope").Select(c => c.Value).ToList();
        Assert.Contains("read", scopeClaims);
        Assert.Contains("write", scopeClaims);
    }

    [Fact]
    public async Task HandleAuthenticateAsync_InvalidApiKey_ReturnsFail()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var user = new User
        {
            Id = userId,
            Email = "test@example.com",
            Name = "Test User",
            Role = UserRole.User
        };

        var rawKey = GenerateRandomKey();
        var apiKey = new ApiKey
        {
            Id = Guid.NewGuid(),
            KeyHash = ComputeSha256Hash(rawKey),
            KeyPrefix = rawKey[..8],
            Name = "Test Key",
            UserId = userId,
            User = user,
            Scopes = "read",
            IsActive = true,
            CreatedAt = DateTimeOffset.UtcNow
        };

        _dbContext.Users.Add(user);
        _dbContext.ApiKeys.Add(apiKey);
        await _dbContext.SaveChangesAsync();

        // Use wrong key
        _httpContext.Request.Headers["X-API-Key"] = GenerateRandomKey();

        // Act
        var result = await _handler.AuthenticateAsync();

        // Assert
        Assert.False(result.Succeeded);
        Assert.NotNull(result.Failure);
    }

    [Fact]
    public async Task HandleAuthenticateAsync_ExpiredApiKey_ReturnsFail()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var user = new User
        {
            Id = userId,
            Email = "test@example.com",
            Name = "Test User",
            Role = UserRole.User
        };

        var rawKey = GenerateRandomKey();
        var apiKey = new ApiKey
        {
            Id = Guid.NewGuid(),
            KeyHash = ComputeSha256Hash(rawKey),
            KeyPrefix = rawKey[..8],
            Name = "Test Key",
            UserId = userId,
            User = user,
            Scopes = "read",
            IsActive = true,
            ExpiresAt = DateTimeOffset.UtcNow.AddDays(-1), // Expired yesterday
            CreatedAt = DateTimeOffset.UtcNow.AddDays(-10)
        };

        _dbContext.Users.Add(user);
        _dbContext.ApiKeys.Add(apiKey);
        await _dbContext.SaveChangesAsync();

        _httpContext.Request.Headers["X-API-Key"] = rawKey;

        // Act
        var result = await _handler.AuthenticateAsync();

        // Assert
        Assert.False(result.Succeeded);
        Assert.NotNull(result.Failure);
    }

    [Fact]
    public async Task HandleAuthenticateAsync_InactiveApiKey_ReturnsFail()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var user = new User
        {
            Id = userId,
            Email = "test@example.com",
            Name = "Test User",
            Role = UserRole.User
        };

        var rawKey = GenerateRandomKey();
        var apiKey = new ApiKey
        {
            Id = Guid.NewGuid(),
            KeyHash = ComputeSha256Hash(rawKey),
            KeyPrefix = rawKey[..8],
            Name = "Test Key",
            UserId = userId,
            User = user,
            Scopes = "read",
            IsActive = false, // Inactive
            CreatedAt = DateTimeOffset.UtcNow
        };

        _dbContext.Users.Add(user);
        _dbContext.ApiKeys.Add(apiKey);
        await _dbContext.SaveChangesAsync();

        _httpContext.Request.Headers["X-API-Key"] = rawKey;

        // Act
        var result = await _handler.AuthenticateAsync();

        // Assert
        Assert.False(result.Succeeded);
        Assert.NotNull(result.Failure);
    }

    [Fact]
    public async Task HandleAuthenticateAsync_ValidKey_UpdatesLastUsedAt()
    {
        // Arrange
        var userId = Guid.NewGuid();
        var user = new User
        {
            Id = userId,
            Email = "test@example.com",
            Name = "Test User",
            Role = UserRole.Admin
        };

        var rawKey = GenerateRandomKey();
        var apiKey = new ApiKey
        {
            Id = Guid.NewGuid(),
            KeyHash = ComputeSha256Hash(rawKey),
            KeyPrefix = rawKey[..8],
            Name = "Test Key",
            UserId = userId,
            User = user,
            Scopes = "admin",
            IsActive = true,
            CreatedAt = DateTimeOffset.UtcNow,
            LastUsedAt = null
        };

        _dbContext.Users.Add(user);
        _dbContext.ApiKeys.Add(apiKey);
        await _dbContext.SaveChangesAsync();

        _httpContext.Request.Headers["X-API-Key"] = rawKey;

        // Act
        var result = await _handler.AuthenticateAsync();

        // Assert
        Assert.True(result.Succeeded);
        
        var updatedKey = await _dbContext.ApiKeys.FindAsync(apiKey.Id);
        Assert.NotNull(updatedKey);
        Assert.NotNull(updatedKey.LastUsedAt);
        Assert.True((DateTimeOffset.UtcNow - updatedKey.LastUsedAt.Value).TotalSeconds < 5);
    }

    [Fact]
    public void ComputeSha256Hash_SameInput_ProducesSameHash()
    {
        // Arrange
        var input = "test-api-key-12345";

        // Act
        var hash1 = ComputeSha256Hash(input);
        var hash2 = ComputeSha256Hash(input);

        // Assert
        Assert.Equal(hash1, hash2);
    }

    [Fact]
    public void ComputeSha256Hash_DifferentInput_ProducesDifferentHash()
    {
        // Arrange
        var input1 = "test-api-key-12345";
        var input2 = "test-api-key-67890";

        // Act
        var hash1 = ComputeSha256Hash(input1);
        var hash2 = ComputeSha256Hash(input2);

        // Assert
        Assert.NotEqual(hash1, hash2);
    }

    private static string GenerateRandomKey()
    {
        var keyBytes = new byte[32];
        using var rng = RandomNumberGenerator.Create();
        rng.GetBytes(keyBytes);
        return Convert.ToBase64String(keyBytes)
            .Replace("+", "-")
            .Replace("/", "_")
            .TrimEnd('=');
    }

    private static string ComputeSha256Hash(string input)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }

    public void Dispose()
    {
        _dbContext?.Dispose();
        GC.SuppressFinalize(this);
    }
}
