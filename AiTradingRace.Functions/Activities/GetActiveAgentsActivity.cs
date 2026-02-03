using AiTradingRace.Infrastructure.Database;
using Microsoft.Azure.Functions.Worker;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Activities;

/// <summary>
/// Activity function to get all active agent IDs.
/// </summary>
public sealed class GetActiveAgentsActivity
{
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<GetActiveAgentsActivity> _logger;

    public GetActiveAgentsActivity(
        TradingDbContext dbContext,
        ILogger<GetActiveAgentsActivity> logger)
    {
        _dbContext = dbContext;
        _logger = logger;
    }

    [Function(nameof(GetActiveAgentsActivity))]
    public async Task<List<Guid>> Run(
        [ActivityTrigger] object? input,
        CancellationToken ct)
    {
        var agentIds = await _dbContext.Agents
            .AsNoTracking()
            .Where(a => a.IsActive)
            .Select(a => a.Id)
            .ToListAsync(ct);

        _logger.LogInformation("Found {Count} active agents", agentIds.Count);

        return agentIds;
    }
}
