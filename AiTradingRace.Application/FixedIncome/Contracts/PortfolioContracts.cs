using System.Text.Json;
using System.Text.Json.Serialization;

namespace AiTradingRace.Application.FixedIncome.Contracts;

// C# mirrors of ai-trading-race-ml/research_engine/contracts/portfolio.py.
// Decimals are decimal strings, instants are UTC strings ending in "Z", dates are
// "YYYY-MM-DD" strings. Property names serialize to the camelCase wire names.
// These DTOs are for reading/building payloads; hashes are computed over the raw
// JSON (see RawContractJson), never over re-serialized DTOs.

public sealed record RiskPolicyDto
{
    public string PolicyId { get; init; } = "treasury-long-only-v1";
    public string InitialCapitalUsd { get; init; } = "1000000";
    public bool LongOnly { get; init; } = true;
    public bool LeverageAllowed { get; init; }
    public string MinCashRatio { get; init; } = "0.05";
    public string MaxSingleSecurityRatio { get; init; } = "0.40";
    public string MaxParallelDv01UsdPerMillionNav { get; init; } = "600";
    public string MaxDailyTurnoverRatio { get; init; } = "0.20";
    public int MaxOrdersPerDecision { get; init; } = 6;
    public string MinWeightChange { get; init; } = "0.02";
    public string WeightSumTolerance { get; init; } = "0.000001";
    public int MaxMarkAgeBusinessDays { get; init; } = 1;
    public bool BootstrapTurnoverExemption { get; init; } = true;
    public string ProjectionMode { get; init; } = "disabled";
    public string BreachPolicy { get; init; } = "block_risk_increasing_v1";
}

public sealed record ExecutionModelDto
{
    public string ExecutionModelId { get; init; } = "synthetic-half-spread-0.02-v1";
    public string HalfSpreadPer100 { get; init; } = "0.02";
    public string SlippagePer100 { get; init; } = "0";
    public string CommissionUsdPerMillionFace { get; init; } = "0";
    public string TimeInForce { get; init; } = "next_session_only";
    public string FillTiming { get; init; } = "next_session_close_daily";
    public string FundingRule { get; init; } = "settled_cash_reserve_commitments_v1";
    public string BatchPriority { get; init; } = "sells_first_then_security_id_v1";
    public string CashInterestRate { get; init; } = "0";
    public string FaceSizing { get; init; } = "fixed_at_submission_v1";
}

public sealed record LotDto
{
    public string LotId { get; init; } = string.Empty;
    public string SecurityId { get; init; } = string.Empty;
    public string Face { get; init; } = "0";
    public string TradeDate { get; init; } = string.Empty;
    public string SettlementDate { get; init; } = string.Empty;
    public string CleanPricePer100 { get; init; } = "0";
    public string PrincipalCostUsd { get; init; } = "0";
    public string AccruedPurchasedUsd { get; init; } = "0";
}

public sealed record PositionDto
{
    public string SecurityId { get; init; } = string.Empty;
    public string EconomicFace { get; init; } = "0";
    public string SettledFace { get; init; } = "0";
    public List<LotDto> Lots { get; init; } = new();
}

public sealed record OrderIntentDto
{
    public string OrderId { get; init; } = string.Empty;
    public string DecisionId { get; init; } = string.Empty;
    public string SecurityId { get; init; } = string.Empty;
    public string Side { get; init; } = string.Empty;
    public string Face { get; init; } = "0";
    public string SubmittedAt { get; init; } = string.Empty;
    public string EligibleSessionDate { get; init; } = string.Empty;
    public string ExpiresAt { get; init; } = string.Empty;
    public string Status { get; init; } = "ACCEPTED";
    public string ReservedCashUsd { get; init; } = "0";
    public int BatchPriority { get; init; }
    public string? StatusReason { get; init; }
    public bool Bootstrap { get; init; }
}

