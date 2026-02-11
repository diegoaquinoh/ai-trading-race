using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Functions.Models;

/// <summary>
/// Request to ingest market data.
/// </summary>
public record IngestMarketDataRequest(
    DateTimeOffset Timestamp,
    string OrchestratorInstanceId);

/// <summary>
/// Result of market data ingestion.
/// </summary>
public record MarketDataResult(
    Guid BatchId,
    DateTimeOffset Timestamp,
    Dictionary<string, decimal> Prices);

/// <summary>
/// Request to capture equity snapshots for all agents.
/// </summary>
public record CaptureSnapshotsRequest(Guid BatchId, DateTimeOffset Timestamp);

/// <summary>
/// Request to run a single agent's decision logic.
/// </summary>
public record AgentDecisionRequest(
    Guid AgentId,
    Guid BatchId,
    DateTimeOffset Timestamp);

/// <summary>
/// Result of an agent's decision.
/// </summary>
public record AgentDecisionResult(
    Guid AgentId,
    string AgentName,
    AgentDecision Decision,
    decimal PortfolioValue,
    bool Success,
    string? ErrorMessage = null);

/// <summary>
/// Request to execute trades from agent decisions.
/// </summary>
public record ExecuteTradesRequest(
    List<AgentDecisionResult> Decisions,
    DateTimeOffset Timestamp);

/// <summary>
/// Final result of a market cycle orchestration.
/// </summary>
public record MarketCycleResult(
    Guid BatchId,
    DateTimeOffset Timestamp,
    int SnapshotCount,
    bool WasDecisionCycle,
    int AgentsRun,
    int TradesExecuted,
    TimeSpan Duration);
