using AiTradingRace.Application.Decisions;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using System.Text.Json;

namespace AiTradingRace.Infrastructure.Decisions;

/// <summary>
/// Service for logging and analyzing AI trading decisions
/// </summary>
public class DecisionLogService : IDecisionLogService
{
    private readonly TradingDbContext _context;
    private readonly ILogger<DecisionLogService> _logger;

    public DecisionLogService(
        TradingDbContext context,
        ILogger<DecisionLogService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<DecisionLog> LogDecisionAsync(CreateDecisionLogDto dto)
    {
        _logger.LogInformation(
            "Logging decision for agent {AgentId}: {Action} {Asset}",
            dto.AgentId, dto.Action, dto.Asset ?? "N/A");

        var log = new DecisionLog
        {
            AgentId = dto.AgentId,
            Timestamp = DateTime.UtcNow,
            Action = dto.Action,
            Asset = dto.Asset,
            Quantity = dto.Quantity,
            Rationale = dto.Rationale,
            CitedRuleIds = JsonSerializer.Serialize(dto.CitedRuleIds),
            DetectedRegime = dto.DetectedRegime,
            SubgraphSnapshot = dto.Subgraph.ToJson(),
            PortfolioValueBefore = dto.PortfolioValueBefore,
            PortfolioValueAfter = dto.PortfolioValueAfter,
            MarketConditions = JsonSerializer.Serialize(dto.MarketConditions),
            WasValidated = true,
            CreatedAt = DateTime.UtcNow
        };

        _context.DecisionLogs.Add(log);
        await _context.SaveChangesAsync();

        _logger.LogInformation(
            "Decision {DecisionId} logged successfully. Rules cited: {RuleCount}",
            log.Id, dto.CitedRuleIds.Count);

        return log;
    }

    public async Task<List<DecisionLog>> GetDecisionHistoryAsync(
        Guid agentId,
        DateTime? fromDate = null,
        int? limit = null)
    {
        var query = _context.DecisionLogs
            .Where(d => d.AgentId == agentId);

        if (fromDate.HasValue)
        {
            query = query.Where(d => d.Timestamp >= fromDate.Value);
        }

        query = query.OrderByDescending(d => d.Timestamp);

        if (limit.HasValue)
        {
            query = query.Take(limit.Value);
        }

        return await query.ToListAsync();
    }

    public async Task<DecisionLog?> GetDecisionByIdAsync(int decisionId)
    {
        return await _context.DecisionLogs
            .Include(d => d.Agent)
            .FirstOrDefaultAsync(d => d.Id == decisionId);
    }

    public async Task<DecisionAnalytics> AnalyzeDecisionsAsync(
        Guid agentId,
        DateTime fromDate,
        DateTime toDate)
    {
        _logger.LogInformation(
            "Analyzing decisions for agent {AgentId} from {FromDate} to {ToDate}",
            agentId, fromDate, toDate);

        var decisions = await _context.DecisionLogs
            .Where(d => d.AgentId == agentId
                && d.Timestamp >= fromDate
                && d.Timestamp <= toDate)
            .ToListAsync();

        var ruleCitationCounts = new Dictionary<string, int>();
        var regimeDistribution = new Dictionary<string, int>();

        foreach (var decision in decisions)
        {
            // Count rule citations
            var citedRules = JsonSerializer.Deserialize<List<string>>(decision.CitedRuleIds) ?? new List<string>();
            foreach (var ruleId in citedRules)
            {
                ruleCitationCounts[ruleId] = ruleCitationCounts.GetValueOrDefault(ruleId, 0) + 1;
            }

            // Count regime occurrences
            var regime = decision.DetectedRegime;
            regimeDistribution[regime] = regimeDistribution.GetValueOrDefault(regime, 0) + 1;
        }

        var analytics = new DecisionAnalytics
        {
            TotalDecisions = decisions.Count,
            BuyCount = decisions.Count(d => d.Action == "BUY"),
            SellCount = decisions.Count(d => d.Action == "SELL"),
            HoldCount = decisions.Count(d => d.Action == "HOLD"),
            RuleCitationCounts = ruleCitationCounts,
            RegimeDistribution = regimeDistribution,
            AveragePortfolioChange = decisions.Any()
                ? decisions.Average(d => d.PortfolioValueAfter - d.PortfolioValueBefore)
                : 0m
        };

        _logger.LogInformation(
            "Analytics for agent {AgentId}: {TotalDecisions} decisions, {BuyCount} buys, {SellCount} sells",
            agentId, analytics.TotalDecisions, analytics.BuyCount, analytics.SellCount);

        return analytics;
    }
}
