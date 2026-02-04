using AiTradingRace.Application.Decisions;
using AiTradingRace.Domain.Entities;
using Microsoft.AspNetCore.Mvc;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// API endpoints for querying agent decision logs and analytics
/// </summary>
[ApiController]
[Route("api/agents/{agentId}/decisions")]
public class DecisionLogsController : ControllerBase
{
    private const int MaxDateRangeDays = 90;
    private readonly IDecisionLogService _decisionLogService;
    private readonly ILogger<DecisionLogsController> _logger;

    public DecisionLogsController(
        IDecisionLogService decisionLogService,
        ILogger<DecisionLogsController> logger)
    {
        _decisionLogService = decisionLogService;
        _logger = logger;
    }

    /// <summary>
    /// Get decision history for an agent
    /// </summary>
    /// <param name="agentId">Agent GUID</param>
    /// <param name="fromDate">Optional start date filter</param>
    /// <param name="limit">Optional limit on number of results (default: 50)</param>
    [HttpGet]
    [ProducesResponseType(typeof(List<DecisionLog>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<DecisionLog>>> GetDecisions(
        Guid agentId,
        [FromQuery] DateTime? fromDate = null,
        [FromQuery] int? limit = 50)
    {
        _logger.LogInformation(
            "Fetching decision history for agent {AgentId} (fromDate: {FromDate}, limit: {Limit})",
            agentId,
            fromDate,
            limit);

        var decisions = await _decisionLogService.GetDecisionHistoryAsync(
            agentId,
            fromDate,
            limit);

        return Ok(decisions);
    }

    /// <summary>
    /// Get a specific decision by ID
    /// </summary>
    /// <param name="agentId">Agent GUID</param>
    /// <param name="decisionId">Decision ID</param>
    [HttpGet("{decisionId}")]
    [ProducesResponseType(typeof(DecisionLog), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<DecisionLog>> GetDecision(
        Guid agentId,
        int decisionId)
    {
        _logger.LogDebug("Fetching decision {DecisionId} for agent {AgentId}", decisionId, agentId);

        var decision = await _decisionLogService.GetDecisionByIdAsync(decisionId);

        if (decision == null)
        {
            _logger.LogWarning("Decision {DecisionId} not found", decisionId);
            return NotFound(new { message = $"Decision {decisionId} not found" });
        }

        if (decision.AgentId != agentId)
        {
            _logger.LogWarning(
                "Decision {DecisionId} belongs to agent {ActualAgentId}, not {RequestedAgentId}",
                decisionId,
                decision.AgentId,
                agentId);
            return NotFound(new { message = $"Decision {decisionId} not found for agent {agentId}" });
        }

        return Ok(decision);
    }

    /// <summary>
    /// Get decision analytics for an agent over a time period
    /// </summary>
    /// <param name="agentId">Agent GUID</param>
    /// <param name="fromDate">Start date for analytics</param>
    /// <param name="toDate">End date for analytics (optional, defaults to now)</param>
    [HttpGet("analytics")]
    [ProducesResponseType(typeof(DecisionAnalytics), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<DecisionAnalytics>> GetAnalytics(
        Guid agentId,
        [FromQuery] DateTime fromDate,
        [FromQuery] DateTime? toDate = null)
    {
        var endDate = toDate ?? DateTime.UtcNow;

        // Validate date range
        if (fromDate > endDate)
        {
            return BadRequest(new { error = "fromDate cannot be after toDate" });
        }

        if (fromDate > DateTime.UtcNow)
        {
            return BadRequest(new { error = "fromDate cannot be in the future" });
        }

        if ((endDate - fromDate).TotalDays > MaxDateRangeDays)
        {
            return BadRequest(new { error = $"Date range cannot exceed {MaxDateRangeDays} days" });
        }

        _logger.LogInformation(
            "Fetching analytics for agent {AgentId} from {FromDate} to {ToDate}",
            agentId,
            fromDate,
            endDate);

        var analytics = await _decisionLogService.AnalyzeDecisionsAsync(
            agentId,
            fromDate,
            endDate);

        return Ok(analytics);
    }
}
