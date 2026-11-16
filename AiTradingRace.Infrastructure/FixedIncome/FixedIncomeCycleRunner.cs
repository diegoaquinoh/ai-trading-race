using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using DomainCycleStatus = AiTradingRace.Domain.Entities.FixedIncome.FiCycleStatus;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Application-mode cycle executor (spec 6.4, 9.5, 10.1, 15). Orchestrates, verifies and
/// commits; it never prices, accrues, sizes or computes risk. Per session:
/// (a) PROCESS_EVENTS for every portfolio up to the decision time; (b) shared-input check
/// (stale/unavailable curve ⇒ skipped cycle with a persisted skip decision for every
/// strategy); (c) the common bootstrap for invested strategies on the first eligible
/// session; (d) bounded-parallel strategy decisions, each verified and persisted, with
/// SUBMIT_DECISION for verified REBALANCE proposals; (e) VALUE_PORTFOLIO for every
/// portfolio; (f) cycle checkpoint and run progress (simulated clock ≠ operational time).
/// Every command id is deterministic, and a committed command is detected before any
/// recomputation, so retries and restarts never duplicate a financial effect.
/// </summary>
public sealed class FixedIncomeCycleRunner : IFixedIncomeCycleRunner
{
    public const string Actor = "fi-run-executor";

    private readonly TradingDbContext _db;
    private readonly IResearchEngineClient _engine;
    private readonly ITransitionCommitService _commits;
    private readonly IDecisionAuditService _audit;
    private readonly IExperimentService _experiments;
    private readonly IRiskPolicyProvider _policies;
    private readonly FixedIncomeExecutionOptions _options;
    private readonly ResearchEngineOptions _engineOptions;
    private readonly FixedIncomeMetrics _metrics;
    private readonly TimeProvider _clock;
    private readonly ILogger<FixedIncomeCycleRunner> _logger;

    public FixedIncomeCycleRunner(
        TradingDbContext db,
        IResearchEngineClient engine,
        ITransitionCommitService commits,
        IDecisionAuditService audit,
        IExperimentService experiments,
        IRiskPolicyProvider policies,
        IOptions<FixedIncomeOptions> options,
        IOptions<ResearchEngineOptions> engineOptions,
        FixedIncomeMetrics metrics,
        ILogger<FixedIncomeCycleRunner> logger,
        TimeProvider? clock = null)
    {
        _db = db;
        _engine = engine;
        _commits = commits;
        _audit = audit;
        _experiments = experiments;
        _policies = policies;
        _options = options.Value.Execution ?? new FixedIncomeExecutionOptions();
        _engineOptions = engineOptions.Value;
        _metrics = metrics;
        _logger = logger;
        _clock = clock ?? TimeProvider.System;
    }

    // ------------------------------------------------------------------ planning

    public Task<FiRunPlan> PrepareRunAsync(string runId, CancellationToken cancellationToken = default) =>
        RecordPauseAsync(runId, "run preparation", () => PrepareRunCoreAsync(runId, cancellationToken), cancellationToken);

    public Task<FiRunPlan> PreparePaperCycleAsync(string runId, DateOnly sessionDate, CancellationToken cancellationToken = default) =>
        RecordPauseAsync(runId, $"paper cycle preparation ({FiWire.FormatDate(sessionDate)})",
            () => PreparePaperCycleCoreAsync(runId, sessionDate, cancellationToken), cancellationToken);

    /// <summary>A transient dependency failure pauses the run (resumable); record it as an operator-visible run error first.</summary>
    private async Task<T> RecordPauseAsync<T>(string runId, string step, Func<Task<T>> body, CancellationToken ct)
    {
        try
        {
            return await body();
        }
        catch (FiTransientDependencyException ex)
        {
            await AppendRunErrorAsync(runId, FiErrorScope.Source, "engine_unavailable",
                $"{step} paused (resumable, no financial effect lost): {ex.Message}", ct);
            throw;
        }
    }

    private async Task<FiRunPlan> PrepareRunCoreAsync(string runId, CancellationToken cancellationToken)
    {
        var ctx = await LoadAsync(runId, cancellationToken);
        if (ctx is null)
        {
            return Plan(runId, FiPlanStatus.Failed, reason: $"Run '{runId}' was not found or its configuration is incomplete.");
        }

        using var scope = RunScope(ctx);
        if (Terminal(ctx.Run, out var terminalPlan))
        {
            return terminalPlan;
        }

        var spec = ctx.Spec;
        var start = spec.StartDate;
        var end = spec.EndDate;
        if (ctx.Run.RunType == FiRunType.Forward)
        {
            // Forward runs only process sessions from their creation onwards whose decision time has passed.
            var created = DateOnly.FromDateTime(FiMarketClock.ToLocal(ctx.Run.CreatedAt));
            var latestDue = PaperCycleSchedule.LatestDueSessionDate(_clock.GetUtcNow(), FiMarketClock.DecisionTime.Hour,
                FiMarketClock.MarketTimeZone);
            start = created > start ? created : start;
            end = latestDue < end ? latestDue : end;
            if (start > end)
            {
                return Plan(runId, FiPlanStatus.NothingToDo, ctx.Run.RunType, reason: "No forward session is due yet.",
                    windowComplete: latestDue >= spec.EndDate);
            }
        }

        var sessions = await FetchSessionsAsync(ctx, start, end, cancellationToken);
        if (sessions.Error is not null)
        {
            await AppendRunErrorAsync(runId, FiErrorScope.Source, "sessions_invalid", sessions.Error, cancellationToken);
            return Plan(runId, FiPlanStatus.Failed, ctx.Run.RunType, reason: $"{FiErrorScope.Source}: {sessions.Error}");
        }

        await EnsurePortfoliosAsync(ctx, cancellationToken);
        var freeze = await FreezeCyclesAsync(ctx, sessions.Sessions, append: ctx.Run.RunType == FiRunType.Forward, cancellationToken);
        if (freeze is not null)
        {
            await AppendRunErrorAsync(runId, FiErrorScope.Cycle, "cycle_manifest_changed", freeze, cancellationToken);
            return Plan(runId, FiPlanStatus.Failed, ctx.Run.RunType, reason: $"{FiErrorScope.Cycle}: {freeze}");
        }

        var cycles = await _db.FiCycles.AsNoTracking().Where(c => c.RunId == runId).OrderBy(c => c.Sequence).ToListAsync(cancellationToken);
        if (cycles.Count == 0)
        {
            if (ctx.Run.RunType == FiRunType.Forward)
            {
                return Plan(runId, FiPlanStatus.NothingToDo, ctx.Run.RunType, reason: "No supported market session is due.",
                    windowComplete: end >= spec.EndDate);
            }

            const string reason = "no supported market sessions in the experiment window";
            await AppendRunErrorAsync(runId, FiErrorScope.Source, "no_sessions", reason, cancellationToken);
            return Plan(runId, FiPlanStatus.Failed, ctx.Run.RunType, reason: $"{FiErrorScope.Source}: {reason}");
        }

        var capital = await EnsureInitialCapitalAsync(ctx, cycles[0].SessionDate, cancellationToken);
        if (capital is not null)
        {
            await AppendRunErrorAsync(runId, FiErrorScope.FinancialState, "initialization_failed", capital, cancellationToken);
            return Plan(runId, FiPlanStatus.Failed, ctx.Run.RunType, reason: "initialization_failed: " + capital);
        }

        await UpdateRunAsync(runId, run =>
        {
            run.TotalCycles = ctx.Run.RunType == FiRunType.Replay ? cycles.Count : null;
        }, cancellationToken);
        await RecordEngineVersionAsync(ctx, cancellationToken);

        var pending = cycles.Where(c => !IsCheckpointed(c.Status)).Select(c => c.CycleId).ToList();
        var lastCheckpoint = cycles.LastOrDefault(c => IsCheckpointed(c.Status));
        if (lastCheckpoint is not null && pending.Count > 0)
        {
            _logger.LogInformation(
                "Resuming run {RunId} after checkpoint {CycleId} (sequence {Sequence}); {Pending} cycle(s) left",
                runId, lastCheckpoint.CycleId, lastCheckpoint.Sequence, pending.Count);
        }

        return new FiRunPlan
        {
            RunId = runId,
            Status = pending.Count == 0 ? FiPlanStatus.NothingToDo : FiPlanStatus.Ready,
            RunType = ctx.Run.RunType,
            CycleIds = cycles.Select(c => c.CycleId).ToList(),
            PendingCycleIds = pending,
            WindowComplete = ctx.Run.RunType == FiRunType.Replay || end >= spec.EndDate,
        };
    }

