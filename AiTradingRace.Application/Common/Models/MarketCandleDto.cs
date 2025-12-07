namespace AiTradingRace.Application.Common.Models;

public record MarketCandleDto(
    string AssetSymbol,
    DateTime TimestampUtc,
    decimal Open,
    decimal High,
    decimal Low,
    decimal Close,
    decimal Volume);

