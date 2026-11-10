using System.Text.Json;
using System.Text.Json.Nodes;

namespace AiTradingRace.Application.FixedIncome.Contracts;

// Request bodies for the Python internal endpoints that do not yet have a
// Pydantic contract. The Python API (workstream A/B/E) must accept exactly these
// camelCase fields; responses are passed through as opaque JSON objects.

/// <summary>POST /internal/v1/analytics/price.</summary>
public sealed record PriceRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public string CurveSnapshotId { get; init; } = string.Empty;
    public string ValuationDate { get; init; } = string.Empty;
    public string? SettlementDate { get; init; }
    public List<string> SecurityIds { get; init; } = new();
    public string? FaceUsd { get; init; }
}

/// <summary>POST /internal/v1/analytics/risk.</summary>
public sealed record RiskRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public JsonElement PortfolioState { get; init; }
    public string PortfolioStateHash { get; init; } = string.Empty;
    public string CurveSnapshotId { get; init; } = string.Empty;
    public string ValuationDate { get; init; } = string.Empty;
    public List<string> ScenarioIds { get; init; } = new();
}

/// <summary>POST /internal/v1/evidence/retrieve.</summary>
public sealed record EvidenceRetrieveRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public string Query { get; init; } = string.Empty;
    public string AsOf { get; init; } = string.Empty;
    public string EvidenceSnapshotId { get; init; } = string.Empty;
    public string? IndexBuildId { get; init; }
    public string RetrievalMode { get; init; } = "hybrid_rag_v1";
    public int MaxChunks { get; init; } = 12;
    public string? ExperimentId { get; init; }
    public string? StrategyId { get; init; }
}

/// <summary>POST /internal/v1/research-notes (informational; no order authority).</summary>
public sealed record ResearchNoteRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public string Question { get; init; } = string.Empty;
    public string? AsOf { get; init; }
    public string? EvidenceSnapshotId { get; init; }
    public string? IndexBuildId { get; init; }
    public string RetrievalMode { get; init; } = "hybrid_rag_v1";
    public string ResponseMode { get; init; } = "recorded_replay";
    public string? RequestedBy { get; init; }
}

/// <summary>POST /internal/v1/admin/ingestions.</summary>
public sealed record IngestionRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public List<string> SourceIds { get; init; } = new();
    public string? Reason { get; init; }
    public string? RequestedBy { get; init; }
}

/// <summary>POST /internal/v1/admin/index-builds.</summary>
public sealed record IndexBuildRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public string? EvidenceSnapshotId { get; init; }
    public string? BaseIndexBuildId { get; init; }
    public bool ValidateOnly { get; init; }
    public string? Reason { get; init; }
    public string? RequestedBy { get; init; }
}

/// <summary>
/// POST /internal/v1/analytics/performance (app/v1/schemas.py PerformanceRequest). Carries the
/// values the platform stores; every evaluation metric is computed by the research engine
/// (research_engine.experiments.metrics), never in .NET.
/// </summary>
public sealed record PerformanceRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public string? RunId { get; init; }
    public List<PerformancePortfolioDto> Portfolios { get; init; } = new();
    public List<PerformancePairDto> Pairs { get; init; } = new();
    public RiskFreeSeriesDto? RiskFree { get; init; }
    public int MinSharpeObservations { get; init; } = 60;
    public int AnnualizeMinObservations { get; init; } = 252;
    public BootstrapPolicyRequestDto Bootstrap { get; init; } = new();
    public bool IncludeDailyReturns { get; init; }
}

public sealed record PerformancePortfolioDto
{
    public string PortfolioId { get; init; } = string.Empty;
    public string? StrategyId { get; init; }
    public int Repetition { get; init; }
    public List<PerformanceValuationDto> Valuations { get; init; } = new();
    public List<PerformanceFillDto> Fills { get; init; } = new();
    public List<PerformanceCashFlowDto> CashFlows { get; init; } = new();
    public int OrdersCreated { get; init; }
    public Dictionary<string, int> OrderStatusCounts { get; init; } = new();
    public int PolicyEvaluations { get; init; }
    public int PolicyRejections { get; init; }
    public Dictionary<string, int> DecisionOutcomes { get; init; } = new();
}

