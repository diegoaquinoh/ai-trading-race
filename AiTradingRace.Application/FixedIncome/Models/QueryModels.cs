using System.Text.Json.Nodes;

namespace AiTradingRace.Application.FixedIncome.Models;

// Read models for the public /api/v1 dashboard endpoints. Monetary values are
// decimal strings (spec 14.1); instants are UTC.

public sealed record RunListFilter(
    string? ExperimentId = null,
    string? JobState = null,
    string? DataMode = null,
    string? RunType = null,
    int Page = 1,
    int PageSize = 50);

public sealed record RunSummaryView(
    string RunId,
    string ExperimentId,
    int ExperimentVersion,
    string RunType,
    string ResponseMode,
    string DataMode,
    string DataModeLabel,
    string RiskPolicyId,
    string ExecutionModelId,
    string JobState,
    string? StatusReason,
    int CompletedCycles,
    int? TotalCycles,
    DateTimeOffset? SimulatedClock,
    DateTimeOffset CreatedAt,
    DateTimeOffset? StartedAt,
    DateTimeOffset? CompletedAt,
    // Evaluation window of the experiment definition the run executes (spec 17.1).
    DateOnly? StartDate = null,
    DateOnly? EndDate = null,
    string? ManifestHash = null,
    RunCheckpointView? Checkpoint = null,
    RunErrorSummaryView? Errors = null);

/// <summary>Latest checkpointed cycle (spec 15.4): resume starts after it.</summary>
public sealed record RunCheckpointView(
    string CycleId,
    int Sequence,
    DateOnly SessionDate,
    string Status,
    DateTimeOffset? CompletedAt,
    int CheckpointedCycles,
    int? TotalCycles,
    DateTimeOffset? LastCheckpointAt);

/// <summary>Classified error (spec 18.3): scope source | strategy | cycle | financial_state.</summary>
public sealed record ClassifiedErrorView(
    string Scope,
    string Severity,
    string Code,
    string Message,
    string? StrategyId = null,
    string? PortfolioId = null,
    string? CommandId = null,
    string? DecisionId = null,
    string? CycleId = null,
    string? At = null);

/// <summary>Error classification of a run: run-level errors plus cycle errors/warnings by scope.</summary>
public sealed record RunErrorSummaryView(
    int RunErrors,
    int CycleErrors,
    int CycleWarnings,
    IReadOnlyDictionary<string, int> ByScope,
    IReadOnlyDictionary<string, int> CycleStatusCounts);

public sealed record StrategyInstanceView(
    string StrategyId,
    string StrategyKind,
    string StrategyConfigId,
    int Repetition,
    string PortfolioId,
    string? Label,
    IReadOnlyList<string>? ObservedModels = null);

public sealed record RunDetailView(
    RunSummaryView Run,
    string ManifestHash,
    JsonNode? Manifest,
    string? EngineVersion,
    IReadOnlyList<StrategyInstanceView> Strategies,
    IReadOnlyDictionary<string, int> OutcomeCounts,
    IReadOnlyList<ClassifiedErrorView>? RunErrors = null,
    IReadOnlyList<PortfolioRestrictionView>? ImpairedPortfolios = null);

/// <summary>
/// A portfolio of the run whose commits are restricted until operator action (spec 9.3, 15.3).
/// Kind "impaired": one of its commands failed with a deterministic engine error; discretionary
/// commits are refused while due events, cash flows and valuations continue. Kind "blocked": a
/// reconciliation failure stopped every commit.
/// </summary>
public sealed record PortfolioRestrictionView(
    string PortfolioId,
    string StrategyId,
    int Repetition,
    string Kind,
    string Reason,
    DateTimeOffset? Since,
    string? CommandId);

public sealed record CycleView(
    string CycleId,
    int Sequence,
    DateOnly SessionDate,
    DateTimeOffset DecisionAsOf,
    string Status,
    string? SkipReason,
    string? MarketSnapshotId,
    string? MarketSnapshotHash,
    string? CurveSnapshotId,
    DateTimeOffset? StartedAt,
    DateTimeOffset? CompletedAt,
    bool Checkpointed = false,
    int ErrorCount = 0,
    int WarningCount = 0,
    IReadOnlyList<ClassifiedErrorView>? Errors = null,
    JsonNode? Checkpoint = null);

/// <summary>
/// Runs are only compared inside one compatibility group: same data mode, risk policy, execution
/// (cost) model, run type and evaluation window. Groups are never ranked against each other.
/// </summary>
public sealed record ComparisonGroupKey(
    string DataMode,
    string RiskPolicyId,
    string ExecutionModelId,
    string? RunType = null,
    DateOnly? StartDate = null,
    DateOnly? EndDate = null);

