using System.Threading.Channels;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Web.FixedIncome;

/// <summary>
/// In-process bounded queue of run ids. SQL remains the source of truth: a run is
/// persisted as "queued" before it is enqueued, and queued runs are re-enqueued on
/// startup, so a full queue or a restart never loses a run.
/// </summary>
public sealed class FixedIncomeRunQueue : IFixedIncomeRunQueue
{
    private readonly Channel<string> _channel;

    public FixedIncomeRunQueue(IOptions<FixedIncomeOptions> options)
    {
        _channel = Channel.CreateBounded<string>(new BoundedChannelOptions(Math.Max(1, options.Value.RunQueueCapacity))
        {
            SingleReader = true,
            FullMode = BoundedChannelFullMode.Wait,
        });
    }

    public ChannelReader<string> Reader => _channel.Reader;

    public ValueTask<bool> TryEnqueueAsync(string runId, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(runId);
        return ValueTask.FromResult(_channel.Writer.TryWrite(runId));
    }
}
