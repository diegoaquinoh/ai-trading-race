namespace AiTradingRace.Application.Common.Models;

/// <summary>
/// DTO for raw candle data from an external API (before mapping to domain entity).
/// </summary>
/// <param name="TimestampUtc">Candle timestamp in UTC.</param>
/// <param name="Open">Opening price.</param>
/// <param name="High">Highest price during the candle period.</param>
/// <param name="Low">Lowest price during the candle period.</param>
/// <param name="Close">Closing price.</param>
public record ExternalCandleDto(
    DateTimeOffset TimestampUtc,
    decimal Open,
    decimal High,
    decimal Low,
    decimal Close);
