using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Application.FixedIncome;

/// <summary>
/// Transactional authority for fixed income portfolios (spec 5.1, 9.5). Applies only
/// verified, signed engine proposals, in one SQL transaction, with expected-version
/// checks and logical command-id idempotency.
/// </summary>
public interface ITransitionCommitService
{
    /// <summary>Creates a portfolio at version 0 (genesis state or a supplied canonical state).</summary>
    Task<PortfolioStateSnapshot> CreatePortfolioAsync(CreateFiPortfolioRequest request, CancellationToken cancellationToken = default);

    /// <summary>Verifies and commits a proposal. Never throws for domain outcomes; see <see cref="TransitionCommitResult.Status"/>.</summary>
    Task<TransitionCommitResult> CommitAsync(RawContractJson proposal, TransitionCommitContext context, CancellationToken cancellationToken = default);

    /// <summary>Returns the committed record of a logical command, if any (check before recomputing a retry).</summary>
    Task<CommandRecordView?> GetCommandAsync(string commandId, CancellationToken cancellationToken = default);

    /// <summary>Current authoritative state (exact canonical text to send back to the engine).</summary>
    Task<PortfolioStateSnapshot?> GetCurrentStateAsync(string portfolioId, CancellationToken cancellationToken = default);

    /// <summary>Operator action clearing a reconciliation block or an impairment.</summary>
    Task<bool> UnblockAsync(string portfolioId, string actor, string reason, CancellationToken cancellationToken = default);

    /// <summary>
    /// Marks the portfolio impaired after one of its commands failed with a deterministic engine error
    /// (spec 15.3): further discretionary commits (submit_decision) are refused with an operator-visible
    /// reason until <see cref="UnblockAsync"/>; due events, cash flows and valuations still commit. An
    /// existing restriction (earlier impairment or reconciliation block) is kept. Returns false when the
    /// portfolio does not exist.
    /// </summary>
    Task<bool> MarkImpairedAsync(string portfolioId, string reason, string? commandId, CancellationToken cancellationToken = default);
}

public sealed record CreateFiPortfolioRequest
{
    public string PortfolioId { get; init; } = string.Empty;
    public string RunId { get; init; } = string.Empty;
    public string StrategyId { get; init; } = string.Empty;
    public int Repetition { get; init; }
    public string RiskPolicyId { get; init; } = string.Empty;
    public string DataMode { get; init; } = string.Empty;
    public DateTimeOffset AsOf { get; init; }

    /// <summary>Optional engine-produced version-0 state JSON (e.g. parity fixtures). Built by .NET when null.</summary>
    public string? InitialStateJson { get; init; }
}

public sealed record PortfolioStateSnapshot(
    string PortfolioId,
    long Version,
    string StateHash,
    string StateJson,
    string RiskPolicyId,
    string? BlockedReason);

public sealed record TransitionCommitContext
{
    /// <summary>Command id the caller issued; the proposal must echo it.</summary>
    public string? ExpectedCommandId { get; init; }

    /// <summary>
    /// Canonical hash of the request body the caller sent (<c>FiRequestBody</c>); the proposal's
    /// requestHash must equal it. Null only for payloads produced without a platform request
    /// (e.g. offline parity fixtures).
    /// </summary>
    public string? ExpectedRequestHash { get; init; }

    public string? ExpectedDecisionId { get; init; }

    public string? Actor { get; init; }
}

public enum TransitionCommitStatus
{
    /// <summary>Effects committed in this call.</summary>
    Committed,

    /// <summary>Same command id and request hash already committed: returns the original result, no new effect.</summary>
    AlreadyCommitted,

    /// <summary>Expected version / input state hash no longer current: discard and recompute.</summary>
    Stale,

    /// <summary>Same command id with a different request/proposal (idempotency mismatch).</summary>
    Conflict,

    /// <summary>Verification failed (tampering, policy, unbalanced journal, duplicate effect...).</summary>
    Rejected,

    /// <summary>Portfolio blocked by a reconciliation failure until operator action.</summary>
    PortfolioBlocked,

    NotFound,
}

public sealed record TransitionCommitResult
{
    public TransitionCommitStatus Status { get; init; }
    public string PortfolioId { get; init; } = string.Empty;
    public string CommandId { get; init; } = string.Empty;
    public string? ProposalHash { get; init; }
    public long? CommittedVersion { get; init; }
    public string? StateHash { get; init; }
    public string? Message { get; init; }
    public IReadOnlyList<VerificationIssue> Issues { get; init; } = Array.Empty<VerificationIssue>();

    public bool Succeeded => Status is TransitionCommitStatus.Committed or TransitionCommitStatus.AlreadyCommitted;
}

public sealed record CommandRecordView(
    string CommandId,
    string CommandType,
    string PortfolioId,
    string RequestHash,
    string ProposalHash,
    string Status,
    long ExpectedVersion,
    long? CommittedVersion,
    string? Reason,
    DateTimeOffset CreatedAt);
