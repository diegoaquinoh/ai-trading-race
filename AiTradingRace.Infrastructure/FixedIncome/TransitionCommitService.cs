using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.Logging;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Atomic, idempotent application of verified transition proposals (spec 9.5).
/// One SQL transaction per commit: load the portfolio with its concurrency token,
/// enforce command-id idempotency, verify version/state hash/policy, insert the
/// authorized ledger/order/settlement/cash-flow/valuation records and advance the
/// version. Nothing that is not part of a verified, signed proposal is applied.
/// </summary>
public sealed class TransitionCommitService : ITransitionCommitService
{
    private const int MaxReasonLength = 1900;

    private readonly TradingDbContext _db;
    private readonly IProposalVerifier _verifier;
    private readonly IRiskPolicyProvider _policies;
    private readonly TimeProvider _clock;
    private readonly ILogger<TransitionCommitService> _logger;

    public TransitionCommitService(
        TradingDbContext db,
        IProposalVerifier verifier,
        IRiskPolicyProvider policies,
        ILogger<TransitionCommitService> logger,
        TimeProvider? clock = null)
    {
        _db = db;
        _verifier = verifier;
        _policies = policies;
        _logger = logger;
        _clock = clock ?? TimeProvider.System;
    }

    public async Task<PortfolioStateSnapshot> CreatePortfolioAsync(CreateFiPortfolioRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!FiWire.IsOpaqueId(request.PortfolioId) || !FiWire.IsOpaqueId(request.RunId) || !FiWire.IsStrategyId(request.StrategyId))
        {
            throw new ArgumentException("Portfolio, run and strategy identifiers must match the contract patterns.");
        }

        if (_policies.FindRiskPolicy(request.RiskPolicyId) is null)
        {
            throw new ArgumentException($"Risk policy '{request.RiskPolicyId}' is not configured.");
        }

        JsonObject state;
        if (request.InitialStateJson is null)
        {
            state = PortfolioGenesis.Build(request.PortfolioId, request.StrategyId, request.RunId, request.AsOf);
        }
        else
        {
            state = JsonNode.Parse(request.InitialStateJson) as JsonObject
                    ?? throw new ArgumentException("InitialStateJson must be a JSON object.");
            var parsed = FiWire.Deserialize<PortfolioStateDto>(state);
            if (parsed.Version != 0 || parsed.PortfolioId != request.PortfolioId ||
                parsed.StrategyId != request.StrategyId || parsed.RunId != request.RunId)
            {
                throw new ArgumentException("InitialStateJson must be version 0 of the requested portfolio.");
            }
        }

        var canonical = CanonicalJson.Serialize(state);
        var hash = CanonicalJson.Sha256(canonical);

        var existing = await _db.FiPortfolios.AsNoTracking()
            .FirstOrDefaultAsync(p => p.PortfolioId == request.PortfolioId, cancellationToken);
        if (existing is not null)
        {
            var genesis = await _db.FiPortfolioStateVersions.AsNoTracking()
                .FirstOrDefaultAsync(v => v.PortfolioId == request.PortfolioId && v.Version == 0, cancellationToken);
            if (genesis is not null && genesis.StateHash == hash)
            {
                return (await GetCurrentStateAsync(request.PortfolioId, cancellationToken))!;
            }

            throw new InvalidOperationException($"Portfolio '{request.PortfolioId}' already exists with a different genesis state.");
        }

        var now = _clock.GetUtcNow();
        _db.FiPortfolios.Add(new FiPortfolio
        {
            PortfolioId = request.PortfolioId,
            RunId = request.RunId,
            StrategyId = request.StrategyId,
            Repetition = request.Repetition,
            RiskPolicyId = request.RiskPolicyId,
            DataMode = request.DataMode,
            CurrentVersion = 0,
            CurrentStateHash = hash,
            CreatedAt = now,
            UpdatedAt = now,
        });
        _db.FiPortfolioStateVersions.Add(new PortfolioStateVersion
        {
            PortfolioId = request.PortfolioId,
            Version = 0,
            StateJson = canonical,
            StateHash = hash,
            AsOf = FiWire.ParseInstant(state["asOf"]?.GetValue<string>(), "asOf"),
            CreatedAt = now,
        });
        await _db.SaveChangesAsync(cancellationToken);

