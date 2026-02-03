using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Equity;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Controller for managing equity snapshots and performance metrics.
/// </summary>
[ApiController]
[Route("api/agents/{agentId:guid}/equity")]
public class EquityController : ControllerBase
{
    private readonly IEquityService _equityService;
    private readonly ILogger<EquityController> _logger;

    public EquityController(IEquityService equityService, ILogger<EquityController> logger)
    {
        _equityService = equityService;
        _logger = logger;
    }

    /// <summary>
    /// Get the equity curve (historical snapshots) for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="from">Optional start date filter.</param>
    /// <param name="to">Optional end date filter.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>List of equity snapshots ordered by date.</returns>
    [HttpGet]
    [ProducesResponseType(typeof(IEnumerable<EquitySnapshotDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IEnumerable<EquitySnapshotDto>>> GetEquityCurve(
        Guid agentId,
        [FromQuery] DateTimeOffset? from,
        [FromQuery] DateTimeOffset? to,
        CancellationToken ct)
    {
        _logger.LogDebug("Getting equity curve for agent {AgentId}", agentId);
        var curve = await _equityService.GetEquityCurveAsync(agentId, from, to, ct);
        return Ok(curve);
    }

    /// <summary>
    /// Get the latest equity snapshot for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The most recent snapshot, or 404 if none exist.</returns>
    [HttpGet("latest")]
    [ProducesResponseType(typeof(EquitySnapshotDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<EquitySnapshotDto>> GetLatestSnapshot(
        Guid agentId,
        CancellationToken ct)
    {
        var snapshot = await _equityService.GetLatestSnapshotAsync(agentId, ct);
        if (snapshot == null)
        {
            return NotFound(new { message = $"No equity snapshots found for agent {agentId}" });
        }

        return Ok(snapshot);
    }

    /// <summary>
    /// Capture a new equity snapshot for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The newly created equity snapshot.</returns>
    [Authorize(Policy = "RequireOperator")]
    [HttpPost("snapshot")]
    [ProducesResponseType(typeof(EquitySnapshotDto), StatusCodes.Status201Created)]
    public async Task<ActionResult<EquitySnapshotDto>> CaptureSnapshot(
        Guid agentId,
        CancellationToken ct)
    {
        _logger.LogInformation("Capturing equity snapshot for agent {AgentId}", agentId);
        var snapshot = await _equityService.CaptureSnapshotAsync(agentId, ct);
        return CreatedAtAction(nameof(GetLatestSnapshot), new { agentId }, snapshot);
    }

    /// <summary>
    /// Get performance metrics for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Performance metrics including returns, drawdown, and trade statistics.</returns>
    [HttpGet("performance")]
    [ProducesResponseType(typeof(PerformanceMetrics), StatusCodes.Status200OK)]
    public async Task<ActionResult<PerformanceMetrics>> GetPerformance(
        Guid agentId,
        CancellationToken ct)
    {
        var metrics = await _equityService.CalculatePerformanceAsync(agentId, ct);
        return Ok(metrics);
    }
}
