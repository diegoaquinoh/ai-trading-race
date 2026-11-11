namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Wire values shared with the Python research-engine contracts
/// (ai-trading-race-ml/research_engine/contracts). Stored as strings so the
/// database, the JSON contracts and the dashboard use the same vocabulary.
/// </summary>
public static class FiJobState
{
    public const string Queued = "queued";
    public const string Running = "running";
    public const string Completed = "completed";
    public const string Failed = "failed";
    public const string Cancelled = "cancelled";

    public static readonly IReadOnlySet<string> All =
        new HashSet<string> { Queued, Running, Completed, Failed, Cancelled };

    public static bool IsTerminal(string state) =>
        state is Completed or Failed or Cancelled;
}

public static class FiRunType
{
    public const string Replay = "replay";
    public const string Forward = "forward";

    public static readonly IReadOnlySet<string> All = new HashSet<string> { Replay, Forward };
}

public static class FiResponseMode
{
    public const string RecordedReplay = "recorded_replay";
    public const string FreshInference = "fresh_inference";

    public static readonly IReadOnlySet<string> All = new HashSet<string> { RecordedReplay, FreshInference };
}

public static class FiDataMode
{
    public const string SyntheticCurve = "synthetic_curve";
    public const string ObservedSecurity = "observed_security";

    public static readonly IReadOnlySet<string> All = new HashSet<string> { SyntheticCurve, ObservedSecurity };
}

public static class FiCycleStatus
{
    public const string Pending = "pending";
    public const string Running = "running";
    public const string Completed = "completed";
    public const string Skipped = "skipped";
    public const string Failed = "failed";

    /// <summary>Stopped by an operator cancellation; committed events remain authoritative.</summary>
    public const string Cancelled = "cancelled";
}

public static class FiStrategyKind
{
    public const string CashReference = "cash_reference";
    public const string QuantPolicy = "quant_policy";
    public const string SingleAgent = "single_agent";
    public const string SpecialistTeam = "specialist_team";

    public static readonly IReadOnlySet<string> All =
        new HashSet<string> { CashReference, QuantPolicy, SingleAgent, SpecialistTeam };
}

/// <summary>Strategy outcomes (spec 15.2) - distinct from job lifecycle states.</summary>
public static class FiDecisionOutcome
{
    public const string CompletedHold = "completed_hold";
    public const string CompletedProposal = "completed_proposal";
    public const string AbstainedInsufficientEvidence = "abstained_insufficient_evidence";
    public const string ReviewRequired = "review_required";
    public const string FailedInvalidOutput = "failed_invalid_output";
    public const string FailedDependency = "failed_dependency";
    public const string FailedBudget = "failed_budget";
    public const string SkippedStaleData = "skipped_stale_data";
    public const string Cancelled = "cancelled";

    public static readonly IReadOnlySet<string> All = new HashSet<string>
    {
        CompletedHold, CompletedProposal, AbstainedInsufficientEvidence, ReviewRequired,
        FailedInvalidOutput, FailedDependency, FailedBudget, SkippedStaleData, Cancelled
    };
}

public static class FiCommandType
{
    public const string ProcessEvents = "process_events";
    public const string SubmitDecision = "submit_decision";
    public const string ValuePortfolio = "value_portfolio";
    public const string CapitalFlow = "capital_flow";

    public static readonly IReadOnlySet<string> All =
        new HashSet<string> { ProcessEvents, SubmitDecision, ValuePortfolio, CapitalFlow };
}

public static class FiCommandStatus
{
    /// <summary>The proposal was verified and its effects were committed.</summary>
    public const string Committed = "committed";

    /// <summary>The proposal reported a failed reconciliation; the portfolio was blocked.</summary>
    public const string RejectedReconciliation = "rejected_reconciliation";
}

public static class FiSettlementStatus
{
    public const string Pending = "pending";
    public const string Completed = "completed";
}

public static class FiOrderStatus
{
    public const string Accepted = "ACCEPTED";
    public const string Filled = "FILLED";
    public const string Expired = "EXPIRED";
    public const string Cancelled = "CANCELLED";
    public const string Rejected = "REJECTED";

    public static readonly IReadOnlySet<string> All =
        new HashSet<string> { Accepted, Filled, Expired, Cancelled, Rejected };
}

public static class FiAuditIntegrity
{
    /// <summary>Result hash recomputed and HMAC signature verified.</summary>
    public const string Verified = "verified";

    /// <summary>Synthesized by .NET because no engine result exists (dependency failure, stale skip, ...).</summary>
    public const string Synthesized = "synthesized";

    public const string HashMismatch = "hash_mismatch";
    public const string SignatureInvalid = "signature_invalid";

    /// <summary>Authentic result whose requestHash is not the hash of the request the platform sent (no order).</summary>
    public const string RequestHashMismatch = "request_hash_mismatch";
}

/// <summary>
/// Portfolio commit restrictions stored in <see cref="FiPortfolio.BlockedReason"/> (spec 9.3, 15.3).
/// A reconciliation block stops every commit until operator action. An impairment (reason prefixed
/// <see cref="ImpairedPrefix"/>) is recorded when one of the portfolio's commands failed with a
/// deterministic engine error: it stops further discretionary commits (submit_decision) only, so due
/// events, contractual cash flows and valuations keep being processed. Both are cleared by the
/// operator unblock action.
/// </summary>
public static class FiPortfolioRestriction
{
    public const string ImpairedPrefix = "impaired: ";

    public const string Impaired = "impaired";
    public const string Blocked = "blocked";

    public static bool IsImpairment(string? blockedReason) =>
        blockedReason is not null && blockedReason.StartsWith(ImpairedPrefix, StringComparison.Ordinal);

    /// <summary>"impaired", "blocked" or null when the portfolio is unrestricted.</summary>
    public static string? KindOf(string? blockedReason) =>
        blockedReason is null ? null : IsImpairment(blockedReason) ? Impaired : Blocked;

    /// <summary>True when the restriction forbids committing a command of this type.</summary>
    public static bool Forbids(string? blockedReason, string commandType) =>
        blockedReason is not null &&
        (!IsImpairment(blockedReason) || commandType == FiCommandType.SubmitDecision);
}