    private async Task<FiRunPlan> PreparePaperCycleCoreAsync(string runId, DateOnly sessionDate, CancellationToken cancellationToken)
    {
        var ctx = await LoadAsync(runId, cancellationToken);
        if (ctx is null)
        {
            return Plan(runId, FiPlanStatus.Failed, FiRunType.Forward, reason: $"Run '{runId}' was not found or its configuration is incomplete.");
        }

        using var scope = RunScope(ctx);
        if (Terminal(ctx.Run, out var terminalPlan))
        {
            return terminalPlan;
        }

        if (ctx.Run.RunType != FiRunType.Forward)
        {
            return Plan(runId, FiPlanStatus.Failed, ctx.Run.RunType, reason: "Paper cycles apply to forward runs only.");
        }

        if (sessionDate > ctx.Spec.EndDate)
        {
            return Plan(runId, FiPlanStatus.NothingToDo, FiRunType.Forward, reason: "The forward window has ended.", windowComplete: true);
        }

        if (sessionDate < ctx.Spec.StartDate)
        {
            return Plan(runId, FiPlanStatus.NothingToDo, FiRunType.Forward, reason: "The forward window has not started.");
        }

        var sessions = await FetchSessionsAsync(ctx, sessionDate, sessionDate, cancellationToken);
        if (sessions.Error is not null)
        {
            await AppendRunErrorAsync(runId, FiErrorScope.Source, "sessions_invalid", sessions.Error, cancellationToken);
            return Plan(runId, FiPlanStatus.NothingToDo, FiRunType.Forward, reason: $"{FiErrorScope.Source}: {sessions.Error}");
        }

        var session = sessions.Sessions.FirstOrDefault(s => s.SessionDate == FiWire.FormatDate(sessionDate));
        if (session is null)
        {
            return Plan(runId, FiPlanStatus.NothingToDo, FiRunType.Forward,
                reason: $"{FiWire.FormatDate(sessionDate)} is not a supported market session.",
                windowComplete: sessionDate >= ctx.Spec.EndDate);
        }

        await EnsurePortfoliosAsync(ctx, cancellationToken);
        var freeze = await FreezeCyclesAsync(ctx, new[] { session }, append: true, cancellationToken);
        if (freeze is not null)
        {
            return Plan(runId, FiPlanStatus.Failed, FiRunType.Forward, reason: $"{FiErrorScope.Cycle}: {freeze}");
        }

        var cycles = await _db.FiCycles.AsNoTracking().Where(c => c.RunId == runId).OrderBy(c => c.Sequence).ToListAsync(cancellationToken);
        var capital = await EnsureInitialCapitalAsync(ctx, cycles[0].SessionDate, cancellationToken);
        if (capital is not null)
        {
            await AppendRunErrorAsync(runId, FiErrorScope.FinancialState, "initialization_failed", capital, cancellationToken);
            return Plan(runId, FiPlanStatus.Failed, FiRunType.Forward, reason: "initialization_failed: " + capital);
        }

        await RecordEngineVersionAsync(ctx, cancellationToken);
        var cycleId = FiIds.Cycle(sessionDate);
        var pending = cycles.Where(c => !IsCheckpointed(c.Status)).Select(c => c.CycleId).ToList();
        return new FiRunPlan
        {
            RunId = runId,
            Status = pending.Count == 0 ? FiPlanStatus.NothingToDo : FiPlanStatus.Ready,
            RunType = FiRunType.Forward,
            CycleIds = cycles.Select(c => c.CycleId).ToList(),
            PendingCycleIds = pending,
            Reason = pending.Contains(cycleId) ? null : "The paper cycle was already completed.",
            WindowComplete = sessionDate >= ctx.Spec.EndDate,
        };
    }

    public async Task FinalizeRunAsync(string runId, FiRunFinalization finalization, CancellationToken cancellationToken = default)
    {
        if (finalization.Cancelled || finalization.KeepRunning)
        {
            return;
        }

        if (finalization.Succeeded)
        {
            await _experiments.MarkCompletedAsync(runId, cancellationToken);
        }
        else
        {
            var reason = finalization.Reason ?? "Run failed without a reason.";
            await AppendRunErrorAsync(runId, FiErrorScope.Cycle, "run_failed", reason, cancellationToken);
            await _experiments.MarkFailedAsync(runId, reason, cancellationToken);
        }
    }

    // ------------------------------------------------------------------ cycle

    public async Task<FiCycleResult> ExecuteCycleAsync(string runId, string cycleId, CancellationToken cancellationToken = default)
    {
        var ctx = await LoadAsync(runId, cancellationToken);
        if (ctx is null)
        {
            return CycleResult(runId, cycleId, FiCycleRunStatus.Failed, $"Run '{runId}' was not found or its configuration is incomplete.");
        }

        using var runScope = RunScope(ctx);
        using var cycleScope = _logger.BeginScope(new Dictionary<string, object?> { ["CycleId"] = cycleId });

        if (ctx.Run.JobState == FiJobState.Cancelled)
        {
            return CycleResult(runId, cycleId, FiCycleRunStatus.Cancelled, ctx.Run.StatusReason ?? "Run cancelled.");
        }

        if (ctx.Run.JobState is FiJobState.Failed or FiJobState.Completed)
        {
            return CycleResult(runId, cycleId, FiCycleRunStatus.Failed, $"Run is already {ctx.Run.JobState}.");
        }

        var cycle = await _db.FiCycles.AsNoTracking().FirstOrDefaultAsync(c => c.RunId == runId && c.CycleId == cycleId, cancellationToken);
        if (cycle is null)
        {
            return CycleResult(runId, cycleId, FiCycleRunStatus.Failed, $"Cycle '{cycleId}' is not part of run '{runId}'.");
        }

        if (IsCheckpointed(cycle.Status))
        {
            _metrics.Add(FixedIncomeMetrics.DuplicateCommands, tagKey: "kind", tagValue: "cycle");
            return CycleResult(runId, cycleId, FiCycleRunStatus.AlreadyDone, cycle.Status);
        }

        var unfinished = await _db.FiCycles.AsNoTracking()
            .Where(c => c.RunId == runId && c.Sequence < cycle.Sequence &&
                        c.Status != DomainCycleStatus.Completed && c.Status != DomainCycleStatus.Skipped)
            .Select(c => c.CycleId).FirstOrDefaultAsync(cancellationToken);
        if (unfinished is not null)
        {
            return CycleResult(runId, cycleId, FiCycleRunStatus.Failed,
                $"Cycle '{cycleId}' cannot run before earlier cycle '{unfinished}' reaches its checkpoint.");
        }

        var session = ReadInputs(cycle);
        // The run's previous frozen session (offline replay's sessions[index - 1]); sent as the
        // authoritative DecisionRequest.sessionContext so both paths give strategies the same value.
        var previousSession = await _db.FiCycles.AsNoTracking()
            .Where(c => c.RunId == runId && c.Sequence < cycle.Sequence)
            .OrderByDescending(c => c.Sequence)
            .Select(c => (DateOnly?)c.SessionDate)
            .FirstOrDefaultAsync(cancellationToken);
        var work = new CycleWork(ctx, cycle, session) { PreviousSessionDate = previousSession };
        work.Errors.Metrics = _metrics;
        work.Errors.Logger = _logger;
        await UpdateCycleAsync(cycle.Id, c =>
        {
            c.Status = DomainCycleStatus.Running;
            c.StartedAt ??= _clock.GetUtcNow();
            c.SkipReason = null;
        }, cancellationToken);

        try
        {
            return await RunCycleAsync(work, cancellationToken);
        }
        catch (FiTransientDependencyException ex)
        {
            await PauseCycleAsync(work, ex, cancellationToken);
            throw;
        }
    }

    /// <summary>
    /// A transient dependency failure pauses the run without a checkpoint: the cycle is marked failed
    /// (resumable) with the errors collected so far, and the run records an operator-visible error.
    /// A resumed run re-executes the cycle with the same command ids (committed ones are not recomputed).
    /// </summary>
    private async Task PauseCycleAsync(CycleWork work, FiTransientDependencyException ex, CancellationToken ct)
    {
        var reason = $"paused (resumable): {ex.Message}";
        work.Errors.Add(FiErrorScope.Source, "engine_unavailable", reason);
        await UpdateCycleAsync(work.Cycle.Id, c =>
        {
            c.Status = DomainCycleStatus.Failed;
            c.SkipReason = Truncate(reason);
            c.ErrorsJson = work.Errors.ToJson();
        }, ct);
        await AppendRunErrorAsync(work.Ctx.Run.RunId, FiErrorScope.Source, "engine_unavailable",
            $"cycle {work.Cycle.CycleId} {reason}", ct);
    }

    private async Task<FiCycleResult> RunCycleAsync(CycleWork work, CancellationToken cancellationToken)
    {
        var ctx = work.Ctx;
        var session = work.Session;
        var runId = ctx.Run.RunId;

        // (a) Due events for every portfolio up to the decision time (fills, settlements, cash flows).
        foreach (var strategy in ctx.Strategies)
        {
            var outcome = await RunCommandAsync(work, strategy, FiIds.Steps.Process, FiCommandType.ProcessEvents,
                work.DecisionAsOf, marketSnapshot: null, cancellationToken: cancellationToken);
            if (!outcome.Succeeded)
            {
                work.Impaired.Add(strategy.PortfolioId);
                work.Errors.Add(outcome.Scope, "process_events_failed", outcome.Message, strategy, outcome.CommandId);
            }
        }

        if (await IsCancelledAsync(runId, cancellationToken))
        {
            return await CancelCycleAsync(work, cancellationToken);
        }

        // Matched variants must start identically: verify the common bootstrap fills once they occur.
        var bootstrapCheck = await CheckBootstrapAsync(work, cancellationToken);
        if (bootstrapCheck is not null)
        {
            return await FailCycleAsync(work, "initialization_failed: " + bootstrapCheck, cancellationToken);
        }

        // (b) Shared-input check: invalid shared inputs skip the matched cycle for all competitors.
        var staleReason = SharedInputProblem(session, work.DecisionAsOf);
        if (staleReason is not null)
        {
            foreach (var strategy in ctx.Strategies)
            {
                await RecordSynthesizedAsync(work, strategy, FiDecisionOutcome.SkippedStaleData, new[] { staleReason }, cancellationToken);
            }

            work.Errors.Add(FiErrorScope.Cycle, "skipped_stale_data", staleReason, severity: "warning");
            await ValueAllAsync(work, marketSnapshot: null, cancellationToken);
            return await CheckpointAsync(work, DomainCycleStatus.Skipped, $"{FiDecisionOutcome.SkippedStaleData}: {staleReason}", cancellationToken);
        }

        var marketSnapshot = MarketSnapshotRef(ctx, session);

        // (c) Common bootstrap on the first eligible session.
        var handled = new HashSet<string>(StringComparer.Ordinal);
        if (await IsBootstrapCycleAsync(work, cancellationToken))
        {
            var bootstrap = await BootstrapAsync(work, marketSnapshot, handled, cancellationToken);
            if (bootstrap is not null)
            {
                return await FailCycleAsync(work, "initialization_failed: " + bootstrap, cancellationToken);
            }
        }

        // (d) Bounded-parallel strategy decisions; every outcome is persisted.
        var cancelled = await DecideAsync(work, marketSnapshot, handled, cancellationToken);
        if (cancelled)
        {
            return await CancelCycleAsync(work, cancellationToken);
        }

        // (e) Common end-of-day valuation for every portfolio (failed strategies included).
        await ValueAllAsync(work, marketSnapshot, cancellationToken);

        // (f) Checkpoint.
        return await CheckpointAsync(work, DomainCycleStatus.Completed, null, cancellationToken);
    }

    // ------------------------------------------------------------------ cycle steps

