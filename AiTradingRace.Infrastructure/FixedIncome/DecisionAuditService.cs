using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Persists the audit trail of every logical strategy decision (spec 14.7, 15.2):
/// outcome, proposal, research note, validation, attempts, tool traces, usage and
/// policy evaluation. Independent of the legacy knowledge graph and regime detector:
/// HOLD, abstention, failure, budget exhaustion and stale skips are all recorded.
/// </summary>
public sealed class DecisionAuditService : IDecisionAuditService
{
    private readonly TradingDbContext _db;
    private readonly ResearchEngineOptions _engineOptions;
    private readonly TimeProvider _clock;
    private readonly ILogger<DecisionAuditService> _logger;

    public DecisionAuditService(
        TradingDbContext db,
        IOptions<ResearchEngineOptions> engineOptions,
        ILogger<DecisionAuditService> logger,
        TimeProvider? clock = null)
    {
        _db = db;
        _engineOptions = engineOptions.Value;
        _logger = logger;
        _clock = clock ?? TimeProvider.System;
    }

    public async Task<DecisionAuditResult> RecordResultAsync(
        RawContractJson strategyResult,
        DecisionAuditContext context,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(strategyResult);
        ArgumentNullException.ThrowIfNull(context);
        var node = strategyResult.Node;
        var issues = new List<string>();

        var schemaVersion = node["schemaVersion"] is JsonValue sv && sv.TryGetValue<string>(out var s) ? s : null;
        if (!ProposalVerifier.IsSupportedSchema(schemaVersion))
        {
            return Rejected(string.Empty, $"Unsupported StrategyResult schema version '{schemaVersion}'.");
        }

        string computedHash;
        StrategyResultDto dto;
        try
        {
            computedHash = CanonicalJson.EnvelopeHash(node, "resultHash");
            dto = FiWire.Deserialize<StrategyResultDto>(node);
        }
        catch (Exception ex) when (ex is FormatException or JsonException or InvalidOperationException)
        {
            return Rejected(string.Empty, $"StrategyResult is malformed: {ex.Message}");
        }

        if (string.IsNullOrEmpty(dto.DecisionId) || string.IsNullOrEmpty(dto.RunId) ||
            string.IsNullOrEmpty(dto.CycleId) || string.IsNullOrEmpty(dto.StrategyId))
        {
            return Rejected(dto.DecisionId, "StrategyResult identity fields are missing.");
        }

        if (!FiDecisionOutcome.All.Contains(dto.Outcome))
        {
            return Rejected(dto.DecisionId, $"Unknown outcome '{dto.Outcome}'.");
        }

        if (context.ExpectedDecisionId is { } expected && expected != dto.DecisionId)
        {
            return Rejected(dto.DecisionId, $"Result is for decision '{dto.DecisionId}', expected '{expected}'.");
        }

        // Integrity is recorded rather than used to drop the audit row.
        var integrity = FiAuditIntegrity.Verified;
        if (!string.Equals(dto.ResultHash, computedHash, StringComparison.Ordinal))
        {
            integrity = FiAuditIntegrity.HashMismatch;
            issues.Add($"Declared resultHash does not match recomputed {computedHash}.");
        }
        else if (string.IsNullOrEmpty(_engineOptions.SigningKey))
        {
            integrity = FiAuditIntegrity.SignatureInvalid;
            issues.Add("ResearchEngine:SigningKey is not configured; result signature cannot be verified.");
        }
        else if (!CanonicalJson.VerifySignature(computedHash, dto.Signature,
                     System.Text.Encoding.UTF8.GetBytes(_engineOptions.SigningKey)))
        {
            integrity = FiAuditIntegrity.SignatureInvalid;
            issues.Add("Result signature is missing or invalid.");
        }
        else if (context.ExpectedRequestHash is { } requestHash &&
                 !string.Equals(requestHash, dto.RequestHash, StringComparison.Ordinal))
        {
            // Authentic, but computed for a different request than the one sent: audited, never actionable.
            integrity = FiAuditIntegrity.RequestHashMismatch;
            issues.Add($"Result requestHash '{dto.RequestHash}' does not match the hash of the request that was sent '{requestHash}'.");
        }

        var engineAllowed = _engineOptions.IsEngineVersionAllowed(dto.Versions.EngineVersion);
        if (!engineAllowed)
        {
            issues.Add($"Engine version '{dto.Versions.EngineVersion}' is not allowed.");
        }

        var existing = await FindExistingAsync(dto.RunId, dto.CycleId, dto.StrategyId, dto.Repetition, dto.DecisionId, cancellationToken);
        if (existing is not null)
        {
            return existing.ResultHash == computedHash && existing.DecisionId == dto.DecisionId
                ? Recorded(DecisionAuditStatus.AlreadyRecorded, existing.DecisionId, existing.Outcome, existing.Integrity, false, issues)
                : Conflict(dto.DecisionId, "A different result is already recorded for this logical decision.");
        }

        var now = _clock.GetUtcNow();
        var decision = new Decision
        {
            DecisionId = dto.DecisionId,
            RunId = dto.RunId,
            CycleId = dto.CycleId,
            StrategyId = dto.StrategyId,
            Repetition = dto.Repetition,
            StrategyKind = dto.StrategyKind,
            PortfolioId = context.PortfolioId,
            Outcome = dto.Outcome,
            Action = dto.Proposal?.Action,
            CompletedAt = SafeInstant(dto.CompletedAt, now),
            ReasonsJson = JsonSerializer.Serialize(dto.Reasons),
            ProposalJson = Json(node["proposal"]),
            ResearchNoteJson = Json(node["researchNote"]),
            ValidationJson = Json(node["validation"]) ?? "[]",
            SpecialistTasksJson = Json(node["specialistTasks"]) ?? "[]",
            VersionsJson = Json(node["versions"]),
            EvidenceBundleIdsJson = JsonSerializer.Serialize(dto.EvidenceBundleIds),
            RequestHash = dto.RequestHash,
            InputHashesJson = Json(node["inputHashes"]) ?? "{}",
            ResultHash = computedHash,
            Signature = dto.Signature,
            Integrity = integrity,
            EngineVersion = dto.Versions.EngineVersion,
            Provider = dto.Versions.Provider,
            Model = dto.Versions.Model,
            ResultJson = strategyResult.Text,
            RecordedAt = now,
        };

        var traceNodes = node["toolTraces"] as JsonArray;
        for (var i = 0; i < dto.ToolTraces.Count; i++)
        {
            var trace = dto.ToolTraces[i];
            decision.ToolTraces.Add(new ToolTrace
            {
                TraceId = trace.TraceId,
                AgentRole = trace.AgentRole,
                ToolName = trace.ToolName,
                RequestJson = Json(traceNodes?[i]?["request"]) ?? "{}",
                ResponseSummaryJson = Json(traceNodes?[i]?["responseSummary"]) ?? "{}",
                OutputRef = trace.OutputRef,
                StartedAt = SafeInstant(trace.StartedAt, now),
                DurationMs = trace.DurationMs,
                Status = trace.Status,
                Error = Truncate(trace.Error),
            });
        }

        foreach (var attempt in dto.Attempts)
        {
            decision.Attempts.Add(new DecisionAttempt
            {
                AttemptId = attempt.AttemptId,
                AttemptNumber = attempt.AttemptNumber,
                AgentRole = attempt.AgentRole,
                Purpose = attempt.Purpose,
                Provider = attempt.Provider,
                Model = attempt.Model,
                InputTokens = attempt.InputTokens,
                OutputTokens = attempt.OutputTokens,
                StartedAt = SafeInstant(attempt.StartedAt, now),
                DurationMs = attempt.DurationMs,
                Status = attempt.Status,
                RecordedResponseId = attempt.RecordedResponseId,
                Error = Truncate(attempt.Error),
            });
        }

        var usage = dto.Usage;
        decision.Usage = new UsageRecord
        {
            GenerationCalls = usage.GenerationCalls,
            ToolCalls = usage.ToolCalls,
            EvidenceCalls = usage.EvidenceCalls,
            UniqueEvidenceChunks = usage.UniqueEvidenceChunks,
            EvidenceTokens = usage.EvidenceTokens,
            InputTokens = usage.InputTokens,
            OutputTokens = usage.OutputTokens,
            DurationMs = usage.DurationMs,
            EstimatedCostUsd = SafeDecimal(usage.EstimatedCostUsd),
            PriceScheduleId = usage.PriceScheduleId,
            BudgetExhausted = usage.BudgetExhausted,
        };

        if (dto.PolicyEvaluation is { } evaluation)
        {
            decision.PolicyEvaluations.Add(MapPolicyEvaluation(evaluation, node["policyEvaluation"], "strategy_result",
                decisionDbId: null, context.PortfolioId, commandId: null, platformRecheckPassed: null, now));
        }

        _db.FiDecisions.Add(decision);
        try
        {
            await _db.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException ex)
        {
            _db.ChangeTracker.Clear();
            var raced = await FindExistingAsync(dto.RunId, dto.CycleId, dto.StrategyId, dto.Repetition, dto.DecisionId, cancellationToken);
            if (raced is not null && raced.ResultHash == computedHash)
            {
                return Recorded(DecisionAuditStatus.AlreadyRecorded, raced.DecisionId, raced.Outcome, raced.Integrity, false, issues);
            }

            _logger.LogWarning(ex, "Decision {DecisionId} could not be recorded", dto.DecisionId);
            return Conflict(dto.DecisionId, "A different result is already recorded for this logical decision.");
        }

        var actionable = integrity == FiAuditIntegrity.Verified && engineAllowed &&
                         dto.Outcome == FiDecisionOutcome.CompletedProposal &&
                         dto.Proposal is { } proposal && proposal.Action != FiDecisionAction.Hold;

        _logger.LogInformation("Recorded decision {DecisionId} ({Outcome}, integrity {Integrity})",
            dto.DecisionId, dto.Outcome, integrity);
        return Recorded(DecisionAuditStatus.Recorded, dto.DecisionId, dto.Outcome, integrity, actionable, issues);
    }

