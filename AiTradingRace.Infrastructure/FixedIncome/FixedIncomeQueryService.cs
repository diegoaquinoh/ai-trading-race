using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Models;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Read-only dashboard queries over the fi schema. Aggregations of committed,
/// engine-produced values only (no pricing or risk computation). Evaluation metrics
/// (Sharpe, drawdown, volatility, attribution, ...) and payment calendars are requested
/// from the research engine and passed through; they are cached per committed state.
/// Ordering uses identity keys so the same queries run on SQL Server and SQLite.
/// </summary>
public sealed class FixedIncomeQueryService : IFixedIncomeQueryService
{
    /// <summary>Bumped when the performance request built from stored values changes shape.</summary>
    public const string PerformanceRequestVersion = "perf-request-v1";

    public const string MetricsAvailable = "available";
    public const string MetricsUnavailable = "unavailable";

    private readonly TradingDbContext _db;
    private readonly IRiskPolicyProvider _policies;
    private readonly IResearchEngineClient? _engine;
    private readonly FiAnalyticsCache _cache;
    private readonly ILogger<FixedIncomeQueryService> _logger;

    public FixedIncomeQueryService(TradingDbContext db, IRiskPolicyProvider policies,
        IResearchEngineClient? engine = null, FiAnalyticsCache? cache = null,
        ILogger<FixedIncomeQueryService>? logger = null)
    {
        _db = db;
        _policies = policies;
        _engine = engine;
        _cache = cache ?? new FiAnalyticsCache();
        _logger = logger ?? NullLogger<FixedIncomeQueryService>.Instance;
    }

    public async Task<PagedResult<RunSummaryView>> ListRunsAsync(RunListFilter filter, CancellationToken cancellationToken = default)
    {
        var (page, size) = PagedResult<RunSummaryView>.Normalize(filter.Page, filter.PageSize);
        var query = _db.FiExperimentRuns.AsNoTracking();
        if (!string.IsNullOrEmpty(filter.ExperimentId))
        {
            query = query.Where(r => r.ExperimentId == filter.ExperimentId);
        }

        if (!string.IsNullOrEmpty(filter.JobState))
        {
            query = query.Where(r => r.JobState == filter.JobState);
        }

        if (!string.IsNullOrEmpty(filter.DataMode))
        {
            query = query.Where(r => r.DataMode == filter.DataMode);
        }

        if (!string.IsNullOrEmpty(filter.RunType))
        {
            query = query.Where(r => r.RunType == filter.RunType);
        }

        var total = await query.CountAsync(cancellationToken);
        var runs = await query.OrderByDescending(r => r.Id).Skip((page - 1) * size).Take(size).ToListAsync(cancellationToken);
        return new PagedResult<RunSummaryView>(await SummariesAsync(runs, cancellationToken), page, size, total);
    }

    public async Task<RunDetailView?> GetRunAsync(string runId, CancellationToken cancellationToken = default)
    {
        var run = await _db.FiExperimentRuns.AsNoTracking().FirstOrDefaultAsync(r => r.RunId == runId, cancellationToken);
        if (run is null)
        {
            return null;
        }

        var strategies = await _db.FiStrategyInstances.AsNoTracking()
            .Where(s => s.RunId == runId)
            .OrderBy(s => s.Repetition).ThenBy(s => s.Id)
            .ToListAsync(cancellationToken);
        var outcomes = await _db.FiDecisions.AsNoTracking()
            .Where(d => d.RunId == runId)
            .GroupBy(d => d.Outcome)
            .Select(g => new { Outcome = g.Key, Count = g.Count() })
            .ToListAsync(cancellationToken);

        // Provider/model identity as recorded on each verified StrategyResult (e.g.
        // "reference/reference-heuristic-v1"); deterministic strategies record none.
        var observedModels = (await _db.FiDecisions.AsNoTracking()
                .Where(d => d.RunId == runId && d.Model != null)
                .Select(d => new { d.StrategyId, d.Repetition, d.Provider, d.Model })
                .Distinct()
                .ToListAsync(cancellationToken))
            .GroupBy(d => (d.StrategyId, d.Repetition))
            .ToDictionary(
                g => g.Key,
                g => (IReadOnlyList<string>)g.Select(d => d.Provider is null ? d.Model! : $"{d.Provider}/{d.Model}")
                    .OrderBy(m => m, StringComparer.Ordinal).ToList());

        var restricted = await _db.FiPortfolios.AsNoTracking()
            .Where(p => p.RunId == runId && p.BlockedReason != null)
            .OrderBy(p => p.Repetition).ThenBy(p => p.StrategyId)
            .Select(p => new { p.PortfolioId, p.StrategyId, p.Repetition, p.BlockedReason, p.BlockedAt, p.BlockedByCommandId })
            .ToListAsync(cancellationToken);

        var summary = (await SummariesAsync(new[] { run }, cancellationToken))[0];
        return new RunDetailView(
            summary,
            run.ManifestHash,
            FiWire.TryParseNode(run.ManifestJson),
            run.EngineVersion,
            strategies.Select(s => new StrategyInstanceView(s.StrategyId, s.StrategyKind, s.StrategyConfigId,
                s.Repetition, s.PortfolioId, s.Label,
                observedModels.TryGetValue((s.StrategyId, s.Repetition), out var models) ? models : Array.Empty<string>()))
                .ToList(),
            outcomes.ToDictionary(o => o.Outcome, o => o.Count),
            ParseErrors(run.ErrorsJson, cycleId: null),
            restricted.Select(p => new PortfolioRestrictionView(p.PortfolioId, p.StrategyId, p.Repetition,
                FiPortfolioRestriction.KindOf(p.BlockedReason)!, p.BlockedReason!, p.BlockedAt, p.BlockedByCommandId)).ToList());
    }

    public async Task<PagedResult<CycleView>?> GetRunCyclesAsync(string runId, int page, int pageSize, CancellationToken cancellationToken = default)
    {
        if (!await _db.FiExperimentRuns.AsNoTracking().AnyAsync(r => r.RunId == runId, cancellationToken))
        {
            return null;
        }

        var (p, s) = PagedResult<CycleView>.Normalize(page, pageSize);
        var query = _db.FiCycles.AsNoTracking().Where(c => c.RunId == runId);
        var total = await query.CountAsync(cancellationToken);
        var cycles = await query.OrderBy(c => c.Sequence).Skip((p - 1) * s).Take(s).ToListAsync(cancellationToken);
        return new PagedResult<CycleView>(cycles.Select(c =>
        {
            var errors = ParseErrors(c.ErrorsJson, c.CycleId);
            return new CycleView(c.CycleId, c.Sequence, c.SessionDate,
                c.DecisionAsOf, c.Status, c.SkipReason, c.MarketSnapshotId, c.MarketSnapshotHash, c.CurveSnapshotId,
                c.StartedAt, c.CompletedAt,
                Checkpointed: IsCheckpointed(c.Status),
                ErrorCount: errors.Count(e => e.Severity == "error"),
                WarningCount: errors.Count(e => e.Severity == "warning"),
                Errors: errors,
                Checkpoint: FiWire.TryParseNode(c.CheckpointJson));
        }).ToList(), p, s, total);
    }

