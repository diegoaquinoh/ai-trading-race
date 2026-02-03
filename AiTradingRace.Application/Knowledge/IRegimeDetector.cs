namespace AiTradingRace.Application.Knowledge;

/// <summary>
/// Service for detecting market regimes based on price data
/// </summary>
public interface IRegimeDetector
{
    /// <summary>
    /// Detect the current market regime for an asset
    /// </summary>
    Task<MarketRegime> DetectRegimeAsync(string assetSymbol, DateTime fromDate, DateTime toDate);
    
    /// <summary>
    /// Get historical regime changes for an asset
    /// </summary>
    Task<List<Domain.Entities.DetectedRegime>> GetHistoricalRegimesAsync(string assetSymbol, DateTime fromDate);
}

/// <summary>
/// Represents a detected market regime
/// </summary>
public class MarketRegime
{
    /// <summary>
    /// ID of the regime (e.g., "VOLATILE", "BULLISH")
    /// </summary>
    public string RegimeId { get; set; } = string.Empty;
    
    /// <summary>
    /// Human-readable name
    /// </summary>
    public string Name { get; set; } = string.Empty;
    
    /// <summary>
    /// Calculated volatility (standard deviation of returns)
    /// </summary>
    public decimal Volatility { get; set; }
    
    /// <summary>
    /// 7-day moving average
    /// </summary>
    public decimal? MA7 { get; set; }
    
    /// <summary>
    /// 30-day moving average
    /// </summary>
    public decimal? MA30 { get; set; }
    
    /// <summary>
    /// When the regime was detected
    /// </summary>
    public DateTime DetectedAt { get; set; }
    
    /// <summary>
    /// Whether the regime is currently active
    /// </summary>
    public bool IsActive { get; set; }
}
