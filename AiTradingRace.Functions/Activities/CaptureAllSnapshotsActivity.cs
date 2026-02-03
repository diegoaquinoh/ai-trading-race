using AiTradingRace.Application.Equity;
using AiTradingRace.Functions.Models;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Activities;

/// <summary>
/// Activity function to capture equity snapshots for all active agents.
/// </summary>
public sealed class CaptureAllSnapshotsActivity
{
    private readonly IEquityService _equityService;
    private readonly ILogger<CaptureAllSnapshotsActivity> _logger;

    public CaptureAllSnapshotsActivity(
        IEquityService equityService,
        ILogger<CaptureAllSnapshotsActivity> logger)
    {
        _equityService = equityService;
        _logger = logger;
    }

    [Function(nameof(CaptureAllSnapshotsActivity))]
    public async Task<int> Run(
        [ActivityTrigger] CaptureSnapshotsRequest request,
        CancellationToken ct)
    {
        _logger.LogInformation(
            "Capturing equity snapshots for batch {BatchId} at {Timestamp}",
            request.BatchId, request.Timestamp);

        var count = await _equityService.CaptureAllSnapshotsAsync(
            request.BatchId,
            request.Timestamp,
            ct);

        _logger.LogInformation(
            "Captured {Count} equity snapshots for batch {BatchId}",
            count, request.BatchId);

        return count;
    }
}