    private async Task<string?> BootstrapAsync(CycleWork work, MarketSnapshotRefDto marketSnapshot, HashSet<string> handled, CancellationToken ct)
    {
        var invested = work.Ctx.Strategies.Where(s => s.Invested).ToList();
        if (invested.Count == 0)
        {
            return null;
        }

        BootstrapAllocationDto allocation;
        try
        {
            allocation = await _engine.GetBootstrapAllocationAsync(new BootstrapAllocationRequestDto
            {
                SessionDate = work.Session.SessionDate,
                UniverseVersion = work.Ctx.Spec.InstrumentUniverseVersion,
                RiskPolicy = work.Ctx.Policy.ToWire(work.Ctx.Run.RiskPolicyId),
            }, ct);
        }
        catch (Exception ex) when (ex is ResearchEngineUnavailableException or ResearchEngineRateLimitedException)
        {
            throw new FiTransientDependencyException($"Bootstrap allocation unavailable: {ex.Message}", ex);
        }
        catch (ResearchEngineException ex)
        {
            work.Errors.Add(FiErrorScope.Source, "bootstrap_allocation_failed", ex.Message);
            return "bootstrap allocation rejected by the engine: " + ex.Message;
        }

        if (allocation.Targets.Count == 0 ||
            allocation.Targets.Any(t => !FiWire.TryParseDecimal(t.Weight, out var w) || w < 0 || string.IsNullOrEmpty(t.SecurityId)))
        {
            work.Errors.Add(FiErrorScope.Source, "bootstrap_allocation_invalid", "Empty or malformed bootstrap targets.");
            return "bootstrap allocation is empty or malformed";
        }

        var proposalJson = CanonicalJson.Serialize(new JsonObject
        {
            ["action"] = FiDecisionAction.Bootstrap,
            ["targetWeights"] = FiWire.ToNode(allocation.Targets),
            ["supportingClaimIds"] = new JsonArray(),
            ["supportingCalculationIds"] = new JsonArray(),
            ["allocationVersion"] = allocation.Version,
        });

        foreach (var strategy in invested)
        {
            handled.Add(strategy.PortfolioId);
            var decisionId = work.DecisionId(strategy);
            using var decisionScope = _logger.BeginScope(new Dictionary<string, object?>
            {
                ["StrategyId"] = strategy.StrategyId,
                ["DecisionId"] = decisionId,
            });

            // Isolation (spec 15.3): a portfolio that cannot take the common bootstrap (due events failed, or
            // already impaired/blocked) is left out of it and impaired; the other competitors still bootstrap.
            // A resumed cycle whose bootstrap submission already committed keeps its committed result.
            var submitted = await _commits.GetCommandAsync(
                FiIds.Command(work.Ctx.Run.RunId, work.Cycle.CycleId, strategy.PortfolioId, FiIds.Steps.Submit), ct) is not null;
            var restriction = submitted ? null
                : work.Impaired.Contains(strategy.PortfolioId) ? "due events could not be processed before the bootstrap"
                : (await _commits.GetCurrentStateAsync(strategy.PortfolioId, ct))?.BlockedReason;
            if (restriction is not null)
            {
                var reason = "bootstrap_skipped: " + restriction;
                await RecordSynthesizedAsync(work, strategy, FiDecisionOutcome.FailedDependency, new[] { reason }, ct);
                work.Errors.Add(FiErrorScope.FinancialState, "bootstrap_isolated", reason, strategy, decisionId: decisionId);
                await IsolateAsync(work, strategy, reason, commandId: null, ct);
                continue;
            }

            await RecordSynthesizedAsync(work, strategy, FiDecisionOutcome.CompletedProposal,
                new[] { $"common_bootstrap:{allocation.Version}" }, ct, FiDecisionAction.Bootstrap, proposalJson);

            var outcome = await RunCommandAsync(work, strategy, FiIds.Steps.Submit, FiCommandType.SubmitDecision,
                work.DecisionAsOf, marketSnapshot, decisionId, FiDecisionAction.Bootstrap, allocation.Targets, cancellationToken: ct);
            if (outcome.Status == CommandStatus.EngineError)
            {
                // Already isolated by RunCommandAsync: this competitor stays out of the matched bootstrap.
                work.Errors.Add(outcome.Scope, "bootstrap_isolated", outcome.Message, strategy, outcome.CommandId, decisionId);
                continue;
            }

            var accepted = outcome.Succeeded && await BootstrapAcceptedAsync(strategy.PortfolioId, decisionId, outcome.CommandId, ct);
            if (!accepted)
            {
                var detail = outcome.Succeeded ? "policy evaluation rejected the bootstrap targets" : outcome.Message;
                work.Errors.Add(FiErrorScope.FinancialState, "bootstrap_rejected", detail, strategy, outcome.CommandId, decisionId);
                return $"{strategy.StrategyId}: bootstrap rejected ({detail})";
            }
        }

        return null;
    }

    /// <summary>Fans out decisions; returns true when an operator cancelled the run meanwhile.</summary>
    private async Task<bool> DecideAsync(CycleWork work, MarketSnapshotRefDto marketSnapshot, HashSet<string> handled, CancellationToken ct)
    {
        var ctx = work.Ctx;
        var calls = new List<DecisionCall>();
        foreach (var strategy in ctx.Strategies.Where(s => !handled.Contains(s.PortfolioId)))
        {
            var decisionId = work.DecisionId(strategy);
            var stored = await _db.FiDecisions.AsNoTracking().FirstOrDefaultAsync(d => d.DecisionId == decisionId, ct);
            if (stored is not null)
            {
                // Resumed cycle: the logical decision is final; never re-request it.
                calls.Add(new DecisionCall(strategy, decisionId, null) { Stored = stored });
                continue;
            }

            if (work.Impaired.Contains(strategy.PortfolioId))
            {
                await RecordSynthesizedAsync(work, strategy, FiDecisionOutcome.FailedDependency,
                    new[] { "process_events_failed: the portfolio's due events could not be processed this cycle" }, ct);
                continue;
            }

            var state = await _commits.GetCurrentStateAsync(strategy.PortfolioId, ct);
            if (state is null || state.BlockedReason is not null)
            {
                // Blocked (reconciliation) or impaired (isolated engine error): no new discretionary decision.
                var kind = FiPortfolioRestriction.KindOf(state?.BlockedReason) ?? FiPortfolioRestriction.Blocked;
                var reason = state is null ? "portfolio_missing" : $"portfolio_{kind}: " + state.BlockedReason;
                work.Errors.Add(FiErrorScope.FinancialState, "portfolio_" + kind, reason, strategy);
                await RecordSynthesizedAsync(work, strategy, FiDecisionOutcome.FailedDependency, new[] { reason }, ct);
                continue;
            }

            var request = BuildDecisionRequest(work, strategy, decisionId, state, marketSnapshot);
            calls.Add(new DecisionCall(strategy, decisionId, request) { RequestHash = FiRequestBody.Hash(request) });
        }

        // Only the engine calls run in parallel; persistence stays sequential on this scope's DbContext.
        var maxParallel = Math.Max(1, _options.MaxParallelDecisions);
        using (var gate = new SemaphoreSlim(maxParallel, maxParallel))
        {
            await Task.WhenAll(calls.Where(c => c.Request is not null).Select(async call =>
            {
                await gate.WaitAsync(ct);
                try
                {
                    call.Result = await _engine.RequestDecisionAsync(call.Request!, ct);
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested)
                {
                    throw;
                }
                catch (Exception ex)
                {
                    call.Failure = ex;
                }
                finally
                {
                    gate.Release();
                }
            }));
        }

        var cancelled = await IsCancelledAsync(ctx.Run.RunId, ct);
        foreach (var call in calls)
        {
            using var decisionScope = _logger.BeginScope(new Dictionary<string, object?>
            {
                ["StrategyId"] = call.Strategy.StrategyId,
                ["DecisionId"] = call.DecisionId,
            });

            var actionable = await PersistDecisionAsync(work, call, ct);
            if (actionable is null || cancelled)
            {
                continue;
            }

            var outcome = await RunCommandAsync(work, call.Strategy, FiIds.Steps.Submit, FiCommandType.SubmitDecision,
                work.DecisionAsOf, marketSnapshot, call.DecisionId, FiDecisionAction.Rebalance, actionable.TargetWeights,
                cancellationToken: ct);
            if (!outcome.Succeeded)
            {
                work.Errors.Add(outcome.Scope, "submit_decision_failed", outcome.Message, call.Strategy, outcome.CommandId, call.DecisionId);
            }
        }

        return cancelled;
    }

    /// <summary>Persists the decision outcome; returns the proposal when it is a verified REBALANCE to submit.</summary>
    private async Task<ProposalDto?> PersistDecisionAsync(CycleWork work, DecisionCall call, CancellationToken ct)
    {
        var strategy = call.Strategy;
        Decision? stored = call.Stored;

        if (stored is null && call.Result is not null)
        {
            var audit = await _audit.RecordResultAsync(call.Result, new DecisionAuditContext
            {
                PortfolioId = strategy.PortfolioId,
                ExpectedDecisionId = call.DecisionId,
                ExpectedRequestHash = call.RequestHash,
            }, ct);

            if (audit.Status == DecisionAuditStatus.Rejected)
            {
                var reason = "result_rejected: " + string.Join("; ", audit.Issues);
                work.Errors.Add(FiErrorScope.Strategy, "strategy_result_rejected", reason, strategy, decisionId: call.DecisionId);
                await RecordSynthesizedAsync(work, strategy, FiDecisionOutcome.FailedInvalidOutput, new[] { reason }, ct);
                return null;
            }

            if (audit.Status == DecisionAuditStatus.Conflict)
            {
                work.Errors.Add(FiErrorScope.Strategy, "decision_conflict", string.Join("; ", audit.Issues), strategy,
                    decisionId: call.DecisionId);
            }

            CountBudget(call.Result.Node);
            stored = await _db.FiDecisions.AsNoTracking().FirstOrDefaultAsync(d => d.DecisionId == call.DecisionId, ct);
        }
        else if (stored is null)
        {
            var (outcome, reason, scope) = ClassifyFailure(call.Failure);
            work.Errors.Add(scope, "decision_request_failed", reason, strategy, decisionId: call.DecisionId);
            await RecordSynthesizedAsync(work, strategy, outcome, new[] { reason }, ct);
            return null;
        }

        if (stored is null)
        {
            return null;
        }

        _metrics.Add(FixedIncomeMetrics.DecisionOutcomes, tagKey: "outcome", tagValue: stored.Outcome);
        if (stored.Integrity is not (FiAuditIntegrity.Verified or FiAuditIntegrity.Synthesized))
        {
            work.Errors.Add(FiErrorScope.Strategy, "result_integrity", $"Strategy result integrity is {stored.Integrity}; no order.",
                strategy, decisionId: call.DecisionId);
            return null;
        }

        if (stored.Outcome != FiDecisionOutcome.CompletedProposal)
        {
            return null;
        }

        if (stored.Action == FiDecisionAction.Bootstrap && stored.Integrity != FiAuditIntegrity.Synthesized)
        {
            work.Errors.Add(FiErrorScope.Strategy, "strategy_bootstrap_ignored",
                "Bootstrap is platform-owned and applied identically; a strategy-proposed BOOTSTRAP is not submitted.",
                strategy, decisionId: call.DecisionId, severity: "warning");
            return null;
        }

        if (stored.Action != FiDecisionAction.Rebalance || stored.Integrity != FiAuditIntegrity.Verified ||
            !_engineOptions.IsEngineVersionAllowed(stored.EngineVersion))
        {
            return null;
        }

        try
        {
            var proposal = stored.ProposalJson is null ? null : JsonSerializer.Deserialize<ProposalDto>(stored.ProposalJson, FiContract.WireOptions);
            if (proposal is null || proposal.TargetWeights.Count == 0)
            {
                work.Errors.Add(FiErrorScope.Strategy, "proposal_without_targets", "REBALANCE proposal has no target weights.",
                    strategy, decisionId: call.DecisionId);
                return null;
            }

            return proposal;
        }
        catch (JsonException ex)
        {
            work.Errors.Add(FiErrorScope.Strategy, "proposal_unreadable", ex.Message, strategy, decisionId: call.DecisionId);
            return null;
        }
    }

