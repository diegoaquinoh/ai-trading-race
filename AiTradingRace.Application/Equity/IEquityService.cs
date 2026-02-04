using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.Equity;

/// <summary>
/// Service for managing equity snapshots and calculating performance metrics.
/// </summary>
public interface IEquityService
{
    /// <summary>
    /// Creates an equity snapshot for the agent's portfolio using current market prices.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The newly created equity snapshot.</returns>
    Task<EquitySnapshotDto> CaptureSnapshotAsync(
        Guid agentId,
        CancellationToken ct = default);

    /// <summary>
    /// Retrieves the equity curve (historical snapshots) for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="from">Optional start date filter.</param>
    /// <param name="to">Optional end date filter.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>List of equity snapshots ordered by date.</returns>
    Task<IReadOnlyList<EquitySnapshotDto>> GetEquityCurveAsync(
        Guid agentId,
        DateTimeOffset? from = null,
        DateTimeOffset? to = null,
        CancellationToken ct = default);

    /// <summary>
    /// Gets the latest equity snapshot for an agent.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The most recent snapshot, or null if none exist.</returns>
    Task<EquitySnapshotDto?> GetLatestSnapshotAsync(
        Guid agentId,
        CancellationToken ct = default);

    /// <summary>
    /// Calculates performance metrics for an agent based on their trading history.
    /// </summary>
    /// <param name="agentId">The agent's unique identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Performance metrics including returns, drawdown, and trade statistics.</returns>
    Task<PerformanceMetrics> CalculatePerformanceAsync(
        Guid agentId,
        CancellationToken ct = default);

    /// <summary>
    /// Captures equity snapshots for all active agents.
    /// </summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The number of snapshots captured.</returns>
    Task<int> CaptureAllSnapshotsAsync(CancellationToken ct = default);

    /// <summary>
    /// Captures equity snapshots for all active agents with a shared batch and timestamp.
    /// This ensures all agents are valued at the same market prices at the same point in time.
    /// </summary>
    /// <param name="batchId">Unique identifier correlating this snapshot to a market data batch.</param>
    /// <param name="timestamp">The exact timestamp to use for all snapshots.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The number of snapshots captured.</returns>
    Task<int> CaptureAllSnapshotsAsync(
        Guid batchId,
        DateTimeOffset timestamp,
        CancellationToken ct = default);
}