    public async Task<RunComparisonView?> GetRunComparisonAsync(string runId, CancellationToken cancellationToken = default)
    {
        var run = await _db.FiExperimentRuns.AsNoTracking().Include(r => r.ExperimentDefinition)
            .FirstOrDefaultAsync(r => r.RunId == runId, cancellationToken);
        return run is null ? null : await BuildComparisonAsync(run, cancellationToken);
    }

    public async Task<ExperimentComparisonView?> GetExperimentComparisonAsync(string experimentId, CancellationToken cancellationToken = default)
    {
        var runs = await _db.FiExperimentRuns.AsNoTracking()
            .Include(r => r.ExperimentDefinition)
            .Where(r => r.ExperimentId == experimentId)
            .OrderBy(r => r.Id)
            .ToListAsync(cancellationToken);
        if (runs.Count == 0)
        {
            return await _db.FiExperimentDefinitions.AsNoTracking().AnyAsync(d => d.ExperimentId == experimentId, cancellationToken)
                ? new ExperimentComparisonView(experimentId, Array.Empty<ComparisonGroupView>(), new[] { "No runs yet." })
                : null;
        }

        var groups = new List<ComparisonGroupView>();
        foreach (var group in runs.GroupBy(GroupKey))
        {
            var comparisons = new List<RunComparisonView>();
            foreach (var run in group)
            {
                comparisons.Add(await BuildComparisonAsync(run, cancellationToken));
            }

            groups.Add(new ComparisonGroupView(group.Key, DataModeLabels.For(group.Key.DataMode), comparisons));
        }

        var notes = new List<string>();
        if (groups.Count > 1)
        {
            notes.Add("Runs are grouped by data mode, risk policy, execution (cost) model, run type and evaluation window; groups are not ranked against each other.");
        }

        return new ExperimentComparisonView(experimentId, groups, notes);
    }

    public async Task<PagedResult<DecisionSummaryView>?> ListRunDecisionsAsync(string runId, DecisionListFilter filter, CancellationToken cancellationToken = default)
    {
        if (!await _db.FiExperimentRuns.AsNoTracking().AnyAsync(r => r.RunId == runId, cancellationToken))
        {
            return null;
        }

        var (page, size) = PagedResult<DecisionSummaryView>.Normalize(filter.Page, filter.PageSize);
        var query = _db.FiDecisions.AsNoTracking().Where(d => d.RunId == runId);
        if (!string.IsNullOrEmpty(filter.CycleId))
        {
            query = query.Where(d => d.CycleId == filter.CycleId);
        }

        if (!string.IsNullOrEmpty(filter.StrategyId))
        {
            query = query.Where(d => d.StrategyId == filter.StrategyId);
        }

        if (!string.IsNullOrEmpty(filter.Outcome))
        {
            query = query.Where(d => d.Outcome == filter.Outcome);
        }

        var total = await query.CountAsync(cancellationToken);
        var decisions = await query.OrderBy(d => d.Id).Skip((page - 1) * size).Take(size).ToListAsync(cancellationToken);
        return new PagedResult<DecisionSummaryView>(decisions.Select(ToSummary).ToList(), page, size, total);
    }

    public async Task<DecisionDetailView?> GetDecisionAsync(string decisionId, CancellationToken cancellationToken = default)
    {
        var decision = await _db.FiDecisions.AsNoTracking()
            .Include(d => d.Attempts)
            .Include(d => d.ToolTraces)
            .Include(d => d.Usage)
            .AsSplitQuery()
            .FirstOrDefaultAsync(d => d.DecisionId == decisionId, cancellationToken);
        if (decision is null)
        {
            return null;
        }

        var evaluations = await _db.FiPolicyEvaluations.AsNoTracking()
            .Where(p => p.DecisionId == decisionId)
            .OrderBy(p => p.Id)
            .ToListAsync(cancellationToken);
        var orders = await _db.FiOrderIntents.AsNoTracking()
            .Where(o => o.DecisionId == decisionId)
            .OrderBy(o => o.Id)
            .ToListAsync(cancellationToken);
        var fills = await LoadFillsAsync(orders, cancellationToken);
        var cycle = await _db.FiCycles.AsNoTracking()
            .FirstOrDefaultAsync(c => c.RunId == decision.RunId && c.CycleId == decision.CycleId, cancellationToken);
        var frozen = await FrozenInputsAsync(decision, cycle, cancellationToken);
        var fillIds = orders
            .Select(o => fills.TryGetValue(o.PortfolioId + "\u0000" + o.OrderId, out var f) ? f.FillId : null)
            .Where(id => id is not null).Select(id => id!).ToList();

        var usage = decision.Usage;
        return new DecisionDetailView(
            ToSummary(decision),
            decision.PortfolioId,
            decision.RequestHash,
            FiWire.TryParseNode(decision.InputHashesJson),
            FiWire.TryParseNode(decision.ProposalJson),
            FiWire.TryParseNode(decision.ResearchNoteJson),
            FiWire.TryParseNode(decision.ValidationJson),
            FiWire.TryParseNode(decision.SpecialistTasksJson),
            FiWire.TryParseNode(decision.VersionsJson),
            ReadStrings(decision.EvidenceBundleIdsJson),
            evaluations.Select(e => new PolicyEvaluationView(e.Source, e.PolicyId, e.Action, e.Passed, e.BreachMode,
                e.BootstrapExemptionApplied, e.PlatformRecheckPassed, ReadStrings(e.PlatformRecheckReasonsJson),
                e.CommandId, FiWire.TryParseNode(e.EvaluationJson))).ToList(),
            decision.Attempts.OrderBy(a => a.AttemptNumber).ThenBy(a => a.Id).Select(a => new DecisionAttemptView(
                a.AttemptId, a.AttemptNumber, a.AgentRole, a.Purpose, a.Provider, a.Model, a.InputTokens,
                a.OutputTokens, a.StartedAt, a.DurationMs, a.Status, a.RecordedResponseId, a.Error)).ToList(),
            decision.ToolTraces.OrderBy(t => t.Id).Select(t => new ToolTraceView(t.TraceId, t.AgentRole, t.ToolName,
                FiWire.TryParseNode(t.RequestJson), FiWire.TryParseNode(t.ResponseSummaryJson), t.OutputRef,
                t.StartedAt, t.DurationMs, t.Status, t.Error)).ToList(),
            usage is null ? null : new UsageView(usage.GenerationCalls, usage.ToolCalls, usage.EvidenceCalls,
                usage.UniqueEvidenceChunks, usage.EvidenceTokens, usage.InputTokens, usage.OutputTokens,
                usage.DurationMs, FiWire.FormatDecimal(usage.EstimatedCostUsd), usage.PriceScheduleId, usage.BudgetExhausted),
            orders.Select(o => ToOrderView(o, fills)).ToList(),
            decision.ResultHash,
            decision.EngineVersion,
            DecisionAsOf: cycle?.DecisionAsOf,
            MarketSessionDate: cycle?.SessionDate,
            CycleSequence: cycle?.Sequence,
            FrozenInputs: frozen,
            FillIds: fillIds,
            Links: new DecisionLinksView(
                "/api/v1/runs/" + Uri.EscapeDataString(decision.RunId),
                "/api/v1/runs/" + Uri.EscapeDataString(decision.RunId) + "/cycles",
                decision.PortfolioId is null ? null : "/api/v1/portfolios/" + Uri.EscapeDataString(decision.PortfolioId),
                decision.PortfolioId is null ? null
                    : "/api/v1/portfolios/" + Uri.EscapeDataString(decision.PortfolioId) + "/orders?decisionId=" +
                      Uri.EscapeDataString(decision.DecisionId)));
    }

