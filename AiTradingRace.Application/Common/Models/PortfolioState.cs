namespace AiTradingRace.Application.Common.Models;

public record PortfolioState(
    Guid PortfolioId,
    Guid AgentId,
    decimal Cash,
    IReadOnlyList<PositionSnapshot> Positions,
    DateTimeOffset AsOf,
    decimal TotalValue);

public record PositionSnapshot(
    string AssetSymbol,
    decimal Quantity,
    decimal AveragePrice,
    decimal CurrentPrice);