    private async Task ValueAllAsync(CycleWork work, MarketSnapshotRefDto? marketSnapshot, CancellationToken ct)
    {
        foreach (var strategy in work.Ctx.Strategies)
        {
            var outcome = await RunCommandAsync(work, strategy, FiIds.Steps.Value, FiCommandType.ValuePortfolio,
                work.ValuationAt, marketSnapshot, cancellationToken: ct);
            if (!outcome.Succeeded)
            {
                _metrics.Add(FixedIncomeMetrics.IncompleteValuations, tagKey: "reason", tagValue: "deferred");
                work.Errors.Add(outcome.Scope, "valuation_deferred", outcome.Message, strategy, outcome.CommandId);
            }
            else if (outcome.Proposal?["valuation"] is JsonObject valuation &&
                     valuation["complete"] is JsonValue complete && complete.GetValueKind() == JsonValueKind.False)
            {
                var reasons = valuation["incompleteReasons"] is JsonArray array
                    ? string.Join("; ", array.Select(r => r?.ToString()))
                    : "incomplete";
                work.Errors.Add(FiErrorScope.FinancialState, "valuation_incomplete", reasons, strategy, outcome.CommandId,
                    severity: "warning");
            }
        }
    }

    private async Task<string?> CheckBootstrapAsync(CycleWork work, CancellationToken ct)
    {
        var invested = work.Ctx.Strategies.Where(s => s.Invested).Select(s => s.PortfolioId).ToList();
        if (invested.Count == 0)
        {
            return null;
        }

        // Impaired or blocked portfolios were isolated (spec 15.3) and are not part of the matched start.
        var restricted = await _db.FiPortfolios.AsNoTracking()
            .Where(p => invested.Contains(p.PortfolioId) && p.BlockedReason != null)
            .Select(p => p.PortfolioId)
            .ToListAsync(ct);
        invested = invested.Except(restricted, StringComparer.Ordinal).ToList();
        if (invested.Count == 0)
        {
            return null;
        }

        var bootstrapDone = await _db.FiCycles.AsNoTracking().AnyAsync(c =>
            c.RunId == work.Ctx.Run.RunId && c.Sequence < work.Cycle.Sequence && c.Status == DomainCycleStatus.Completed, ct);
        if (!bootstrapDone)
        {
            return null;
        }

        var orders = await _db.FiOrderIntents.AsNoTracking()
            .Where(o => invested.Contains(o.PortfolioId) && o.Bootstrap)
            .Select(o => new { o.PortfolioId, o.OrderId, o.Status })
            .ToListAsync(ct);
        foreach (var portfolioId in invested)
        {
            if (!orders.Any(o => o.PortfolioId == portfolioId))
            {
                return $"{portfolioId}: no bootstrap orders were submitted";
            }
        }

        if (orders.Any(o => o.Status == FiOrderStatus.Accepted))
        {
            return null; // fills pending; check again next cycle
        }

        var unfilled = orders.Where(o => o.Status != FiOrderStatus.Filled).ToList();
        if (unfilled.Count > 0)
        {
            return "bootstrap_not_filled: " + string.Join(", ", unfilled.Select(o => $"{o.PortfolioId}/{o.OrderId}={o.Status}"));
        }

        var orderIds = orders.Select(o => o.OrderId).ToList();
        var fills = await _db.FiFills.AsNoTracking()
            .Where(f => invested.Contains(f.PortfolioId) && orderIds.Contains(f.OrderId))
            .Select(f => new { f.PortfolioId, f.SecurityId, f.Face, f.ExecutionCleanPricePer100 })
            .ToListAsync(ct);
        string Signature(string portfolioId) => string.Join("|", fills.Where(f => f.PortfolioId == portfolioId)
            .Select(f => $"{f.SecurityId}:{f.Face:0.########}:{f.ExecutionCleanPricePer100:0.##########}")
            .OrderBy(x => x, StringComparer.Ordinal));
        var reference = Signature(invested[0]);
        var differing = invested.Skip(1).Where(p => Signature(p) != reference).ToList();
        return differing.Count == 0 ? null : "bootstrap_fills_differ: " + string.Join(", ", differing);
    }

    private async Task<bool> IsBootstrapCycleAsync(CycleWork work, CancellationToken ct)
    {
        if (!work.Ctx.Strategies.Any(s => s.Invested))
        {
            return false;
        }

        return !await _db.FiCycles.AsNoTracking().AnyAsync(c =>
            c.RunId == work.Ctx.Run.RunId && c.Sequence < work.Cycle.Sequence && c.Status == DomainCycleStatus.Completed, ct);
    }

    private async Task<bool> BootstrapAcceptedAsync(string portfolioId, string decisionId, string commandId, CancellationToken ct)
    {
        var orders = await _db.FiOrderIntents.AsNoTracking()
            .CountAsync(o => o.PortfolioId == portfolioId && o.DecisionId == decisionId && o.Bootstrap, ct);
        if (orders == 0)
        {
            return false;
        }

        var evaluation = await _db.FiPolicyEvaluations.AsNoTracking()
            .Where(p => p.PortfolioId == portfolioId && p.CommandId == commandId)
            .Select(p => (bool?)p.Passed)
            .FirstOrDefaultAsync(ct);
        return evaluation ?? true;
    }

    private async Task<FiCycleResult> CheckpointAsync(CycleWork work, string status, string? reason, CancellationToken ct)
    {
        var ctx = work.Ctx;
        var portfolios = new JsonArray();
        foreach (var strategy in ctx.Strategies)
        {
            var portfolio = await _db.FiPortfolios.AsNoTracking().FirstOrDefaultAsync(p => p.PortfolioId == strategy.PortfolioId, ct);
            portfolios.Add(new JsonObject
            {
                ["portfolioId"] = strategy.PortfolioId,
                ["strategyId"] = strategy.StrategyId,
                ["repetition"] = strategy.Repetition,
                ["version"] = portfolio?.CurrentVersion,
                ["stateHash"] = portfolio?.CurrentStateHash,
                ["blocked"] = portfolio?.BlockedReason is not null,
                ["restriction"] = FiPortfolioRestriction.KindOf(portfolio?.BlockedReason),
                ["blockedReason"] = portfolio?.BlockedReason,
            });
        }

        var checkpoint = new JsonObject
        {
            ["cycleId"] = work.Cycle.CycleId,
            ["sequence"] = work.Cycle.Sequence,
            ["sessionDate"] = work.Session.SessionDate,
            ["decisionAsOf"] = FiWire.FormatInstant(work.DecisionAsOf),
            ["valuationAt"] = FiWire.FormatInstant(work.ValuationAt),
            ["marketSnapshotId"] = work.Session.MarketSnapshotId,
            ["manifestHash"] = ctx.Run.ManifestHash,
            ["status"] = status,
            ["portfolios"] = portfolios,
        };

        var now = _clock.GetUtcNow();
        await UpdateCycleAsync(work.Cycle.Id, c =>
        {
            c.Status = status;
            c.SkipReason = Truncate(reason);
            c.CompletedAt = now;
            c.CheckpointJson = CanonicalJson.Serialize(checkpoint);
            c.ErrorsJson = work.Errors.ToJson();
        }, ct);

        await UpdateProgressAsync(ctx.Run.RunId, work.DecisionAsOf, now, ct);
        _metrics.Add(FixedIncomeMetrics.Cycles, tagKey: "status", tagValue: status);
        _logger.LogInformation("Cycle {CycleId} of run {RunId} {Status} ({Errors} error(s), {Warnings} warning(s))",
            work.Cycle.CycleId, ctx.Run.RunId, status, work.Errors.ErrorCount, work.Errors.WarningCount);

        return CycleResult(ctx.Run.RunId, work.Cycle.CycleId,
            status == DomainCycleStatus.Skipped ? FiCycleRunStatus.Skipped : FiCycleRunStatus.Completed, reason, work.Errors.ErrorCount);
    }

    private async Task<FiCycleResult> FailCycleAsync(CycleWork work, string reason, CancellationToken ct)
    {
        work.Errors.Add(FiErrorScope.Cycle, "cycle_failed", reason);
        await UpdateCycleAsync(work.Cycle.Id, c =>
        {
            c.Status = DomainCycleStatus.Failed;
            c.SkipReason = Truncate(reason);
            c.CompletedAt = _clock.GetUtcNow();
            c.ErrorsJson = work.Errors.ToJson();
        }, ct);
        _logger.LogError("Cycle {CycleId} of run {RunId} failed: {Reason}", work.Cycle.CycleId, work.Ctx.Run.RunId, reason);
        return CycleResult(work.Ctx.Run.RunId, work.Cycle.CycleId, FiCycleRunStatus.Failed, reason, work.Errors.ErrorCount);
    }