        return new PortfolioStateSnapshot(request.PortfolioId, 0, hash, canonical, request.RiskPolicyId, null);
    }

    public async Task<PortfolioStateSnapshot?> GetCurrentStateAsync(string portfolioId, CancellationToken cancellationToken = default)
    {
        var portfolio = await _db.FiPortfolios.AsNoTracking()
            .FirstOrDefaultAsync(p => p.PortfolioId == portfolioId, cancellationToken);
        if (portfolio is null)
        {
            return null;
        }

        var state = await _db.FiPortfolioStateVersions.AsNoTracking()
            .FirstOrDefaultAsync(v => v.PortfolioId == portfolioId && v.Version == portfolio.CurrentVersion, cancellationToken);
        if (state is null)
        {
            return null;
        }

        return new PortfolioStateSnapshot(portfolio.PortfolioId, portfolio.CurrentVersion, state.StateHash,
            state.StateJson, portfolio.RiskPolicyId, portfolio.BlockedReason);
    }

    public async Task<CommandRecordView?> GetCommandAsync(string commandId, CancellationToken cancellationToken = default)
    {
        var record = await _db.FiCommandRecords.AsNoTracking()
            .FirstOrDefaultAsync(c => c.CommandId == commandId, cancellationToken);
        return record is null ? null : ToView(record);
    }

    public async Task<bool> UnblockAsync(string portfolioId, string actor, string reason, CancellationToken cancellationToken = default)
    {
        var portfolio = await _db.FiPortfolios.FirstOrDefaultAsync(p => p.PortfolioId == portfolioId, cancellationToken);
        if (portfolio is null)
        {
            return false;
        }

        if (portfolio.BlockedReason is null)
        {
            return true;
        }

        _logger.LogWarning(
            "Operator {Actor} unblocked fixed income portfolio {PortfolioId} (was: {BlockedReason}). Reason: {Reason}",
            actor, portfolioId, portfolio.BlockedReason, reason);
        portfolio.BlockedReason = null;
        portfolio.BlockedAt = null;
        portfolio.BlockedByCommandId = null;
        portfolio.UpdatedAt = _clock.GetUtcNow();
        portfolio.ConcurrencyStamp = Guid.NewGuid();
        await _db.SaveChangesAsync(cancellationToken);
        return true;
    }

    public async Task<bool> MarkImpairedAsync(string portfolioId, string reason, string? commandId, CancellationToken cancellationToken = default)
    {
        for (var attempt = 0; attempt < 3; attempt++)
        {
            var portfolio = await _db.FiPortfolios.FirstOrDefaultAsync(p => p.PortfolioId == portfolioId, cancellationToken);
            if (portfolio is null)
            {
                return false;
            }

            if (portfolio.BlockedReason is not null)
            {
                _db.Entry(portfolio).State = EntityState.Detached;
                return true; // keep the first restriction (a reconciliation block is never downgraded)
            }

            var now = _clock.GetUtcNow();
            portfolio.BlockedReason = Truncate(FiPortfolioRestriction.ImpairedPrefix + reason);
            portfolio.BlockedAt = now;
            portfolio.BlockedByCommandId = commandId;
            portfolio.UpdatedAt = now;
            portfolio.ConcurrencyStamp = Guid.NewGuid();
            try
            {
                await _db.SaveChangesAsync(cancellationToken);
                _db.Entry(portfolio).State = EntityState.Detached;
                _logger.LogError(
                    "Fixed income portfolio {PortfolioId} impaired by command {CommandId}; discretionary commits are blocked " +
                    "until operator action: {Reason}", portfolioId, commandId, reason);
                return true;
            }
            catch (DbUpdateConcurrencyException)
            {
                _db.ChangeTracker.Clear(); // a commit raced; reload and re-apply
            }
        }

        return true;
    }

    public async Task<TransitionCommitResult> CommitAsync(
        RawContractJson proposal,
        TransitionCommitContext context,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(proposal);
        ArgumentNullException.ThrowIfNull(context);

        var portfolioId = proposal.Node["portfolioId"] is JsonValue v && v.TryGetValue<string>(out var id) ? id : null;
        var commandIdHint = proposal.Node["commandId"] is JsonValue c && c.TryGetValue<string>(out var cid) ? cid : string.Empty;
        if (string.IsNullOrEmpty(portfolioId))
        {
            return Result(TransitionCommitStatus.Rejected, string.Empty, commandIdHint, "Proposal has no portfolioId.",
                new[] { new VerificationIssue(VerificationCodes.Malformed, "portfolioId is missing.") });
        }

        await using var transaction = await BeginTransactionAsync(cancellationToken);
        try
        {
            var outcome = await CommitInTransactionAsync(proposal, context, portfolioId, commandIdHint, cancellationToken);
            if (outcome.Persist)
            {
                await _db.SaveChangesAsync(cancellationToken);
                if (transaction is not null)
                {
                    await transaction.CommitAsync(cancellationToken);
                }
            }
            else if (transaction is not null)
            {
                await transaction.RollbackAsync(cancellationToken);
            }

            if (outcome.Result.Status == TransitionCommitStatus.Committed)
            {
                _logger.LogInformation(
                    "Committed {CommandId} on {PortfolioId}: version {Version}, state {StateHash}",
                    outcome.Result.CommandId, portfolioId, outcome.Result.CommittedVersion, outcome.Result.StateHash);
            }
            else if (!outcome.Result.Succeeded)
            {
                _logger.LogWarning("Commit {CommandId} on {PortfolioId} returned {Status}: {Message}",
                    outcome.Result.CommandId, portfolioId, outcome.Result.Status, outcome.Result.Message);
            }

            return outcome.Result;
        }
        catch (DbUpdateConcurrencyException)
        {
            await RollbackQuietlyAsync(transaction);
            _db.ChangeTracker.Clear();
            return Result(TransitionCommitStatus.Stale, portfolioId, commandIdHint,
                "The portfolio changed concurrently; discard this proposal and recompute against the new state.",
                new[] { new VerificationIssue(VerificationCodes.StaleVersion, "Concurrent commit detected.") });
        }
        catch (DbUpdateException ex)
        {
            await RollbackQuietlyAsync(transaction);
            _db.ChangeTracker.Clear();

            // A racing retry of the same command may have committed first.
            var existing = await _db.FiCommandRecords.AsNoTracking()
                .FirstOrDefaultAsync(r => r.CommandId == commandIdHint, cancellationToken);
            var requestHash = proposal.Node["requestHash"] is JsonValue rh && rh.TryGetValue<string>(out var h) ? h : null;
            if (existing is not null)
            {
                return existing.RequestHash == requestHash
                    ? FromRecord(existing, TransitionCommitStatus.AlreadyCommitted)
                    : Result(TransitionCommitStatus.Conflict, portfolioId, commandIdHint,
                        "Command id was already used with a different request.", Array.Empty<VerificationIssue>());
            }

            // A concurrent writer advanced the portfolio between verification and save (the next state
            // version already exists): stale, recompute against the new state.
            var expectedVersion = proposal.Node["expectedVersion"] is JsonValue ev && ev.TryGetValue<long>(out var x) ? x : (long?)null;
            var currentVersion = await _db.FiPortfolios.AsNoTracking()
                .Where(p => p.PortfolioId == portfolioId)
                .Select(p => (long?)p.CurrentVersion)
                .FirstOrDefaultAsync(cancellationToken);
            if (expectedVersion is not null && currentVersion is not null && currentVersion != expectedVersion)
            {
                return Result(TransitionCommitStatus.Stale, portfolioId, commandIdHint,
                    "The portfolio changed concurrently; discard this proposal and recompute against the new state.",
                    new[] { new VerificationIssue(VerificationCodes.StaleVersion, $"Current version is {currentVersion}.") });
            }

            _logger.LogWarning(ex, "Commit {CommandId} violated a uniqueness constraint", commandIdHint);
            return Result(TransitionCommitStatus.Rejected, portfolioId, commandIdHint,
                "The proposal would create a second financial effect for an already-committed event.",
                new[] { new VerificationIssue("duplicate_effect", ex.InnerException?.Message ?? ex.Message) });
        }
    }

    private sealed record CommitOutcome(TransitionCommitResult Result, bool Persist);

    private async Task<CommitOutcome> CommitInTransactionAsync(
        RawContractJson proposal,
        TransitionCommitContext context,
        string portfolioId,
        string commandIdHint,
        CancellationToken ct)
    {
        // Always read the authoritative row: an instance still tracked from an earlier commit in this scope is
        // stale when another writer committed meanwhile, and must surface as Stale (recompute), not as a
        // duplicate effect (spec 9.5 step 6).
        foreach (var tracked in _db.ChangeTracker.Entries<FiPortfolio>().Where(e => e.Entity.PortfolioId == portfolioId).ToList())
        {
            tracked.State = EntityState.Detached;
        }

        var portfolio = await _db.FiPortfolios.FirstOrDefaultAsync(p => p.PortfolioId == portfolioId, ct);
        if (portfolio is null)
        {
            return new(Result(TransitionCommitStatus.NotFound, portfolioId, commandIdHint,
                $"Portfolio '{portfolioId}' does not exist.", Array.Empty<VerificationIssue>()), false);
        }

        var currentState = await _db.FiPortfolioStateVersions.AsNoTracking()
            .FirstOrDefaultAsync(s => s.PortfolioId == portfolioId && s.Version == portfolio.CurrentVersion, ct);

        var verification = _verifier.Verify(proposal, new ProposalVerificationContext
        {
            CheckState = true,
            ExpectedCommandId = context.ExpectedCommandId,
            ExpectedRequestHash = context.ExpectedRequestHash,
            ExpectedDecisionId = context.ExpectedDecisionId,
            ExpectedPortfolioId = portfolioId,
            CurrentVersion = portfolio.CurrentVersion,
            CurrentStateHash = portfolio.CurrentStateHash,
            CurrentStateJson = currentState?.StateJson,
            RiskPolicyId = portfolio.RiskPolicyId,
            RiskPolicy = _policies.FindRiskPolicy(portfolio.RiskPolicyId),
        });

        var dto = verification.Proposal;
        if (!verification.IsAuthentic || dto is null)
        {
            // Unauthenticated payloads never consume a command id or touch state.
            return new(Result(TransitionCommitStatus.Rejected, portfolioId, commandIdHint,
                "Proposal failed integrity verification.", verification.Issues, verification.ComputedProposalHash), false);
        }

        // Command-id idempotency precedes version checks: a retry must see the original result.
        var existing = await _db.FiCommandRecords.AsNoTracking()
            .FirstOrDefaultAsync(r => r.CommandId == dto.CommandId, ct);
        if (existing is not null)
        {
            if (existing.RequestHash == dto.RequestHash && existing.PortfolioId == portfolioId)
            {
                var status = existing.Status == FiCommandStatus.Committed
                    ? TransitionCommitStatus.AlreadyCommitted
                    : TransitionCommitStatus.PortfolioBlocked;
                return new(FromRecord(existing, status), false);
            }

            return new(Result(TransitionCommitStatus.Conflict, portfolioId, dto.CommandId,
                "Command id was already used with a different request (idempotency key mismatch).",
                new[] { new VerificationIssue("idempotency_mismatch", "Same command id, different request hash.") },
                verification.ComputedProposalHash), false);
        }

        // An impairment only forbids discretionary commits; due events and valuations still apply.
        if (FiPortfolioRestriction.Forbids(portfolio.BlockedReason, dto.CommandType))
        {
            return new(Result(TransitionCommitStatus.PortfolioBlocked, portfolioId, dto.CommandId,
                $"Portfolio is blocked until operator action: {portfolio.BlockedReason}",
                Array.Empty<VerificationIssue>(), verification.ComputedProposalHash), false);
        }

        if (verification.ReconciliationFailed)
        {
            BlockPortfolio(portfolio, dto, verification);
            return new(Result(TransitionCommitStatus.PortfolioBlocked, portfolioId, dto.CommandId,
                "Reconciliation failed; the portfolio is blocked until operator action.",
                verification.Issues, verification.ComputedProposalHash), true);
        }

        if (verification.Issues.Any(i => i.Code is VerificationCodes.StaleVersion or VerificationCodes.StateHashMismatch))
        {
            return new(Result(TransitionCommitStatus.Stale, portfolioId, dto.CommandId,
                "Proposal was computed against a state that is no longer current; recompute.",
                verification.Issues, verification.ComputedProposalHash), false);
        }

        if (!verification.IsValid)
        {
            return new(Result(TransitionCommitStatus.Rejected, portfolioId, dto.CommandId,
                "Proposal failed verification.", verification.Issues, verification.ComputedProposalHash), false);
        }

        var duplicates = await FindDuplicateEffectsAsync(portfolioId, dto, ct);
        if (duplicates.Count > 0)
        {
            return new(Result(TransitionCommitStatus.Rejected, portfolioId, dto.CommandId,
                "Proposal repeats an already-committed financial effect.", duplicates,
                verification.ComputedProposalHash), false);
        }

        var applied = await ApplyAsync(portfolio, proposal.Node, dto, verification, ct);
        if (applied.Count > 0)
        {
            _db.ChangeTracker.Clear();
            return new(Result(TransitionCommitStatus.Rejected, portfolioId, dto.CommandId,
                "Proposal references orders or settlements that are not open.", applied,
                verification.ComputedProposalHash), false);
        }

        var committedVersion = dto.NoOp ? portfolio.CurrentVersion : dto.NewVersion;
        return new(new TransitionCommitResult
        {
            Status = TransitionCommitStatus.Committed,
            PortfolioId = portfolioId,
            CommandId = dto.CommandId,
            ProposalHash = verification.ComputedProposalHash,
            CommittedVersion = committedVersion,
            StateHash = dto.NoOp ? portfolio.CurrentStateHash : dto.NewStateHash,
            Message = dto.NoOp ? "No-op proposal recorded." : "Committed.",
        }, true);
    }

    private async Task<List<VerificationIssue>> FindDuplicateEffectsAsync(string portfolioId, TransitionProposalDto dto, CancellationToken ct)
    {
        var issues = new List<VerificationIssue>();

        var eventIds = dto.Events.Select(e => e.EventId).Concat(dto.Journals.Select(j => j.EventId)).Distinct().ToList();
        if (eventIds.Count > 0)
        {
            var seen = await _db.FiPortfolioEvents.AsNoTracking()
                .Where(e => e.PortfolioId == portfolioId && eventIds.Contains(e.EventId))
                .Select(e => e.EventId).ToListAsync(ct);
            issues.AddRange(seen.Select(id => new VerificationIssue("duplicate_event", $"Event '{id}' was already committed.")));
        }

        var journalIds = dto.Journals.Select(j => j.JournalId).ToList();
        if (journalIds.Count > 0)
        {
            var seen = await _db.FiJournals.AsNoTracking()
                .Where(j => j.PortfolioId == portfolioId && journalIds.Contains(j.JournalId))
                .Select(j => j.JournalId).ToListAsync(ct);
            issues.AddRange(seen.Select(id => new VerificationIssue("duplicate_journal", $"Journal '{id}' was already committed.")));
        }

        var newOrderIds = dto.OrdersCreated.Select(o => o.OrderId).ToList();
        if (newOrderIds.Count > 0)
        {
            var seen = await _db.FiOrderIntents.AsNoTracking()
                .Where(o => o.PortfolioId == portfolioId && newOrderIds.Contains(o.OrderId))
                .Select(o => o.OrderId).ToListAsync(ct);
            issues.AddRange(seen.Select(id => new VerificationIssue("duplicate_order", $"Order '{id}' already exists.")));
        }

        var fillIds = dto.Fills.Select(f => f.FillId).ToList();
        var filledOrders = dto.Fills.Select(f => f.OrderId).ToList();
        if (fillIds.Count > 0)
        {
            var seen = await _db.FiFills.AsNoTracking()
                .Where(f => f.PortfolioId == portfolioId && (fillIds.Contains(f.FillId) || filledOrders.Contains(f.OrderId)))
                .Select(f => f.FillId).ToListAsync(ct);
            issues.AddRange(seen.Select(id => new VerificationIssue("duplicate_fill", $"Fill '{id}' (or a fill for its order) already exists.")));
        }

        var settlementIds = dto.SettlementsCreated.Select(s => s.SettlementId).ToList();
        var settledFills = dto.SettlementsCreated.Select(s => s.FillId).ToList();
        if (settlementIds.Count > 0)
        {
            var seen = await _db.FiSettlements.AsNoTracking()
                .Where(s => s.PortfolioId == portfolioId && (settlementIds.Contains(s.SettlementId) || settledFills.Contains(s.FillId)))
                .Select(s => s.SettlementId).ToListAsync(ct);
            issues.AddRange(seen.Select(id => new VerificationIssue("duplicate_settlement", $"Settlement '{id}' (or one for its fill) already exists.")));
        }

        var cashFlowIds = dto.CashFlows.Select(cf => cf.CashFlowId).ToList();
        if (cashFlowIds.Count > 0)
        {
            var seen = await _db.FiCashFlowEvents.AsNoTracking()
                .Where(cf => cf.PortfolioId == portfolioId && cashFlowIds.Contains(cf.CashFlowId))
                .Select(cf => cf.CashFlowId).ToListAsync(ct);
            issues.AddRange(seen.Select(id => new VerificationIssue("duplicate_cash_flow", $"Cash flow '{id}' was already committed.")));
        }

        if (dto.Valuation is { } valuation)
        {
            var exists = await _db.FiValuationSnapshots.AsNoTracking()
                .AnyAsync(x => x.PortfolioId == portfolioId && x.ValuationId == valuation.ValuationId, ct);
            if (exists)
            {
                issues.Add(new VerificationIssue("duplicate_valuation", $"Valuation '{valuation.ValuationId}' was already committed."));
            }
        }

        return issues;
    }

    /// <summary>Stages every effect of the verified proposal. Returns issues for dangling references.</summary>
    private async Task<List<VerificationIssue>> ApplyAsync(
        FiPortfolio portfolio,
        JsonObject node,
        TransitionProposalDto dto,
        ProposalVerificationResult verification,
        CancellationToken ct)
    {
        var issues = new List<VerificationIssue>();
        var now = _clock.GetUtcNow();
        var portfolioId = portfolio.PortfolioId;
        var version = dto.NoOp ? portfolio.CurrentVersion : dto.NewVersion;

        if (!dto.NoOp)
        {
            _db.FiPortfolioStateVersions.Add(new PortfolioStateVersion
            {
                PortfolioId = portfolioId,
                Version = dto.NewVersion,
                StateJson = verification.CanonicalNewStateJson!,
                StateHash = dto.NewStateHash,
                AsOf = FiWire.ParseInstant(dto.NewState.AsOf, "newState.asOf"),
                CommandId = dto.CommandId,
                ProposalHash = verification.ComputedProposalHash,
                CreatedAt = now,
            });
        }

        // Economic events: one committed effect per (portfolio, event id).
        var eventNodes = node["events"] as JsonArray ?? new JsonArray();
        var recordedEvents = new HashSet<string>(StringComparer.Ordinal);
        for (var i = 0; i < dto.Events.Count; i++)
        {
            var e = dto.Events[i];
            recordedEvents.Add(e.EventId);
            _db.FiPortfolioEvents.Add(new PortfolioEvent
            {
                PortfolioId = portfolioId,
                EventId = e.EventId,
                EventType = e.Type,
                EffectiveAt = FiWire.ParseInstant(e.EffectiveAt, "event.effectiveAt"),
                Priority = e.Priority,
                CommittedVersion = version,
                CommandId = dto.CommandId,
                EventJson = CanonicalJson.Serialize(eventNodes[i]),
            });
        }

        foreach (var journal in dto.Journals)
        {
            if (recordedEvents.Add(journal.EventId))
            {
                _db.FiPortfolioEvents.Add(new PortfolioEvent
                {
                    PortfolioId = portfolioId,
                    EventId = journal.EventId,
                    EventType = journal.EventType,
                    EffectiveAt = FiWire.ParseInstant(journal.EffectiveAt, "journal.effectiveAt"),
                    CommittedVersion = version,
                    CommandId = dto.CommandId,
                });
            }

            var entity = new Journal
            {
                PortfolioId = portfolioId,
                JournalId = journal.JournalId,
                EventId = journal.EventId,
                EventType = journal.EventType,
                EffectiveAt = FiWire.ParseInstant(journal.EffectiveAt, "journal.effectiveAt"),
                Template = journal.Template,
                CommittedVersion = version,
                CommandId = dto.CommandId,
            };
            var lineNumber = 0;
            foreach (var line in journal.Lines)
            {
                entity.Entries.Add(new JournalEntry
                {
                    PortfolioId = portfolioId,
                    LineId = line.LineId,
                    LineNumber = lineNumber++,
                    Account = line.Account,
                    SecurityId = line.SecurityId,
                    DebitUsd = FiWire.ParseDecimal(line.DebitUsd, "debitUsd"),
                    CreditUsd = FiWire.ParseDecimal(line.CreditUsd, "creditUsd"),
                    Memo = line.Memo,
                });
            }

            _db.FiJournals.Add(entity);
        }

        // Orders.
        var createdOrders = new Dictionary<string, OrderIntent>(StringComparer.Ordinal);
        var createdNodes = node["ordersCreated"] as JsonArray ?? new JsonArray();
        for (var i = 0; i < dto.OrdersCreated.Count; i++)
        {
            var order = dto.OrdersCreated[i];
            var entity = new OrderIntent
            {
                PortfolioId = portfolioId,
                OrderId = order.OrderId,
                DecisionId = order.DecisionId,
                SecurityId = order.SecurityId,
                Side = order.Side,
                Face = FiWire.ParseDecimal(order.Face, "order.face"),
                SubmittedAt = FiWire.ParseInstant(order.SubmittedAt, "order.submittedAt"),
                EligibleSessionDate = FiWire.ParseDate(order.EligibleSessionDate, "order.eligibleSessionDate"),
                ExpiresAt = FiWire.ParseInstant(order.ExpiresAt, "order.expiresAt"),
                Status = order.Status,
                StatusReason = Truncate(order.StatusReason),
                ReservedCashUsd = FiWire.ParseDecimal(order.ReservedCashUsd, "order.reservedCashUsd"),
                BatchPriority = order.BatchPriority,
                Bootstrap = order.Bootstrap,
                CreatedInVersion = version,
                LastUpdatedVersion = version,
                OrderJson = CanonicalJson.Serialize(createdNodes[i]),
            };
            createdOrders[order.OrderId] = entity;
            _db.FiOrderIntents.Add(entity);
        }

        var changedIds = dto.OrderStatusChanges.Select(o => o.OrderId).Where(id => !createdOrders.ContainsKey(id)).ToList();
        var filledOrderIds = dto.Fills.Select(f => f.OrderId).Where(id => !createdOrders.ContainsKey(id)).ToList();
        var lookupIds = changedIds.Concat(filledOrderIds).Distinct().ToList();
        var existingOrders = lookupIds.Count == 0
            ? new Dictionary<string, OrderIntent>(StringComparer.Ordinal)
            : await _db.FiOrderIntents
                .Where(o => o.PortfolioId == portfolioId && lookupIds.Contains(o.OrderId))
                .ToDictionaryAsync(o => o.OrderId, StringComparer.Ordinal, ct);

        var originalStatus = existingOrders.ToDictionary(kv => kv.Key, kv => kv.Value.Status, StringComparer.Ordinal);
        var changeNodes = node["orderStatusChanges"] as JsonArray ?? new JsonArray();
        for (var i = 0; i < dto.OrderStatusChanges.Count; i++)
        {
            var change = dto.OrderStatusChanges[i];
            if (!createdOrders.TryGetValue(change.OrderId, out var entity) &&
                !existingOrders.TryGetValue(change.OrderId, out entity))
            {
                issues.Add(new VerificationIssue("unknown_order", $"Status change references unknown order '{change.OrderId}'."));
                continue;
            }

            if (!createdOrders.ContainsKey(change.OrderId) && entity.Status != FiOrderStatus.Accepted)
            {
                issues.Add(new VerificationIssue("order_not_open",
                    $"Order '{change.OrderId}' is {entity.Status}; only ACCEPTED orders can change status."));
                continue;
            }

            entity.Status = change.Status;
            entity.StatusReason = Truncate(change.StatusReason);
            entity.ReservedCashUsd = FiWire.ParseDecimal(change.ReservedCashUsd, "order.reservedCashUsd");
            entity.LastUpdatedVersion = version;
            entity.OrderJson = CanonicalJson.Serialize(changeNodes[i]);
        }

        // Fills (one per order).
        var fillNodes = node["fills"] as JsonArray ?? new JsonArray();
        for (var i = 0; i < dto.Fills.Count; i++)
        {
            var fill = dto.Fills[i];
            if (!createdOrders.ContainsKey(fill.OrderId) && !existingOrders.ContainsKey(fill.OrderId))
            {
                issues.Add(new VerificationIssue("unknown_order", $"Fill '{fill.FillId}' references unknown order '{fill.OrderId}'."));
                continue;
            }

            if (originalStatus.TryGetValue(fill.OrderId, out var statusBefore) && statusBefore != FiOrderStatus.Accepted)
            {
                issues.Add(new VerificationIssue("order_not_open",
                    $"Fill '{fill.FillId}' targets order '{fill.OrderId}' which is {statusBefore}."));
                continue;
            }

            _db.FiFills.Add(new Fill
            {
                PortfolioId = portfolioId,
                FillId = fill.FillId,
                OrderId = fill.OrderId,
                SecurityId = fill.SecurityId,
                Side = fill.Side,
                Face = FiWire.ParseDecimal(fill.Face, "fill.face"),
                ExecutedAt = FiWire.ParseInstant(fill.ExecutedAt, "fill.executedAt"),
                ObservationId = fill.ObservationId,
                QuoteKind = fill.QuoteKind,
                ReferenceCleanPricePer100 = FiWire.ParseDecimal(fill.ReferenceCleanPricePer100, "referenceCleanPricePer100"),
                ExecutionCleanPricePer100 = FiWire.ParseDecimal(fill.ExecutionCleanPricePer100, "executionCleanPricePer100"),
                AccruedPer100 = FiWire.ParseDecimal(fill.AccruedPer100, "accruedPer100"),
                DirtyPricePer100 = FiWire.ParseDecimal(fill.DirtyPricePer100, "dirtyPricePer100"),
                HalfSpreadPer100 = FiWire.ParseDecimal(fill.HalfSpreadPer100, "halfSpreadPer100"),
                SettlementDate = FiWire.ParseDate(fill.SettlementDate, "fill.settlementDate"),
                ConsiderationUsd = FiWire.ParseDecimal(fill.ConsiderationUsd, "considerationUsd"),
                FeesUsd = FiWire.ParseDecimal(fill.FeesUsd, "feesUsd"),
                SpreadCostUsd = FiWire.ParseDecimal(fill.SpreadCostUsd, "spreadCostUsd"),
                TimingLabel = fill.TimingLabel,
                CommittedVersion = version,
                FillJson = CanonicalJson.Serialize(fillNodes[i]),
            });
        }

        // Settlements (one per fill) and completions.
        var createdSettlements = new Dictionary<string, Settlement>(StringComparer.Ordinal);
        var settlementNodes = node["settlementsCreated"] as JsonArray ?? new JsonArray();
        for (var i = 0; i < dto.SettlementsCreated.Count; i++)
        {
            var settlement = dto.SettlementsCreated[i];
            var entity = new Settlement
            {
                PortfolioId = portfolioId,
                SettlementId = settlement.SettlementId,
                FillId = settlement.FillId,
                SecurityId = settlement.SecurityId,
                Side = settlement.Side,
                Face = FiWire.ParseDecimal(settlement.Face, "settlement.face"),
                SettlementDate = FiWire.ParseDate(settlement.SettlementDate, "settlement.settlementDate"),
                CashUsd = FiWire.ParseDecimal(settlement.CashUsd, "settlement.cashUsd"),
                Status = FiSettlementStatus.Pending,
                CreatedInVersion = version,
                SettlementJson = CanonicalJson.Serialize(settlementNodes[i]),
            };
            createdSettlements[settlement.SettlementId] = entity;
            _db.FiSettlements.Add(entity);
        }

        var completedIds = dto.SettlementsCompleted.Where(id => !createdSettlements.ContainsKey(id)).ToList();
        var pendingSettlements = completedIds.Count == 0
            ? new Dictionary<string, Settlement>(StringComparer.Ordinal)
            : await _db.FiSettlements
                .Where(s => s.PortfolioId == portfolioId && completedIds.Contains(s.SettlementId))
                .ToDictionaryAsync(s => s.SettlementId, StringComparer.Ordinal, ct);
        foreach (var settlementId in dto.SettlementsCompleted)
        {
            if (!createdSettlements.TryGetValue(settlementId, out var entity) &&
                !pendingSettlements.TryGetValue(settlementId, out entity))
            {
                issues.Add(new VerificationIssue("unknown_settlement", $"Settlement '{settlementId}' does not exist."));
                continue;
            }

            if (entity.Status != FiSettlementStatus.Pending)
            {
                issues.Add(new VerificationIssue("settlement_not_pending", $"Settlement '{settlementId}' was already completed."));
                continue;
            }

            entity.Status = FiSettlementStatus.Completed;
            entity.CompletedInVersion = version;
        }

        foreach (var cashFlow in dto.CashFlows)
        {
            _db.FiCashFlowEvents.Add(new CashFlowEvent
            {
                PortfolioId = portfolioId,
                CashFlowId = cashFlow.CashFlowId,
                SecurityId = cashFlow.SecurityId,
                Kind = cashFlow.Kind,
                PaymentDate = FiWire.ParseDate(cashFlow.PaymentDate, "cashFlow.paymentDate"),
                EntitledFace = FiWire.ParseDecimal(cashFlow.EntitledFace, "cashFlow.entitledFace"),
                AmountUsd = FiWire.ParseDecimal(cashFlow.AmountUsd, "cashFlow.amountUsd"),
                CommittedVersion = version,
            });
        }

        if (dto.Valuation is { } valuation)
        {
            _db.FiValuationSnapshots.Add(new ValuationSnapshot
            {
                PortfolioId = portfolioId,
                ValuationId = valuation.ValuationId,
                StateVersion = valuation.StateVersion,
                ValuationAt = FiWire.ParseInstant(valuation.ValuationAt, "valuation.valuationAt"),
                DataMode = valuation.DataMode,
                CurveSnapshotId = valuation.CurveSnapshotId,
                MarkPolicy = valuation.MarkPolicy,
                Complete = valuation.Complete,
                IncompleteReasonsJson = JsonSerializer.Serialize(valuation.IncompleteReasons),
                CashUsd = FiWire.ParseDecimal(valuation.CashUsd, "valuation.cashUsd"),
                BondValueUsd = FiWire.ParseOptionalDecimal(valuation.BondValueUsd, "valuation.bondValueUsd"),
                ReceivablesPvUsd = FiWire.ParseOptionalDecimal(valuation.ReceivablesPvUsd, "valuation.receivablesPvUsd"),
                PayablesPvUsd = FiWire.ParseOptionalDecimal(valuation.PayablesPvUsd, "valuation.payablesPvUsd"),
                EquityUsd = FiWire.ParseOptionalDecimal(valuation.EquityUsd, "valuation.equityUsd"),
                ParallelDv01Usd = FiWire.ParseOptionalDecimal(valuation.ParallelDv01Usd, "valuation.parallelDv01Usd"),
                EffectiveDurationYears = FiWire.ParseOptionalDecimal(valuation.EffectiveDurationYears, "valuation.effectiveDurationYears"),
                CommittedVersion = version,
                ValuationJson = CanonicalJson.Serialize(node["valuation"]),
            });
        }

        if (dto.PolicyEvaluation is { } evaluation)
        {
            var decisionDbId = await _db.FiDecisions.AsNoTracking()
                .Where(d => d.DecisionId == evaluation.DecisionId)
                .Select(d => (long?)d.Id)
                .FirstOrDefaultAsync(ct);
            _db.FiPolicyEvaluations.Add(DecisionAuditService.MapPolicyEvaluation(
                evaluation, node["policyEvaluation"], "transition_proposal", decisionDbId, portfolioId,
                dto.CommandId, platformRecheckPassed: true, now));
        }

        _db.FiCommandRecords.Add(new CommandRecord
        {
            CommandId = dto.CommandId,
            CommandType = dto.CommandType,
            PortfolioId = portfolioId,
            RequestHash = dto.RequestHash,
            ProposalHash = verification.ComputedProposalHash!,
            ProposalId = dto.ProposalId,
            EngineVersion = dto.EngineVersion,
            ExpectedVersion = dto.ExpectedVersion,
            CommittedVersion = version,
            Status = FiCommandStatus.Committed,
            ResultJson = ResultJson(FiCommandStatus.Committed, portfolioId, dto, version,
                dto.NoOp ? portfolio.CurrentStateHash : dto.NewStateHash, verification.ComputedProposalHash),
            CreatedAt = now,
        });

        if (!dto.NoOp)
        {
            portfolio.CurrentVersion = dto.NewVersion;
            portfolio.CurrentStateHash = dto.NewStateHash;
        }

        portfolio.UpdatedAt = now;
        portfolio.ConcurrencyStamp = Guid.NewGuid();
        return issues;
    }

    private void BlockPortfolio(FiPortfolio portfolio, TransitionProposalDto dto, ProposalVerificationResult verification)
    {
        var now = _clock.GetUtcNow();
        var reason = Truncate("reconciliation_failed: " + string.Join("; ",
            verification.Issues.Where(i => i.Code == VerificationCodes.ReconciliationFailed).Select(i => i.Message)))!;

        portfolio.BlockedReason = reason;
        portfolio.BlockedAt = now;
        portfolio.BlockedByCommandId = dto.CommandId;
        portfolio.UpdatedAt = now;
        portfolio.ConcurrencyStamp = Guid.NewGuid();

        _db.FiCommandRecords.Add(new CommandRecord
        {
            CommandId = dto.CommandId,
            CommandType = dto.CommandType,
            PortfolioId = portfolio.PortfolioId,
            RequestHash = dto.RequestHash,
            ProposalHash = verification.ComputedProposalHash!,
            ProposalId = dto.ProposalId,
            EngineVersion = dto.EngineVersion,
            ExpectedVersion = dto.ExpectedVersion,
            CommittedVersion = null,
            Status = FiCommandStatus.RejectedReconciliation,
            Reason = reason,
            ResultJson = ResultJson(FiCommandStatus.RejectedReconciliation, portfolio.PortfolioId, dto, null, null,
                verification.ComputedProposalHash),
            CreatedAt = now,
        });

        _logger.LogError(
            "Reconciliation failure on fixed income portfolio {PortfolioId} (command {CommandId}); further commits are blocked: {Reason}",
            portfolio.PortfolioId, dto.CommandId, reason);
    }

    private static string ResultJson(string status, string portfolioId, TransitionProposalDto dto, long? version, string? stateHash, string? proposalHash)
    {
        var node = new JsonObject
        {
            ["status"] = status,
            ["portfolioId"] = portfolioId,
            ["commandId"] = dto.CommandId,
            ["proposalId"] = dto.ProposalId,
            ["proposalHash"] = proposalHash,
            ["committedVersion"] = version,
            ["stateHash"] = stateHash,
        };
        return CanonicalJson.Serialize(node);
    }

    private static TransitionCommitResult FromRecord(CommandRecord record, TransitionCommitStatus status)
    {
        string? stateHash = null;
        if (FiWire.TryParseNode(record.ResultJson) is JsonObject result &&
            result["stateHash"] is JsonValue value && value.TryGetValue<string>(out var hash))
        {
            stateHash = hash;
        }

        return new TransitionCommitResult
        {
            Status = status,
            PortfolioId = record.PortfolioId,
            CommandId = record.CommandId,
            ProposalHash = record.ProposalHash,
            CommittedVersion = record.CommittedVersion,
            StateHash = stateHash,
            Message = status == TransitionCommitStatus.AlreadyCommitted
                ? "Command already committed; returning the original result."
                : record.Reason,
        };
    }

    private static CommandRecordView ToView(CommandRecord record) => new(
        record.CommandId, record.CommandType, record.PortfolioId, record.RequestHash, record.ProposalHash,
        record.Status, record.ExpectedVersion, record.CommittedVersion, record.Reason, record.CreatedAt);

    private static TransitionCommitResult Result(
        TransitionCommitStatus status,
        string portfolioId,
        string commandId,
        string message,
        IReadOnlyList<VerificationIssue> issues,
        string? proposalHash = null) => new()
        {
            Status = status,
            PortfolioId = portfolioId,
            CommandId = commandId,
            Message = message,
            Issues = issues,
            ProposalHash = proposalHash,
        };

    private async Task<IDbContextTransaction?> BeginTransactionAsync(CancellationToken ct) =>
        _db.Database.IsRelational() ? await _db.Database.BeginTransactionAsync(ct) : null;

    private static async Task RollbackQuietlyAsync(IDbContextTransaction? transaction)
    {
        if (transaction is null)
        {
            return;
        }

        try
        {
            await transaction.RollbackAsync();
        }
        catch (InvalidOperationException)
        {
            // Already completed.
        }
    }

    private static string? Truncate(string? value) =>
        value is null || value.Length <= MaxReasonLength ? value : value[..MaxReasonLength];
}