    public async Task<PortfolioView?> GetPortfolioAsync(string portfolioId, CancellationToken cancellationToken = default)
    {
        var portfolio = await _db.FiPortfolios.AsNoTracking().FirstOrDefaultAsync(p => p.PortfolioId == portfolioId, cancellationToken);
        if (portfolio is null)
        {
            return null;
        }

        var state = await _db.FiPortfolioStateVersions.AsNoTracking()
            .FirstOrDefaultAsync(s => s.PortfolioId == portfolioId && s.Version == portfolio.CurrentVersion, cancellationToken);
        var stateNode = FiWire.TryParseNode(state?.StateJson);
        var latest = await _db.FiValuationSnapshots.AsNoTracking()
            .Where(v => v.PortfolioId == portfolioId)
            .OrderByDescending(v => v.Id)
            .FirstOrDefaultAsync(cancellationToken);

        var parsed = TryReadState(state?.StateJson);
        return new PortfolioView(
            portfolio.PortfolioId, portfolio.RunId, portfolio.StrategyId, portfolio.Repetition, portfolio.RiskPolicyId,
            portfolio.DataMode, DataModeLabels.For(portfolio.DataMode), portfolio.CurrentVersion, portfolio.CurrentStateHash,
            portfolio.BlockedReason, portfolio.BlockedAt, stateNode,
            (stateNode?["openOrders"] as JsonArray)?.Count ?? 0,
            (stateNode?["pendingSettlements"] as JsonArray)?.Count ?? 0,
            latest is null ? null : ToValuationView(latest, includeDetail: false),
            portfolio.UpdatedAt,
            parsed is null ? null : CashView(parsed),
            await PaymentCalendarAsync(portfolio, state, parsed, cancellationToken),
            FiPortfolioRestriction.KindOf(portfolio.BlockedReason));
    }

    public async Task<PagedResult<ValuationView>?> GetValuationsAsync(string portfolioId, int page, int pageSize, bool? completeOnly, CancellationToken cancellationToken = default)
    {
        if (!await PortfolioExistsAsync(portfolioId, cancellationToken))
        {
            return null;
        }

        var (p, s) = PagedResult<ValuationView>.Normalize(page, pageSize);
        var query = _db.FiValuationSnapshots.AsNoTracking().Where(v => v.PortfolioId == portfolioId);
        if (completeOnly == true)
        {
            query = query.Where(v => v.Complete);
        }

        var total = await query.CountAsync(cancellationToken);
        var rows = await query.OrderBy(v => v.Id).Skip((p - 1) * s).Take(s).ToListAsync(cancellationToken);
        return new PagedResult<ValuationView>(rows.Select(v => ToValuationView(v, includeDetail: true)).ToList(), p, s, total);
    }

    public async Task<PagedResult<JournalView>?> GetJournalAsync(string portfolioId, JournalFilter filter, CancellationToken cancellationToken = default)
    {
        if (!await PortfolioExistsAsync(portfolioId, cancellationToken))
        {
            return null;
        }

        var (page, size) = PagedResult<JournalView>.Normalize(filter.Page, filter.PageSize);
        var query = _db.FiJournals.AsNoTracking().Where(j => j.PortfolioId == portfolioId);
        if (!string.IsNullOrEmpty(filter.EventType))
        {
            query = query.Where(j => j.EventType == filter.EventType);
        }

        if (filter.FromVersion is { } from)
        {
            query = query.Where(j => j.CommittedVersion >= from);
        }

        if (filter.ToVersion is { } to)
        {
            query = query.Where(j => j.CommittedVersion <= to);
        }

        if (!string.IsNullOrEmpty(filter.Account))
        {
            query = query.Where(j => j.Entries.Any(e => e.Account == filter.Account));
        }

        var total = await query.CountAsync(cancellationToken);
        var journals = await query.OrderBy(j => j.Id).Skip((page - 1) * size).Take(size)
            .Include(j => j.Entries)
            .ToListAsync(cancellationToken);

        return new PagedResult<JournalView>(journals.Select(j => new JournalView(
            j.JournalId, j.EventId, j.EventType, j.EffectiveAt, j.Template, j.CommittedVersion, j.CommandId,
            j.Entries.OrderBy(e => e.LineNumber).Select(e => new JournalLineView(e.LineId, e.Account, e.SecurityId,
                FiWire.FormatDecimal(e.DebitUsd), FiWire.FormatDecimal(e.CreditUsd), e.Memo)).ToList())).ToList(),
            page, size, total);
    }

