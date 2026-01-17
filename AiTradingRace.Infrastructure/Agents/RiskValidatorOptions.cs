namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Configuration options for server-side risk validation.
/// These constraints are enforced regardless of AI agent instructions.
/// </summary>
public sealed class RiskValidatorOptions
{
    public const string SectionName = "RiskValidator";

    /// <summary>
    /// Maximum percentage of total portfolio value allowed in a single asset.
    /// Default: 0.50 (50%)
    /// </summary>
    public decimal MaxPositionSizePercent { get; set; } = 0.50m;

    /// <summary>
    /// Minimum cash amount that must be kept liquid at all times.
    /// Default: $100
    /// </summary>
    public decimal MinCashReserve { get; set; } = 100m;

    /// <summary>
    /// Maximum value (USD) for a single trade.
    /// Default: $5,000
    /// </summary>
    public decimal MaxSingleTradeValue { get; set; } = 5_000m;

    /// <summary>
    /// Minimum value (USD) for an order to be accepted (avoids dust trades).
    /// Default: $10
    /// </summary>
    public decimal MinOrderValue { get; set; } = 10m;

    /// <summary>
    /// Whitelist of assets that can be traded.
    /// Default: ["BTC", "ETH"]
    /// </summary>
    public List<string> AllowedAssets { get; set; } = new() { "BTC", "ETH" };

    /// <summary>
    /// Maximum number of orders an agent can submit in one execution cycle.
    /// Default: 5
    /// </summary>
    public int MaxOrdersPerCycle { get; set; } = 5;

    /// <summary>
    /// Whether short selling or margin trading is permitted.
    /// Default: false
    /// </summary>
    public bool AllowLeverage { get; set; } = false;

    /// <summary>
    /// Maximum acceptable slippage percentage (future use).
    /// Default: 0.02 (2%)
    /// </summary>
    public decimal MaxSlippagePercent { get; set; } = 0.02m;
}