public sealed record FillDto
{
    public string FillId { get; init; } = string.Empty;
    public string OrderId { get; init; } = string.Empty;
    public string SecurityId { get; init; } = string.Empty;
    public string Side { get; init; } = string.Empty;
    public string Face { get; init; } = "0";
    public string ExecutedAt { get; init; } = string.Empty;
    public string ObservationId { get; init; } = string.Empty;
    public string QuoteKind { get; init; } = string.Empty;
    public string ReferenceCleanPricePer100 { get; init; } = "0";
    public string ExecutionCleanPricePer100 { get; init; } = "0";
    public string AccruedPer100 { get; init; } = "0";
    public string DirtyPricePer100 { get; init; } = "0";
    public string HalfSpreadPer100 { get; init; } = "0";
    public string SettlementDate { get; init; } = string.Empty;
    public string ConsiderationUsd { get; init; } = "0";
    public string FeesUsd { get; init; } = "0";
    public string SpreadCostUsd { get; init; } = "0";
    public string TimingLabel { get; init; } = "next_session_close_daily";
}

public sealed record PendingSettlementDto
{
    public string SettlementId { get; init; } = string.Empty;
    public string FillId { get; init; } = string.Empty;
    public string SecurityId { get; init; } = string.Empty;
    public string Side { get; init; } = string.Empty;
    public string Face { get; init; } = "0";
    public string SettlementDate { get; init; } = string.Empty;
    public string CashUsd { get; init; } = "0";
}

public sealed record CashFlowRecordDto
{
    public string CashFlowId { get; init; } = string.Empty;
    public string SecurityId { get; init; } = string.Empty;
    public string Kind { get; init; } = string.Empty;
    public string PaymentDate { get; init; } = string.Empty;
    public string EntitledFace { get; init; } = "0";
    public string AmountUsd { get; init; } = "0";
}

public sealed record PortfolioStateDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string PortfolioId { get; init; } = string.Empty;
    public string StrategyId { get; init; } = string.Empty;
    public string RunId { get; init; } = string.Empty;
    public long Version { get; init; }
    public string AsOf { get; init; } = string.Empty;
    public string Currency { get; init; } = "USD";
    public string CashUsd { get; init; } = "0";
    public string ReservedCashUsd { get; init; } = "0";
    public List<PositionDto> Positions { get; init; } = new();
    public List<OrderIntentDto> OpenOrders { get; init; } = new();
    public List<PendingSettlementDto> PendingSettlements { get; init; } = new();
    public string ExternalCapitalUsd { get; init; } = "0";
    public string InterestIncomeUsd { get; init; } = "0";
    public string RealizedGainLossUsd { get; init; } = "0";
    public string TransactionFeesUsd { get; init; } = "0";
    public string SpreadCostUsd { get; init; } = "0";
    public string BookedUnrealizedUsd { get; init; } = "0";
    public string? CashFlowsProcessedThrough { get; init; }
    public string? LastValuationId { get; init; }
    public List<string> RiskBreaches { get; init; } = new();
    public string? BlockedReason { get; init; }
}

/// <summary>
/// Common header of every portfolio event (discriminated by <see cref="Type"/>).
/// Type-specific fields are kept in <see cref="Extra"/>.
/// </summary>
public sealed record PortfolioEventDto
{
    public string EventId { get; init; } = string.Empty;
    public string Type { get; init; } = string.Empty;
    public string EffectiveAt { get; init; } = string.Empty;
    public int Priority { get; init; }

    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; init; }
}

public sealed record JournalLineDto
{
    public string LineId { get; init; } = string.Empty;
    public string Account { get; init; } = string.Empty;
    public string? SecurityId { get; init; }
    public string DebitUsd { get; init; } = "0";
    public string CreditUsd { get; init; } = "0";
    public string? Memo { get; init; }
}

