using AiTradingRace.Application.Knowledge;
using AiTradingRace.Domain.Entities;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AiTradingRace.Web.Controllers;

/// <summary>
/// API endpoints for market regime detection and analysis
/// </summary>
[ApiController]
[Route("api/regime")]
[Produces("application/json")]
public class RegimeController : ControllerBase
{
    private readonly IRegimeDetector _regimeDetector;
    private readonly ILogger<RegimeController> _logger;

    public RegimeController(
        IRegimeDetector regimeDetector,
        ILogger<RegimeController> logger)
    {
        _regimeDetector = regimeDetector;
        _logger = logger;
    }

    /// <summary>
    /// Get the current market regime for an asset
    /// </summary>
    /// <param name="assetSymbol">Asset symbol (e.g., BTC, ETH)</param>
    /// <returns>Current market regime with metrics</returns>
    [HttpGet("current/{assetSymbol}")]
    [ProducesResponseType(typeof(MarketRegime), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<MarketRegime>> GetCurrentRegime(string assetSymbol)
    {
        _logger.LogInformation("Getting current regime for {Asset}", assetSymbol);

        var toDate = DateTime.UtcNow;
        var fromDate = toDate.AddDays(-30); // Look back 30 days

        var regime = await _regimeDetector.DetectRegimeAsync(
            assetSymbol.ToUpperInvariant(),
            fromDate,
            toDate);

        if (regime.RegimeId == "UNKNOWN")
        {
            return NotFound(new { message = $"Asset {assetSymbol} not found or insufficient data" });
        }

        return Ok(regime);
    }

    /// <summary>
    /// Get historical regime changes for an asset
    /// </summary>
    /// <param name="assetSymbol">Asset symbol (e.g., BTC, ETH)</param>
    /// <param name="fromDate">Start date for history (defaults to 90 days ago)</param>
    /// <returns>List of detected regimes</returns>
    [HttpGet("history/{assetSymbol}")]
    [ProducesResponseType(typeof(List<DetectedRegime>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<DetectedRegime>>> GetRegimeHistory(
        string assetSymbol,
        [FromQuery] DateTime? fromDate = null)
    {
        var startDate = fromDate ?? DateTime.UtcNow.AddDays(-90);

        _logger.LogInformation(
            "Getting regime history for {Asset} from {FromDate}",
            assetSymbol, startDate);

        var history = await _regimeDetector.GetHistoricalRegimesAsync(
            assetSymbol.ToUpperInvariant(),
            startDate);

        return Ok(history);
    }

    /// <summary>
    /// Get current regimes for all available assets
    /// </summary>
    /// <returns>Dictionary of asset symbols to their current regimes</returns>
    [HttpGet("current")]
    [ProducesResponseType(typeof(Dictionary<string, MarketRegime>), StatusCodes.Status200OK)]
    public async Task<ActionResult<Dictionary<string, MarketRegime>>> GetAllCurrentRegimes()
    {
        _logger.LogInformation("Getting current regimes for all assets");

        var assets = new[] { "BTC", "ETH" }; // TODO: Get from database
        var regimes = new Dictionary<string, MarketRegime>();

        var toDate = DateTime.UtcNow;
        var fromDate = toDate.AddDays(-30);

        foreach (var asset in assets)
        {
            try
            {
                var regime = await _regimeDetector.DetectRegimeAsync(asset, fromDate, toDate);
                if (regime.RegimeId != "UNKNOWN")
                {
                    regimes[asset] = regime;
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to detect regime for {Asset}", asset);
            }
        }

        return Ok(regimes);
    }
}
