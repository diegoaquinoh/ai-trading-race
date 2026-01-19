using AiTradingRace.Infrastructure.Database;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Controller for market data endpoints (prices, candles).
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class MarketController : ControllerBase
{
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<MarketController> _logger;

    public MarketController(
        TradingDbContext dbContext,
        ILogger<MarketController> logger)
    {
        _dbContext = dbContext;
        _logger = logger;
    }

    /// <summary>
    /// Get the latest prices for all tracked assets.
    /// </summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Latest prices for each asset.</returns>
    [HttpGet("prices")]
    [ProducesResponseType(typeof(IEnumerable<MarketPriceDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IEnumerable<MarketPriceDto>>> GetLatestPrices(CancellationToken ct)
    {
        _logger.LogDebug("Fetching latest market prices");

        var assets = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled)
            .ToListAsync(ct);

        var prices = new List<MarketPriceDto>();

        foreach (var asset in assets)
        {
            var latestCandle = await _dbContext.MarketCandles
                .AsNoTracking()
                .Where(c => c.MarketAssetId == asset.Id)
                .OrderByDescending(c => c.TimestampUtc)
                .FirstOrDefaultAsync(ct);

            if (latestCandle != null)
            {
                // Calculate 24h change if we have enough data
                var dayAgo = latestCandle.TimestampUtc.AddHours(-24);
                var previousCandle = await _dbContext.MarketCandles
                    .AsNoTracking()
                    .Where(c => c.MarketAssetId == asset.Id && c.TimestampUtc >= dayAgo)
                    .OrderBy(c => c.TimestampUtc)
                    .FirstOrDefaultAsync(ct);

                decimal change24h = 0;
                decimal changePercent24h = 0;

                if (previousCandle != null && previousCandle.Close != 0)
                {
                    change24h = latestCandle.Close - previousCandle.Close;
                    changePercent24h = (change24h / previousCandle.Close) * 100;
                }

                prices.Add(new MarketPriceDto(
                    Symbol: asset.Symbol,
                    Name: asset.Name,
                    Price: latestCandle.Close,
                    Change24h: change24h,
                    ChangePercent24h: changePercent24h,
                    High24h: latestCandle.High,
                    Low24h: latestCandle.Low,
                    UpdatedAt: latestCandle.TimestampUtc));
            }
        }

        _logger.LogDebug("Returning prices for {Count} assets", prices.Count);

        return Ok(prices);
    }

    /// <summary>
    /// Get the latest price for a specific asset.
    /// </summary>
    /// <param name="symbol">Asset symbol (e.g., BTC, ETH).</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Latest price for the asset.</returns>
    [HttpGet("prices/{symbol}")]
    [ProducesResponseType(typeof(MarketPriceDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<MarketPriceDto>> GetAssetPrice(string symbol, CancellationToken ct)
    {
        var asset = await _dbContext.MarketAssets
            .AsNoTracking()
            .FirstOrDefaultAsync(a => a.Symbol.ToUpper() == symbol.ToUpper(), ct);

        if (asset == null)
        {
            return NotFound(new { message = $"Asset {symbol} not found" });
        }

        var latestCandle = await _dbContext.MarketCandles
            .AsNoTracking()
            .Where(c => c.MarketAssetId == asset.Id)
            .OrderByDescending(c => c.TimestampUtc)
            .FirstOrDefaultAsync(ct);

        if (latestCandle == null)
        {
            return NotFound(new { message = $"No price data for {symbol}" });
        }

        // Calculate 24h change
        var dayAgo = latestCandle.TimestampUtc.AddHours(-24);
        var previousCandle = await _dbContext.MarketCandles
            .AsNoTracking()
            .Where(c => c.MarketAssetId == asset.Id && c.TimestampUtc >= dayAgo)
            .OrderBy(c => c.TimestampUtc)
            .FirstOrDefaultAsync(ct);

        decimal change24h = 0;
        decimal changePercent24h = 0;

        if (previousCandle != null && previousCandle.Close != 0)
        {
            change24h = latestCandle.Close - previousCandle.Close;
            changePercent24h = (change24h / previousCandle.Close) * 100;
        }

        return Ok(new MarketPriceDto(
            Symbol: asset.Symbol,
            Name: asset.Name,
            Price: latestCandle.Close,
            Change24h: change24h,
            ChangePercent24h: changePercent24h,
            High24h: latestCandle.High,
            Low24h: latestCandle.Low,
            UpdatedAt: latestCandle.TimestampUtc));
    }
}

/// <summary>
/// DTO for market price data.
/// </summary>
public record MarketPriceDto(
    string Symbol,
    string Name,
    decimal Price,
    decimal Change24h,
    decimal ChangePercent24h,
    decimal High24h,
    decimal Low24h,
    DateTimeOffset UpdatedAt);
