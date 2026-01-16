namespace AiTradingRace.Application.Common.Models;

/// <summary>
/// Data transfer object for equity snapshots returned by API endpoints.
/// </summary>
public record EquitySnapshotDto(
    Guid Id,
    Guid PortfolioId,
    Guid AgentId,
    DateTimeOffset CapturedAt,
    decimal TotalValue,
    decimal CashValue,
    decimal PositionsValue,
    decimal UnrealizedPnL,
    decimal? PercentChange);
