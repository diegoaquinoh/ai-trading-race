using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Equity;
using AiTradingRace.Application.Portfolios;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Orchestrates a complete agent execution cycle:
/// 1. Build context (portfolio + market data)
/// 2. Generate decision from AI model (selected by ModelProvider)
/// 3. Validate against risk constraints
/// 4. Execute validated trades
/// 5. Capture equity snapshot
/// </summary>
public sealed class AgentRunner : IAgentRunner
{
    private readonly IAgentContextBuilder _contextBuilder;
    private readonly IAgentModelClientFactory _clientFactory;
    private readonly IRiskValidator _riskValidator;
    private readonly IPortfolioService _portfolioService;
    private readonly IEquityService _equityService;
    private readonly ILogger<AgentRunner> _logger;

    public AgentRunner(
        IAgentContextBuilder contextBuilder,
        IAgentModelClientFactory clientFactory,
        IRiskValidator riskValidator,
        IPortfolioService portfolioService,
        IEquityService equityService,
        ILogger<AgentRunner> logger)
    {
        _contextBuilder = contextBuilder;
        _clientFactory = clientFactory;
        _riskValidator = riskValidator;
        _portfolioService = portfolioService;
        _equityService = equityService;
        _logger = logger;
    }

    /// <inheritdoc />
    public async Task<AgentRunResult> RunAgentOnceAsync(
        Guid agentId,
        CancellationToken cancellationToken = default)
    {
        var startedAt = DateTimeOffset.UtcNow;

        _logger.LogInformation("Starting execution cycle for agent {AgentId}", agentId);

        try
        {
            // Step 1: Build context
            _logger.LogDebug("Step 1: Building context for agent {AgentId}", agentId);
            var context = await _contextBuilder.BuildContextAsync(agentId, candleCount: 24, cancellationToken);

            // Step 2: Generate decision from AI model (using provider-specific client)
            _logger.LogDebug("Step 2: Generating decision from {Provider} model for agent {AgentId}",
                context.ModelProvider, agentId);
            var modelClient = _clientFactory.GetClient(context.ModelProvider);
            var rawDecision = await modelClient.GenerateDecisionAsync(context, cancellationToken);

            _logger.LogInformation("Agent {AgentId} proposed {OrderCount} orders",
                agentId, rawDecision.Orders.Count);

            // Step 3: Validate against risk constraints
            _logger.LogDebug("Step 3: Validating decision against risk constraints for agent {AgentId}", agentId);
            var validation = await _riskValidator.ValidateDecisionAsync(
                rawDecision,
                context.Portfolio,
                cancellationToken);

            if (validation.HasWarnings)
            {
                _logger.LogWarning("Agent {AgentId}: {RejectedCount} orders rejected during validation",
                    agentId, validation.RejectedOrders.Count);

                foreach (var rejected in validation.RejectedOrders)
                {
                    _logger.LogWarning("  - {Asset} {Side} {Qty}: {Reason}",
                        rejected.OriginalOrder.AssetSymbol,
                        rejected.OriginalOrder.Side,
                        rejected.OriginalOrder.Quantity,
                        rejected.Reason);
                }
            }

            // Step 4: Apply validated decision to portfolio
            PortfolioState portfolio;
            if (validation.ValidatedDecision.Orders.Count > 0)
            {
                _logger.LogDebug("Step 4: Applying {OrderCount} validated orders for agent {AgentId}",
                    validation.ValidatedDecision.Orders.Count, agentId);

                portfolio = await _portfolioService.ApplyDecisionAsync(
                    agentId,
                    validation.ValidatedDecision,
                    cancellationToken);

                _logger.LogInformation("Agent {AgentId}: Executed {OrderCount} trades. Portfolio value: ${TotalValue:F2}",
                    agentId, validation.ValidatedDecision.Orders.Count, portfolio.TotalValue);
            }
            else
            {
                _logger.LogInformation("Agent {AgentId}: No valid orders to execute (HOLD)", agentId);
                portfolio = context.Portfolio;
            }

            // Step 5: Capture equity snapshot
            _logger.LogDebug("Step 5: Capturing equity snapshot for agent {AgentId}", agentId);
            await _equityService.CaptureSnapshotAsync(agentId, cancellationToken);

            var completedAt = DateTimeOffset.UtcNow;
            var duration = completedAt - startedAt;

            _logger.LogInformation("Agent {AgentId} execution completed in {Duration:F2}s",
                agentId, duration.TotalSeconds);

            return new AgentRunResult(
                agentId,
                startedAt,
                completedAt,
                portfolio,
                validation.ValidatedDecision);
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogError(ex, "Agent {AgentId} execution failed: {Message}", agentId, ex.Message);
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Agent {AgentId} execution failed with unexpected error", agentId);
            throw;
        }
    }
}
