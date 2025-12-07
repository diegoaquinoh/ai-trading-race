using AiTradingRace.Application.Agents;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Functions.Functions;

public sealed class RunAgentsFunction
{
    private readonly IAgentRunner _agentRunner;
    private readonly ILogger<RunAgentsFunction> _logger;

    public RunAgentsFunction(
        IAgentRunner agentRunner,
        ILogger<RunAgentsFunction> logger)
    {
        _agentRunner = agentRunner;
        _logger = logger;
    }

    [Function(nameof(RunAgentsFunction))]
    public async Task RunAsync(
        [TimerTrigger("0 */30 * * * *")] TimerInfo timerInfo,
        CancellationToken cancellationToken)
    {
        var agentId = Guid.NewGuid();
        var result = await _agentRunner.RunAgentOnceAsync(agentId, cancellationToken);
        _logger.LogInformation("Agent {AgentId} executed with portfolio value {Value}", result.AgentId, result.Portfolio.TotalValue);
    }
}

