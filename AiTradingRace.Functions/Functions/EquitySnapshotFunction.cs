using AiTradingRace.Application.Equity;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

/// <summary>
/// Timer-triggered function to capture equity snapshots for all active agents.
/// </summary>
public sealed class EquitySnapshotFunction
{
    private readonly IEquityService _equityService;
    private readonly ILogger<EquitySnapshotFunction> _logger;

    public EquitySnapshotFunction(
        IEquityService equityService,
        ILogger<EquitySnapshotFunction> logger)
    {
        _equityService = equityService;
        _logger = logger;
    }

    /// <summary>
    /// Capture equity snapshots for all agents every hour.
    /// CRON: 0 0 * * * * (at the top of every hour)
    /// </summary>
    [Function(nameof(CaptureEquitySnapshots))]
    public async Task CaptureEquitySnapshots(
        [TimerTrigger("0 0 * * * *")] TimerInfo timer,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Equity snapshot capture started at {Time}. Next run at {NextRun}",
            DateTime.UtcNow,
            timer.ScheduleStatus?.Next);

        try
        {
            var capturedCount = await _equityService.CaptureAllSnapshotsAsync(cancellationToken);

            _logger.LogInformation(
                "Equity snapshot capture completed. Captured {Count} snapshots",
                capturedCount);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Equity snapshot capture failed");
            throw; // Let Azure Functions handle retry
        }
    }
}
