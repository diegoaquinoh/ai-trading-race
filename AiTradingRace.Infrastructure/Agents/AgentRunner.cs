using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Decisions;
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
    private readonly IDecisionLogService _decisionLogService;
    private readonly ILogger<AgentRunner> _logger;

    public AgentRunner(
        IAgentContextBuilder contextBuilder,
        IAgentModelClientFactory clientFactory,
        IRiskValidator riskValidator,
        IPortfolioService portfolioService,
        IEquityService equityService,
        IDecisionLogService decisionLogService,
        ILogger<AgentRunner> logger)
    {
        _contextBuilder = contextBuilder;
        _clientFactory = clientFactory;
        _riskValidator = riskValidator;
        _portfolioService = portfolioService;
        _equityService = equityService;
        _decisionLogService = decisionLogService;
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
            var context = await _contextBuilder.BuildContextAsync(
                agentId, 
                candleCount: 24, 
                includeKnowledgeGraph: true, // Phase 10.4: Enable knowledge graph for explainability
                cancellationToken);

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
            decimal portfolioValueBefore = context.Portfolio.TotalValue;
            
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

            // Phase 10.4: Log decision with citations and knowledge graph context
            if (context.KnowledgeGraph != null && context.DetectedRegime != null)
            {
                try
                {
                    var action = validation.ValidatedDecision.Orders.Count == 0 
                        ? "HOLD" 
                        : validation.ValidatedDecision.Orders[0].Side.ToString().ToUpperInvariant();
                    
                    var marketConditions = new Dictionary<string, decimal>();
                    foreach (var candle in context.RecentCandles.GroupBy(c => c.AssetSymbol))
                    {
                        var latest = candle.OrderByDescending(c => c.TimestampUtc).First();
                        marketConditions[candle.Key] = latest.Close;
                    }

                    await _decisionLogService.LogDecisionAsync(new CreateDecisionLogDto
                    {
                        AgentId = agentId,
                        Action = action,
                        Asset = validation.ValidatedDecision.Orders.FirstOrDefault()?.AssetSymbol,
                        Quantity = validation.ValidatedDecision.Orders.FirstOrDefault()?.Quantity,
                        Rationale = rawDecision.Rationale ?? "No rationale provided",
                        CitedRuleIds = rawDecision.CitedRuleIds ?? new List<string>(),
                        DetectedRegime = context.DetectedRegime.RegimeId,
                        Subgraph = context.KnowledgeGraph,
                        PortfolioValueBefore = portfolioValueBefore,
                        PortfolioValueAfter = portfolio.TotalValue,
                        MarketConditions = marketConditions
                    });

                    _logger.LogInformation(
                        "Agent {AgentId}: Decision logged with {RuleCount} cited rules in {Regime} regime",
                        agentId, 
                        rawDecision.CitedRuleIds?.Count ?? 0,
                        context.DetectedRegime.Name);
                }
                catch (Exception ex)
                {
                    // Don't fail the agent run if decision logging fails
                    _logger.LogError(ex, "Failed to log decision for agent {AgentId}", agentId);
                }
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
