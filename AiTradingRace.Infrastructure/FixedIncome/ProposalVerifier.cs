using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Verifies research-engine transition proposals (spec 9.5 step 3, 14.1). All hashes
/// are recomputed from the received JSON. The policy re-check compares the engine's
/// reported post-trade metrics with the platform's own RiskPolicy; .NET never
/// prices, accrues, sizes or computes risk itself.
/// </summary>
public sealed class ProposalVerifier : IProposalVerifier
{
    private const decimal OneMillion = 1_000_000m;

    private readonly ResearchEngineOptions _engineOptions;

    public ProposalVerifier(IOptions<ResearchEngineOptions> engineOptions)
    {
        _engineOptions = engineOptions.Value;
    }

    public ProposalVerificationResult Verify(RawContractJson proposal, ProposalVerificationContext context)
    {
        ArgumentNullException.ThrowIfNull(proposal);
        ArgumentNullException.ThrowIfNull(context);

        var issues = new List<VerificationIssue>();
        var node = proposal.Node;

        // 1. Schema major version.
        var schemaVersion = ReadString(node, "schemaVersion");
        if (!IsSupportedSchema(schemaVersion))
        {
            issues.Add(Issue(VerificationCodes.SchemaVersion,
                $"Unsupported schema version '{schemaVersion}'; expected major {FiContract.SchemaMajor}."));
            return new ProposalVerificationResult(issues, null, null, null, authentic: false);
        }

        // 2. Proposal hash recomputed from the received JSON (minus proposalHash/signature).
        string computedHash;
        try
        {
            computedHash = CanonicalJson.EnvelopeHash(node, "proposalHash");
        }
        catch (FormatException ex)
        {
            issues.Add(Issue(VerificationCodes.Malformed, ex.Message));
            return new ProposalVerificationResult(issues, null, null, null, authentic: false);
        }

        var declaredHash = ReadString(node, "proposalHash");
        if (!string.Equals(declaredHash, computedHash, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.HashMismatch,
                $"Declared proposalHash '{declaredHash}' does not match recomputed '{computedHash}'."));
        }

        // 3. HMAC signature over the recomputed hash.
        var key = SigningKeyBytes();
        if (key.Length == 0)
        {
            issues.Add(Issue(VerificationCodes.SigningKeyMissing,
                "ResearchEngine:SigningKey is not configured; proposals cannot be authenticated."));
        }
        else if (!CanonicalJson.VerifySignature(computedHash, ReadString(node, "signature"), key))
        {
            issues.Add(Issue(VerificationCodes.SignatureInvalid, "Proposal signature is missing or invalid."));
        }

        // 4. Typed view of the payload.
        TransitionProposalDto dto;
        try
        {
            dto = FiWire.Deserialize<TransitionProposalDto>(node);
        }
        catch (Exception ex) when (ex is JsonException or FormatException or InvalidOperationException)
        {
            issues.Add(Issue(VerificationCodes.Malformed, $"Proposal does not match the contract: {ex.Message}"));
            return new ProposalVerificationResult(issues, null, computedHash, null, authentic: false);
        }

        // 5. Engine version allowlist.
        if (!_engineOptions.IsEngineVersionAllowed(dto.EngineVersion))
        {
            issues.Add(Issue(VerificationCodes.EngineVersion,
                $"Engine version '{dto.EngineVersion}' is not in ResearchEngine:AllowedEngineVersions."));
        }

        var authentic = issues.Count == 0;

        string? canonicalNewState = null;
        try
        {
            VerifyStructure(dto, issues);
            canonicalNewState = VerifyNewState(node, dto, issues);
            VerifyJournals(dto, issues);
            VerifyLedgerAmounts(dto, issues);
            VerifyLongOnly(dto, context, issues);
            VerifyNoOp(dto, issues);
            VerifyPolicy(dto, context, issues);
            VerifyReconciliation(dto, issues);
            if (context.CheckState)
            {
                VerifyAgainstState(dto, context, issues);
            }
        }
        catch (FormatException ex)
        {
            issues.Add(Issue(VerificationCodes.Malformed, ex.Message));
        }