    public async Task<PagedResult<OrderView>?> GetOrdersAsync(string portfolioId, OrderFilter filter, CancellationToken cancellationToken = default)
    {
        if (!await PortfolioExistsAsync(portfolioId, cancellationToken))
        {
            return null;
        }

        var (page, size) = PagedResult<OrderView>.Normalize(filter.Page, filter.PageSize);
        var query = _db.FiOrderIntents.AsNoTracking().Where(o => o.PortfolioId == portfolioId);
        if (!string.IsNullOrEmpty(filter.Status))
        {
            query = query.Where(o => o.Status == filter.Status);
        }

        if (!string.IsNullOrEmpty(filter.SecurityId))
        {
            query = query.Where(o => o.SecurityId == filter.SecurityId);
        }

        if (!string.IsNullOrEmpty(filter.DecisionId))
        {
            query = query.Where(o => o.DecisionId == filter.DecisionId);
        }

        var total = await query.CountAsync(cancellationToken);
        var orders = await query.OrderBy(o => o.Id).Skip((page - 1) * size).Take(size).ToListAsync(cancellationToken);
        var fills = await LoadFillsAsync(orders, cancellationToken);
        return new PagedResult<OrderView>(orders.Select(o => ToOrderView(o, fills)).ToList(), page, size, total);
    }

    private async Task<RunComparisonView> BuildComparisonAsync(ExperimentRun run, CancellationToken ct)
    {
        var strategies = await _db.FiStrategyInstances.AsNoTracking()
            .Where(s => s.RunId == run.RunId).OrderBy(s => s.Repetition).ThenBy(s => s.Id).ToListAsync(ct);
        var portfolioIds = strategies.Select(s => s.PortfolioId).ToList();

        var portfolios = await _db.FiPortfolios.AsNoTracking()
            .Where(p => portfolioIds.Contains(p.PortfolioId)).ToDictionaryAsync(p => p.PortfolioId, ct);
        var valuations = await _db.FiValuationSnapshots.AsNoTracking()
            .Where(v => portfolioIds.Contains(v.PortfolioId))
            .Select(v => new { v.Id, v.PortfolioId, v.EquityUsd, v.Complete, v.ValuationAt })
            .ToListAsync(ct);
        var decisions = await _db.FiDecisions.AsNoTracking()
            .Where(d => d.RunId == run.RunId)
            .Select(d => new { d.Id, d.StrategyId, d.Repetition, d.Outcome })
            .ToListAsync(ct);
        var decisionIds = decisions.Select(d => d.Id).ToList();
        var usage = await _db.FiUsageRecords.AsNoTracking()
            .Where(u => decisionIds.Contains(u.DecisionDbId))
            .Select(u => new { u.DecisionDbId, u.InputTokens, u.OutputTokens, u.EstimatedCostUsd })
            .ToListAsync(ct);
        var orders = await _db.FiOrderIntents.AsNoTracking()
            .Where(o => portfolioIds.Contains(o.PortfolioId))
            .Select(o => o.PortfolioId).ToListAsync(ct);
        var fills = await _db.FiFills.AsNoTracking()
            .Where(f => portfolioIds.Contains(f.PortfolioId))
            .Select(f => new { f.PortfolioId, f.FeesUsd, f.SpreadCostUsd }).ToListAsync(ct);

        var initialCapital = _policies.FindRiskPolicy(run.RiskPolicyId)?.InitialCapitalUsd;
        var performance = await PerformanceAsync(run, strategies, portfolios, decisions.Count,
            decisions.Count == 0 ? 0 : decisions.Max(d => d.Id), ct);
        var entries = new List<ComparisonEntryView>();
        foreach (var strategy in strategies)
        {
            var own = valuations.Where(v => v.PortfolioId == strategy.PortfolioId).OrderBy(v => v.Id).ToList();
            var latest = own.LastOrDefault();
            var latestComplete = own.LastOrDefault(v => v.Complete && v.EquityUsd is not null);
            var ownDecisions = decisions.Where(d => d.StrategyId == strategy.StrategyId && d.Repetition == strategy.Repetition).ToList();
            var ownDecisionIds = ownDecisions.Select(d => d.Id).ToHashSet();
            var ownUsage = usage.Where(u => ownDecisionIds.Contains(u.DecisionDbId)).ToList();
            var ownFills = fills.Where(f => f.PortfolioId == strategy.PortfolioId).ToList();
            var costs = ownUsage.Where(u => u.EstimatedCostUsd is not null).Select(u => u.EstimatedCostUsd!.Value).ToList();

            string? returnRatio = null;
            if (latestComplete?.EquityUsd is { } equity && initialCapital is { } capital && capital > 0)
            {
                returnRatio = FiWire.FormatDecimal(decimal.Round(equity / capital - 1m, 10));
            }

            entries.Add(new ComparisonEntryView(
                strategy.StrategyId,
                strategy.StrategyKind,
                strategy.Repetition,
                strategy.PortfolioId,
                FiWire.FormatDecimal(initialCapital ?? 0m),
                FiWire.FormatDecimal(latestComplete?.EquityUsd),
                returnRatio,
                latest?.ValuationAt,
                latest?.Complete,
                own.Count,
                own.Count(v => !v.Complete),
                ownDecisions.Count,
                ownDecisions.GroupBy(d => d.Outcome).ToDictionary(g => g.Key, g => g.Count()),
                orders.Count(o => o == strategy.PortfolioId),
                ownFills.Count,
                FiWire.FormatDecimal(ownFills.Sum(f => f.FeesUsd)),
                FiWire.FormatDecimal(ownFills.Sum(f => f.SpreadCostUsd)),
                ownUsage.Sum(u => (long)u.InputTokens),
                ownUsage.Sum(u => (long)u.OutputTokens),
                costs.Count == 0 ? null : FiWire.FormatDecimal(costs.Sum()),
                portfolios.TryGetValue(strategy.PortfolioId, out var portfolio) ? portfolio.BlockedReason : null,
                performance.Metrics.TryGetValue(strategy.PortfolioId, out var metrics) ? metrics : null,
                performance.Metrics.ContainsKey(strategy.PortfolioId)
                    ? null
                    : performance.EntryReasons.GetValueOrDefault(strategy.PortfolioId) ?? performance.View.UnavailableReason));
        }

        var notes = new List<string>
        {
            "Returns use the latest complete valuation; incomplete or stale valuations are excluded and counted.",
            "Risk, cost and return metrics are computed by the research engine (metrics-v1) from the stored series; " +
            "a short window implies no statistical significance.",
        };
        if (run.DataMode == FiDataMode.SyntheticCurve)
        {
            notes.Add("Synthetic curve mode: prices are curve-model values, not market quotes.");
        }

        return new RunComparisonView(run.RunId, run.ExperimentId, GroupKey(run),
            DataModeLabels.For(run.DataMode), run.JobState, entries, notes, performance.View);
    }

    private static ComparisonGroupKey GroupKey(ExperimentRun run) => new(
        run.DataMode, run.RiskPolicyId, run.ExecutionModelId, run.RunType,
        run.ExperimentDefinition?.StartDate, run.ExperimentDefinition?.EndDate);

