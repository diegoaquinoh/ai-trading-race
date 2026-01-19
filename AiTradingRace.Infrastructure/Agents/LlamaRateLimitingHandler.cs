using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// HTTP delegating handler that enforces rate limiting for Llama API calls.
/// Ensures requests are spaced according to the configured minimum interval
/// to comply with free tier rate limits.
/// </summary>
public sealed class LlamaRateLimitingHandler : DelegatingHandler
{
    private static readonly SemaphoreSlim Semaphore = new(1, 1);
    private static DateTime _lastRequestTime = DateTime.MinValue;

    private readonly LlamaOptions _options;
    private readonly ILogger<LlamaRateLimitingHandler> _logger;

    public LlamaRateLimitingHandler(
        IOptions<LlamaOptions> options,
        ILogger<LlamaRateLimitingHandler> logger)
    {
        _options = options.Value;
        _logger = logger;
    }

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        await Semaphore.WaitAsync(cancellationToken);
        try
        {
            var minInterval = TimeSpan.FromMilliseconds(_options.MinRequestIntervalMs);
            var elapsed = DateTime.UtcNow - _lastRequestTime;

            if (elapsed < minInterval)
            {
                var delay = minInterval - elapsed;
                _logger.LogDebug(
                    "Rate limiting: waiting {DelayMs}ms before Llama API request",
                    delay.TotalMilliseconds);
                await Task.Delay(delay, cancellationToken);
            }

            _lastRequestTime = DateTime.UtcNow;
            return await base.SendAsync(request, cancellationToken);
        }
        finally
        {
            Semaphore.Release();
        }
    }
}