public sealed record ComparisonEntryView(
    string StrategyId,
    string StrategyKind,
    int Repetition,
    string PortfolioId,
    string InitialCapitalUsd,
    string? LatestEquityUsd,
    string? ReturnRatio,
    DateTimeOffset? LatestValuationAt,
    bool? LatestValuationComplete,
    int ValuationCount,
    int IncompleteValuationCount,
    int DecisionCount,
    IReadOnlyDictionary<string, int> OutcomeCounts,
    int OrdersCreated,
    int Fills,
    string FeesUsd,
    string SpreadCostUsd,
    long InputTokens,
    long OutputTokens,
    string? EstimatedCostUsd,
    string? BlockedReason,
    // metrics-v1 output of POST /internal/v1/analytics/performance (computed by the research
    // engine, passed through unchanged); null with a reason when unavailable.
    JsonNode? Metrics = null,
    string? MetricsUnavailableReason = null);

/// <summary>Provenance of the evaluation metrics of a run comparison.</summary>
public sealed record ComparisonMetricsView(
    string Status,
    string? UnavailableReason,
    string? MetricsVersion,
    string? EngineVersion,
    JsonNode? Conventions,
    JsonNode? PairedComparisons);

public sealed record RunComparisonView(
    string RunId,
    string ExperimentId,
    ComparisonGroupKey Group,
    string DataModeLabel,
    string JobState,
    IReadOnlyList<ComparisonEntryView> Entries,
    IReadOnlyList<string> Notes,
    ComparisonMetricsView? Metrics = null);

public sealed record ComparisonGroupView(
    ComparisonGroupKey Group,
    string DataModeLabel,
    IReadOnlyList<RunComparisonView> Runs);

public sealed record ExperimentComparisonView(
    string ExperimentId,
    IReadOnlyList<ComparisonGroupView> Groups,
    IReadOnlyList<string> Notes);

public sealed record DecisionListFilter(
    string? CycleId = null,
    string? StrategyId = null,
    string? Outcome = null,
    int Page = 1,
    int PageSize = 50);

public sealed record DecisionSummaryView(
    string DecisionId,
    string RunId,
    string CycleId,
    string StrategyId,
    int Repetition,
    string? StrategyKind,
    string Outcome,
    string? Action,
    DateTimeOffset CompletedAt,
    string Integrity,
    IReadOnlyList<string> Reasons);

public sealed record DecisionAttemptView(
    string AttemptId,
    int AttemptNumber,
    string AgentRole,
    string Purpose,
    string Provider,
    string Model,
    int InputTokens,
    int OutputTokens,
    DateTimeOffset StartedAt,
    int DurationMs,
    string Status,
    string? RecordedResponseId,
    string? Error);

public sealed record ToolTraceView(
    string TraceId,
    string AgentRole,
    string ToolName,
    JsonNode? Request,
    JsonNode? ResponseSummary,
    string? OutputRef,
    DateTimeOffset StartedAt,
    int DurationMs,
    string Status,
    string? Error);

public sealed record UsageView(
    int GenerationCalls,
    int ToolCalls,
    int EvidenceCalls,
    int UniqueEvidenceChunks,
    int EvidenceTokens,
    int InputTokens,
    int OutputTokens,
    int DurationMs,
    string? EstimatedCostUsd,
    string? PriceScheduleId,
    string? BudgetExhausted);

public sealed record PolicyEvaluationView(
    string Source,
    string PolicyId,
    string Action,
    bool Passed,
    bool BreachMode,
    bool BootstrapExemptionApplied,
    bool? PlatformRecheckPassed,
    IReadOnlyList<string> PlatformRecheckReasons,
    string? CommandId,
    JsonNode? Evaluation);

public sealed record DecisionDetailView(
    DecisionSummaryView Decision,
    string? PortfolioId,
    string? RequestHash,
    JsonNode? InputHashes,
    JsonNode? Proposal,
    JsonNode? ResearchNote,
    JsonNode? Validation,
    JsonNode? SpecialistTasks,
    JsonNode? Versions,
    IReadOnlyList<string> EvidenceBundleIds,
    IReadOnlyList<PolicyEvaluationView> PolicyEvaluations,
    IReadOnlyList<DecisionAttemptView> Attempts,
    IReadOnlyList<ToolTraceView> ToolTraces,
    UsageView? Usage,
    IReadOnlyList<OrderView> Orders,
    string? ResultHash,
    string? EngineVersion,
    // Information cutoff and session of the decision's cycle (simulated time).
    DateTimeOffset? DecisionAsOf = null,
    DateOnly? MarketSessionDate = null,
    int? CycleSequence = null,
    DecisionFrozenInputsView? FrozenInputs = null,
    IReadOnlyList<string>? FillIds = null,
    DecisionLinksView? Links = null);

