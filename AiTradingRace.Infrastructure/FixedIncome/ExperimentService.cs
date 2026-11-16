using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Immutable experiment definitions and run job lifecycle (spec 14.2, 15.2, 16.1).
/// Definitions are content-hashed: re-posting identical content is idempotent,
/// different content under the same (id, version) is a conflict.
/// </summary>
public sealed partial class ExperimentService : IExperimentService
{
    public const int MaxExperimentIdLength = 100;
    public const int MaxRunIdLength = 80;
    public const int MaxRepetitions = 20;
    public const int MaxStrategies = 20;

    private static readonly IReadOnlySet<string> AvailabilityPolicies = new HashSet<string>
    {
        "reconstructed_publication_plus_lag_v1",
        "forward_receipt_v1",
    };

    private readonly TradingDbContext _db;
    private readonly IRiskPolicyProvider _policies;
    private readonly TimeProvider _clock;
    private readonly ILogger<ExperimentService> _logger;

    public ExperimentService(
        TradingDbContext db,
        IRiskPolicyProvider policies,
        ILogger<ExperimentService> logger,
        TimeProvider? clock = null)
    {
        _db = db;
        _policies = policies;
        _logger = logger;
        _clock = clock ?? TimeProvider.System;
    }

    [GeneratedRegex(@"^[A-Za-z0-9][A-Za-z0-9_\-\.:]{0,79}$", RegexOptions.CultureInvariant)]
    private static partial Regex RunIdRegex();

    public async Task<ExperimentDefinitionResult> CreateDefinitionAsync(
        CreateExperimentDefinitionRequest request,
        string? actor,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        var errors = ValidateDefinition(request);

        string canonical = string.Empty;
        if (errors.Count == 0)
        {
            try
            {
                canonical = CanonicalJson.Serialize(FiWire.ToNode(request));
            }
            catch (FormatException ex)
            {
                Add(errors, "parameters", $"Definition cannot be canonicalized: {ex.Message}");
            }
        }

        if (errors.Count > 0)
        {
            return new ExperimentDefinitionResult
            {
                Status = ExperimentDefinitionStatus.Invalid,
                Errors = Freeze(errors),
                Message = "The experiment definition is invalid.",
            };
        }

        var hash = CanonicalJson.Sha256(canonical);
        var existing = await _db.FiExperimentDefinitions.AsNoTracking()
            .FirstOrDefaultAsync(d => d.ExperimentId == request.ExperimentId && d.Version == request.Version, cancellationToken);
        if (existing is not null)
        {
            return CompareExisting(existing, hash);
        }

        var entity = new ExperimentDefinition
        {
            ExperimentId = request.ExperimentId,
            Version = request.Version,
            Name = request.Name,
            Description = request.Description,
            DataMode = request.DataMode,
            RiskPolicyId = request.RiskPolicyId,
            ExecutionModelId = request.ExecutionModelId,
            InstrumentUniverseVersion = request.InstrumentUniverseVersion,
            StartDate = request.StartDate,
            EndDate = request.EndDate,
            Repetitions = request.Repetitions,
            DefinitionJson = canonical,
            DefinitionHash = hash,
            CreatedBy = actor,
            CreatedAt = _clock.GetUtcNow(),
        };
        _db.FiExperimentDefinitions.Add(entity);
        try
        {
            await _db.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException)
        {
            _db.ChangeTracker.Clear();
            var raced = await _db.FiExperimentDefinitions.AsNoTracking()
                .FirstOrDefaultAsync(d => d.ExperimentId == request.ExperimentId && d.Version == request.Version, cancellationToken);
            if (raced is null)
            {
                throw;
            }

            return CompareExisting(raced, hash);
        }

        _logger.LogInformation("Created experiment definition {ExperimentId} v{Version} ({Hash})",
            entity.ExperimentId, entity.Version, hash);
        return new ExperimentDefinitionResult { Status = ExperimentDefinitionStatus.Created, Definition = ToView(entity) };
    }

    public async Task<ExperimentDefinitionView?> GetDefinitionAsync(string experimentId, int? version, CancellationToken cancellationToken = default)
    {
        var entity = await FindDefinitionAsync(experimentId, version, cancellationToken);
        return entity is null ? null : ToView(entity);
    }