    public async Task<DecisionAuditResult> RecordSynthesizedOutcomeAsync(
        SynthesizedDecisionOutcome outcome,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(outcome);
        if (string.IsNullOrEmpty(outcome.DecisionId) || string.IsNullOrEmpty(outcome.RunId) ||
            string.IsNullOrEmpty(outcome.CycleId) || string.IsNullOrEmpty(outcome.StrategyId))
        {
            return Rejected(outcome.DecisionId, "Decision identity fields are required.");
        }

        if (!FiDecisionOutcome.All.Contains(outcome.Outcome))
        {
            return Rejected(outcome.DecisionId, $"Unknown outcome '{outcome.Outcome}'.");
        }

        var existing = await FindExistingAsync(outcome.RunId, outcome.CycleId, outcome.StrategyId, outcome.Repetition,
            outcome.DecisionId, cancellationToken);
        if (existing is not null)
        {
            return existing.Integrity == FiAuditIntegrity.Synthesized && existing.Outcome == outcome.Outcome &&
                   existing.DecisionId == outcome.DecisionId
                ? Recorded(DecisionAuditStatus.AlreadyRecorded, existing.DecisionId, existing.Outcome, existing.Integrity, false, Array.Empty<string>())
                : Conflict(outcome.DecisionId, "A different outcome is already recorded for this logical decision.");
        }

        var now = _clock.GetUtcNow();
        _db.FiDecisions.Add(new Decision
        {
            DecisionId = outcome.DecisionId,
            RunId = outcome.RunId,
            CycleId = outcome.CycleId,
            StrategyId = outcome.StrategyId,
            Repetition = outcome.Repetition,
            StrategyKind = outcome.StrategyKind,
            PortfolioId = outcome.PortfolioId,
            Outcome = outcome.Outcome,
            Action = outcome.Action,
            ProposalJson = outcome.ProposalJson,
            CompletedAt = outcome.CompletedAt == default ? now : outcome.CompletedAt,
            ReasonsJson = JsonSerializer.Serialize(outcome.Reasons),
            RequestHash = outcome.RequestHash,
            Integrity = FiAuditIntegrity.Synthesized,
            EngineVersion = outcome.EngineVersion,
            RecordedAt = now,
            Usage = new UsageRecord(),
        });

        try
        {
            await _db.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException ex)
        {
            _db.ChangeTracker.Clear();
            _logger.LogWarning(ex, "Synthesized decision {DecisionId} could not be recorded", outcome.DecisionId);
            return Conflict(outcome.DecisionId, "The logical decision was recorded concurrently.");
        }

        return Recorded(DecisionAuditStatus.Recorded, outcome.DecisionId, outcome.Outcome, FiAuditIntegrity.Synthesized,
            false, Array.Empty<string>());
    }

