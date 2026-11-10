using AiTradingRace.Application.FixedIncome.Models;

namespace AiTradingRace.Application.FixedIncome;

/// <summary>Experiment definitions (immutable versions) and run job lifecycle.</summary>
public interface IExperimentService
{
    /// <summary>Same id+version and same hash → AlreadyExists; different hash → Conflict.</summary>
    Task<ExperimentDefinitionResult> CreateDefinitionAsync(CreateExperimentDefinitionRequest request, string? actor, CancellationToken cancellationToken = default);

    Task<ExperimentDefinitionView?> GetDefinitionAsync(string experimentId, int? version, CancellationToken cancellationToken = default);

    Task<PagedResult<ExperimentDefinitionView>> ListDefinitionsAsync(int page, int pageSize, CancellationToken cancellationToken = default);

    /// <summary>Creates a queued run with its manifest, strategy instances and genesis portfolios.</summary>
    Task<StartRunResult> StartRunAsync(string experimentId, StartRunRequest request, string? actor, CancellationToken cancellationToken = default);

    /// <summary>queued → running. Returns false when the run is not queued (e.g. cancelled).</summary>
    Task<bool> TryMarkRunningAsync(string runId, CancellationToken cancellationToken = default);

    Task MarkCompletedAsync(string runId, CancellationToken cancellationToken = default);

    Task MarkFailedAsync(string runId, string reason, CancellationToken cancellationToken = default);

    Task<RunStateChangeResult> CancelRunAsync(string runId, string? actor, CancellationToken cancellationToken = default);

    Task<string?> GetJobStateAsync(string runId, CancellationToken cancellationToken = default);

    Task<IReadOnlyList<string>> ListQueuedRunIdsAsync(CancellationToken cancellationToken = default);

    /// <summary>running → queued so an interrupted run resumes from its last checkpoint. False when not running.</summary>
    Task<bool> TryRequeueAsync(string runId, string reason, CancellationToken cancellationToken = default);

    /// <summary>
    /// Re-queues runs left "running" by a crashed single in-process worker (startup recovery);
    /// returns their ids. Only valid when exactly one worker executes runs.
    /// </summary>
    Task<IReadOnlyList<string>> RequeueOrphanedRunsAsync(CancellationToken cancellationToken = default);
}