    public async Task<PagedResult<ExperimentDefinitionView>> ListDefinitionsAsync(int page, int pageSize, CancellationToken cancellationToken = default)
    {
        var (p, s) = PagedResult<ExperimentDefinitionView>.Normalize(page, pageSize);
        var query = _db.FiExperimentDefinitions.AsNoTracking();
        var total = await query.CountAsync(cancellationToken);
        var items = await query.OrderByDescending(d => d.Id).Skip((p - 1) * s).Take(s).ToListAsync(cancellationToken);
        return new PagedResult<ExperimentDefinitionView>(items.Select(ToView).ToList(), p, s, total);
    }

    public async Task<StartRunResult> StartRunAsync(
        string experimentId,
        StartRunRequest request,
        string? actor,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        var errors = new Dictionary<string, List<string>>();
        if (!FiRunType.All.Contains(request.RunType))
        {
            Add(errors, "runType", "runType must be 'replay' or 'forward'.");
        }

        if (!FiResponseMode.All.Contains(request.ResponseMode))
        {
            Add(errors, "responseMode", "responseMode must be 'recorded_replay' or 'fresh_inference'.");
        }

        if (request.RunId is not null && !RunIdRegex().IsMatch(request.RunId))
        {
            Add(errors, "runId", $"runId must match ^[A-Za-z0-9][A-Za-z0-9_\\-\\.:]{{0,{MaxRunIdLength - 1}}}$.");
        }

        if (request.ExperimentVersion is < 1)
        {
            Add(errors, "experimentVersion", "experimentVersion must be >= 1.");
        }

        if (errors.Count > 0)
        {
            return new StartRunResult { Status = StartRunStatus.Invalid, Errors = Freeze(errors), Message = "Invalid run request." };
        }

        var definition = await FindDefinitionAsync(experimentId, request.ExperimentVersion, cancellationToken);
        if (definition is null)
        {
            return new StartRunResult { Status = StartRunStatus.NotFound, Message = $"Experiment '{experimentId}' was not found." };
        }

        var policy = _policies.FindRiskPolicy(definition.RiskPolicyId);
        var executionModel = _policies.FindExecutionModel(definition.ExecutionModelId);
        if (policy is null || executionModel is null)
        {
            return new StartRunResult
            {
                Status = StartRunStatus.Invalid,
                Message = "The definition references a risk policy or execution model that is no longer configured.",
                Errors = Freeze(new Dictionary<string, List<string>>
                {
                    ["riskPolicyId"] = new() { $"'{definition.RiskPolicyId}' / '{definition.ExecutionModelId}' must be configured." },
                }),
            };
        }

        var runId = request.RunId ?? "run-" + Guid.NewGuid().ToString("N")[..20];
        var requestHash = CanonicalJson.ContentHash(new JsonObject
        {
            ["experimentId"] = definition.ExperimentId,
            ["experimentVersion"] = definition.Version,
            ["definitionHash"] = definition.DefinitionHash,
            ["runId"] = runId,
            ["runType"] = request.RunType,
            ["responseMode"] = request.ResponseMode,
        });

        var existing = await _db.FiExperimentRuns.AsNoTracking().FirstOrDefaultAsync(r => r.RunId == runId, cancellationToken);
        if (existing is not null)
        {
            return CompareExistingRun(existing, requestHash);
        }

        var definitionNode = JsonNode.Parse(definition.DefinitionJson) as JsonObject ?? new JsonObject();
        var strategies = (definitionNode["strategies"] as JsonArray ?? new JsonArray())
            .OfType<JsonObject>()
            .Select(s => FiWire.Deserialize<ExperimentStrategyRequest>(s))
            .ToList();

        var now = _clock.GetUtcNow();
        var genesisAsOf = request.RunType == FiRunType.Replay
            ? new DateTimeOffset(definition.StartDate.ToDateTime(TimeOnly.MinValue), TimeSpan.Zero)
            : new DateTimeOffset(now.UtcDateTime.Ticks - now.UtcDateTime.Ticks % TimeSpan.TicksPerSecond, TimeSpan.Zero);

        var run = new ExperimentRun
        {
            RunId = runId,
            ExperimentDefinitionId = definition.Id,
            ExperimentId = definition.ExperimentId,
            ExperimentVersion = definition.Version,
            RunType = request.RunType,
            ResponseMode = request.ResponseMode,
            DataMode = definition.DataMode,
            RiskPolicyId = definition.RiskPolicyId,
            ExecutionModelId = definition.ExecutionModelId,
            JobState = FiJobState.Queued,
            RequestHash = requestHash,
            RequestedBy = actor,
            CreatedAt = now,
        };

        var strategyManifest = new JsonArray();
        for (var repetition = 0; repetition < definition.Repetitions; repetition++)
        {
            foreach (var strategy in strategies)
            {
                var portfolioId = $"pf-{runId}-{strategy.StrategyId}-r{repetition}";
                var genesis = CanonicalJson.Serialize(PortfolioGenesis.Build(portfolioId, strategy.StrategyId, runId, genesisAsOf));
                var genesisHash = CanonicalJson.Sha256(genesis);

                run.Strategies.Add(new StrategyInstance
                {
                    RunId = runId,
                    StrategyId = strategy.StrategyId,
                    StrategyKind = strategy.StrategyKind,
                    StrategyConfigId = strategy.StrategyConfigId,
                    Repetition = repetition,
                    PortfolioId = portfolioId,
                    Label = strategy.Label,
                });
                _db.FiPortfolios.Add(new FiPortfolio
                {
                    PortfolioId = portfolioId,
                    RunId = runId,
                    StrategyId = strategy.StrategyId,
                    Repetition = repetition,
                    RiskPolicyId = definition.RiskPolicyId,
                    DataMode = definition.DataMode,
                    CurrentVersion = 0,
                    CurrentStateHash = genesisHash,
                    CreatedAt = now,
                    UpdatedAt = now,
                });
                _db.FiPortfolioStateVersions.Add(new PortfolioStateVersion
                {
                    PortfolioId = portfolioId,
                    Version = 0,
                    StateJson = genesis,
                    StateHash = genesisHash,
                    AsOf = genesisAsOf,
                    CreatedAt = now,
                });
                strategyManifest.Add(new JsonObject
                {
                    ["strategyId"] = strategy.StrategyId,
                    ["strategyKind"] = strategy.StrategyKind,
                    ["strategyConfigId"] = strategy.StrategyConfigId,
                    ["repetition"] = repetition,
                    ["portfolioId"] = portfolioId,
                    ["genesisStateHash"] = genesisHash,
                });
            }
        }

        var manifest = new JsonObject
        {
            ["schemaVersion"] = FiContract.SchemaVersion,
            ["runId"] = runId,
            ["experimentId"] = definition.ExperimentId,
            ["experimentVersion"] = definition.Version,
            ["definitionHash"] = definition.DefinitionHash,
            ["runType"] = request.RunType,
            ["responseMode"] = request.ResponseMode,
            ["dataMode"] = definition.DataMode,
            ["window"] = new JsonObject
            {
                ["startDate"] = FiWire.FormatDate(definition.StartDate),
                ["endDate"] = FiWire.FormatDate(definition.EndDate),
            },
            ["instrumentUniverseVersion"] = definition.InstrumentUniverseVersion,
            ["availabilityPolicy"] = definitionNode["availabilityPolicy"]?.DeepClone(),
            ["evidenceSnapshotId"] = definitionNode["evidenceSnapshotId"]?.DeepClone(),
            ["indexBuildId"] = definitionNode["indexBuildId"]?.DeepClone(),
            ["eventPriorityTable"] = FiContract.EventPriorityTable,
            ["riskPolicy"] = FiWire.ToNode(policy.ToWire(definition.RiskPolicyId)),
            ["executionModel"] = FiWire.ToNode(executionModel.ToWire(definition.ExecutionModelId)),
            ["strategies"] = strategyManifest,
            ["createdAt"] = FiWire.FormatInstant(now),
        };
        run.ManifestJson = CanonicalJson.Serialize(manifest);
        run.ManifestHash = CanonicalJson.Sha256(run.ManifestJson);
        _db.FiExperimentRuns.Add(run);

        try
        {
            await _db.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException)
        {
            _db.ChangeTracker.Clear();
            var raced = await _db.FiExperimentRuns.AsNoTracking().FirstOrDefaultAsync(r => r.RunId == runId, cancellationToken);
            if (raced is null)
            {
                throw;
            }

            return CompareExistingRun(raced, requestHash);
        }

        _logger.LogInformation("Queued fixed income run {RunId} for {ExperimentId} v{Version} ({RunType}, {ResponseMode})",
            runId, definition.ExperimentId, definition.Version, request.RunType, request.ResponseMode);
        return new StartRunResult { Status = StartRunStatus.Accepted, RunId = runId, JobState = run.JobState };
    }

