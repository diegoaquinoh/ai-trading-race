using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Application.Knowledge;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Builds the context needed for an AI agent to make trading decisions.
/// Gathers portfolio state, recent market data, agent instructions, and optionally knowledge graph.
/// </summary>
public sealed class AgentContextBuilder : IAgentContextBuilder
{
    private readonly TradingDbContext _dbContext;
    private readonly IPortfolioService _portfolioService;
    private readonly IMarketDataProvider _marketDataProvider;
    private readonly IKnowledgeGraphService _knowledgeGraphService;
    private readonly IRegimeDetector _regimeDetector;
    private readonly AzureOpenAiOptions _azureOptions;
    private readonly ILogger<AgentContextBuilder> _logger;

    public AgentContextBuilder(
        TradingDbContext dbContext,
        IPortfolioService portfolioService,
        IMarketDataProvider marketDataProvider,
        IKnowledgeGraphService knowledgeGraphService,
        IRegimeDetector regimeDetector,
        IOptions<AzureOpenAiOptions> azureOptions,
        ILogger<AgentContextBuilder> logger)
    {
        _dbContext = dbContext;
        _portfolioService = portfolioService;
        _marketDataProvider = marketDataProvider;
        _knowledgeGraphService = knowledgeGraphService;
        _regimeDetector = regimeDetector;
        _azureOptions = azureOptions.Value;
        _logger = logger;
    }

    /// <inheritdoc />
    public async Task<AgentContext> BuildContextAsync(
        Guid agentId,
        int candleCount = 24,
        bool includeKnowledgeGraph = false,
        CancellationToken cancellationToken = default)
    {
        _logger.LogDebug(
            "Building context for agent {AgentId} with {CandleCount} candles (KG: {IncludeKG})",
            agentId,
            candleCount,
            includeKnowledgeGraph);

        // 1. Load and validate agent
        var agent = await _dbContext.Agents
            .AsNoTracking()
            .FirstOrDefaultAsync(a => a.Id == agentId, cancellationToken);

        if (agent is null)
        {
            throw new InvalidOperationException($"Agent {agentId} not found.");
        }

        if (!agent.IsActive)
        {
            throw new InvalidOperationException($"Agent {agentId} is not active.");
        }

        // 2. Get portfolio state
        var portfolio = await _portfolioService.GetPortfolioAsync(agentId, cancellationToken);

        // 3. Get recent market candles for all enabled assets
        var candles = await GetRecentCandlesAsync(candleCount, cancellationToken);

        // 4. Optionally detect regime and fetch knowledge graph
        KnowledgeSubgraph? knowledgeGraph = null;
        MarketRegime? detectedRegime = null;

        if (includeKnowledgeGraph)
        {
            try
            {
                // Detect current market regime for primary asset (BTC or first available)
                var primaryCandle = candles.FirstOrDefault(c => c.AssetSymbol == "BTC")
                                   ?? candles.FirstOrDefault();

                if (primaryCandle != null)
                {
                    var primaryAsset = primaryCandle.AssetSymbol;
                    var toDate = DateTime.UtcNow;
                    var fromDate = toDate.AddDays(-30); // Look back 30 days for regime detection

                    _logger.LogDebug("Detecting regime for primary asset: {Asset}", primaryAsset);
                    
                    var regime = await _regimeDetector.DetectRegimeAsync(
                        primaryAsset,
                        fromDate,
                        toDate);

                    detectedRegime = regime;

                    _logger.LogInformation(
                        "Detected regime for {Asset}: {RegimeId} (Volatility: {Volatility})",
                        primaryAsset,
                        regime.RegimeId,
                        regime.Volatility);

                    // Fetch relevant knowledge subgraph for the detected regime
                    // Get unique asset symbols from candles
                    var assetSymbols = candles.Select(c => c.AssetSymbol).Distinct().ToList();
                    
                    var subgraph = await _knowledgeGraphService.GetRelevantSubgraphAsync(
                        regime.RegimeId,
                        assetSymbols);

                    knowledgeGraph = subgraph;

                    _logger.LogDebug(
                        "Fetched knowledge subgraph: {RuleCount} rules for regime {Regime}",
                        subgraph.ApplicableRules.Count,
                        regime.RegimeId);
                }
                else
                {
                    _logger.LogWarning("No market candles available for regime detection");
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(
                    ex,
                    "Failed to build knowledge graph context for agent {AgentId}. Continuing without KG.",
                    agentId);
                // Continue without knowledge graph - graceful degradation
            }
        }

        _logger.LogDebug(
            "Built context: Portfolio ${TotalValue:N2}, {PositionCount} positions, {CandleCount} candles, KG: {HasKG}",
            portfolio.TotalValue,
            portfolio.Positions.Count,
            candles.Count,
            knowledgeGraph != null);

        return new AgentContext(
            agentId,
            agent.ModelProvider,
            portfolio,
            candles,
            agent.Instructions,
            ResolveDeploymentName(agent),
            knowledgeGraph,
            detectedRegime);
    }

    private string? ResolveDeploymentName(Agent agent)
    {
        if (agent.ModelProvider != ModelProvider.AzureOpenAI || string.IsNullOrEmpty(agent.DeploymentKey))
            return null;

        return agent.DeploymentKey switch
        {
            "GPT4oMini" => _azureOptions.GPT4_o_Mini_DeploymentName,
            "GPT41Nano" => _azureOptions.GPT4_1_nano_DeploymentName,
            _ => throw new InvalidOperationException(
                $"Unknown DeploymentKey '{agent.DeploymentKey}' for agent {agent.Id}.")
        };
    }

    private async Task<IReadOnlyList<MarketCandleDto>> GetRecentCandlesAsync(
        int limit,
        CancellationToken cancellationToken)
    {
        // Get all enabled asset symbols
        var enabledAssets = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled)
            .Select(a => a.Symbol)
            .ToListAsync(cancellationToken);

        if (enabledAssets.Count == 0)
        {
            _logger.LogWarning("No enabled assets found for market data");
            return Array.Empty<MarketCandleDto>();
        }

        var allCandles = new List<MarketCandleDto>();

        foreach (var symbol in enabledAssets)
        {
            try
            {
                var candles = await _marketDataProvider.GetLatestCandlesAsync(
                    symbol,
                    limit,
                    cancellationToken);

                allCandles.AddRange(candles);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to get candles for {Symbol}", symbol);
                // Continue with other assets
            }
        }

        // Order by timestamp descending so most recent are first
        return allCandles
            .OrderByDescending(c => c.TimestampUtc)
            .ToList();
    }
}
