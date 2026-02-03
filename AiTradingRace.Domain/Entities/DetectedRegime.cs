namespace AiTradingRace.Domain.Entities;

/// <summary>
/// Represents a detected market regime period for historical tracking
/// </summary>
public class DetectedRegime
{
    /// <summary>
    /// Unique identifier for the detected regime entry
    /// </summary>
    public int Id { get; set; }
    
    /// <summary>
    /// ID of the regime (e.g., "VOLATILE", "BULLISH")
    /// </summary>
    public string RegimeId { get; set; } = string.Empty;
    
    /// <summary>
    /// Timestamp when the regime was detected
    /// </summary>
    public DateTime DetectedAt { get; set; }
    
    /// <summary>
    /// Timestamp when the regime ended (null if still active)
    /// </summary>
    public DateTime? EndedAt { get; set; }
    
    /// <summary>
    /// Calculated volatility at detection time
    /// </summary>
    public decimal Volatility { get; set; }
    
    /// <summary>
    /// 7-day moving average at detection time
    /// </summary>
    public decimal? MA7 { get; set; }
    
    /// <summary>
    /// 30-day moving average at detection time
    /// </summary>
    public decimal? MA30 { get; set; }
    
    /// <summary>
    /// Asset symbol (e.g., "BTC") or "Market" for overall market regime
    /// </summary>
    public string Asset { get; set; } = string.Empty;
    
    /// <summary>
    /// Timestamp when the entry was created
    /// </summary>
    public DateTime CreatedAt { get; set; }
}
