namespace AiTradingRace.Application.Common;

public sealed class AgentOrchestrationClock
{
    private readonly TimeProvider _timeProvider;

    public AgentOrchestrationClock(TimeProvider? timeProvider = null)
    {
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public DateTimeOffset UtcNow => _timeProvider.GetUtcNow();
}