    /// <summary>Maps a contract policy evaluation to its audit row (shared with the commit path).</summary>
    internal static PolicyEvaluation MapPolicyEvaluation(
        PolicyEvaluationDto evaluation,
        JsonNode? node,
        string source,
        long? decisionDbId,
        string? portfolioId,
        string? commandId,
        bool? platformRecheckPassed,
        DateTimeOffset now) => new()
        {
            DecisionDbId = decisionDbId,
            DecisionId = evaluation.DecisionId,
            PortfolioId = portfolioId,
            CommandId = commandId,
            Source = source,
            PolicyId = evaluation.PolicyId,
            Action = evaluation.Action,
            Passed = evaluation.Passed,
            BreachMode = evaluation.BreachMode,
            BootstrapExemptionApplied = evaluation.BootstrapExemptionApplied,
            PostTradeNavUsd = SafeDecimal(evaluation.PostTradeNavUsd),
            PostTradeCashRatio = SafeDecimal(evaluation.PostTradeCashRatio),
            PostTradeMaxSecurityRatio = SafeDecimal(evaluation.PostTradeMaxSecurityRatio),
            PostTradeParallelDv01Usd = SafeDecimal(evaluation.PostTradeParallelDv01Usd),
            TurnoverRatio = SafeDecimal(evaluation.TurnoverRatio),
            OrderCount = evaluation.OrderCount,
            RejectedReasonsJson = JsonSerializer.Serialize(evaluation.RejectedReasons),
            PlatformRecheckPassed = platformRecheckPassed,
            PlatformRecheckReasonsJson = "[]",
            EvaluationJson = Json(node) ?? "{}",
            RecordedAt = now,
        };