    private async Task<FiCycleResult> CancelCycleAsync(CycleWork work, CancellationToken ct)
    {
        const string reason = "Run cancelled by an operator; uncommitted work stopped, committed events remain authoritative.";
        foreach (var strategy in work.Ctx.Strategies)
        {
            var decisionId = work.DecisionId(strategy);
            if (!await _db.FiDecisions.AsNoTracking().AnyAsync(d => d.DecisionId == decisionId, ct))
            {
                await RecordSynthesizedAsync(work, strategy, FiDecisionOutcome.Cancelled, new[] { "run_cancelled" }, ct);
            }
        }

        await UpdateCycleAsync(work.Cycle.Id, c =>
        {
            c.Status = DomainCycleStatus.Cancelled;
            c.SkipReason = reason;
            c.CompletedAt = _clock.GetUtcNow();
            c.ErrorsJson = work.Errors.ToJson();
        }, ct);
        _logger.LogWarning("Cycle {CycleId} of run {RunId} stopped: run cancelled", work.Cycle.CycleId, work.Ctx.Run.RunId);
        return CycleResult(work.Ctx.Run.RunId, work.Cycle.CycleId, FiCycleRunStatus.Cancelled, reason, work.Errors.ErrorCount);
    }

    // ------------------------------------------------------------------ commands

    private sealed record CommandOutcome(CommandStatus Status, string CommandId, string Message, string Scope, JsonObject? Proposal = null)
    {
        public bool Succeeded => Status is CommandStatus.Committed or CommandStatus.AlreadyCommitted;
    }

    private enum CommandStatus
    {
        Committed,
        AlreadyCommitted,
        Rejected,
        Blocked,
        Failed,

        /// <summary>The engine rejected the command deterministically (4xx, 500, unreadable payload) after the configured retries.</summary>
        EngineError,
    }

    private async Task<CommandOutcome> RunCommandAsync(
        CycleWork work,
        StrategyRef strategy,
        string step,
        string commandType,
        DateTimeOffset advanceTo,
        MarketSnapshotRefDto? marketSnapshot,
        string? decisionId = null,
        string? action = null,
        IReadOnlyList<TargetWeightDto>? targets = null,
        string? capitalAmountUsd = null,
        CancellationToken cancellationToken = default)
    {
        var outcome = await RunCommandCoreAsync(work.Ctx, work.Cycle.CycleId, strategy, step, commandType, advanceTo, marketSnapshot,
            decisionId, action, targets, capitalAmountUsd, cancellationToken);
        if (outcome.Status == CommandStatus.EngineError)
        {
            await IsolateAsync(work, strategy, $"{commandType} {outcome.CommandId} failed: {outcome.Message}", outcome.CommandId,
                cancellationToken);
        }

        return outcome;
    }

    /// <summary>
    /// Failure isolation (spec 15.3): a deterministic failure of one portfolio's command affects only that
    /// portfolio. It is impaired for the rest of this cycle and persistently for discretionary commits
    /// (operator-visible reason, cleared by the unblock action); due events, cash flows and valuations
    /// continue, and every other strategy proceeds normally.
    /// </summary>
    private async Task IsolateAsync(CycleWork work, StrategyRef strategy, string reason, string? commandId, CancellationToken ct)
    {
        work.Impaired.Add(strategy.PortfolioId);
        await _commits.MarkImpairedAsync(strategy.PortfolioId, Truncate(reason, 900)!, commandId, ct);
        work.Errors.Add(FiErrorScope.FinancialState, "portfolio_impaired",
            "Discretionary commits are blocked until operator action: " + reason, strategy, commandId);
    }

    private async Task<CommandOutcome> RunCommandCoreAsync(
        RunContext ctx,
        string cycleId,
        StrategyRef strategy,
        string step,
        string commandType,
        DateTimeOffset advanceTo,
        MarketSnapshotRefDto? marketSnapshot,
        string? decisionId,
        string? action,
        IReadOnlyList<TargetWeightDto>? targets,
        string? capitalAmountUsd,
        CancellationToken ct)
    {
        var commandId = FiIds.Command(ctx.Run.RunId, cycleId, strategy.PortfolioId, step);
        using var commandScope = _logger.BeginScope(new Dictionary<string, object?>
        {
            ["StrategyId"] = strategy.StrategyId,
            ["PortfolioId"] = strategy.PortfolioId,
            ["CommandId"] = commandId,
            ["DecisionId"] = decisionId,
        });

        // A restarted run or retried activity re-issues the same command id: the committed
        // result is authoritative and no recomputation (and no second effect) happens.
        var existing = await _commits.GetCommandAsync(commandId, ct);
        if (existing is not null)
        {
            _metrics.Add(FixedIncomeMetrics.DuplicateCommands, tagKey: "kind", tagValue: "command");
            _logger.LogDebug("Command {CommandId} already recorded ({Status}); returning the committed result", commandId, existing.Status);
            return existing.Status == FiCommandStatus.Committed
                ? new CommandOutcome(CommandStatus.AlreadyCommitted, commandId, "Already committed.", FiErrorScope.FinancialState)
                : new CommandOutcome(CommandStatus.Blocked, commandId,
                    $"Command previously blocked the portfolio: {existing.Reason}", FiErrorScope.FinancialState);
        }

        var attempts = Math.Max(0, _options.StaleRecomputeAttempts) + 1;
        for (var attempt = 0; attempt < attempts; attempt++)
        {
            var state = await _commits.GetCurrentStateAsync(strategy.PortfolioId, ct);
            if (state is null)
            {
                return new CommandOutcome(CommandStatus.Failed, commandId, $"Portfolio '{strategy.PortfolioId}' does not exist.",
                    FiErrorScope.FinancialState);
            }

            if (FiPortfolioRestriction.Forbids(state.BlockedReason, commandType))
            {
                return new CommandOutcome(CommandStatus.Blocked, commandId, "Portfolio blocked: " + state.BlockedReason,
                    FiErrorScope.FinancialState);
            }

            var request = new TransitionRequestDto
            {
                CommandId = commandId,
                CommandType = commandType,
                PortfolioState = ParseElement(state.StateJson),
                PortfolioStateHash = state.StateHash,
                AdvanceTo = FiWire.FormatInstant(advanceTo),
                MarketSnapshot = marketSnapshot,
                RiskPolicy = ctx.Policy.ToWire(ctx.Run.RiskPolicyId),
                ExecutionModel = ctx.ExecutionModel.ToWire(ctx.Run.ExecutionModelId),
                InstrumentUniverseVersion = ctx.Spec.InstrumentUniverseVersion,
                DecisionId = decisionId,
                Action = action,
                TargetWeights = targets?.ToList() ?? new List<TargetWeightDto>(),
                CapitalAmountUsd = capitalAmountUsd,
            };

            // Bound the proposal to exactly this request: recomputed on every (stale) attempt.
            var requestHash = FiRequestBody.Hash(request);

            RawContractJson proposal;
            try
            {
                proposal = await ProposeWithRetryAsync(request, ct);
            }
            catch (ResearchEngineException ex)
            {
                // Deterministic for this command (transient failures surface as FiTransientDependencyException).
                var code = ex.ProblemCode is null ? string.Empty : $" [{ex.ProblemCode}]";
                var scope = commandType == FiCommandType.SubmitDecision && ex.StatusCode is >= 400 and < 500
                    ? FiErrorScope.Strategy
                    : FiErrorScope.FinancialState;
                return new CommandOutcome(CommandStatus.EngineError, commandId,
                    $"Engine rejected {commandType} ({ex.StatusCode?.ToString() ?? "n/a"}){code}: {ex.Message} {Truncate(ex.Body, 500)}".Trim(),
                    scope);
            }

            var result = await _commits.CommitAsync(proposal, new TransitionCommitContext
            {
                ExpectedCommandId = commandId,
                ExpectedRequestHash = requestHash,
                ExpectedDecisionId = decisionId,
                Actor = Actor,
            }, ct);

            switch (result.Status)
            {
                case TransitionCommitStatus.Committed:
                    CountCommitted(proposal.Node);
                    return new CommandOutcome(CommandStatus.Committed, commandId, result.Message ?? "Committed.",
                        FiErrorScope.FinancialState, proposal.Node);
                case TransitionCommitStatus.AlreadyCommitted:
                    _metrics.Add(FixedIncomeMetrics.DuplicateCommands, tagKey: "kind", tagValue: "commit");
                    return new CommandOutcome(CommandStatus.AlreadyCommitted, commandId, "Already committed.", FiErrorScope.FinancialState);
                case TransitionCommitStatus.Stale:
                    // Discard and recompute against the new state; never merge two transitions.
                    _metrics.Add(FixedIncomeMetrics.ConcurrencyConflicts);
                    _logger.LogWarning("Stale proposal for {CommandId} (attempt {Attempt}); recomputing against the current state",
                        commandId, attempt + 1);
                    continue;
                case TransitionCommitStatus.PortfolioBlocked:
                    return new CommandOutcome(CommandStatus.Blocked, commandId, result.Message ?? "Portfolio blocked.",
                        FiErrorScope.FinancialState);
                case TransitionCommitStatus.Conflict:
                    _metrics.Add(FixedIncomeMetrics.DuplicateCommands, tagKey: "kind", tagValue: "conflict");
                    return new CommandOutcome(CommandStatus.Rejected, commandId, result.Message ?? "Idempotency conflict.",
                        FiErrorScope.Cycle);
                default:
                    var issues = string.Join("; ", result.Issues.Select(i => $"{i.Code}: {i.Message}"));
                    return new CommandOutcome(CommandStatus.Rejected, commandId,
                        $"{result.Status}: {result.Message} {issues}".Trim(), FiErrorScope.FinancialState);
            }
        }

        return new CommandOutcome(CommandStatus.Failed, commandId,
            "The portfolio kept changing concurrently; the recomputed proposal was stale again.", FiErrorScope.FinancialState);
    }