public sealed record JournalDto
{
    public string JournalId { get; init; } = string.Empty;
    public string EventId { get; init; } = string.Empty;
    public string EventType { get; init; } = string.Empty;
    public string EffectiveAt { get; init; } = string.Empty;
    public string Template { get; init; } = string.Empty;
    public List<JournalLineDto> Lines { get; init; } = new();
}

public sealed record PolicyCheckDto
{
    public string CheckId { get; init; } = string.Empty;
    public string? Limit { get; init; }
    public string? Observed { get; init; }
    public string Unit { get; init; } = string.Empty;
    public bool Passed { get; init; }
    public string? Reason { get; init; }
}

public sealed record TargetWeightDto
{
    public string SecurityId { get; init; } = string.Empty;
    public string Weight { get; init; } = "0";
}

public sealed record SizedOrderDto
{
    public string SecurityId { get; init; } = string.Empty;
    public string Side { get; init; } = string.Empty;
    public string Face { get; init; } = "0";
    public string EstimatedDirtyPricePer100 { get; init; } = "0";
    public string EstimatedConsiderationUsd { get; init; } = "0";
}

public sealed record PolicyEvaluationDto
{
    public string PolicyId { get; init; } = string.Empty;
    public string DecisionId { get; init; } = string.Empty;
    public string Action { get; init; } = string.Empty;
    public bool Passed { get; init; }
    public bool BreachMode { get; init; }
    public bool BootstrapExemptionApplied { get; init; }
    public List<TargetWeightDto> OriginalTargets { get; init; } = new();
    public List<TargetWeightDto> NormalizedTargets { get; init; } = new();
    public List<string> NormalizationNotes { get; init; } = new();
    public List<SizedOrderDto> SizedOrders { get; init; } = new();
    public List<string> RejectedReasons { get; init; } = new();
    public List<PolicyCheckDto> Checks { get; init; } = new();
    public string? PostTradeNavUsd { get; init; }
    public string? PostTradeCashRatio { get; init; }
    public string? PostTradeMaxSecurityRatio { get; init; }
    public string? PostTradeParallelDv01Usd { get; init; }

    /// <summary>
    /// Pre-trade values of the limited metrics (filled whenever the post-trade metrics are). Used by
    /// the breach policy: a limit already breached before the decision may stay breached only when
    /// the order set does not worsen it (spec 9.3).
    /// </summary>
    public string? PreTradeNavUsd { get; init; }
    public string? PreTradeCashRatio { get; init; }
    public string? PreTradeMaxSecurityRatio { get; init; }
    public string? PreTradeParallelDv01Usd { get; init; }

    public string? TurnoverRatio { get; init; }
    public int OrderCount { get; init; }
    public List<string> CalculationIds { get; init; } = new();
}

public sealed record PositionMarkDto
{
    public string SecurityId { get; init; } = string.Empty;
    public string EconomicFace { get; init; } = "0";
    public string MarkType { get; init; } = string.Empty;
    public string? CleanPricePer100 { get; init; }
    public string? AccruedPer100 { get; init; }
    public string? PvDirtyUsd { get; init; }
    public string? ObservedAt { get; init; }
    public int? MarkAgeBusinessDays { get; init; }
    public bool Stale { get; init; }
    public string? CalculationId { get; init; }
}

public sealed record ValuationSnapshotDto
{
    public string ValuationId { get; init; } = string.Empty;
    public string PortfolioId { get; init; } = string.Empty;
    public long StateVersion { get; init; }
    public string ValuationAt { get; init; } = string.Empty;
    public string DataMode { get; init; } = string.Empty;
    public string? CurveSnapshotId { get; init; }
    public string MarkPolicy { get; init; } = "synthetic_curve_model_v1";
    public bool Complete { get; init; }
    public List<string> IncompleteReasons { get; init; } = new();
    public string CashUsd { get; init; } = "0";
    public string? BondValueUsd { get; init; }
    public string? ReceivablesPvUsd { get; init; }
    public string? PayablesPvUsd { get; init; }
    public string? EquityUsd { get; init; }
    public List<PositionMarkDto> Marks { get; init; } = new();
    public string? ParallelDv01Usd { get; init; }
    public string? EffectiveDurationYears { get; init; }
    public List<string> CalculationIds { get; init; } = new();
}

