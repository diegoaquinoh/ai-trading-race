using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Equity;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Controller for the leaderboard endpoint, providing ranked agent performance data.
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class LeaderboardController : ControllerBase
{
    private readonly TradingDbContext _dbContext;
    private readonly IEquityService _equityService;
    private readonly ILogger<LeaderboardController> _logger;

    public LeaderboardController(
        TradingDbContext dbContext,
        IEquityService equityService,
        ILogger<LeaderboardController> logger)
    {
        _dbContext = dbContext;
        _equityService = equityService;
        _logger = logger;
    }

    /// <summary>
    /// Get the leaderboard with all agents ranked by performance.
    /// </summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>List of agents ranked by total portfolio value with performance metrics.</returns>
    [HttpGet]
    [ProducesResponseType(typeof(IEnumerable<LeaderboardEntryDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IEnumerable<LeaderboardEntryDto>>> GetLeaderboard(CancellationToken ct)
    {
        _logger.LogDebug("Fetching leaderboard data");

        var agents = await _dbContext.Agents
            .AsNoTracking()
            .ToListAsync(ct);

        var entries = new List<LeaderboardEntryDto>();

        foreach (var agent in agents)
        {
            var performance = await _equityService.CalculatePerformanceAsync(agent.Id, ct);
            var latestSnapshot = await _equityService.GetLatestSnapshotAsync(agent.Id, ct);

            entries.Add(new LeaderboardEntryDto(
                new AgentDto(
                    agent.Id,
                    agent.Name,
                    agent.ModelProvider.ToString(),
                    agent.Strategy,
                    agent.IsActive,
                    agent.CreatedAt),
                CurrentValue: latestSnapshot?.TotalValue ?? 100_000m,
                PerformancePercent: performance.PercentReturn,
                Drawdown: performance.MaxDrawdown));
        }

        // Sort by current value descending (highest first)
        var ranked = entries
            .OrderByDescending(e => e.CurrentValue)
            .ToList();

        _logger.LogDebug("Returning leaderboard with {Count} agents", ranked.Count);

        return Ok(ranked);
    }
}

/// <summary>
/// DTO for a leaderboard entry matching frontend LeaderboardEntry type.
/// </summary>
public record LeaderboardEntryDto(
    AgentDto Agent,
    decimal CurrentValue,
    decimal PerformancePercent,
    decimal Drawdown);

/// <summary>
/// DTO for agent data matching frontend Agent type.
/// </summary>
public record AgentDto(
    Guid Id,
    string Name,
    string ModelType,
    string Provider,
    bool IsActive,
    DateTimeOffset CreatedAt);