    // ------------------------------------------------------------------ evaluation metrics (engine-computed)

    private sealed record PerformanceOutcome(
        ComparisonMetricsView View,
        IReadOnlyDictionary<string, JsonNode> Metrics,
        IReadOnlyDictionary<string, string> EntryReasons);

    private static PerformanceOutcome Unavailable(string reason, IReadOnlyDictionary<string, string>? entryReasons = null) =>
        new(new ComparisonMetricsView(MetricsUnavailable, reason, null, null, null, null),
            new Dictionary<string, JsonNode>(), entryReasons ?? new Dictionary<string, string>());

    /// <summary>
    /// Requests metrics-v1 from POST /internal/v1/analytics/performance for every portfolio of the run.
    /// Cached in memory by run + committed portfolio versions + decision count, so the series is only
    /// rebuilt after a new commit. Never computes a metric in .NET.
    /// </summary>
    private async Task<PerformanceOutcome> PerformanceAsync(ExperimentRun run, IReadOnlyList<StrategyInstance> strategies,
        IReadOnlyDictionary<string, FiPortfolio> portfolios, int decisionCount, long lastDecisionId, CancellationToken ct)
    {
        if (strategies.Count == 0)
        {
            return Unavailable("no_strategies");
        }

        if (_engine is null)
        {
            return Unavailable("research_engine_not_configured");
        }

        var versions = string.Join(",", strategies.Select(s =>
            s.PortfolioId + "@" + (portfolios.TryGetValue(s.PortfolioId, out var p) ? p.CurrentVersion : -1)));
        var key = string.Join("|", PerformanceRequestVersion, run.RunId, versions,
            decisionCount.ToString(CultureInfo.InvariantCulture), lastDecisionId.ToString(CultureInfo.InvariantCulture));

        if (!_cache.TryGet(key, out var body))
        {
            var (request, skipped) = await BuildPerformanceRequestAsync(run, strategies, ct);
            if (request.Portfolios.Count == 0)
            {
                return Unavailable("no_portfolio_series", skipped);
            }

            try
            {
                var document = await _engine.GetPerformanceAsync(request, ct);
                body = document.Body as JsonObject;
            }
            catch (ResearchEngineException ex)
            {
                _logger.LogWarning(ex, "Performance metrics for run {RunId} are unavailable", run.RunId);
                return Unavailable($"research_engine_unavailable: {ex.Message}", skipped);
            }

            if (body is not JsonObject obj || obj["portfolios"] is not JsonArray)
            {
                return Unavailable("research_engine_invalid_response", skipped);
            }

            if (skipped.Count > 0)
            {
                obj["platformSkipped"] = new JsonObject(skipped.Select(kv =>
                    KeyValuePair.Create(kv.Key, (JsonNode?)JsonValue.Create(kv.Value))));
            }

            _cache.Set(key, obj);
        }

        var result = (JsonObject)body!;
        var metrics = new Dictionary<string, JsonNode>(StringComparer.Ordinal);
        foreach (var item in result["portfolios"]!.AsArray().OfType<JsonObject>())
        {
            if (item["portfolioId"]?.GetValue<string>() is { } pid && item["metrics"] is JsonNode m)
            {
                metrics[pid] = m.DeepClone();
            }
        }

        var reasons = new Dictionary<string, string>(StringComparer.Ordinal);
        if (result["platformSkipped"] is JsonObject skippedNode)
        {
            foreach (var (pid, reason) in skippedNode)
            {
                reasons[pid] = reason?.GetValue<string>() ?? "skipped";
            }
        }

        return new PerformanceOutcome(new ComparisonMetricsView(
                MetricsAvailable, null,
                result["metricsVersion"]?.GetValue<string>(),
                result["engineVersion"] is JsonValue ev && ev.TryGetValue<string>(out var engineVersion) ? engineVersion : null,
                result["conventions"]?.DeepClone(),
                result["pairedComparisons"]?.DeepClone()),
            metrics, reasons);
    }

