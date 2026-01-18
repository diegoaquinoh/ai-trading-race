using AiTradingRace.Infrastructure.Database;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using System.Net;
using System.Text.Json;

namespace AiTradingRace.Functions.Functions;

/// <summary>
/// HTTP-triggered function for health check and service monitoring.
/// </summary>
public sealed class HealthCheckFunction
{
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<HealthCheckFunction> _logger;

    public HealthCheckFunction(
        TradingDbContext dbContext,
        ILogger<HealthCheckFunction> logger)
    {
        _dbContext = dbContext;
        _logger = logger;
    }

    /// <summary>
    /// Health check endpoint for monitoring and readiness probes.
    /// </summary>
    [Function(nameof(HealthCheck))]
    public async Task<HttpResponseData> HealthCheck(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", Route = "health")]
        HttpRequestData req,
        CancellationToken cancellationToken)
    {
        var healthStatus = new HealthStatus
        {
            Status = "Healthy",
            Timestamp = DateTime.UtcNow,
            Database = await CheckDatabaseAsync(cancellationToken),
            ActiveAgentCount = await GetActiveAgentCountAsync(cancellationToken),
            LatestCandleTime = await GetLatestCandleTimeAsync(cancellationToken)
        };

        var isHealthy = healthStatus.Database == "Connected";
        healthStatus.Status = isHealthy ? "Healthy" : "Unhealthy";

        var response = req.CreateResponse(
            isHealthy ? HttpStatusCode.OK : HttpStatusCode.ServiceUnavailable);

        response.Headers.Add("Content-Type", "application/json");
        await response.WriteStringAsync(
            JsonSerializer.Serialize(healthStatus, JsonOptions),
            cancellationToken);

        return response;
    }

    private async Task<string> CheckDatabaseAsync(CancellationToken ct)
    {
        try
        {
            var canConnect = await _dbContext.Database.CanConnectAsync(ct);
            return canConnect ? "Connected" : "Disconnected";
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Database health check failed");
            return $"Error: {ex.Message}";
        }
    }

    private async Task<int> GetActiveAgentCountAsync(CancellationToken ct)
    {
        try
        {
            return await _dbContext.Agents.CountAsync(a => a.IsActive, ct);
        }
        catch
        {
            return -1;
        }
    }

    private async Task<DateTimeOffset?> GetLatestCandleTimeAsync(CancellationToken ct)
    {
        try
        {
            return await _dbContext.MarketCandles
                .MaxAsync(c => (DateTimeOffset?)c.TimestampUtc, ct);
        }
        catch
        {
            return null;
        }
    }

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private sealed class HealthStatus
    {
        public string Status { get; set; } = string.Empty;
        public DateTime Timestamp { get; set; }
        public string Database { get; set; } = string.Empty;
        public int ActiveAgentCount { get; set; }
        public DateTimeOffset? LatestCandleTime { get; set; }
    }
}
