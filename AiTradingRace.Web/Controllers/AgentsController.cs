using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Equity;
using AiTradingRace.Infrastructure.Database;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Controller for managing agents and leaderboard.
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class AgentsController : ControllerBase
{
    private readonly TradingDbContext _dbContext;
    private readonly IEquityService _equityService;
    private readonly IAgentRunner _agentRunner;
    private readonly ILogger<AgentsController> _logger;

    public AgentsController(
        TradingDbContext dbContext,
        IEquityService equityService,
        IAgentRunner agentRunner,
        ILogger<AgentsController> logger)
    {
        _dbContext = dbContext;
        _equityService = equityService;
        _agentRunner = agentRunner;
        _logger = logger;
    }

    /// <summary>
    /// Get all agents with their current portfolio value (leaderboard).
    /// </summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>List of agents ordered by total portfolio value (descending).</returns>
    [HttpGet]
    [ProducesResponseType(typeof(IEnumerable<AgentSummaryDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IEnumerable<AgentSummaryDto>>> GetAgents(CancellationToken ct)
    {
        var agents = await _dbContext.Agents
            .AsNoTracking()
            .ToListAsync(ct);

        var summaries = new List<AgentSummaryDto>();
        foreach (var agent in agents)
        {
            var latestSnapshot = await _equityService.GetLatestSnapshotAsync(agent.Id, ct);
            summaries.Add(new AgentSummaryDto(
                agent.Id,
                agent.Name,
                agent.Strategy,
                agent.IsActive,
                latestSnapshot?.TotalValue ?? 100_000m,  // Default starting value
                latestSnapshot?.PercentChange ?? 0m,
                latestSnapshot?.CapturedAt ?? agent.CreatedAt));
        }

        return Ok(summaries.OrderByDescending(a => a.TotalValue));
    }

    /// <summary>
    /// Get details for a specific agent.
    /// </summary>
    /// <param name="id">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Agent details with latest snapshot and performance metrics.</returns>
    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(AgentDetailDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<AgentDetailDto>> GetAgent(Guid id, CancellationToken ct)
    {
        var agent = await _dbContext.Agents
            .AsNoTracking()
            .FirstOrDefaultAsync(a => a.Id == id, ct);

        if (agent == null)
        {
            return NotFound(new { message = $"Agent {id} not found" });
        }

        var latestSnapshot = await _equityService.GetLatestSnapshotAsync(id, ct);
        var performance = await _equityService.CalculatePerformanceAsync(id, ct);

        return Ok(new AgentDetailDto(
            agent.Id,
            agent.Name,
            agent.Strategy,
            agent.IsActive,
            agent.CreatedAt,
            latestSnapshot,
            performance));
    }

    /// <summary>
    /// Execute a single trading cycle for an agent.
    /// Builds context, generates AI decision, validates against risk constraints, and executes trades.
    /// </summary>
    /// <param name="id">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The result of the agent run including portfolio state and executed orders.</returns>
    [HttpPost("{id:guid}/run")]
    [ProducesResponseType(typeof(AgentRunResultDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<AgentRunResultDto>> RunAgent(Guid id, CancellationToken ct)
    {
        _logger.LogInformation("Manual run triggered for agent {AgentId}", id);

        var agent = await _dbContext.Agents
            .AsNoTracking()
            .FirstOrDefaultAsync(a => a.Id == id, ct);

        if (agent == null)
        {
            return NotFound(new { message = $"Agent {id} not found" });
        }

        if (!agent.IsActive)
        {
            return BadRequest(new { message = $"Agent {id} is not active" });
        }

        try
        {
            var result = await _agentRunner.RunAgentOnceAsync(id, ct);

            _logger.LogInformation("Agent {AgentId} run completed. Portfolio value: ${TotalValue:F2}",
                id, result.Portfolio.TotalValue);

            return Ok(new AgentRunResultDto(
                result.AgentId,
                result.StartedAt,
                result.CompletedAt,
                (result.CompletedAt - result.StartedAt).TotalSeconds,
                result.Portfolio.TotalValue,
                result.Portfolio.Cash,
                result.Decision.Orders.Count,
                result.Decision.Orders.Select(o => new OrderDto(o.AssetSymbol, o.Side.ToString(), o.Quantity)).ToList()));
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "Agent {AgentId} run failed", id);
            return BadRequest(new { message = ex.Message });
        }
    }
}

/// <summary>
/// Summary DTO for agent list/leaderboard.
/// </summary>
public record AgentSummaryDto(
    Guid Id,
    string Name,
    string Strategy,
    bool IsActive,
    decimal TotalValue,
    decimal? PercentChange,
    DateTimeOffset LastUpdated);

/// <summary>
/// Detailed DTO for single agent view.
/// </summary>
public record AgentDetailDto(
    Guid Id,
    string Name,
    string Strategy,
    bool IsActive,
    DateTimeOffset CreatedAt,
    EquitySnapshotDto? LatestSnapshot,
    PerformanceMetrics? Performance);

/// <summary>
/// Result DTO for agent run endpoint.
/// </summary>
public record AgentRunResultDto(
    Guid AgentId,
    DateTimeOffset StartedAt,
    DateTimeOffset CompletedAt,
    double DurationSeconds,
    decimal TotalValue,
    decimal Cash,
    int OrderCount,
    IReadOnlyList<OrderDto> ExecutedOrders);

/// <summary>
/// Order DTO for displaying executed orders.
/// </summary>
public record OrderDto(
    string Asset,
    string Side,
    decimal Quantity);