    private async Task<(PerformanceRequestDto Request, Dictionary<string, string> Skipped)> BuildPerformanceRequestAsync(
        ExperimentRun run, IReadOnlyList<StrategyInstance> strategies, CancellationToken ct)
    {
        var portfolioIds = strategies.Select(s => s.PortfolioId).Distinct().ToList();
        var valuations = await _db.FiValuationSnapshots.AsNoTracking()
            .Where(v => portfolioIds.Contains(v.PortfolioId))
            .OrderBy(v => v.Id)
            .Select(v => new { v.PortfolioId, v.ValuationId, v.CommittedVersion, v.ValuationJson })
            .ToListAsync(ct);
        var fills = await _db.FiFills.AsNoTracking()
            .Where(f => portfolioIds.Contains(f.PortfolioId))
            .OrderBy(f => f.Id)
            .Select(f => new { f.PortfolioId, f.FillId, f.ExecutedAt, f.ConsiderationUsd, f.FeesUsd, f.SpreadCostUsd })
            .ToListAsync(ct);
        var cashFlows = await _db.FiCashFlowEvents.AsNoTracking()
            .Where(c => portfolioIds.Contains(c.PortfolioId))
            .OrderBy(c => c.Id)
            .Select(c => new { c.PortfolioId, c.CashFlowId, c.Kind, c.PaymentDate, c.AmountUsd })
            .ToListAsync(ct);
        var orders = await _db.FiOrderIntents.AsNoTracking()
            .Where(o => portfolioIds.Contains(o.PortfolioId))
            .Select(o => new { o.PortfolioId, o.Status })
            .ToListAsync(ct);
        var evaluations = await _db.FiPolicyEvaluations.AsNoTracking()
            .Where(e => e.PortfolioId != null && portfolioIds.Contains(e.PortfolioId) && e.Source == "transition_proposal")
            .Select(e => new { e.PortfolioId, e.Passed })
            .ToListAsync(ct);
        var outcomes = await _db.FiDecisions.AsNoTracking()
            .Where(d => d.RunId == run.RunId)
            .GroupBy(d => new { d.StrategyId, d.Repetition, d.Outcome })
            .Select(g => new { g.Key.StrategyId, g.Key.Repetition, g.Key.Outcome, Count = g.Count() })
            .ToListAsync(ct);

        var skipped = new Dictionary<string, string>(StringComparer.Ordinal);
        var portfolios = new List<PerformancePortfolioDto>();
        foreach (var strategy in strategies)
        {
            var pid = strategy.PortfolioId;
            var own = valuations.Where(v => v.PortfolioId == pid).ToList();
            var neededVersions = own.Select(v => v.CommittedVersion).Distinct().ToList();
            var states = await _db.FiPortfolioStateVersions.AsNoTracking()
                .Where(sv => sv.PortfolioId == pid && neededVersions.Contains(sv.Version))
                .Select(sv => new { sv.Version, sv.StateJson })
                .ToDictionaryAsync(sv => sv.Version, sv => sv.StateJson, ct);

            var points = new List<PerformanceValuationDto>();
            string? problem = null;
            foreach (var row in own)
            {
                var valuation = TryRead<ValuationSnapshotDto>(row.ValuationJson);
                var state = states.TryGetValue(row.CommittedVersion, out var json) ? TryReadState(json) : null;
                if (valuation is null || state is null)
                {
                    problem = valuation is null
                        ? $"valuation_unreadable: {row.ValuationId}"
                        : $"state_version_missing: v{row.CommittedVersion}";
                    break;
                }

                points.Add(new PerformanceValuationDto
                {
                    ValuationId = valuation.ValuationId,
                    ValuationAt = valuation.ValuationAt,
                    StateVersion = row.CommittedVersion,
                    Complete = valuation.Complete,
                    CashUsd = valuation.CashUsd,
                    EquityUsd = valuation.EquityUsd,
                    BondValueUsd = valuation.BondValueUsd,
                    ParallelDv01Usd = valuation.ParallelDv01Usd,
                    EffectiveDurationYears = valuation.EffectiveDurationYears,
                    Marks = valuation.Marks.Select(m => new PerformanceMarkDto
                    {
                        EconomicFace = m.EconomicFace,
                        AccruedPer100 = m.AccruedPer100,
                    }).ToList(),
                    Ledger = new PerformanceLedgerDto
                    {
                        ExternalCapitalUsd = state.ExternalCapitalUsd,
                        InterestIncomeUsd = state.InterestIncomeUsd,
                        RealizedGainLossUsd = state.RealizedGainLossUsd,
                        BookedUnrealizedUsd = state.BookedUnrealizedUsd,
                        TransactionFeesUsd = state.TransactionFeesUsd,
                        SpreadCostUsd = state.SpreadCostUsd,
                        LotAccruedPurchasedUsd = state.Positions.SelectMany(p => p.Lots).Select(l => l.AccruedPurchasedUsd).ToList(),
                    },
                });
            }

            if (problem is not null)
            {
                skipped[pid] = problem;
                continue;
            }

            var ownEvaluations = evaluations.Where(e => e.PortfolioId == pid).ToList();
            portfolios.Add(new PerformancePortfolioDto
            {
                PortfolioId = pid,
                StrategyId = strategy.StrategyId,
                Repetition = strategy.Repetition,
                Valuations = points,
                Fills = fills.Where(f => f.PortfolioId == pid).Select(f => new PerformanceFillDto
                {
                    FillId = f.FillId,
                    ExecutedAt = FiWire.FormatInstant(f.ExecutedAt),
                    ConsiderationUsd = FiWire.FormatDecimal(f.ConsiderationUsd),
                    FeesUsd = FiWire.FormatDecimal(f.FeesUsd),
                    SpreadCostUsd = FiWire.FormatDecimal(f.SpreadCostUsd),
                }).ToList(),
                CashFlows = cashFlows.Where(c => c.PortfolioId == pid).Select(c => new PerformanceCashFlowDto
                {
                    CashFlowId = c.CashFlowId,
                    Kind = c.Kind,
                    PaymentDate = FiWire.FormatDate(c.PaymentDate),
                    AmountUsd = FiWire.FormatDecimal(c.AmountUsd),
                }).ToList(),
                OrdersCreated = orders.Count(o => o.PortfolioId == pid),
                OrderStatusCounts = orders.Where(o => o.PortfolioId == pid && o.Status != FiOrderStatus.Accepted)
                    .GroupBy(o => o.Status).ToDictionary(g => g.Key, g => g.Count()),
                PolicyEvaluations = ownEvaluations.Count,
                PolicyRejections = ownEvaluations.Count(e => !e.Passed),
                DecisionOutcomes = outcomes.Where(o => o.StrategyId == strategy.StrategyId && o.Repetition == strategy.Repetition)
                    .ToDictionary(o => o.Outcome, o => o.Count),
            });
        }

        // Paired differences versus the cash reference of the same repetition (block bootstrap in the engine).
        var included = portfolios.Select(p => p.PortfolioId).ToHashSet(StringComparer.Ordinal);
        var references = strategies.Where(s => s.StrategyKind == FiStrategyKind.CashReference && included.Contains(s.PortfolioId)).ToList();
        var pairs = new List<PerformancePairDto>();
        foreach (var strategy in strategies.Where(s => s.StrategyKind != FiStrategyKind.CashReference && included.Contains(s.PortfolioId)))
        {
            var reference = references.FirstOrDefault(r => r.Repetition == strategy.Repetition) ?? references.FirstOrDefault();
            if (reference is not null)
            {
                pairs.Add(new PerformancePairDto { PortfolioId = strategy.PortfolioId, VersusPortfolioId = reference.PortfolioId });
            }
        }

        var request = new PerformanceRequestDto
        {
            RequestId = FiIds.Make("perf", run.RunId,
                CanonicalJson.ContentHash(new JsonObject { ["portfolios"] = FiWire.ToNode(portfolios), ["pairs"] = FiWire.ToNode(pairs) })
                    [FiContract.HashPrefix.Length..][..24]),
            RunId = run.RunId,
            Portfolios = portfolios,
            Pairs = pairs,
        };
        return (request, skipped);
    }

    private async Task<Dictionary<string, Fill>> LoadFillsAsync(IReadOnlyCollection<OrderIntent> orders, CancellationToken ct)
    {
        if (orders.Count == 0)
        {
            return new Dictionary<string, Fill>();
        }

        var keys = orders.Select(o => o.OrderId).Distinct().ToList();
        var portfolioIds = orders.Select(o => o.PortfolioId).Distinct().ToList();
        var fills = await _db.FiFills.AsNoTracking()
            .Where(f => portfolioIds.Contains(f.PortfolioId) && keys.Contains(f.OrderId))
            .ToListAsync(ct);
        return fills.ToDictionary(f => f.PortfolioId + "\u0000" + f.OrderId);
    }

    private Task<bool> PortfolioExistsAsync(string portfolioId, CancellationToken ct) =>
        _db.FiPortfolios.AsNoTracking().AnyAsync(p => p.PortfolioId == portfolioId, ct);