public sealed record ReconciliationReportDto
{
    public bool Ok { get; init; }
    public bool JournalsBalanced { get; init; }
    public string LedgerCashUsd { get; init; } = "0";
    public string StateCashUsd { get; init; } = "0";
    public bool LedgerPrincipalFaceCheck { get; init; }
    public string BookEquityUsd { get; init; } = "0";
    public string? EconomicEquityUsd { get; init; }
    public string? DifferenceUsd { get; init; }
    public List<string> Messages { get; init; } = new();
}

public sealed record MarketSnapshotRefDto
{
    public string MarketSnapshotId { get; init; } = string.Empty;
    public string ContentHash { get; init; } = string.Empty;
    public string? CurveSnapshotId { get; init; }
    public string SessionDate { get; init; } = string.Empty;
    public string DataMode { get; init; } = string.Empty;
}

/// <summary>
/// POST /internal/v1/simulation/transitions request. <see cref="PortfolioState"/> is
/// the stored canonical state JSON sent back verbatim.
/// </summary>
public sealed record TransitionRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string CommandId { get; init; } = string.Empty;
    public string CommandType { get; init; } = string.Empty;
    public JsonElement PortfolioState { get; init; }
    public string PortfolioStateHash { get; init; } = string.Empty;
    public string AdvanceTo { get; init; } = string.Empty;
    public MarketSnapshotRefDto? MarketSnapshot { get; init; }
    public RiskPolicyDto RiskPolicy { get; init; } = new();
    public ExecutionModelDto ExecutionModel { get; init; } = new();
    public string InstrumentUniverseVersion { get; init; } = string.Empty;
    public string? DecisionId { get; init; }
    public string? Action { get; init; }
    public List<TargetWeightDto> TargetWeights { get; init; } = new();
    public string? CapitalAmountUsd { get; init; }
}

/// <summary>Signed transition proposal returned by the research engine.</summary>
public sealed record TransitionProposalDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string ProposalId { get; init; } = string.Empty;
    public string CommandId { get; init; } = string.Empty;
    public string CommandType { get; init; } = string.Empty;
    public string PortfolioId { get; init; } = string.Empty;
    public string StrategyId { get; init; } = string.Empty;
    public string RunId { get; init; } = string.Empty;
    public long ExpectedVersion { get; init; }
    public long NewVersion { get; init; }
    public bool NoOp { get; init; }
    public string EngineVersion { get; init; } = string.Empty;
    public string EventPriorityTable { get; init; } = FiContract.EventPriorityTable;
    public string RequestHash { get; init; } = string.Empty;
    public Dictionary<string, string> InputHashes { get; init; } = new();
    public List<PortfolioEventDto> Events { get; init; } = new();
    public List<JournalDto> Journals { get; init; } = new();
    public PortfolioStateDto NewState { get; init; } = new();
    public string NewStateHash { get; init; } = string.Empty;
    public List<OrderIntentDto> OrdersCreated { get; init; } = new();
    public List<OrderIntentDto> OrderStatusChanges { get; init; } = new();
    public List<FillDto> Fills { get; init; } = new();
    public List<PendingSettlementDto> SettlementsCreated { get; init; } = new();
    public List<string> SettlementsCompleted { get; init; } = new();
    public List<CashFlowRecordDto> CashFlows { get; init; } = new();
    public PolicyEvaluationDto? PolicyEvaluation { get; init; }
    public ValuationSnapshotDto? Valuation { get; init; }
    public ReconciliationReportDto Reconciliation { get; init; } = new();
    public string? ProposalHash { get; init; }
    public string? Signature { get; init; }
}
