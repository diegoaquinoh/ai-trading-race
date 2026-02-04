using AiTradingRace.Application.Knowledge;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.Knowledge;

/// <summary>
/// Detects market regimes based on volatility and moving averages
/// </summary>
public class VolatilityBasedRegimeDetector : IRegimeDetector
{
    private readonly IMarketDataProvider _marketDataProvider;
    private readonly TradingDbContext _context;
    private readonly ILogger<VolatilityBasedRegimeDetector> _logger;

    public VolatilityBasedRegimeDetector(
        IMarketDataProvider marketDataProvider,
        TradingDbContext context,
        ILogger<VolatilityBasedRegimeDetector> logger)
    {
        _marketDataProvider = marketDataProvider;
        _context = context;
        _logger = logger;
    }

    public async Task<MarketRegime> DetectRegimeAsync(
        string assetSymbol,
        DateTime fromDate,
        DateTime toDate)
    {
        _logger.LogInformation(
            "Detecting market regime for {Asset} from {FromDate} to {ToDate}",
            assetSymbol, fromDate, toDate);

        // Get market asset
        var asset = await _context.MarketAssets
            .FirstOrDefaultAsync(a => a.Symbol == assetSymbol);

        if (asset == null)
        {
            _logger.LogWarning("Asset {Asset} not found", assetSymbol);
            return new MarketRegime
            {
                RegimeId = "UNKNOWN",
                Name = "Unknown Asset",
                DetectedAt = DateTime.UtcNow,
                IsActive = false
            };
        }

        // Get candles
        var candles = await _context.MarketCandles
            .Where(c => c.MarketAssetId == asset.Id
                && c.TimestampUtc >= fromDate
                && c.TimestampUtc <= toDate)
            .OrderBy(c => c.TimestampUtc)
            .Select(c => new { c.TimestampUtc, c.Close })
            .ToListAsync();

        if (candles.Count < 7)
        {
            _logger.LogWarning(
                "Insufficient data for {Asset}: only {Count} candles",
                assetSymbol, candles.Count);

            return new MarketRegime
            {
                RegimeId = "UNKNOWN",
                Name = "Insufficient Data",
                DetectedAt = DateTime.UtcNow,
                IsActive = true
            };
        }

        // Calculate daily returns
        var returns = new List<decimal>();
        for (int i = 1; i < candles.Count; i++)
        {
            var dailyReturn = (candles[i].Close - candles[i - 1].Close) / candles[i - 1].Close;
            returns.Add(dailyReturn); // Don't take absolute value - volatility measures deviation from mean
        }

        // Calculate volatility (standard deviation of returns)
        var volatility = CalculateStandardDeviation(returns);

        // Calculate moving averages
        var prices = candles.Select(c => c.Close).ToList();
        var ma7 = CalculateMovingAverage(prices, 7);
        var ma30 = prices.Count >= 30 ? CalculateMovingAverage(prices, 30) : (decimal?)null;

        _logger.LogDebug(
            "Calculated metrics for {Asset}: Volatility={Volatility:P2}, MA7={MA7}, MA30={MA30}",
            assetSymbol, volatility, ma7, ma30);

        // Determine regime
        string regimeId;
        string name;

        if (volatility > 0.05m)
        {
            regimeId = "VOLATILE";
            name = "Volatile Market";
            _logger.LogInformation(
                "Detected VOLATILE regime for {Asset} (volatility: {Volatility:P2})",
                assetSymbol, volatility);
        }
        else if (ma30.HasValue && ma7 > ma30.Value * 1.02m) // 2% above MA30
        {
            regimeId = "BULLISH";
            name = "Bullish Trend";
            _logger.LogInformation(
                "Detected BULLISH regime for {Asset} (MA7: {MA7} > MA30: {MA30})",
                assetSymbol, ma7, ma30);
        }
        else if (ma30.HasValue && ma7 < ma30.Value * 0.98m) // 2% below MA30
        {
            regimeId = "BEARISH";
            name = "Bearish Trend";
            _logger.LogInformation(
                "Detected BEARISH regime for {Asset} (MA7: {MA7} < MA30: {MA30})",
                assetSymbol, ma7, ma30);
        }
        else
        {
            regimeId = "STABLE";
            name = "Stable Market";
            _logger.LogInformation(
                "Detected STABLE regime for {Asset} (volatility: {Volatility:P2})",
                assetSymbol, volatility);
        }

        // Persist detected regime
        var detectedRegime = new DetectedRegime
        {
            RegimeId = regimeId,
            DetectedAt = DateTime.UtcNow,
            Volatility = volatility,
            MA7 = ma7,
            MA30 = ma30,
            Asset = assetSymbol,
            CreatedAt = DateTime.UtcNow
        };

        _context.DetectedRegimes.Add(detectedRegime);
        await _context.SaveChangesAsync();

        return new MarketRegime
        {
            RegimeId = regimeId,
            Name = name,
            Volatility = volatility,
            MA7 = ma7,
            MA30 = ma30,
            DetectedAt = DateTime.UtcNow,
            IsActive = true
        };
    }

    public async Task<List<DetectedRegime>> GetHistoricalRegimesAsync(
        string assetSymbol,
        DateTime fromDate)
    {
        return await _context.DetectedRegimes
            .Where(r => r.Asset == assetSymbol && r.DetectedAt >= fromDate)
            .OrderByDescending(r => r.DetectedAt)
            .ToListAsync();
    }

    /// <summary>
    /// Calculate standard deviation of a list of values
    /// </summary>
    private decimal CalculateStandardDeviation(List<decimal> values)
    {
        if (values.Count == 0)
            return 0m;

        var average = values.Average();
        var sumOfSquares = values.Sum(v => (v - average) * (v - average));
        var variance = sumOfSquares / values.Count;

        return (decimal)Math.Sqrt((double)variance);
    }

    /// <summary>
    /// Calculate simple moving average
    /// </summary>
    private decimal CalculateMovingAverage(List<decimal> prices, int period)
    {
        if (prices.Count < period)
            return prices.Average();

        return prices.TakeLast(period).Average();
    }
}
