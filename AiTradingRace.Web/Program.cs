using System.Security.Claims;
using System.Text;
using System.Threading.RateLimiting;
using AiTradingRace.Application.DependencyInjection;
using AiTradingRace.Infrastructure.DependencyInjection;
using AiTradingRace.Web.Authentication;
using AiTradingRace.Web.Components;
using AiTradingRace.Web.Data;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);

// CORS for React dev server
builder.Services.AddCors(options =>
{
    options.AddPolicy("ReactDevServer", policy =>
    {
        policy.WithOrigins("http://localhost:5173")
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials();
    });
});

// API Controllers
builder.Services.AddControllers();

// Blazor (kept for now, will be removed when React is ready)
builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents();

builder.Services.AddApplicationServices();

// Use Test AI client for E2E testing of risk validation
// Generates aggressive orders that will be adjusted by RiskValidator
builder.Services.AddInfrastructureServicesWithTestAI(builder.Configuration);

builder.Services.AddSingleton<WeatherForecastService>();

// ═══════════════════════════════════════════════════════════════════════════
// AUTHENTICATION CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════
// NOTE: This service validates tokens, not generates them.
// Tokens are issued by an external Identity Provider (IdP).
// For development/testing, set a JWT secret to enable token validation.

// Bind JWT options
builder.Services.Configure<JwtOptions>(
    builder.Configuration.GetSection(JwtOptions.SectionName));

// Configure authentication with multiple schemes
var jwtSection = builder.Configuration.GetSection(JwtOptions.SectionName);
var jwtSecretKey = jwtSection["SecretKey"] ?? "";

// Only configure JWT if secret key is provided (allows running without auth in dev)
if (!string.IsNullOrWhiteSpace(jwtSecretKey) && jwtSecretKey.Length >= 32)
{
    builder.Services.AddAuthentication(options =>
    {
        options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
        options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
    })
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = jwtSection["Issuer"] ?? "ai-trading-race",
            ValidAudience = jwtSection["Audience"] ?? "ai-trading-race-api",
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(jwtSecretKey)),
            ClockSkew = TimeSpan.Zero
        };
    })
    .AddScheme<ApiKeyAuthOptions, ApiKeyAuthHandler>(
        ApiKeyAuthOptions.SchemeName, 
        options => { options.HeaderName = "X-API-Key"; });

    // ═══════════════════════════════════════════════════════════════════════════
    // AUTHORIZATION CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════════════

    builder.Services.AddAuthorization(options =>
    {
        // Role-based policies
        options.AddPolicy("RequireAdmin", policy => 
            policy.RequireRole("Admin"));
        
        options.AddPolicy("RequireOperator", policy => 
            policy.RequireRole("Admin", "Operator"));
        
        options.AddPolicy("RequireUser", policy => 
            policy.RequireRole("Admin", "Operator", "User"));
        
        // Scope-based policies (for API keys)
        options.AddPolicy("ReadAccess", policy => 
            policy.RequireClaim("scope", "read"));
        
        options.AddPolicy("WriteAccess", policy => 
            policy.RequireClaim("scope", "write"));
    });
}
else
{
    // Development mode without authentication - just add empty auth
    builder.Services.AddAuthentication();
    builder.Services.AddAuthorization();
    
    builder.Logging.AddConsole();
    Console.WriteLine("⚠️  WARNING: JWT SecretKey not configured. Authentication is disabled.");
    Console.WriteLine("   Set 'Authentication:Jwt:SecretKey' via user-secrets for local dev.");
}

// ═══════════════════════════════════════════════════════════════════════════
// RATE LIMITING CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    
    // Global rate limit
    options.AddFixedWindowLimiter("fixed", limiter =>
    {
        limiter.PermitLimit = 100;
        limiter.Window = TimeSpan.FromMinutes(1);
        limiter.QueueProcessingOrder = QueueProcessingOrder.OldestFirst;
        limiter.QueueLimit = 10;
    });
    
    // Strict limit for auth endpoints (prevent brute force)
    options.AddFixedWindowLimiter("auth", limiter =>
    {
        limiter.PermitLimit = 10;
        limiter.Window = TimeSpan.FromMinutes(1);
        limiter.QueueLimit = 0;
    });
    
    // Per-user rate limiting
    options.AddPolicy("per-user", context =>
    {
        var userId = context.User?.FindFirst(ClaimTypes.NameIdentifier)?.Value ?? "anonymous";
        return RateLimitPartition.GetFixedWindowLimiter(userId, _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 200,
            Window = TimeSpan.FromMinutes(1)
        });
    });
});

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
    app.UseHsts();
    app.UseHttpsRedirection();
}

app.UseStaticFiles();

// Enable CORS
app.UseCors("ReactDevServer");

// Rate limiting (must be before auth to protect auth endpoints)
app.UseRateLimiter();

// Authentication & Authorization
app.UseAuthentication();
app.UseAuthorization();

app.UseAntiforgery();

// API endpoints
app.MapControllers();

// Blazor (kept for now)
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