        return new ProposalVerificationResult(issues, dto, computedHash, canonicalNewState, authentic);
    }

    public static bool IsSupportedSchema(string? schemaVersion)
    {
        if (string.IsNullOrEmpty(schemaVersion))
        {
            return false;
        }

        var majorText = schemaVersion.Split('.', 2)[0];
        return int.TryParse(majorText, System.Globalization.NumberStyles.None,
                   System.Globalization.CultureInfo.InvariantCulture, out var major)
               && major == FiContract.SchemaMajor;
    }

    private byte[] SigningKeyBytes() =>
        string.IsNullOrEmpty(_engineOptions.SigningKey)
            ? Array.Empty<byte>()
            : System.Text.Encoding.UTF8.GetBytes(_engineOptions.SigningKey);

    private static void VerifyStructure(TransitionProposalDto dto, List<VerificationIssue> issues)
    {
        if (!FiWire.IsOpaqueId(dto.ProposalId) || !FiWire.IsOpaqueId(dto.CommandId) ||
            !FiWire.IsOpaqueId(dto.PortfolioId) || !FiWire.IsOpaqueId(dto.RunId) ||
            !FiWire.IsStrategyId(dto.StrategyId))
        {
            issues.Add(Issue(VerificationCodes.Malformed, "Proposal identifiers are missing or malformed."));
        }

        if (!FiCommandType.All.Contains(dto.CommandType))
        {
            issues.Add(Issue(VerificationCodes.Malformed, $"Unknown commandType '{dto.CommandType}'."));
        }

        if (!FiWire.IsContentHash(dto.RequestHash))
        {
            issues.Add(Issue(VerificationCodes.Malformed, "requestHash is missing or malformed."));
        }

        if (!string.Equals(dto.EventPriorityTable, FiContract.EventPriorityTable, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.Malformed,
                $"Unsupported event priority table '{dto.EventPriorityTable}'."));
        }

        var expectedNew = dto.NoOp ? dto.ExpectedVersion : dto.ExpectedVersion + 1;
        if (dto.ExpectedVersion < 0 || dto.NewVersion != expectedNew || dto.NewState.Version != dto.NewVersion)
        {
            issues.Add(Issue(VerificationCodes.VersionInconsistent,
                $"newVersion {dto.NewVersion} / newState.version {dto.NewState.Version} inconsistent with " +
                $"expectedVersion {dto.ExpectedVersion} (noOp={dto.NoOp})."));
        }

        if (dto.CommandType != FiCommandType.SubmitDecision && dto.OrdersCreated.Count > 0)
        {
            issues.Add(Issue(VerificationCodes.PolicyFlagInconsistent,
                "Orders may only be created by a submit_decision command."));
        }

        RequireUnique(dto.Events.Select(e => e.EventId), "event", issues);
        RequireUnique(dto.Journals.Select(j => j.JournalId), "journal", issues);
        RequireUnique(dto.OrdersCreated.Select(o => o.OrderId), "order", issues);
        RequireUnique(dto.Fills.Select(f => f.FillId), "fill", issues);
        RequireUnique(dto.Fills.Select(f => f.OrderId), "fill order", issues);
        RequireUnique(dto.SettlementsCreated.Select(s => s.SettlementId), "settlement", issues);
        RequireUnique(dto.SettlementsCreated.Select(s => s.FillId), "settlement fill", issues);
        RequireUnique(dto.CashFlows.Select(c => c.CashFlowId), "cash flow", issues);

        foreach (var order in dto.OrdersCreated.Concat(dto.OrderStatusChanges))
        {
            if (!FiOrderStatus.All.Contains(order.Status) || order.Side is not (FiSide.Buy or FiSide.Sell))
            {
                issues.Add(Issue(VerificationCodes.Malformed, $"Order {order.OrderId} has invalid side/status."));
            }
        }
    }

    private static string? VerifyNewState(JsonObject node, TransitionProposalDto dto, List<VerificationIssue> issues)
    {
        if (node["newState"] is not JsonObject newState)
        {
            issues.Add(Issue(VerificationCodes.Malformed, "newState is missing."));
            return null;
        }

        var canonical = CanonicalJson.Serialize(newState);
        var hash = CanonicalJson.Sha256(canonical);
        if (!string.Equals(hash, dto.NewStateHash, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.NewStateHashMismatch,
                $"newStateHash '{dto.NewStateHash}' does not match SHA-256 of canonical newState '{hash}'."));
        }

        if (dto.NewState.PortfolioId != dto.PortfolioId || dto.NewState.StrategyId != dto.StrategyId ||
            dto.NewState.RunId != dto.RunId)
        {
            issues.Add(Issue(VerificationCodes.PortfolioMismatch,
                "newState identity (portfolio/strategy/run) differs from the proposal identity."));
        }

        if (!IsSupportedSchema(dto.NewState.SchemaVersion))
        {
            issues.Add(Issue(VerificationCodes.SchemaVersion,
                $"newState schema version '{dto.NewState.SchemaVersion}' is not supported."));
        }

        return canonical;
    }

    private static void VerifyJournals(TransitionProposalDto dto, List<VerificationIssue> issues)
    {
        foreach (var journal in dto.Journals)
        {
            if (journal.Lines.Count < 2)
            {
                issues.Add(Issue(VerificationCodes.JournalLineInvalid,
                    $"Journal {journal.JournalId} needs at least two lines."));
            }

            var debits = 0m;
            var credits = 0m;
            foreach (var line in journal.Lines)
            {
                if (!FiWire.IsCents(line.DebitUsd) || !FiWire.IsCents(line.CreditUsd))
                {
                    issues.Add(Issue(VerificationCodes.AmountNotCents,
                        $"Journal {journal.JournalId} line {line.LineId} is not posted in cents."));
                    continue;
                }

                var debit = FiWire.ParseDecimal(line.DebitUsd, "debitUsd");
                var credit = FiWire.ParseDecimal(line.CreditUsd, "creditUsd");
                if (debit < 0 || credit < 0 || (debit > 0) == (credit > 0))
                {
                    issues.Add(Issue(VerificationCodes.JournalLineInvalid,
                        $"Journal {journal.JournalId} line {line.LineId} must have exactly one positive side."));
                }

                debits += debit;
                credits += credit;
            }

            if (debits != credits)
            {
                issues.Add(Issue(VerificationCodes.JournalUnbalanced,
                    $"Journal {journal.JournalId} is unbalanced: debits {debits} != credits {credits}."));
            }
        }
    }

    private static void VerifyLedgerAmounts(TransitionProposalDto dto, List<VerificationIssue> issues)
    {
        foreach (var fill in dto.Fills)
        {
            RequireCents(fill.ConsiderationUsd, $"fill {fill.FillId} considerationUsd", issues);
            RequireCents(fill.FeesUsd, $"fill {fill.FillId} feesUsd", issues);
        }

        foreach (var settlement in dto.SettlementsCreated)
        {
            RequireCents(settlement.CashUsd, $"settlement {settlement.SettlementId} cashUsd", issues);
        }

        foreach (var cashFlow in dto.CashFlows)
        {
            RequireCents(cashFlow.AmountUsd, $"cash flow {cashFlow.CashFlowId} amountUsd", issues);
        }
    }

    private static void VerifyLongOnly(TransitionProposalDto dto, ProposalVerificationContext context, List<VerificationIssue> issues)
    {
        var state = dto.NewState;
        if (FiWire.ParseDecimal(state.CashUsd, "newState.cashUsd") < 0 ||
            FiWire.ParseDecimal(state.ReservedCashUsd, "newState.reservedCashUsd") < 0)
        {
            issues.Add(Issue(VerificationCodes.LongOnlyViolation,
                "Settled or reserved cash is negative (leverage is disabled)."));
        }

        foreach (var position in state.Positions)
        {
            if (FiWire.ParseDecimal(position.EconomicFace, "economicFace") < 0 ||
                FiWire.ParseDecimal(position.SettledFace, "settledFace") < 0)
            {
                issues.Add(Issue(VerificationCodes.LongOnlyViolation,
                    $"Negative face for {position.SecurityId} is not permitted (long only)."));
            }
        }

        foreach (var order in dto.OrdersCreated)
        {
            if (FiWire.ParseDecimal(order.Face, "order.face") <= 0)
            {
                issues.Add(Issue(VerificationCodes.LongOnlyViolation,
                    $"Order {order.OrderId} face must be positive."));
            }
        }

        foreach (var fill in dto.Fills)
        {
            if (FiWire.ParseDecimal(fill.Face, "fill.face") <= 0)
            {
                issues.Add(Issue(VerificationCodes.LongOnlyViolation, $"Fill {fill.FillId} face must be positive."));
            }
        }

        var longOnly = context.RiskPolicy?.LongOnly ?? true;
        if (longOnly && dto.PolicyEvaluation is { } evaluation)
        {
            foreach (var target in evaluation.OriginalTargets.Concat(evaluation.NormalizedTargets))
            {
                if (FiWire.ParseDecimal(target.Weight, "targetWeight") < 0)
                {
                    issues.Add(Issue(VerificationCodes.LongOnlyViolation,
                        $"Negative target weight for {target.SecurityId} is not permitted."));
                }
            }
        }
    }

    private static void VerifyNoOp(TransitionProposalDto dto, List<VerificationIssue> issues)
    {
        if (!dto.NoOp)
        {
            return;
        }

        if (dto.Journals.Count > 0 || dto.OrdersCreated.Count > 0 || dto.OrderStatusChanges.Count > 0 ||
            dto.Fills.Count > 0 || dto.SettlementsCreated.Count > 0 || dto.SettlementsCompleted.Count > 0 ||
            dto.CashFlows.Count > 0 || dto.Valuation is not null)
        {
            issues.Add(Issue(VerificationCodes.NoOpWithEffects, "A no-op proposal cannot carry financial effects."));
        }
    }

    private void VerifyPolicy(TransitionProposalDto dto, ProposalVerificationContext context, List<VerificationIssue> issues)
    {
        if (dto.CommandType != FiCommandType.SubmitDecision)
        {
            return;
        }

        var policy = context.RiskPolicy;
        if (policy is null)
        {
            issues.Add(Issue(VerificationCodes.PolicyMissing,
                $"Risk policy '{context.RiskPolicyId}' is not configured on the platform."));
            return;
        }

        var evaluation = dto.PolicyEvaluation;
        if (evaluation is null)
        {
            issues.Add(Issue(VerificationCodes.PolicyMissing, "submit_decision proposals must include a policy evaluation."));
            return;
        }

        if (!string.Equals(evaluation.PolicyId, context.RiskPolicyId, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.PolicyIdMismatch,
                $"Policy evaluation used '{evaluation.PolicyId}' but the portfolio is governed by '{context.RiskPolicyId}'."));
        }

        // The engine must have evaluated exactly the platform's policy document.
        var platformPolicyHash = CanonicalJson.ContentHash(FiWire.ToNode(policy.ToWire(context.RiskPolicyId)));
        if (!dto.InputHashes.TryGetValue("riskPolicy", out var usedPolicyHash))
        {
            issues.Add(Issue(VerificationCodes.PolicyInputHashMismatch, "inputHashes.riskPolicy is missing."));
        }
        else if (!string.Equals(usedPolicyHash, platformPolicyHash, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.PolicyInputHashMismatch,
                "The risk policy evaluated by the engine differs from the platform-configured policy."));
        }

        if (context.ExpectedDecisionId is { } expectedDecision &&
            !string.Equals(evaluation.DecisionId, expectedDecision, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.DecisionMismatch,
                $"Policy evaluation decision '{evaluation.DecisionId}' differs from expected '{expectedDecision}'."));
        }

        var orders = dto.OrdersCreated;
        if (orders.Any(o => !string.Equals(o.DecisionId, evaluation.DecisionId, StringComparison.Ordinal)))
        {
            issues.Add(Issue(VerificationCodes.DecisionMismatch, "Every created order must reference the evaluated decision."));
        }

        // Passed flag consistency.
        if (!evaluation.Passed && orders.Count > 0)
        {
            issues.Add(Issue(VerificationCodes.PolicyFlagInconsistent,
                "Orders were created although the policy evaluation did not pass."));
        }

        if (evaluation.Passed && (evaluation.Checks.Any(c => !c.Passed) || evaluation.RejectedReasons.Count > 0))
        {
            issues.Add(Issue(VerificationCodes.PolicyFlagInconsistent,
                "Policy evaluation reports passed=true with failed checks or rejection reasons."));
        }

        if (evaluation.OrderCount != orders.Count)
        {
            issues.Add(Issue(VerificationCodes.PolicyFlagInconsistent,
                $"Policy orderCount {evaluation.OrderCount} differs from {orders.Count} created orders."));
        }

        if (evaluation.Action == FiDecisionAction.Hold && orders.Count > 0)
        {
            issues.Add(Issue(VerificationCodes.PolicyFlagInconsistent, "A HOLD decision cannot create orders."));
        }

        VerifyCheckLimits(evaluation, policy, issues);

        // Bootstrap exemption: honoured only when flagged, on a BOOTSTRAP action from an
        // uninvested state, and when the platform policy allows it.
        var bootstrapValid = false;
        if (evaluation.BootstrapExemptionApplied)
        {
            var reasons = BootstrapPreconditionFailures(dto, evaluation, policy, context);
            if (reasons.Count == 0)
            {
                bootstrapValid = true;
            }
            else
            {
                issues.Add(Issue(VerificationCodes.BootstrapExemptionInvalid,
                    "Bootstrap turnover exemption is not applicable: " + string.Join("; ", reasons)));
            }
        }

        if (orders.Count == 0)
        {
            return;
        }

        // Missing risk output blocks the order set; it is never interpreted as zero risk.
        if (orders.Count > policy.MaxOrdersPerDecision)
        {
            issues.Add(Limit($"{orders.Count} orders exceed maxOrdersPerDecision {policy.MaxOrdersPerDecision}."));
        }

        var nav = Metric(evaluation.PostTradeNavUsd, "postTradeNavUsd", issues);
        var cashRatio = Metric(evaluation.PostTradeCashRatio, "postTradeCashRatio", issues);
        var maxSecurity = Metric(evaluation.PostTradeMaxSecurityRatio, "postTradeMaxSecurityRatio", issues);
        var dv01 = Metric(evaluation.PostTradeParallelDv01Usd, "postTradeParallelDv01Usd", issues);
        var turnover = Metric(evaluation.TurnoverRatio, "turnoverRatio", issues);

        // Breach policy (spec 9.3, block_risk_increasing_v1): a post-trade value outside its limit is
        // accepted only in breach mode, when the engine reported the pre-trade value, that value was
        // already outside the same limit, and the order set does not worsen it. Anything else fails closed.
        if (cashRatio is { } cr && cr < policy.MinCashRatio)
        {
            var pre = OptionalMetric(evaluation.PreTradeCashRatio, "preTradeCashRatio");
            if (!BreachNotWorsened(evaluation, pre, preViolates: p => p < policy.MinCashRatio, notWorse: p => cr >= p))
            {
                issues.Add(Limit($"Post-trade cash ratio {cr} is below minCashRatio {policy.MinCashRatio}" +
                                 BreachDetail(evaluation, pre) + "."));
            }
        }

        if (maxSecurity is { } ms && ms > policy.MaxSingleSecurityRatio)
        {
            var pre = OptionalMetric(evaluation.PreTradeMaxSecurityRatio, "preTradeMaxSecurityRatio");
            if (!BreachNotWorsened(evaluation, pre, preViolates: p => p > policy.MaxSingleSecurityRatio, notWorse: p => ms <= p))
            {
                issues.Add(Limit($"Post-trade single-security ratio {ms} exceeds {policy.MaxSingleSecurityRatio}" +
                                 BreachDetail(evaluation, pre) + "."));
            }
        }

        if (nav is { } n && dv01 is { } d)
        {
            if (n <= 0)
            {
                issues.Add(Limit($"Post-trade NAV {n} must be positive for risk-taking orders."));
            }
            else if (ExceedsDv01(d, n, policy))
            {
                // The pre-trade DV01 is tested against the cap scaled by pre-trade NAV; an engine that does
                // not report pre-trade NAV (older proposals) falls back to the post-trade NAV.
                var pre = OptionalMetric(evaluation.PreTradeParallelDv01Usd, "preTradeParallelDv01Usd");
                var preNav = OptionalMetric(evaluation.PreTradeNavUsd, "preTradeNavUsd") is { } pn && pn > 0 ? pn : n;
                if (!BreachNotWorsened(evaluation, pre, preViolates: p => ExceedsDv01(p, preNav, policy),
                        notWorse: p => Math.Abs(d) <= Math.Abs(p)))
                {
                    issues.Add(Limit(
                        $"Post-trade parallel DV01 {d} USD exceeds {policy.MaxParallelDv01UsdPerMillionNav} USD per 1,000,000 NAV (NAV {n})" +
                        BreachDetail(evaluation, pre) + "."));
                }
            }
        }

        if (turnover is { } t && t > policy.MaxDailyTurnoverRatio && !bootstrapValid)
        {
            issues.Add(Limit($"Turnover ratio {t} exceeds maxDailyTurnoverRatio {policy.MaxDailyTurnoverRatio}."));
        }
    }

    private static void VerifyCheckLimits(PolicyEvaluationDto evaluation, RiskPolicyOptions policy, List<VerificationIssue> issues)
    {
        foreach (var check in evaluation.Checks)
        {
            if (check.Limit is null || !FiWire.TryParseDecimal(check.Limit, out var limit))
            {
                continue;
            }

            var id = check.CheckId.Split(':', 2)[0];
            decimal? platformLimit = id switch
            {
                "min_cash_ratio" => policy.MinCashRatio,
                "max_single_security_ratio" => policy.MaxSingleSecurityRatio,
                "max_daily_turnover_ratio" => policy.MaxDailyTurnoverRatio,
                "max_orders_per_decision" => policy.MaxOrdersPerDecision,
                _ => null,
            };

            if (platformLimit is { } expected && limit != expected)
            {
                issues.Add(Issue(VerificationCodes.PolicyIdMismatch,
                    $"Check '{check.CheckId}' used limit {limit}; the platform policy limit is {expected}."));
            }
        }
    }

    private static List<string> BootstrapPreconditionFailures(
        TransitionProposalDto dto,
        PolicyEvaluationDto evaluation,
        RiskPolicyOptions policy,
        ProposalVerificationContext context)
    {
        var reasons = new List<string>();
        if (!policy.BootstrapTurnoverExemption)
        {
            reasons.Add("the platform policy disables the bootstrap exemption");
        }

        if (evaluation.Action != FiDecisionAction.Bootstrap)
        {
            reasons.Add($"action is {evaluation.Action}, not BOOTSTRAP");
        }

        if (dto.OrdersCreated.Any(o => !o.Bootstrap))
        {
            reasons.Add("every bootstrap order must carry bootstrap=true");
        }

        if (string.IsNullOrEmpty(context.CurrentStateJson))
        {
            reasons.Add("the current state is unavailable to confirm an uninvested starting point");
            return reasons;
        }

        var current = JsonSerializer.Deserialize<PortfolioStateDto>(context.CurrentStateJson, FiContract.WireOptions)
                      ?? new PortfolioStateDto();
        var invested = current.Positions.Any(p =>
            FiWire.ParseDecimal(p.EconomicFace, "economicFace") != 0 ||
            FiWire.ParseDecimal(p.SettledFace, "settledFace") != 0);
        if (invested || current.OpenOrders.Count > 0 || current.PendingSettlements.Count > 0)
        {
            reasons.Add("the portfolio is not in its uninvested initial state");
        }

        return reasons;
    }

    private static void VerifyReconciliation(TransitionProposalDto dto, List<VerificationIssue> issues)
    {
        var reconciliation = dto.Reconciliation;
        if (!reconciliation.Ok || !reconciliation.JournalsBalanced)
        {
            var detail = reconciliation.Messages.Count > 0 ? string.Join("; ", reconciliation.Messages) : "no detail";
            issues.Add(Issue(VerificationCodes.ReconciliationFailed, $"Engine reconciliation failed: {detail}"));
        }
        else if (!string.IsNullOrEmpty(dto.NewState.BlockedReason))
        {
            issues.Add(Issue(VerificationCodes.ReconciliationFailed,
                $"Engine marked the state blocked: {dto.NewState.BlockedReason}"));
        }
    }

    private static void VerifyAgainstState(TransitionProposalDto dto, ProposalVerificationContext context, List<VerificationIssue> issues)
    {
        if (context.ExpectedCommandId is { } commandId && !string.Equals(dto.CommandId, commandId, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.CommandIdMismatch,
                $"Proposal command id '{dto.CommandId}' differs from the issued command '{commandId}'."));
        }

        if (context.ExpectedRequestHash is { } requestHash && !string.Equals(dto.RequestHash, requestHash, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.RequestHashMismatch,
                "Proposal requestHash differs from the hash of the request that was sent."));
        }

        if (context.ExpectedPortfolioId is { } portfolioId && !string.Equals(dto.PortfolioId, portfolioId, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.PortfolioMismatch,
                $"Proposal targets portfolio '{dto.PortfolioId}', expected '{portfolioId}'."));
        }

        if (dto.ExpectedVersion != context.CurrentVersion)
        {
            issues.Add(Issue(VerificationCodes.StaleVersion,
                $"Proposal expects version {dto.ExpectedVersion} but the current version is {context.CurrentVersion}."));
        }

        if (!dto.InputHashes.TryGetValue("portfolioState", out var inputStateHash) ||
            !string.Equals(inputStateHash, context.CurrentStateHash, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.StateHashMismatch,
                "inputHashes.portfolioState does not match the stored state hash."));
        }

        if (dto.NoOp && !string.Equals(dto.NewStateHash, context.CurrentStateHash, StringComparison.Ordinal))
        {
            issues.Add(Issue(VerificationCodes.VersionInconsistent, "A no-op proposal must leave the state unchanged."));
        }
    }

    private static bool ExceedsDv01(decimal dv01, decimal nav, RiskPolicyOptions policy) =>
        Math.Abs(dv01) * OneMillion > policy.MaxParallelDv01UsdPerMillionNav * nav;

    /// <summary>
    /// True only for a validated risk-reducing (or neutral) action during a breach: breach mode is on,
    /// the pre-trade value is present and already violates the limit, and the post-trade value is not worse.
    /// </summary>
    private static bool BreachNotWorsened(PolicyEvaluationDto evaluation, decimal? pre, Func<decimal, bool> preViolates,
        Func<decimal, bool> notWorse) =>
        evaluation.BreachMode && pre is { } value && preViolates(value) && notWorse(value);

    private static string BreachDetail(PolicyEvaluationDto evaluation, decimal? pre) => (evaluation.BreachMode, pre) switch
    {
        (false, _) => string.Empty,
        (true, null) => " (breach mode, but the pre-trade value is missing: fail closed)",
        (true, { } p) => $" (breach mode; pre-trade {p}: not an accepted risk-reducing action)",
    };

    private static decimal? OptionalMetric(string? value, string name) => value is null ? null : FiWire.ParseDecimal(value, name);

    private static decimal? Metric(string? value, string name, List<VerificationIssue> issues)
    {
        if (value is null)
        {
            issues.Add(Issue(VerificationCodes.PolicyMetricMissing,
                $"Policy metric '{name}' is missing; missing risk output blocks the affected orders."));
            return null;
        }

        return FiWire.ParseDecimal(value, name);
    }

    private static void RequireCents(string value, string label, List<VerificationIssue> issues)
    {
        if (!FiWire.IsCents(value))
        {
            issues.Add(Issue(VerificationCodes.AmountNotCents, $"{label} '{value}' is not a cents amount."));
        }
    }

    private static void RequireUnique(IEnumerable<string> ids, string label, List<VerificationIssue> issues)
    {
        var duplicates = ids.GroupBy(x => x, StringComparer.Ordinal).Where(g => g.Count() > 1).Select(g => g.Key).ToList();
        if (duplicates.Count > 0)
        {
            issues.Add(Issue(VerificationCodes.Malformed, $"Duplicate {label} ids in proposal: {string.Join(", ", duplicates)}."));
        }
    }

    private static string? ReadString(JsonObject node, string property) =>
        node[property] is JsonValue value && value.GetValueKind() == JsonValueKind.String
            ? value.GetValue<string>()
            : null;

    private static VerificationIssue Limit(string message) => Issue(VerificationCodes.PolicyLimitExceeded, message);

    private static VerificationIssue Issue(string code, string message) => new(code, message);
}
