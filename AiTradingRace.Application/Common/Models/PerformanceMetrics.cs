namespace AiTradingRace.Application.Common.Models;

/// <summary>
/// Performance metrics calculated from an agent's trading history and equity curve.
/// </summary>
public record PerformanceMetrics(
    Guid AgentId,
    decimal InitialValue,
    decimal CurrentValue,
    decimal TotalReturn,
    decimal PercentReturn,
    decimal MaxDrawdown,
    decimal? SharpeRatio,
    int TotalTrades,
    int WinningTrades,
    int LosingTrades,
    decimal WinRate,
    DateTimeOffset CalculatedAt);
