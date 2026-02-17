using System.Net.Http.Json;
using System.Text.Json;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.MarketData;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.MarketData;

/// <summary>
/// CoinGecko API client for fetching OHLC market data.
/// API Reference: https://docs.coingecko.com/v3.0.1/reference/coins-id-ohlc
/// </summary>
public sealed class CoinGeckoMarketDataClient : IExternalMarketDataClient
{
    private readonly HttpClient _httpClient;
    private readonly CoinGeckoOptions _options;
    private readonly ILogger<CoinGeckoMarketDataClient> _logger;

    public CoinGeckoMarketDataClient(
        HttpClient httpClient,
        IOptions<CoinGeckoOptions> options,
        ILogger<CoinGeckoMarketDataClient> logger)
    {
        _httpClient = httpClient;
        _options = options.Value;
        _logger = logger;

        // Configure HttpClient base address
        _httpClient.BaseAddress = new Uri(_options.BaseUrl);
        _httpClient.Timeout = TimeSpan.FromSeconds(_options.TimeoutSeconds);

        // Add User-Agent header (required by CoinGecko to avoid 403)
        _httpClient.DefaultRequestHeaders.Add("User-Agent", "AiTradingRace/1.0 (https://github.com/ai-trading-race)");
        
        // Add API key header if configured
        if (!string.IsNullOrWhiteSpace(_options.ApiKey))
        {
            _httpClient.DefaultRequestHeaders.Add("x-cg-demo-api-key", _options.ApiKey);
        }
        else
        {
            _logger.LogCritical(
                "CoinGecko API key is not configured. Market data ingestion will fail. " +
                "Get a free Demo API key at https://www.coingecko.com/en/api/pricing and set CoinGecko__ApiKey.");
        }
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<ExternalCandleDto>> GetCandlesAsync(
        string coinId,
        string vsCurrency,
        int days,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(coinId);
        ArgumentException.ThrowIfNullOrWhiteSpace(vsCurrency);

        if (days <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(days), "Days must be positive.");
        }

        var endpoint = $"coins/{coinId.ToLowerInvariant()}/ohlc?vs_currency={vsCurrency.ToLowerInvariant()}&days={days}";

        _logger.LogInformation("Fetching OHLC data from CoinGecko: {Endpoint}", endpoint);

        try
        {
            var response = await _httpClient.GetAsync(endpoint, cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
                _logger.LogError(
                    "CoinGecko API request failed: {StatusCode} - {Error}",
                    response.StatusCode,
                    errorContent);

                // Handle rate limiting
                if ((int)response.StatusCode == 429)
                {
                    _logger.LogWarning("CoinGecko rate limit exceeded. Consider implementing backoff.");
                }

                return Array.Empty<ExternalCandleDto>();
            }

            // CoinGecko OHLC response format: [[timestamp, open, high, low, close], ...]
            var rawData = await response.Content.ReadFromJsonAsync<decimal[][]>(cancellationToken: cancellationToken);

            if (rawData is null || rawData.Length == 0)
            {
                _logger.LogWarning("CoinGecko returned empty OHLC data for {CoinId}", coinId);
                return Array.Empty<ExternalCandleDto>();
            }

            var candles = rawData
                .Where(arr => arr.Length >= 5)
                .Select(arr => new ExternalCandleDto(
                    TimestampUtc: DateTimeOffset.FromUnixTimeMilliseconds((long)arr[0]),
                    Open: arr[1],
                    High: arr[2],
                    Low: arr[3],
                    Close: arr[4]))
                .OrderBy(c => c.TimestampUtc)
                .ToList();

            _logger.LogInformation(
                "Successfully fetched {Count} candles for {CoinId}",
                candles.Count,
                coinId);

            return candles;
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "HTTP error while fetching data from CoinGecko for {CoinId}", coinId);
            return Array.Empty<ExternalCandleDto>();
        }
        catch (TaskCanceledException ex) when (ex.InnerException is TimeoutException)
        {
            _logger.LogError("Request to CoinGecko timed out for {CoinId}", coinId);
            return Array.Empty<ExternalCandleDto>();
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Failed to parse CoinGecko OHLC response for {CoinId}", coinId);
            return Array.Empty<ExternalCandleDto>();
        }
    }
}