    /// <summary>
    /// Transient failures (unreachable, timeout, 502/503/504, 429) are retried, then pause the run as
    /// resumable. An unexpected engine error (500) is retried the same number of times and then
    /// rethrown as non-transient so the caller isolates the command instead of re-failing it forever.
    /// Deterministic rejections (4xx) are rethrown immediately.
    /// </summary>
    private async Task<RawContractJson> ProposeWithRetryAsync(TransitionRequestDto request, CancellationToken ct)
    {
        var retries = Math.Max(0, _options.TransientRetryAttempts);
        for (var attempt = 0; ; attempt++)
        {
            try
            {
                return await _engine.ProposeTransitionAsync(request, ct);
            }
            catch (ResearchEngineException ex) when (ResearchEngineException.IsTransient(ex) || ex is ResearchEngineServerException)
            {
                if (attempt >= retries)
                {
                    if (ex is ResearchEngineServerException)
                    {
                        _logger.LogError("Engine error for {CommandId} persisted after {Attempts} attempt(s); isolating the command",
                            request.CommandId, attempt + 1);
                        throw;
                    }

                    throw new FiTransientDependencyException(
                        $"Research engine unavailable for {request.CommandType} {request.CommandId} after {attempt + 1} attempt(s): {ex.Message}", ex);
                }

                var delay = ex is ResearchEngineRateLimitedException { RetryAfter: { } retryAfter }
                    ? retryAfter
                    : TimeSpan.FromMilliseconds(Math.Max(0, _options.TransientRetryDelayMs) * Math.Pow(2, attempt));
                _logger.LogWarning("Engine failure for {CommandId} ({Status}); retrying in {Delay}", request.CommandId,
                    ex.StatusCode?.ToString() ?? "transport", delay);
                if (delay > TimeSpan.Zero)
                {
                    await Task.Delay(delay < TimeSpan.FromSeconds(30) ? delay : TimeSpan.FromSeconds(30), _clock, ct);
                }
            }
        }
    }

    private void CountCommitted(JsonObject proposal)
    {
        if (proposal["ordersCreated"] is JsonArray created)
        {
            _metrics.Add(FixedIncomeMetrics.OrdersPending, created.Count);
        }

        if (proposal["orderStatusChanges"] is JsonArray changes)
        {
            var expired = changes.Count(c => c?["status"] is JsonValue v && v.TryGetValue<string>(out var s) && s == FiOrderStatus.Expired);
            _metrics.Add(FixedIncomeMetrics.OrdersExpired, expired);
        }

        if (proposal["valuation"] is JsonObject valuation &&
            valuation["complete"] is JsonValue complete && complete.GetValueKind() == JsonValueKind.False)
        {
            _metrics.Add(FixedIncomeMetrics.IncompleteValuations, tagKey: "reason", tagValue: "incomplete");
        }
    }

    private void CountBudget(JsonObject result)
    {
        var outcome = result["outcome"] is JsonValue o && o.TryGetValue<string>(out var s) ? s : null;
        var exhausted = result["usage"]?["budgetExhausted"] is JsonValue b && b.TryGetValue<string>(out var x) && !string.IsNullOrEmpty(x);
        if (outcome == FiDecisionOutcome.FailedBudget || exhausted)
        {
            _metrics.Add(FixedIncomeMetrics.BudgetExhausted);
        }
    }

    // ------------------------------------------------------------------ initialization

    private async Task EnsurePortfoliosAsync(RunContext ctx, CancellationToken ct)
    {
        foreach (var strategy in ctx.Strategies)
        {
            var exists = await _db.FiPortfolios.AsNoTracking().AnyAsync(p => p.PortfolioId == strategy.PortfolioId, ct);
            if (!exists)
            {
                var genesisAsOf = ctx.Run.RunType == FiRunType.Replay
                    ? new DateTimeOffset(ctx.Spec.StartDate.ToDateTime(TimeOnly.MinValue), TimeSpan.Zero)
                    : ctx.Run.CreatedAt;
                await _commits.CreatePortfolioAsync(new CreateFiPortfolioRequest
                {
                    PortfolioId = strategy.PortfolioId,
                    RunId = ctx.Run.RunId,
                    StrategyId = strategy.StrategyId,
                    Repetition = strategy.Repetition,
                    RiskPolicyId = ctx.Run.RiskPolicyId,
                    DataMode = ctx.Run.DataMode,
                    AsOf = new DateTimeOffset(genesisAsOf.UtcTicks - genesisAsOf.UtcTicks % TimeSpan.TicksPerSecond, TimeSpan.Zero),
                }, ct);
            }
        }
    }

    /// <summary>CAPITAL_FLOW for initial capital (same starting condition for every competitor). Returns an error or null.</summary>
    private async Task<string?> EnsureInitialCapitalAsync(RunContext ctx, DateOnly firstSession, CancellationToken ct)
    {
        var amount = FiWire.FormatDecimal(ctx.Policy.InitialCapitalUsd);
        foreach (var strategy in ctx.Strategies)
        {
            var genesis = await _db.FiPortfolioStateVersions.AsNoTracking()
                .Where(v => v.PortfolioId == strategy.PortfolioId && v.Version == 0)
                .Select(v => (DateTimeOffset?)v.AsOf)
                .FirstOrDefaultAsync(ct);
            var advanceTo = FiMarketClock.CapitalFlowAt(firstSession);
            if (genesis is { } genesisAsOf && genesisAsOf > advanceTo)
            {
                advanceTo = genesisAsOf; // the simulated clock never moves backward
            }

            var outcome = await RunCommandCoreAsync(ctx, FiIds.InitCycleId, strategy, FiIds.Steps.Capital, FiCommandType.CapitalFlow,
                advanceTo, null, null, null, null, amount, ct);
            if (!outcome.Succeeded)
            {
                return $"{strategy.StrategyId}: initial capital flow failed ({outcome.Message})";
            }
        }

        return null;
    }

    private sealed record SessionFetch(IReadOnlyList<MarketSessionDto> Sessions, string? Error);

    private async Task<SessionFetch> FetchSessionsAsync(RunContext ctx, DateOnly start, DateOnly end, CancellationToken ct)
    {
        MarketSessionsDto response;
        try
        {
            response = await _engine.GetMarketSessionsAsync(start, end, ct);
        }
        catch (Exception ex) when (ex is ResearchEngineUnavailableException or ResearchEngineRateLimitedException)
        {
            throw new FiTransientDependencyException($"Market sessions unavailable: {ex.Message}", ex);
        }
        catch (ResearchEngineException ex)
        {
            return new SessionFetch(Array.Empty<MarketSessionDto>(), $"market sessions request rejected: {ex.Message}");
        }

        if (!string.IsNullOrEmpty(response.DataMode) && response.DataMode != ctx.Run.DataMode)
        {
            return new SessionFetch(Array.Empty<MarketSessionDto>(),
                $"engine data mode '{response.DataMode}' differs from the run data mode '{ctx.Run.DataMode}'");
        }

        if (!string.IsNullOrEmpty(response.UniverseVersion) && response.UniverseVersion != ctx.Spec.InstrumentUniverseVersion &&
            response.UniverseId != ctx.Spec.InstrumentUniverseVersion)
        {
            return new SessionFetch(Array.Empty<MarketSessionDto>(),
                $"engine universe '{response.UniverseVersion}' differs from the experiment universe '{ctx.Spec.InstrumentUniverseVersion}'");
        }

        var sessions = new List<MarketSessionDto>();
        foreach (var session in response.Sessions)
        {
            DateOnly date;
            try
            {
                date = FiWire.ParseDate(session.SessionDate, "sessionDate");
            }
            catch (FormatException ex)
            {
                return new SessionFetch(Array.Empty<MarketSessionDto>(), ex.Message);
            }

            if (date < start || date > end)
            {
                continue;
            }

            sessions.Add(Normalize(session, date));
        }

        var ordered = sessions.OrderBy(s => s.SessionDate, StringComparer.Ordinal).ToList();
        if (ordered.Select(s => s.SessionDate).Distinct(StringComparer.Ordinal).Count() != ordered.Count)
        {
            return new SessionFetch(Array.Empty<MarketSessionDto>(), "duplicate session dates in the engine response");
        }

        return new SessionFetch(ordered, null);
    }

    /// <summary>Resolves missing schedule instants (19:00 / 20:00 America/New_York) and canonical formats.</summary>
    private static MarketSessionDto Normalize(MarketSessionDto session, DateOnly date)
    {
        static string? Instant(string? value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return null;
            }

            try
            {
                return FiWire.FormatInstant(FiWire.ParseInstant(value, "instant"));
            }
            catch (FormatException)
            {
                return null;
            }
        }

