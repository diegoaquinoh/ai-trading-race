using AiTradingRace.Functions.Models;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Activities;

/// <summary>
/// Reporting-only activity for the legacy crypto market cycle. It counts the orders
/// that <c>AgentRunner.RunAgentOnceAsync</c> already executed inside
/// <see cref="RunAgentDecisionActivity"/>; it performs no execution itself, so exactly
/// one component (AgentRunner) executes trades (spec section 4).
/// Formerly named ExecuteTradesActivity.
/// </summary>
public sealed class ReportExecutedTradesActivity
{
    private readonly ILogger<ReportExecutedTradesActivity> _logger;

    public ReportExecutedTradesActivity(ILogger<ReportExecutedTradesActivity> logger)
    {
        _logger = logger;
    }

    [Function(nameof(ReportExecutedTradesActivity))]
    public Task<int> Run(
        [ActivityTrigger] ReportExecutedTradesRequest request,
        CancellationToken ct)
    {
        var successfulDecisions = request.Decisions
            .Where(d => d.Success)
            .ToList();

        var reportedOrders = successfulDecisions
            .Sum(d => d.Decision.Orders.Count);

        _logger.LogInformation(
            "Reported {OrderCount} orders already executed by AgentRunner for {AgentCount} agents at {Timestamp}",
            reportedOrders, successfulDecisions.Count, request.Timestamp);

        return Task.FromResult(reportedOrders);
    }
}
