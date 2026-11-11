using AiTradingRace.Application.FixedIncome;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Placeholder executor: the application-mode run executor (cycle sequencing through
/// the research engine and the commit service) and the Functions orchestration are
/// delivered in a later wave. Runs fail with an explicit, operator-visible reason
/// instead of silently doing nothing.
/// </summary>
public sealed class NotConfiguredRunExecutor : IFixedIncomeRunExecutor
{
    public const string Reason =
        "executor not configured: the application-mode fixed income run executor is not installed yet " +
        "(delivered with the Functions orchestration wave); no financial state was changed.";

    private readonly ILogger<NotConfiguredRunExecutor> _logger;

    public NotConfiguredRunExecutor(ILogger<NotConfiguredRunExecutor> logger)
    {
        _logger = logger;
    }

    public Task<RunExecutionResult> ExecuteAsync(string runId, CancellationToken cancellationToken)
    {
        _logger.LogWarning("Fixed income run {RunId} cannot execute: {Reason}", runId, Reason);
        return Task.FromResult(RunExecutionResult.Failure(Reason));
    }
}
