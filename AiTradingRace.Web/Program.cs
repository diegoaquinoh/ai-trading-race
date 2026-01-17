using AiTradingRace.Application.DependencyInjection;
using AiTradingRace.Infrastructure.DependencyInjection;
using AiTradingRace.Web.Components;
using AiTradingRace.Web.Data;

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

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
    app.UseHsts();
}

app.UseHttpsRedirection();
app.UseStaticFiles();

// Enable CORS
app.UseCors("ReactDevServer");

app.UseAntiforgery();

// API endpoints
app.MapControllers();

// Blazor (kept for now)
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode();

app.Run();