    private static OrderView ToOrderView(OrderIntent o, IReadOnlyDictionary<string, Fill> fills)
    {
        fills.TryGetValue(o.PortfolioId + "\u0000" + o.OrderId, out var fill);
        return new OrderView(o.OrderId, o.PortfolioId, o.DecisionId, o.SecurityId, o.Side, FiWire.FormatDecimal(o.Face),
            o.SubmittedAt, o.EligibleSessionDate, o.ExpiresAt, o.Status, o.StatusReason,
            FiWire.FormatDecimal(o.ReservedCashUsd), o.Bootstrap, o.CreatedInVersion, o.LastUpdatedVersion,
            fill is null ? null : new FillView(fill.FillId, fill.ExecutedAt, fill.ObservationId, fill.QuoteKind,
                FiWire.FormatDecimal(fill.ReferenceCleanPricePer100), FiWire.FormatDecimal(fill.ExecutionCleanPricePer100),
                FiWire.FormatDecimal(fill.DirtyPricePer100), FiWire.FormatDecimal(fill.ConsiderationUsd),
                FiWire.FormatDecimal(fill.FeesUsd), fill.SettlementDate, fill.TimingLabel));
    }

    private static ValuationView ToValuationView(ValuationSnapshot v, bool includeDetail) => new(
        v.ValuationId, v.StateVersion, v.ValuationAt, v.DataMode, v.CurveSnapshotId, v.MarkPolicy, v.Complete,
        ReadStrings(v.IncompleteReasonsJson), FiWire.FormatDecimal(v.CashUsd), FiWire.FormatDecimal(v.BondValueUsd),
        FiWire.FormatDecimal(v.ReceivablesPvUsd), FiWire.FormatDecimal(v.PayablesPvUsd), FiWire.FormatDecimal(v.EquityUsd),
        FiWire.FormatDecimal(v.ParallelDv01Usd), FiWire.FormatDecimal(v.EffectiveDurationYears),
        includeDetail ? FiWire.TryParseNode(v.ValuationJson) : null);

    // ------------------------------------------------------------------ runs: window, checkpoint, errors

    private sealed record CycleDigest(string RunId, string CycleId, int Sequence, DateOnly SessionDate, string Status,
        DateTimeOffset? CompletedAt, string? ErrorsJson);

    private async Task<List<RunSummaryView>> SummariesAsync(IReadOnlyList<ExperimentRun> runs, CancellationToken ct)
    {
        if (runs.Count == 0)
        {
            return new List<RunSummaryView>();
        }

        var runIds = runs.Select(r => r.RunId).ToList();
        var definitionIds = runs.Select(r => r.ExperimentDefinitionId).Distinct().ToList();
        var windows = await _db.FiExperimentDefinitions.AsNoTracking()
            .Where(d => definitionIds.Contains(d.Id))
            .Select(d => new { d.Id, d.StartDate, d.EndDate })
            .ToDictionaryAsync(d => d.Id, ct);
        var cycles = await _db.FiCycles.AsNoTracking()
            .Where(c => runIds.Contains(c.RunId))
            .Select(c => new { c.RunId, c.CycleId, c.Sequence, c.SessionDate, c.Status, c.CompletedAt, c.ErrorsJson })
            .ToListAsync(ct);
        var byRun = cycles
            .Select(c => new CycleDigest(c.RunId, c.CycleId, c.Sequence, c.SessionDate, c.Status, c.CompletedAt, c.ErrorsJson))
            .ToLookup(c => c.RunId, StringComparer.Ordinal);

        return runs.Select(r =>
        {
            windows.TryGetValue(r.ExperimentDefinitionId, out var window);
            return ToSummary(r, window?.StartDate, window?.EndDate, byRun[r.RunId].ToList());
        }).ToList();
    }