    public async Task<bool> TryMarkRunningAsync(string runId, CancellationToken cancellationToken = default)
    {
        var run = await LoadRunForUpdateAsync(runId, cancellationToken);
        if (run is null || run.JobState != FiJobState.Queued)
        {
            return false;
        }

        run.JobState = FiJobState.Running;
        run.StartedAt = _clock.GetUtcNow();
        run.ConcurrencyStamp = Guid.NewGuid();
        return await TrySaveAsync(cancellationToken);
    }

    public Task MarkCompletedAsync(string runId, CancellationToken cancellationToken = default) =>
        FinishAsync(runId, FiJobState.Completed, null, cancellationToken);

    public Task MarkFailedAsync(string runId, string reason, CancellationToken cancellationToken = default) =>
        FinishAsync(runId, FiJobState.Failed, reason, cancellationToken);

    public async Task<RunStateChangeResult> CancelRunAsync(string runId, string? actor, CancellationToken cancellationToken = default)
    {
        var run = await LoadRunForUpdateAsync(runId, cancellationToken);
        if (run is null)
        {
            return new RunStateChangeResult(RunStateChangeStatus.NotFound, null, $"Run '{runId}' was not found.");
        }

        if (FiJobState.IsTerminal(run.JobState))
        {
            return new RunStateChangeResult(RunStateChangeStatus.InvalidTransition, run.JobState,
                $"Run is already {run.JobState}.");
        }

        run.JobState = FiJobState.Cancelled;
        run.StatusReason = $"Cancelled by {actor ?? "operator"}; committed events remain authoritative.";
        run.CompletedAt = _clock.GetUtcNow();
        run.ConcurrencyStamp = Guid.NewGuid();
        return await TrySaveAsync(cancellationToken)
            ? new RunStateChangeResult(RunStateChangeStatus.Changed, run.JobState)
            : new RunStateChangeResult(RunStateChangeStatus.InvalidTransition, null, "The run changed concurrently; retry.");
    }

