using AiTradingRace.Application.MarketData;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// Admin controller for manual data ingestion and administrative operations.
/// </summary>
[ApiController]
[Route("api/[controller]")]
[Authorize(Policy = "RequireAdmin")]  // ← Sprint 9.3: Protect admin endpoints
public class AdminController : ControllerBase
{
    private readonly IMarketDataIngestionService _ingestionService;
    private readonly ILogger<AdminController> _logger;

    public AdminController(
        IMarketDataIngestionService ingestionService,
        ILogger<AdminController> logger)
    {
        _ingestionService = ingestionService;
        _logger = logger;
    }

    /// <summary>
    /// Manually trigger market data ingestion for all enabled assets.
    /// </summary>
    /// <returns>Count of newly inserted candles.</returns>
    [HttpPost("ingest")]
    public async Task<IActionResult> IngestAllAssets(CancellationToken cancellationToken)
    {
        _logger.LogInformation("Manual ingestion triggered for all assets");

        try
        {
            var insertedCount = await _ingestionService.IngestAllAssetsAsync(cancellationToken);

            return Ok(new
            {
                success = true,
                insertedCandles = insertedCount,
                timestamp = DateTimeOffset.UtcNow
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to ingest market data for all assets");
            return StatusCode(500, new
            {
                success = false,
                error = "Failed to ingest market data",
                message = ex.Message
            });
        }
    }

    /// <summary>
    /// Manually trigger market data ingestion for a specific asset.
    /// </summary>
    /// <param name="symbol">Asset symbol (e.g., BTC, ETH).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Count of newly inserted candles for the specified asset.</returns>
    [HttpPost("ingest/{symbol}")]
    public async Task<IActionResult> IngestAsset(string symbol, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return BadRequest(new { success = false, error = "Symbol is required" });
        }

        _logger.LogInformation("Manual ingestion triggered for {Symbol}", symbol);

        try
        {
            var insertedCount = await _ingestionService.IngestLatestCandlesAsync(symbol, cancellationToken);

            return Ok(new
            {
                success = true,
                symbol = symbol.ToUpperInvariant(),
                insertedCandles = insertedCount,
                timestamp = DateTimeOffset.UtcNow
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to ingest market data for {Symbol}", symbol);
            return StatusCode(500, new
            {
                success = false,
                symbol = symbol.ToUpperInvariant(),
                error = "Failed to ingest market data",
                message = ex.Message
            });
        }
    }
}