    private static RunSummaryView ToSummary(ExperimentRun r, DateOnly? start, DateOnly? end, IReadOnlyList<CycleDigest> cycles)
    {
        var checkpointed = cycles.Where(c => IsCheckpointed(c.Status)).OrderBy(c => c.Sequence).ToList();
        var last = checkpointed.LastOrDefault();
        var cycleErrors = cycles.SelectMany(c => ParseErrors(c.ErrorsJson, c.CycleId)).ToList();
        var runErrors = ParseErrors(r.ErrorsJson, cycleId: null);
        var byScope = cycleErrors.Concat(runErrors)
            .GroupBy(e => e.Scope, StringComparer.Ordinal)
            .ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);
        return new RunSummaryView(
            r.RunId, r.ExperimentId, r.ExperimentVersion, r.RunType, r.ResponseMode, r.DataMode,
            DataModeLabels.For(r.DataMode), r.RiskPolicyId, r.ExecutionModelId, r.JobState, r.StatusReason,
            r.CompletedCycles, r.TotalCycles, r.SimulatedClock, r.CreatedAt, r.StartedAt, r.CompletedAt,
            StartDate: start ?? r.ExperimentDefinition?.StartDate,
            EndDate: end ?? r.ExperimentDefinition?.EndDate,
            ManifestHash: r.ManifestHash,
            Checkpoint: last is null ? null : new RunCheckpointView(last.CycleId, last.Sequence, last.SessionDate, last.Status,
                last.CompletedAt, checkpointed.Count, r.TotalCycles, r.LastCheckpointAt),
            Errors: new RunErrorSummaryView(
                runErrors.Count,
                cycleErrors.Count(e => e.Severity == "error"),
                cycleErrors.Count(e => e.Severity == "warning"),
                byScope,
                cycles.GroupBy(c => c.Status, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal)));
    }

    private static bool IsCheckpointed(string status) => status is FiCycleStatus.Completed or FiCycleStatus.Skipped;

    /// <summary>Reads stored classified-error arrays (cycle ErrorsJson / run ErrorsJson) without reinterpreting them.</summary>
    private static List<ClassifiedErrorView> ParseErrors(string? json, string? cycleId)
    {
        var list = new List<ClassifiedErrorView>();
        if (FiWire.TryParseNode(json) is not JsonArray array)
        {
            return list;
        }

        foreach (var item in array.OfType<JsonObject>())
        {
            list.Add(new ClassifiedErrorView(
                Str(item, "scope") ?? "unknown",
                Str(item, "severity") ?? "error",
                Str(item, "code") ?? "unknown",
                Str(item, "message") ?? string.Empty,
                Str(item, "strategyId"),
                Str(item, "portfolioId"),
                Str(item, "commandId"),
                Str(item, "decisionId"),
                cycleId,
                Str(item, "at")));
        }

        return list;
    }

    private static string? Str(JsonObject obj, string name) =>
        obj[name] is JsonValue value && value.TryGetValue<string>(out var text) ? text : null;

    // ------------------------------------------------------------------ decisions: frozen inputs

    private async Task<DecisionFrozenInputsView> FrozenInputsAsync(Decision decision, Cycle? cycle, CancellationToken ct)
    {
        var hashes = FiWire.TryParseNode(decision.InputHashesJson) as JsonObject;
        var portfolioHash = hashes is null ? null : Str(hashes, "portfolioState");
        long? portfolioVersion = null;
        if (portfolioHash is not null && decision.PortfolioId is not null)
        {
            portfolioVersion = await _db.FiPortfolioStateVersions.AsNoTracking()
                .Where(v => v.PortfolioId == decision.PortfolioId && v.StateHash == portfolioHash)
                .OrderBy(v => v.Version)
                .Select(v => (long?)v.Version)
                .FirstOrDefaultAsync(ct);
        }

        var run = await _db.FiExperimentRuns.AsNoTracking().Include(r => r.ExperimentDefinition)
            .FirstOrDefaultAsync(r => r.RunId == decision.RunId, ct);
        var spec = run?.ExperimentDefinition is { } definition ? TryRead<CreateExperimentDefinitionRequest>(definition.DefinitionJson) : null;
        var configId = await _db.FiStrategyInstances.AsNoTracking()
            .Where(s => s.RunId == decision.RunId && s.StrategyId == decision.StrategyId && s.Repetition == decision.Repetition)
            .Select(s => s.StrategyConfigId)
            .FirstOrDefaultAsync(ct);

        return new DecisionFrozenInputsView(
            portfolioVersion is { } v && decision.PortfolioId is not null ? FiIds.PortfolioSnapshot(decision.PortfolioId, v) : null,
            portfolioVersion,
            portfolioHash,
            cycle?.MarketSnapshotId,
            cycle?.MarketSnapshotHash ?? (hashes is null ? null : Str(hashes, "marketSnapshot")),
            cycle?.CurveSnapshotId,
            spec?.EvidenceSnapshotId,
            spec?.IndexBuildId,
            spec?.InstrumentUniverseVersion ?? run?.ExperimentDefinition?.InstrumentUniverseVersion,
            configId,
            run?.RiskPolicyId,
            spec?.AvailabilityPolicy,
            run?.DataMode);
    }

    // ------------------------------------------------------------------ portfolios: cash and payment calendar

    private static PortfolioStateDto? TryReadState(string? json) => TryRead<PortfolioStateDto>(json);

    private static T? TryRead<T>(string? json) where T : class
    {
        if (FiWire.TryParseNode(json) is not JsonNode node)
        {
            return null;
        }

        try
        {
            return FiWire.Deserialize<T>(node);
        }
        catch (Exception ex) when (ex is JsonException or FormatException or InvalidOperationException)
        {
            return null;
        }
    }

    /// <summary>Display arithmetic over the stored state's values (no valuation or accrual).</summary>
    private static PortfolioCashView? CashView(PortfolioStateDto state)
    {
        if (!FiWire.TryParseDecimal(state.CashUsd, out var settled) ||
            !FiWire.TryParseDecimal(state.ReservedCashUsd, out var reserved))
        {
            return null;
        }

        decimal payables = 0m, receivables = 0m;
        foreach (var settlement in state.PendingSettlements)
        {
            if (!FiWire.TryParseDecimal(settlement.CashUsd, out var amount))
            {
                return null;
            }

            if (settlement.Side == "BUY")
            {
                payables += amount;
            }
            else if (settlement.Side == "SELL")
            {
                receivables += amount;
            }
        }

        var committed = reserved + payables;
        return new PortfolioCashView(
            FiWire.FormatDecimal(settled),
            FiWire.FormatDecimal(reserved),
            FiWire.FormatDecimal(payables),
            FiWire.FormatDecimal(receivables),
            FiWire.FormatDecimal(committed),
            FiWire.FormatDecimal(settled - committed),
            "available = settled cash - reserved cash (accepted purchase orders) - pending settlement payables; " +
            "committed = reserved + pending payables; receivables are not available until settlement");
    }

    private async Task<PaymentCalendarView> PaymentCalendarAsync(FiPortfolio portfolio, PortfolioStateVersion? state,
        PortfolioStateDto? parsed, CancellationToken ct)
    {
        if (state is null || parsed is null)
        {
            return new PaymentCalendarView(MetricsUnavailable, "state_unavailable", null);
        }

        static bool Positive(string value) => FiWire.TryParseDecimal(value, out var face) && face > 0;
        if (!parsed.Positions.Any(p => Positive(p.EconomicFace) || Positive(p.SettledFace)) && parsed.PendingSettlements.Count == 0)
        {
            return new PaymentCalendarView("no_holdings", null, null);
        }

        if (_engine is null)
        {
            return new PaymentCalendarView(MetricsUnavailable, "research_engine_not_configured", null);
        }

        var key = "calendar|" + portfolio.PortfolioId + "|" + state.Version.ToString(CultureInfo.InvariantCulture) + "|" + state.StateHash;
        if (_cache.TryGet(key, out var cached))
        {
            return new PaymentCalendarView(MetricsAvailable, null, cached);
        }

        try
        {
            using var document = JsonDocument.Parse(state.StateJson);
            var response = await _engine.GetPaymentCalendarAsync(new PaymentCalendarRequestDto
            {
                RequestId = FiIds.Make("calendar", portfolio.PortfolioId, "v" + state.Version.ToString(CultureInfo.InvariantCulture)),
                PortfolioState = document.RootElement.Clone(),
                PortfolioStateHash = state.StateHash,
            }, ct);
            if (response.Body is not JsonObject body)
            {
                return new PaymentCalendarView(MetricsUnavailable, "research_engine_invalid_response", null);
            }

            _cache.Set(key, body);
            return new PaymentCalendarView(MetricsAvailable, null, body);
        }
        catch (ResearchEngineException ex)
        {
            _logger.LogWarning(ex, "Payment calendar of portfolio {PortfolioId} is unavailable", portfolio.PortfolioId);
            return new PaymentCalendarView(MetricsUnavailable, $"research_engine_unavailable: {ex.Message}", null);
        }
    }

    private static DecisionSummaryView ToSummary(Decision d) => new(
        d.DecisionId, d.RunId, d.CycleId, d.StrategyId, d.Repetition, d.StrategyKind, d.Outcome, d.Action,
        d.CompletedAt, d.Integrity, ReadStrings(d.ReasonsJson));

    private static IReadOnlyList<string> ReadStrings(string? json)
    {
        if (string.IsNullOrEmpty(json))
        {
            return Array.Empty<string>();
        }

        try
        {
            return JsonSerializer.Deserialize<List<string>>(json) ?? new List<string>();
        }
        catch (JsonException)
        {
            return Array.Empty<string>();
        }
    }
}