    public async Task<string?> GetJobStateAsync(string runId, CancellationToken cancellationToken = default) =>
        await _db.FiExperimentRuns.AsNoTracking().Where(r => r.RunId == runId).Select(r => r.JobState)
            .FirstOrDefaultAsync(cancellationToken);

    public async Task<IReadOnlyList<string>> ListQueuedRunIdsAsync(CancellationToken cancellationToken = default) =>
        await _db.FiExperimentRuns.AsNoTracking()
            .Where(r => r.JobState == FiJobState.Queued)
            .OrderBy(r => r.Id)
            .Select(r => r.RunId)
            .ToListAsync(cancellationToken);

    public async Task<bool> TryRequeueAsync(string runId, string reason, CancellationToken cancellationToken = default)
    {
        var run = await LoadRunForUpdateAsync(runId, cancellationToken);
        if (run is null || run.JobState != FiJobState.Running)
        {
            return false;
        }

        run.JobState = FiJobState.Queued;
        run.StatusReason = reason.Length > 1900 ? reason[..1900] : reason;
        run.ConcurrencyStamp = Guid.NewGuid();
        return await TrySaveAsync(cancellationToken);
    }

    public async Task<IReadOnlyList<string>> RequeueOrphanedRunsAsync(CancellationToken cancellationToken = default)
    {
        var running = await _db.FiExperimentRuns.AsNoTracking()
            .Where(r => r.JobState == FiJobState.Running)
            .OrderBy(r => r.Id)
            .Select(r => r.RunId)
            .ToListAsync(cancellationToken);
        var requeued = new List<string>();
        foreach (var runId in running)
        {
            if (await TryRequeueAsync(runId,
                    "Interrupted while running; resuming from the last completed cycle checkpoint.", cancellationToken))
            {
                requeued.Add(runId);
            }
        }

        if (requeued.Count > 0)
        {
            _logger.LogWarning("Re-queued {Count} interrupted fixed income run(s): {RunIds}", requeued.Count, requeued);
        }

        return requeued;
    }