        return session with
        {
            SessionDate = FiWire.FormatDate(date),
            ObservedAt = Instant(session.ObservedAt),
            AvailableAt = Instant(session.AvailableAt),
            DecisionAsOf = Instant(session.DecisionAsOf) ?? FiWire.FormatInstant(FiMarketClock.DecisionAt(date)),
            ExecutionObservationAt = Instant(session.ExecutionObservationAt),
            ValuationAt = Instant(session.ValuationAt) ?? FiWire.FormatInstant(FiMarketClock.ValuationAt(date)),
        };
    }

    /// <summary>Freezes sessions into Cycle rows. Returns an error when the frozen manifest would change.</summary>
    private async Task<string?> FreezeCyclesAsync(RunContext ctx, IReadOnlyList<MarketSessionDto> sessions, bool append, CancellationToken ct)
    {
        var runId = ctx.Run.RunId;
        var existing = await _db.FiCycles.AsNoTracking().Where(c => c.RunId == runId).ToListAsync(ct);
        var byId = existing.ToDictionary(c => c.CycleId, StringComparer.Ordinal);
        var nextSequence = existing.Count == 0 ? 1 : existing.Max(c => c.Sequence) + 1;
        var lastDate = existing.Count == 0 ? (DateOnly?)null : existing.Max(c => c.SessionDate);
        var added = false;

        for (var i = 0; i < sessions.Count; i++)
        {
            var session = sessions[i];
            var date = FiWire.ParseDate(session.SessionDate, "sessionDate");
            var cycleId = FiIds.Cycle(date);
            var inputs = CanonicalJson.Serialize(FiWire.ToNode(session));
            if (byId.TryGetValue(cycleId, out var row))
            {
                if (!IsCheckpointed(row.Status) && row.InputsJson != inputs)
                {
                    _logger.LogWarning("Session inputs for {CycleId} changed since the run was planned; keeping the frozen inputs", cycleId);
                }

                continue;
            }

            int sequence;
            if (append)
            {
                if (lastDate is { } last && date <= last)
                {
                    return $"session {session.SessionDate} precedes the latest frozen cycle; forward cycles are append-only";
                }

                sequence = nextSequence++;
            }
            else
            {
                sequence = i + 1;
                if (existing.Any(c => c.Sequence == sequence))
                {
                    return $"session list changed since the run started (sequence {sequence} is already {existing.First(c => c.Sequence == sequence).CycleId})";
                }
            }

            _db.FiCycles.Add(new Cycle
            {
                RunId = runId,
                CycleId = cycleId,
                Sequence = sequence,
                SessionDate = date,
                DecisionAsOf = FiWire.ParseInstant(session.DecisionAsOf, "decisionAsOf"),
                Status = DomainCycleStatus.Pending,
                MarketSnapshotId = session.MarketSnapshotId,
                MarketSnapshotHash = session.MarketSnapshotHash,
                CurveSnapshotId = session.CurveSnapshotId,
                InputsJson = inputs,
            });
            lastDate = date;
            added = true;
        }

        if (added)
        {
            await _db.SaveChangesAsync(ct);
            DetachAll<Cycle>();
        }

        return null;
    }

    private async Task RecordEngineVersionAsync(RunContext ctx, CancellationToken ct)
    {
        if (!string.IsNullOrEmpty(ctx.Run.EngineVersion))
        {
            return;
        }

        try
        {
            var capabilities = await _engine.GetCapabilitiesAsync(ct);
            if (!string.IsNullOrEmpty(capabilities.EngineVersion))
            {
                await UpdateRunAsync(ctx.Run.RunId, run => run.EngineVersion ??= Truncate(capabilities.EngineVersion, 64), ct);
            }
        }
        catch (ResearchEngineException ex)
        {
            _logger.LogWarning("Could not read research-engine capabilities for run {RunId}: {Message}", ctx.Run.RunId, ex.Message);
        }
    }

    // ------------------------------------------------------------------ decisions

    private DecisionRequestDto BuildDecisionRequest(CycleWork work, StrategyRef strategy, string decisionId,
        PortfolioStateSnapshot state, MarketSnapshotRefDto marketSnapshot)
    {
        var ctx = work.Ctx;
        return new DecisionRequestDto
        {
            ExperimentId = ctx.Run.ExperimentId,
            RunId = ctx.Run.RunId,
            CycleId = work.Cycle.CycleId,
            DecisionId = decisionId,
            StrategyId = strategy.StrategyId,
            Repetition = strategy.Repetition,
            DecisionAsOf = FiWire.FormatInstant(work.DecisionAsOf),
            MarketSessionDate = work.Session.SessionDate,
            AvailabilityPolicy = ctx.Spec.AvailabilityPolicy,
            DataMode = ctx.Run.DataMode,
            PortfolioSnapshot = new SnapshotRefDto
            {
                Id = FiIds.PortfolioSnapshot(strategy.PortfolioId, state.Version),
                ContentHash = state.StateHash,
                Version = state.Version,
            },
            MarketSnapshot = new MarketSnapshotPointerDto
            {
                Id = marketSnapshot.MarketSnapshotId,
                ContentHash = marketSnapshot.ContentHash,
                CurveSnapshotId = marketSnapshot.CurveSnapshotId ?? string.Empty,
            },
            InstrumentUniverseVersion = ctx.Spec.InstrumentUniverseVersion,
            EvidenceSnapshotId = ctx.Spec.EvidenceSnapshotId,
            IndexBuildId = ctx.Spec.IndexBuildId,
            StrategyConfigId = strategy.StrategyConfigId,
            RiskPolicyId = ctx.Run.RiskPolicyId,
            ResponseMode = ctx.Run.ResponseMode,
            Budget = ctx.Spec.Budget ?? new DecisionBudgetDto(),
            PortfolioState = ParseElement(state.StateJson),
            SessionContext = new DecisionSessionContextDto
            {
                PreviousSessionDate = work.PreviousSessionDate is { } previous ? FiWire.FormatDate(previous) : null,
            },
        };
    }

    private static (string Outcome, string Reason, string Scope) ClassifyFailure(Exception? failure) => failure switch
    {
        ResearchEngineRateLimitedException ex => (FiDecisionOutcome.FailedDependency, "rate_limited: " + ex.Message, FiErrorScope.Source),
        ResearchEngineValidationException ex => (FiDecisionOutcome.FailedDependency,
            $"engine_rejected_request ({ex.StatusCode}): {Truncate(ex.Body, 300) ?? ex.Message}", FiErrorScope.Strategy),
        ResearchEngineUnavailableException ex => (FiDecisionOutcome.FailedDependency, "engine_unavailable: " + ex.Message, FiErrorScope.Source),
        ResearchEngineServerException ex => (FiDecisionOutcome.FailedDependency,
            $"engine_error ({ex.StatusCode}){(ex.ProblemCode is null ? "" : $" [{ex.ProblemCode}]")}: {ex.Message}", FiErrorScope.Strategy),
        ResearchEngineException ex => (FiDecisionOutcome.FailedDependency, $"engine_error ({ex.StatusCode}): {ex.Message}", FiErrorScope.Source),
        null => (FiDecisionOutcome.FailedDependency, "no_result", FiErrorScope.Strategy),
        _ => (FiDecisionOutcome.FailedDependency, $"executor_error: {failure.GetType().Name}: {failure.Message}", FiErrorScope.Strategy),
    };

    private async Task RecordSynthesizedAsync(CycleWork work, StrategyRef strategy, string outcome, IReadOnlyList<string> reasons,
        CancellationToken ct, string? action = null, string? proposalJson = null)
    {
        var decisionId = work.DecisionId(strategy);
        var result = await _audit.RecordSynthesizedOutcomeAsync(new SynthesizedDecisionOutcome
        {
            RunId = work.Ctx.Run.RunId,
            CycleId = work.Cycle.CycleId,
            DecisionId = decisionId,
            StrategyId = strategy.StrategyId,
            Repetition = strategy.Repetition,
            StrategyKind = strategy.StrategyKind,
            PortfolioId = strategy.PortfolioId,
            Outcome = outcome,
            Reasons = reasons,
            CompletedAt = work.DecisionAsOf,
            EngineVersion = work.Ctx.Run.EngineVersion,
            Action = action,
            ProposalJson = proposalJson,
        }, ct);

        if (result.Status is DecisionAuditStatus.Recorded)
        {
            _metrics.Add(FixedIncomeMetrics.DecisionOutcomes, tagKey: "outcome", tagValue: outcome);
        }
        else if (result.Status is DecisionAuditStatus.Conflict or DecisionAuditStatus.Rejected)
        {
            _logger.LogWarning("Decision {DecisionId} kept its earlier outcome ({Status}): {Issues}",
                decisionId, result.Status, string.Join("; ", result.Issues));
        }
    }

    // ------------------------------------------------------------------ state helpers

    private static string? SharedInputProblem(MarketSessionDto session, DateTimeOffset decisionAsOf)
    {
        if (session.Gap)
        {
            return "session_gap: " + (session.GapReason ?? "no usable observation");
        }

        if (!string.Equals(session.CurveStatus, "READY", StringComparison.OrdinalIgnoreCase))
        {
            return $"curve_not_ready: status {session.CurveStatus ?? "missing"}";
        }

        if (string.IsNullOrEmpty(session.MarketSnapshotId) || !FiWire.IsContentHash(session.MarketSnapshotHash) ||
            string.IsNullOrEmpty(session.CurveSnapshotId))
        {
            return "market_snapshot_missing";
        }

        if (string.IsNullOrEmpty(session.AvailableAt))
        {
            return "curve_availability_unknown";
        }

        var available = FiWire.ParseInstant(session.AvailableAt, "availableAt");
        return available > decisionAsOf
            ? $"curve_not_available_by_decision_time: available {session.AvailableAt} > decision {FiWire.FormatInstant(decisionAsOf)}"
            : null;
    }

    private static MarketSnapshotRefDto MarketSnapshotRef(RunContext ctx, MarketSessionDto session) => new()
    {
        MarketSnapshotId = session.MarketSnapshotId!,
        ContentHash = session.MarketSnapshotHash!,
        CurveSnapshotId = session.CurveSnapshotId,
        SessionDate = session.SessionDate,
        DataMode = ctx.Run.DataMode,
    };

    private static MarketSessionDto ReadInputs(Cycle cycle)
    {
        if (!string.IsNullOrEmpty(cycle.InputsJson))
        {
            var parsed = JsonSerializer.Deserialize<MarketSessionDto>(cycle.InputsJson, FiContract.WireOptions);
            if (parsed is not null)
            {
                return parsed;
            }
        }

        // Cycle frozen without inputs (not produced by this executor): treat its shared inputs as unknown.
        return new MarketSessionDto
        {
            SessionDate = FiWire.FormatDate(cycle.SessionDate),
            MarketSnapshotId = cycle.MarketSnapshotId,
            MarketSnapshotHash = cycle.MarketSnapshotHash,
            CurveSnapshotId = cycle.CurveSnapshotId,
            DecisionAsOf = FiWire.FormatInstant(cycle.DecisionAsOf),
            ValuationAt = FiWire.FormatInstant(FiMarketClock.ValuationAt(cycle.SessionDate)),
            Gap = true,
            GapReason = "cycle inputs were not frozen",
        };
    }

    private async Task<bool> IsCancelledAsync(string runId, CancellationToken ct) =>
        await _db.FiExperimentRuns.AsNoTracking().Where(r => r.RunId == runId).Select(r => r.JobState)
            .FirstOrDefaultAsync(ct) == FiJobState.Cancelled;

    private async Task UpdateCycleAsync(long id, Action<Cycle> mutate, CancellationToken ct)
    {
        var cycle = await _db.FiCycles.FirstAsync(c => c.Id == id, ct);
        mutate(cycle);
        await _db.SaveChangesAsync(ct);
        _db.Entry(cycle).State = EntityState.Detached;
    }

    private async Task UpdateRunAsync(string runId, Action<ExperimentRun> mutate, CancellationToken ct)
    {
        for (var attempt = 0; attempt < 3; attempt++)
        {
            var run = await _db.FiExperimentRuns.FirstOrDefaultAsync(r => r.RunId == runId, ct);
            if (run is null)
            {
                return;
            }

            mutate(run);
            run.ConcurrencyStamp = Guid.NewGuid();
            try
            {
                await _db.SaveChangesAsync(ct);
                _db.Entry(run).State = EntityState.Detached;
                return;
            }
            catch (DbUpdateConcurrencyException)
            {
                // A job-state change (e.g. cancellation) raced; reload and re-apply progress only.
                _db.Entry(run).State = EntityState.Detached;
            }
        }
    }

    private Task UpdateProgressAsync(string runId, DateTimeOffset decisionAsOf, DateTimeOffset now, CancellationToken ct) =>
        UpdateRunAsync(runId, run =>
        {
            run.CompletedCycles = _db.FiCycles.AsNoTracking().Count(c => c.RunId == runId &&
                (c.Status == DomainCycleStatus.Completed || c.Status == DomainCycleStatus.Skipped));
            if (run.SimulatedClock is null || decisionAsOf > run.SimulatedClock)
            {
                run.SimulatedClock = decisionAsOf; // simulated time, separate from operational time
            }

            run.LastCheckpointAt = now;
        }, ct);

    private async Task AppendRunErrorAsync(string runId, string scope, string code, string message, CancellationToken ct)
    {
        _metrics.Add(FixedIncomeMetrics.Errors, tagKey: "scope", tagValue: scope);
        _logger.LogError("Fixed income run {RunId} error [{Scope}/{Code}]: {Message}", runId, scope, code, message);
        await UpdateRunAsync(runId, run =>
        {
            var errors = FiWire.TryParseNode(run.ErrorsJson) as JsonArray ?? new JsonArray();
            errors.Add(new JsonObject
            {
                ["scope"] = scope,
                ["code"] = code,
                ["message"] = Truncate(message, 1000),
                ["at"] = FiWire.FormatInstant(_clock.GetUtcNow()),
            });
            while (errors.Count > 100)
            {
                errors.RemoveAt(0);
            }

            run.ErrorsJson = errors.ToJsonString();
        }, ct);
    }

    private void DetachAll<T>() where T : class
    {
        foreach (var entry in _db.ChangeTracker.Entries<T>().ToList())
        {
            entry.State = EntityState.Detached;
        }
    }

    private bool Terminal(ExperimentRun run, out FiRunPlan plan)
    {
        plan = run.JobState switch
        {
            FiJobState.Cancelled => Plan(run.RunId, FiPlanStatus.Cancelled, run.RunType, reason: run.StatusReason ?? "Run cancelled."),
            FiJobState.Failed => Plan(run.RunId, FiPlanStatus.Failed, run.RunType, reason: run.StatusReason ?? "Run already failed."),
            FiJobState.Completed => Plan(run.RunId, FiPlanStatus.NothingToDo, run.RunType, reason: "Run already completed.",
                windowComplete: true),
            _ => null!,
        };
        return plan is not null;
    }

    private static bool IsCheckpointed(string status) =>
        status is DomainCycleStatus.Completed or DomainCycleStatus.Skipped;

    private static FiRunPlan Plan(string runId, FiPlanStatus status, string runType = FiRunType.Replay, string? reason = null,
        bool windowComplete = false) => new()
        {
            RunId = runId,
            Status = status,
            RunType = runType,
            Reason = reason,
            WindowComplete = windowComplete,
        };

    private static FiCycleResult CycleResult(string runId, string cycleId, FiCycleRunStatus status, string? reason, int errors = 0) => new()
    {
        RunId = runId,
        CycleId = cycleId,
        Status = status,
        Reason = reason,
        ErrorCount = errors,
    };

    private static JsonElement ParseElement(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private static string? Truncate(string? value, int max = 1900) =>
        value is null || value.Length <= max ? value : value[..max];

    private IDisposable? RunScope(RunContext ctx) => _logger.BeginScope(new Dictionary<string, object?>
    {
        ["ExperimentId"] = ctx.Run.ExperimentId,
        ["ExperimentVersion"] = ctx.Run.ExperimentVersion,
        ["RunId"] = ctx.Run.RunId,
    });

    // ------------------------------------------------------------------ context

    private sealed record StrategyRef(
        string StrategyId,
        string StrategyKind,
        string StrategyConfigId,
        int Repetition,
        string PortfolioId,
        bool Invested);

    private sealed record RunContext(
        ExperimentRun Run,
        CreateExperimentDefinitionRequest Spec,
        IReadOnlyList<StrategyRef> Strategies,
        RiskPolicyOptions Policy,
        ExecutionModelOptions ExecutionModel);

    private async Task<RunContext?> LoadAsync(string runId, CancellationToken ct)
    {
        var run = await _db.FiExperimentRuns.AsNoTracking()
            .Include(r => r.ExperimentDefinition)
            .FirstOrDefaultAsync(r => r.RunId == runId, ct);
        if (run?.ExperimentDefinition is null)
        {
            return null;
        }

        CreateExperimentDefinitionRequest spec;
        try
        {
            spec = JsonSerializer.Deserialize<CreateExperimentDefinitionRequest>(run.ExperimentDefinition.DefinitionJson, FiContract.WireOptions)
                   ?? throw new JsonException("empty definition");
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Experiment definition of run {RunId} cannot be read", runId);
            return null;
        }

        var policy = _policies.FindRiskPolicy(run.RiskPolicyId);
        var executionModel = _policies.FindExecutionModel(run.ExecutionModelId);
        if (policy is null || executionModel is null)
        {
            _logger.LogError("Run {RunId} references unconfigured policy {PolicyId} / execution model {ExecutionModelId}",
                runId, run.RiskPolicyId, run.ExecutionModelId);
            return null;
        }

        var strategies = await _db.FiStrategyInstances.AsNoTracking()
            .Where(s => s.RunId == runId)
            .OrderBy(s => s.Repetition).ThenBy(s => s.Id)
            .ToListAsync(ct);

        return new RunContext(run, spec, strategies.Select(s => new StrategyRef(
            s.StrategyId, s.StrategyKind, s.StrategyConfigId, s.Repetition, s.PortfolioId,
            Invested: s.StrategyKind != FiStrategyKind.CashReference && s.StrategyId != "cash")).ToList(), policy, executionModel);
    }

    private sealed class CycleWork
    {
        public CycleWork(RunContext ctx, Cycle cycle, MarketSessionDto session)
        {
            Ctx = ctx;
            Cycle = cycle;
            Session = session;
            DecisionAsOf = FiWire.ParseInstant(session.DecisionAsOf ?? FiWire.FormatInstant(cycle.DecisionAsOf), "decisionAsOf");
            ValuationAt = session.ValuationAt is { } v
                ? FiWire.ParseInstant(v, "valuationAt")
                : FiMarketClock.ValuationAt(cycle.SessionDate);
            Errors = new ErrorLog(ctx.Run.RunId, cycle.CycleId);
        }

        public RunContext Ctx { get; }
        public Cycle Cycle { get; }
        public MarketSessionDto Session { get; }
        public DateTimeOffset DecisionAsOf { get; }
        public DateTimeOffset ValuationAt { get; }
        public ErrorLog Errors { get; }

        /// <summary>Session of the run's previous frozen cycle (null for the first cycle).</summary>
        public DateOnly? PreviousSessionDate { get; init; }

        /// <summary>Portfolios whose due events could not be processed this cycle (no new decision).</summary>
        public HashSet<string> Impaired { get; } = new(StringComparer.Ordinal);

        public string DecisionId(StrategyRef strategy) =>
            FiIds.Decision(Ctx.Run.RunId, Cycle.CycleId, strategy.StrategyId, strategy.Repetition);
    }

    private sealed class DecisionCall
    {
        public DecisionCall(StrategyRef strategy, string decisionId, DecisionRequestDto? request)
        {
            Strategy = strategy;
            DecisionId = decisionId;
            Request = request;
        }

        public StrategyRef Strategy { get; }
        public string DecisionId { get; }
        public DecisionRequestDto? Request { get; }

        /// <summary>Canonical hash of the request body sent (the StrategyResult must echo it).</summary>
        public string? RequestHash { get; init; }

        public Decision? Stored { get; init; }
        public RawContractJson? Result { get; set; }
        public Exception? Failure { get; set; }
    }

    /// <summary>Classified cycle errors (spec 18.3), logged with their ids and counted.</summary>
    private sealed class ErrorLog
    {
        private readonly List<JsonObject> _items = new();
        private readonly string _runId;
        private readonly string _cycleId;

        public ErrorLog(string runId, string cycleId)
        {
            _runId = runId;
            _cycleId = cycleId;
        }

        public FixedIncomeMetrics? Metrics { get; set; }
        public ILogger? Logger { get; set; }

        public int ErrorCount => _items.Count(i => (string?)i["severity"] == "error");
        public int WarningCount => _items.Count(i => (string?)i["severity"] == "warning");

        public void Add(string scope, string code, string message, StrategyRef? strategy = null, string? commandId = null,
            string? decisionId = null, string severity = "error")
        {
            _items.Add(new JsonObject
            {
                ["scope"] = scope,
                ["severity"] = severity,
                ["code"] = code,
                ["message"] = message.Length > 1000 ? message[..1000] : message,
                ["strategyId"] = strategy?.StrategyId,
                ["portfolioId"] = strategy?.PortfolioId,
                ["commandId"] = commandId,
                ["decisionId"] = decisionId,
            });
            Metrics?.Add(FixedIncomeMetrics.Errors, tagKey: "scope", tagValue: scope);
            if (severity == "error")
            {
                Logger?.LogWarning(
                    "Run {RunId} cycle {CycleId} [{Scope}/{Code}] strategy {StrategyId} command {CommandId} decision {DecisionId}: {Message}",
                    _runId, _cycleId, scope, code, strategy?.StrategyId, commandId, decisionId, message);
            }
            else
            {
                Logger?.LogInformation("Run {RunId} cycle {CycleId} [{Scope}/{Code}] {StrategyId}: {Message}",
                    _runId, _cycleId, scope, code, strategy?.StrategyId, message);
            }
        }

        public string? ToJson() => _items.Count == 0 ? null : new JsonArray(_items.Select(i => (JsonNode)i.DeepClone()).ToArray()).ToJsonString();
    }
}