/// <summary>Frozen inputs of a decision (spec 14.4): the exact snapshots it was given.</summary>
public sealed record DecisionFrozenInputsView(
    string? PortfolioSnapshotId,
    long? PortfolioSnapshotVersion,
    string? PortfolioSnapshotHash,
    string? MarketSnapshotId,
    string? MarketSnapshotHash,
    string? CurveSnapshotId,
    string? EvidenceSnapshotId,
    string? IndexBuildId,
    string? InstrumentUniverseVersion,
    string? StrategyConfigId,
    string? RiskPolicyId,
    string? AvailabilityPolicy,
    string? DataMode);

/// <summary>Public API links to the decision's run, cycle list, portfolio and resulting orders/fills.</summary>
public sealed record DecisionLinksView(
    string Run,
    string Cycles,
    string? Portfolio,
    string? Orders);

public sealed record ValuationView(
    string ValuationId,
    long StateVersion,
    DateTimeOffset ValuationAt,
    string DataMode,
    string? CurveSnapshotId,
    string MarkPolicy,
    bool Complete,
    IReadOnlyList<string> IncompleteReasons,
    string CashUsd,
    string? BondValueUsd,
    string? ReceivablesPvUsd,
    string? PayablesPvUsd,
    string? EquityUsd,
    string? ParallelDv01Usd,
    string? EffectiveDurationYears,
    JsonNode? Detail);

public sealed record PortfolioView(
    string PortfolioId,
    string RunId,
    string StrategyId,
    int Repetition,
    string RiskPolicyId,
    string DataMode,
    string DataModeLabel,
    long Version,
    string StateHash,
    string? BlockedReason,
    DateTimeOffset? BlockedAt,
    JsonNode? State,
    int OpenOrderCount,
    int PendingSettlementCount,
    ValuationView? LatestValuation,
    DateTimeOffset UpdatedAt,
    PortfolioCashView? Cash = null,
    PaymentCalendarView? PaymentCalendar = null,
    // "impaired" (discretionary commits refused) | "blocked" (every commit refused) | null.
    string? Restriction = null);

/// <summary>
/// Cash breakdown of the current state. Display arithmetic over stored values only:
/// committed = reserved + pending settlement payables; available = settled - committed.
/// </summary>
public sealed record PortfolioCashView(
    string SettledCashUsd,
    string ReservedCashUsd,
    string PendingPayablesUsd,
    string PendingReceivablesUsd,
    string CommittedCashUsd,
    string AvailableCashUsd,
    string Basis);

/// <summary>Projected payment calendar from the research engine (never computed in .NET).</summary>
public sealed record PaymentCalendarView(
    string Status,
    string? UnavailableReason,
    JsonNode? Calendar);

public sealed record JournalFilter(
    string? Account = null,
    string? EventType = null,
    long? FromVersion = null,
    long? ToVersion = null,
    int Page = 1,
    int PageSize = 50);

public sealed record JournalLineView(
    string LineId,
    string Account,
    string? SecurityId,
    string DebitUsd,
    string CreditUsd,
    string? Memo);

public sealed record JournalView(
    string JournalId,
    string EventId,
    string EventType,
    DateTimeOffset EffectiveAt,
    string Template,
    long CommittedVersion,
    string CommandId,
    IReadOnlyList<JournalLineView> Lines);

public sealed record OrderFilter(
    string? Status = null,
    string? SecurityId = null,
    string? DecisionId = null,
    int Page = 1,
    int PageSize = 50);

public sealed record FillView(
    string FillId,
    DateTimeOffset ExecutedAt,
    string ObservationId,
    string QuoteKind,
    string ReferenceCleanPricePer100,
    string ExecutionCleanPricePer100,
    string DirtyPricePer100,
    string ConsiderationUsd,
    string FeesUsd,
    DateOnly SettlementDate,
    string TimingLabel);

public sealed record OrderView(
    string OrderId,
    string PortfolioId,
    string DecisionId,
    string SecurityId,
    string Side,
    string Face,
    DateTimeOffset SubmittedAt,
    DateOnly EligibleSessionDate,
    DateTimeOffset ExpiresAt,
    string Status,
    string? StatusReason,
    string ReservedCashUsd,
    bool Bootstrap,
    long CreatedInVersion,
    long LastUpdatedVersion,
    FillView? Fill);

public static class DataModeLabels
{
    public static string For(string dataMode) => dataMode switch
    {
        "synthetic_curve" => "Synthetic curve simulation (model prices, not market quotes)",
        "observed_security" => "Observed-security paper trading",
        _ => dataMode,
    };
}