public sealed record PerformanceValuationDto
{
    public string ValuationId { get; init; } = string.Empty;
    public string ValuationAt { get; init; } = string.Empty;
    public long StateVersion { get; init; }
    public bool Complete { get; init; }
    public string CashUsd { get; init; } = "0";
    public string? EquityUsd { get; init; }
    public string? BondValueUsd { get; init; }
    public string? ParallelDv01Usd { get; init; }
    public string? EffectiveDurationYears { get; init; }
    public List<PerformanceMarkDto> Marks { get; init; } = new();
    public PerformanceLedgerDto Ledger { get; init; } = new();
}

/// <summary>A stored valuation mark (economic face and accrued per 100, as received).</summary>
public sealed record PerformanceMarkDto
{
    public string EconomicFace { get; init; } = "0";
    public string? AccruedPer100 { get; init; }
}

/// <summary>Cumulative balances of the committed state that produced the valuation (as stored).</summary>
public sealed record PerformanceLedgerDto
{
    public string ExternalCapitalUsd { get; init; } = "0";
    public string InterestIncomeUsd { get; init; } = "0";
    public string RealizedGainLossUsd { get; init; } = "0";
    public string BookedUnrealizedUsd { get; init; } = "0";
    public string TransactionFeesUsd { get; init; } = "0";
    public string SpreadCostUsd { get; init; } = "0";
    public List<string> LotAccruedPurchasedUsd { get; init; } = new();
}

public sealed record PerformanceFillDto
{
    public string FillId { get; init; } = string.Empty;
    public string ExecutedAt { get; init; } = string.Empty;
    public string ConsiderationUsd { get; init; } = "0";
    public string FeesUsd { get; init; } = "0";
    public string SpreadCostUsd { get; init; } = "0";
}

public sealed record PerformanceCashFlowDto
{
    public string CashFlowId { get; init; } = string.Empty;
    public string Kind { get; init; } = string.Empty;
    public string PaymentDate { get; init; } = string.Empty;
    public string AmountUsd { get; init; } = "0";
}

public sealed record PerformancePairDto
{
    public string PortfolioId { get; init; } = string.Empty;
    public string VersusPortfolioId { get; init; } = string.Empty;
}

public sealed record RiskFreeObservationDto
{
    public string SessionDate { get; init; } = string.Empty;
    public string DailyReturn { get; init; } = "0";
}

public sealed record RiskFreeSeriesDto
{
    public string SeriesId { get; init; } = string.Empty;
    public List<RiskFreeObservationDto> Observations { get; init; } = new();
}

public sealed record BootstrapPolicyRequestDto
{
    public int BlockLength { get; init; } = 5;
    public int Resamples { get; init; } = 1000;
    public int Seed { get; init; }
}

/// <summary>POST /internal/v1/instruments/payment-calendar (projected payments of a stored state).</summary>
public sealed record PaymentCalendarRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string RequestId { get; init; } = string.Empty;
    public JsonElement PortfolioState { get; init; }
    public string PortfolioStateHash { get; init; } = string.Empty;
    public string? After { get; init; }
    public int HorizonDays { get; init; } = 366;
}

/// <summary>
/// GET /internal/v1/capabilities response: the fields .NET reads. Everything
/// else is preserved in <see cref="Raw"/> and surfaced on the health endpoint.
/// </summary>
public sealed record CapabilitiesDto
{
    public string EngineVersion { get; init; } = string.Empty;
    public bool Ready { get; init; }
    public List<string> SchemaVersions { get; init; } = new();
    public JsonObject Raw { get; init; } = new();
}

/// <summary>Opaque research-engine response (instrument lists, curves, bundles, notes, jobs).</summary>
public sealed record ResearchEngineDocument(int StatusCode, JsonNode? Body);
