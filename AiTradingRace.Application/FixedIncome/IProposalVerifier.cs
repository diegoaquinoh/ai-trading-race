using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Options;

namespace AiTradingRace.Application.FixedIncome;

/// <summary>
/// Verifies a Python-produced transition proposal before commit (spec 9.5 step 3):
/// schema major, proposal hash recomputed from the received JSON, HMAC signature,
/// engine allowlist, identity/version/state-hash, journal balance and the policy
/// re-check against the platform's own risk policy. Never computes prices or risk.
/// </summary>
public interface IProposalVerifier
{
    ProposalVerificationResult Verify(RawContractJson proposal, ProposalVerificationContext context);
}

public sealed record ProposalVerificationContext
{
    /// <summary>When false only context-free integrity checks run (hash, signature, structure, policy).</summary>
    public bool CheckState { get; init; } = true;

    public string? ExpectedCommandId { get; init; }

    public string? ExpectedRequestHash { get; init; }

    public string? ExpectedPortfolioId { get; init; }

    public string? ExpectedDecisionId { get; init; }

    public long CurrentVersion { get; init; }

    public string CurrentStateHash { get; init; } = string.Empty;

    /// <summary>Stored canonical state JSON (used for the bootstrap-exemption precondition).</summary>
    public string? CurrentStateJson { get; init; }

    public string RiskPolicyId { get; init; } = FixedIncomeOptions.DefaultRiskPolicyId;

    /// <summary>The platform's own policy. The proposal cannot choose another one.</summary>
    public RiskPolicyOptions? RiskPolicy { get; init; }
}

public sealed record VerificationIssue(string Code, string Message);

public static class VerificationCodes
{
    public const string Malformed = "malformed";
    public const string SchemaVersion = "unsupported_schema_version";
    public const string HashMismatch = "proposal_hash_mismatch";
    public const string SignatureInvalid = "signature_invalid";
    public const string SigningKeyMissing = "signing_key_not_configured";
    public const string EngineVersion = "engine_version_not_allowed";
    public const string CommandIdMismatch = "command_id_mismatch";
    public const string RequestHashMismatch = "request_hash_mismatch";
    public const string PortfolioMismatch = "portfolio_mismatch";
    public const string StaleVersion = "stale_version";
    public const string StateHashMismatch = "input_state_hash_mismatch";
    public const string VersionInconsistent = "version_inconsistent";
    public const string NewStateHashMismatch = "new_state_hash_mismatch";
    public const string JournalUnbalanced = "journal_unbalanced";
    public const string JournalLineInvalid = "journal_line_invalid";
    public const string AmountNotCents = "amount_not_cents";
    public const string NoOpWithEffects = "no_op_with_effects";
    public const string PolicyMissing = "policy_evaluation_missing";
    public const string PolicyIdMismatch = "policy_id_mismatch";
    public const string PolicyInputHashMismatch = "risk_policy_input_hash_mismatch";
    public const string PolicyFlagInconsistent = "policy_flag_inconsistent";
    public const string PolicyMetricMissing = "policy_metric_missing";
    public const string PolicyLimitExceeded = "policy_limit_exceeded";
    public const string BootstrapExemptionInvalid = "bootstrap_exemption_invalid";
    public const string LongOnlyViolation = "long_only_violation";
    public const string DecisionMismatch = "decision_mismatch";
    public const string ReconciliationFailed = "reconciliation_failed";
}

public sealed class ProposalVerificationResult
{
    public ProposalVerificationResult(
        IReadOnlyList<VerificationIssue> issues,
        TransitionProposalDto? proposal,
        string? computedProposalHash,
        string? canonicalNewStateJson,
        bool authentic)
    {
        Issues = issues;
        Proposal = proposal;
        ComputedProposalHash = computedProposalHash;
        CanonicalNewStateJson = canonicalNewStateJson;
        IsAuthentic = authentic;
    }

    public IReadOnlyList<VerificationIssue> Issues { get; }

    public TransitionProposalDto? Proposal { get; }

    /// <summary>Hash recomputed by .NET from the received JSON.</summary>
    public string? ComputedProposalHash { get; }

    /// <summary>Canonical JSON text of newState (stored verbatim as the next state).</summary>
    public string? CanonicalNewStateJson { get; }

    /// <summary>Schema, hash, signature and engine version checks passed.</summary>
    public bool IsAuthentic { get; }

    public bool IsValid => Issues.Count == 0;

    public bool HasIssue(string code) => Issues.Any(i => i.Code == code);

    /// <summary>True when every issue is a stale-input issue (caller should recompute).</summary>
    public bool IsStaleOnly =>
        Issues.Count > 0 &&
        Issues.All(i => i.Code is VerificationCodes.StaleVersion or VerificationCodes.StateHashMismatch);

    public bool ReconciliationFailed => HasIssue(VerificationCodes.ReconciliationFailed);
}