    private async Task<Decision?> FindExistingAsync(string runId, string cycleId, string strategyId, int repetition,
        string decisionId, CancellationToken ct) =>
        await _db.FiDecisions.AsNoTracking().FirstOrDefaultAsync(d =>
            (d.RunId == runId && d.CycleId == cycleId && d.StrategyId == strategyId && d.Repetition == repetition) ||
            d.DecisionId == decisionId, ct);

    private static string? Json(JsonNode? node) => node?.ToJsonString();

    private static decimal? SafeDecimal(string? value) =>
        FiWire.TryParseDecimal(value, out var result) ? result : null;

    private static DateTimeOffset SafeInstant(string? value, DateTimeOffset fallback)
    {
        try
        {
            return FiWire.ParseInstant(value, "instant");
        }
        catch (FormatException)
        {
            return fallback;
        }
    }

    private static string? Truncate(string? value) => value is null || value.Length <= 1900 ? value : value[..1900];

    private static DecisionAuditResult Recorded(DecisionAuditStatus status, string decisionId, string outcome,
        string integrity, bool actionable, IReadOnlyList<string> issues) => new()
        {
            Status = status,
            DecisionId = decisionId,
            Outcome = outcome,
            Integrity = integrity,
            ActionableProposal = actionable,
            Issues = issues,
        };

    private static DecisionAuditResult Rejected(string decisionId, string issue) => new()
    {
        Status = DecisionAuditStatus.Rejected,
        DecisionId = decisionId,
        Issues = new[] { issue },
    };

    private static DecisionAuditResult Conflict(string decisionId, string issue) => new()
    {
        Status = DecisionAuditStatus.Conflict,
        DecisionId = decisionId,
        Issues = new[] { issue },
    };
}