    private async Task FinishAsync(string runId, string state, string? reason, CancellationToken ct)
    {
        // The cycle runner updates the same run row from its own scope (errors, progress,
        // checkpoints), so a concurrency conflict here is expected: reload and retry rather
        // than leaving the run stuck in 'running'.
        const int attempts = 3;
        for (var attempt = 1; attempt <= attempts; attempt++)
        {
            var run = await LoadRunForUpdateAsync(runId, ct);
            if (run is null || FiJobState.IsTerminal(run.JobState))
            {
                return; // never overwrite a cancellation or an earlier terminal state
            }

            run.JobState = state;
            run.StatusReason = reason is null ? null : reason.Length > 1900 ? reason[..1900] : reason;
            run.CompletedAt = _clock.GetUtcNow();
            run.ConcurrencyStamp = Guid.NewGuid();
            if (await TrySaveAsync(ct))
            {
                return;
            }
        }

        _logger.LogError("Could not record terminal state {State} for run {RunId} after {Attempts} concurrent-update retries",
            state, runId, attempts);
    }

    /// <summary>
    /// Loads the run row for a state transition, discarding any instance this context tracked
    /// earlier: EF identity resolution would otherwise return the stale tracked copy (with an
    /// outdated concurrency stamp) instead of the row other scopes have since updated.
    /// </summary>
    private async Task<ExperimentRun?> LoadRunForUpdateAsync(string runId, CancellationToken ct)
    {
        foreach (var entry in _db.ChangeTracker.Entries<ExperimentRun>().Where(e => e.Entity.RunId == runId).ToList())
        {
            entry.State = EntityState.Detached;
        }

        return await _db.FiExperimentRuns.FirstOrDefaultAsync(r => r.RunId == runId, ct);
    }

    private async Task<bool> TrySaveAsync(CancellationToken ct)
    {
        try
        {
            await _db.SaveChangesAsync(ct);
            return true;
        }
        catch (DbUpdateConcurrencyException)
        {
            _db.ChangeTracker.Clear();
            return false;
        }
    }

    private Dictionary<string, List<string>> ValidateDefinition(CreateExperimentDefinitionRequest request)
    {
        var errors = new Dictionary<string, List<string>>();
        if (!FiWire.IsOpaqueId(request.ExperimentId) || request.ExperimentId.Length > MaxExperimentIdLength)
        {
            Add(errors, "experimentId", $"experimentId must be an opaque id of at most {MaxExperimentIdLength} characters.");
        }

        if (request.Version < 1)
        {
            Add(errors, "version", "version must be >= 1.");
        }

        if (string.IsNullOrWhiteSpace(request.Name) || request.Name.Length > 200)
        {
            Add(errors, "name", "name is required (at most 200 characters).");
        }

        if (!FiDataMode.All.Contains(request.DataMode))
        {
            Add(errors, "dataMode", "dataMode must be 'synthetic_curve' or 'observed_security'.");
        }

        if (request.StartDate == default || request.EndDate == default || request.StartDate > request.EndDate)
        {
            Add(errors, "startDate", "startDate and endDate are required and startDate must not be after endDate.");
        }

        if (_policies.FindRiskPolicy(request.RiskPolicyId) is null)
        {
            Add(errors, "riskPolicyId", $"Unknown risk policy '{request.RiskPolicyId}'. Configured: {string.Join(", ", _policies.RiskPolicyIds)}.");
        }

        if (_policies.FindExecutionModel(request.ExecutionModelId) is null)
        {
            Add(errors, "executionModelId", $"Unknown execution model '{request.ExecutionModelId}'.");
        }

        if (!FiWire.IsOpaqueId(request.InstrumentUniverseVersion))
        {
            Add(errors, "instrumentUniverseVersion", "instrumentUniverseVersion is required.");
        }

        if (!AvailabilityPolicies.Contains(request.AvailabilityPolicy))
        {
            Add(errors, "availabilityPolicy", $"availabilityPolicy must be one of: {string.Join(", ", AvailabilityPolicies)}.");
        }

        if (request.EvidenceSnapshotId is not null && !FiWire.IsOpaqueId(request.EvidenceSnapshotId))
        {
            Add(errors, "evidenceSnapshotId", "evidenceSnapshotId is malformed.");
        }

        if (request.IndexBuildId is not null && !FiWire.IsOpaqueId(request.IndexBuildId))
        {
            Add(errors, "indexBuildId", "indexBuildId is malformed.");
        }

        if (request.Repetitions is < 1 or > MaxRepetitions)
        {
            Add(errors, "repetitions", $"repetitions must be between 1 and {MaxRepetitions}.");
        }

        if (request.Strategies is null || request.Strategies.Count is 0 or > MaxStrategies)
        {
            Add(errors, "strategies", $"Between 1 and {MaxStrategies} strategies are required.");
        }
        else
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (var i = 0; i < request.Strategies.Count; i++)
            {
                var strategy = request.Strategies[i];
                if (!FiWire.IsStrategyId(strategy.StrategyId))
                {
                    Add(errors, $"strategies[{i}].strategyId", "strategyId must match ^[a-z][a-z0-9_]{1,63}$.");
                }
                else if (!seen.Add(strategy.StrategyId))
                {
                    Add(errors, $"strategies[{i}].strategyId", $"Duplicate strategy '{strategy.StrategyId}'.");
                }

                if (!FiStrategyKind.All.Contains(strategy.StrategyKind))
                {
                    Add(errors, $"strategies[{i}].strategyKind", $"strategyKind must be one of: {string.Join(", ", FiStrategyKind.All)}.");
                }

                if (!FiWire.IsOpaqueId(strategy.StrategyConfigId))
                {
                    Add(errors, $"strategies[{i}].strategyConfigId", "strategyConfigId is required.");
                }
            }
        }

