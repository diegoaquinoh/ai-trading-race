namespace AiTradingRace.Application.Common.Models;

public record TradeOrder(
    string AssetSymbol,
    TradeSide Side,
    decimal Quantity,
    decimal? LimitPrice = null);