        return errors;
    }

    private async Task<ExperimentDefinition?> FindDefinitionAsync(string experimentId, int? version, CancellationToken ct)
    {
        var query = _db.FiExperimentDefinitions.AsNoTracking().Where(d => d.ExperimentId == experimentId);
        return version is { } v
            ? await query.FirstOrDefaultAsync(d => d.Version == v, ct)
            : await query.OrderByDescending(d => d.Version).FirstOrDefaultAsync(ct);
    }

    private static ExperimentDefinitionResult CompareExisting(ExperimentDefinition existing, string hash) =>
        existing.DefinitionHash == hash
            ? new ExperimentDefinitionResult { Status = ExperimentDefinitionStatus.AlreadyExists, Definition = ToView(existing) }
            : new ExperimentDefinitionResult
            {
                Status = ExperimentDefinitionStatus.Conflict,
                Definition = ToView(existing),
                Message = $"Experiment '{existing.ExperimentId}' version {existing.Version} already exists with different content " +
                          "(definitions are immutable; publish a new version).",
            };

    private static StartRunResult CompareExistingRun(ExperimentRun existing, string requestHash) =>
        existing.RequestHash == requestHash
            ? new StartRunResult { Status = StartRunStatus.AlreadyExists, RunId = existing.RunId, JobState = existing.JobState }
            : new StartRunResult
            {
                Status = StartRunStatus.Conflict,
                RunId = existing.RunId,
                JobState = existing.JobState,
                Message = $"Run id '{existing.RunId}' already exists with different parameters.",
            };

    internal static ExperimentDefinitionView ToView(ExperimentDefinition d) => new(
        d.ExperimentId, d.Version, d.Name, d.Description, d.DataMode, d.RiskPolicyId, d.ExecutionModelId,
        d.InstrumentUniverseVersion, d.StartDate, d.EndDate, d.Repetitions, d.DefinitionHash,
        FiWire.TryParseNode(d.DefinitionJson), d.CreatedAt);

    private static void Add(Dictionary<string, List<string>> errors, string key, string message)
    {
        if (!errors.TryGetValue(key, out var list))
        {
            errors[key] = list = new List<string>();
        }

        list.Add(message);
    }

    private static IReadOnlyDictionary<string, string[]> Freeze(Dictionary<string, List<string>> errors) =>
        errors.ToDictionary(kv => kv.Key, kv => kv.Value.ToArray());
}
