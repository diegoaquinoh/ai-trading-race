using System.Collections.Concurrent;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Infrastructure.FixedIncome;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>What the fake engine answers for one strategy decision.</summary>
public sealed record FakeDecision(FakeDecisionKind Kind, IReadOnlyList<TargetWeightDto>? Targets = null, Exception? Error = null)
{
    public static readonly FakeDecision Hold = new(FakeDecisionKind.Hold);

    public static FakeDecision Rebalance(params (string SecurityId, string Weight)[] targets) =>
        new(FakeDecisionKind.Rebalance, targets.Select(t => new TargetWeightDto { SecurityId = t.SecurityId, Weight = t.Weight }).ToList());

    public static FakeDecision Throw(Exception error) => new(FakeDecisionKind.Throw, Error: error);
}

public enum FakeDecisionKind
{
    Hold,
    Rebalance,
    Budget,
    Abstain,
    BadSignature,
    Throw,
}

/// <summary>
/// Deterministic in-memory stand-in for the Python research engine. It returns correctly
/// signed TransitionProposals (canonical JSON + HMAC, same rules as the real engine) built
/// from the exact portfolio state it receives, and signed StrategyResults. Prices are a
/// fixed test fixture (100.00 per 100 face) — this is test scaffolding, not .NET pricing.
/// </summary>
public sealed class FakeResearchEngine : IResearchEngineClient
{
    public const string Universe = "synthetic-universe-v1";
    public const string Sec1 = "SYN-USD-NOTE-001";
    public const string Sec2 = "SYN-USD-NOTE-002";
    public const string Sec3 = "SYN-USD-NOTE-003";

    private readonly object _gate = new();
    private readonly ConcurrentDictionary<string, int> _staleOnce = new(StringComparer.Ordinal);

    public List<MarketSessionDto> Sessions { get; } = new();

    public List<TargetWeightDto> BootstrapTargets { get; } = new()
    {
        new() { SecurityId = Sec1, Weight = "0.30" },
        new() { SecurityId = Sec2, Weight = "0.34" },
        new() { SecurityId = Sec3, Weight = "0.30" },
        new() { SecurityId = FiContract.CashSecurityId, Weight = "0.06" },
    };

    /// <summary>Strategies whose BOOTSTRAP submission is rejected by the policy evaluation.</summary>
    public HashSet<string> RejectBootstrapFor { get; } = new(StringComparer.Ordinal);

    /// <summary>Decision behaviour per request (default: HOLD).</summary>
    public Func<DecisionRequestDto, FakeDecision> Decide { get; set; } = _ => FakeDecision.Hold;

    /// <summary>Called before each decision is answered (e.g. to cancel the run mid-fan-out).</summary>
    public Action<DecisionRequestDto>? OnDecision { get; set; }

    /// <summary>Returns an exception to throw for a transition request (simulated crash or outage).</summary>
    public Func<TransitionRequestDto, Exception?>? FailTransition { get; set; }

    /// <summary>Command ids whose first proposal is computed against a stale (older) version.</summary>
    public void StaleOnce(string commandIdContains) => _staleOnce[commandIdContains] = 0;

    /// <summary>
    /// Command ids (transitions) or decision ids (strategy results) for which the engine echoes the
    /// hash of a different request than the one received (a correctly signed answer to the wrong request).
    /// </summary>
    public Func<string, bool>? WrongRequestHashFor { get; set; }

    /// <summary>
    /// What the real engine echoes as requestHash: SHA-256 of the canonical JSON of the request body
    /// as received. The body is reproduced as a plain (non-canonical) wire serialization of the DTO
    /// — exactly what the HTTP client would transmit — then parsed and canonicalized like Python does.
    /// </summary>
    public static string ReceivedBodyHash<T>(T request) =>
        CanonicalJson.Sha256(CanonicalJson.Canonicalize(JsonSerializer.Serialize(request, FiContract.WireOptions)));

    private string EchoedRequestHash<T>(T request, string id) =>
        WrongRequestHashFor?.Invoke(id) == true
            ? CanonicalJson.Sha256("{\"another\":\"request\",\"id\":\"" + id + "\"}")
            : ReceivedBodyHash(request);

    /// <summary>Request hash of every transition the engine received (command id → hash), in order.</summary>
    public ConcurrentQueue<(string CommandId, string RequestHash)> TransitionRequestHashes { get; } = new();

    public ConcurrentQueue<string> TransitionCommandIds { get; } = new();

    public ConcurrentQueue<DecisionRequestDto> DecisionRequests { get; } = new();

    public int BootstrapCalls;

    public string EngineVersion { get; set; } = Fi.EngineVersion;

    public string SigningKey { get; set; } = Fi.SigningKey;

    // ------------------------------------------------------------------ sessions

    public static MarketSessionDto Session(DateOnly date, string curveStatus = "READY", bool late = false, bool gap = false)
    {
        var d = FiWire.FormatDate(date);
        return new MarketSessionDto
        {
            SessionDate = d,
            MarketSnapshotId = "mkt-" + d,
            MarketSnapshotHash = CanonicalJson.ContentHash(JsonValue.Create("market:" + d)),
            CurveSnapshotId = "curve-" + d,
            CurveStatus = curveStatus,
            ObservedAt = FiWire.FormatInstant(FiMarketClock.At(date, new TimeOnly(15, 30))),
            AvailableAt = FiWire.FormatInstant(FiMarketClock.At(date, late ? new TimeOnly(21, 0) : new TimeOnly(18, 0))),
            DecisionAsOf = FiWire.FormatInstant(FiMarketClock.DecisionAt(date)),
            ExecutionObservationAt = FiWire.FormatInstant(FiMarketClock.At(date, new TimeOnly(15, 30))),
            Gap = gap,
            GapReason = gap ? "missing_observation" : null,
        };
    }

    public Task<MarketSessionsDto> GetMarketSessionsAsync(DateOnly start, DateOnly end, CancellationToken cancellationToken = default) =>
        Task.FromResult(new MarketSessionsDto
        {
            DataMode = "synthetic_curve",
            UniverseVersion = Universe,
            Sessions = Sessions.Where(s =>
            {
                var date = FiWire.ParseDate(s.SessionDate, "sessionDate");
                return date >= start && date <= end;
            }).ToList(),
        });

    public Task<BootstrapAllocationDto> GetBootstrapAllocationAsync(BootstrapAllocationRequestDto request, CancellationToken cancellationToken = default)
    {
        Interlocked.Increment(ref BootstrapCalls);
        return Task.FromResult(new BootstrapAllocationDto
        {
            Version = "bootstrap-30-34-30-6-v1",
            SessionDate = request.SessionDate,
            Targets = BootstrapTargets.ToList(),
        });
    }

    public Task<CapabilitiesDto> GetCapabilitiesAsync(CancellationToken cancellationToken = default) =>
        Task.FromResult(new CapabilitiesDto { EngineVersion = EngineVersion, Ready = true, SchemaVersions = new() { "1.0" } });

    // ------------------------------------------------------------------ decisions

    public Task<RawContractJson> RequestDecisionAsync(DecisionRequestDto request, CancellationToken cancellationToken = default)
    {
        DecisionRequests.Enqueue(request);
        OnDecision?.Invoke(request);
        var behaviour = Decide(request);
        if (behaviour.Kind == FakeDecisionKind.Throw)
        {
            throw behaviour.Error!;
        }

        if (request.PortfolioState is not { } state ||
            CanonicalJson.ContentHash(JsonNode.Parse(state.GetRawText())) != request.PortfolioSnapshot.ContentHash)
        {
            throw new ResearchEngineValidationException("inline portfolio state hash mismatch", 422, "{}");
        }

        var outcome = behaviour.Kind switch
        {
            FakeDecisionKind.Rebalance or FakeDecisionKind.BadSignature => "completed_proposal",
            FakeDecisionKind.Budget => "failed_budget",
            FakeDecisionKind.Abstain => "abstained_insufficient_evidence",
            _ => "completed_hold",
        };
        var targets = behaviour.Targets ?? new List<TargetWeightDto>
        {
            new() { SecurityId = Sec1, Weight = "0.35" },
            new() { SecurityId = Sec2, Weight = "0.34" },
            new() { SecurityId = Sec3, Weight = "0.25" },
            new() { SecurityId = FiContract.CashSecurityId, Weight = "0.06" },
        };
        var proposal = outcome switch
        {
            "completed_proposal" => new JsonObject
            {
                ["action"] = "REBALANCE",
                ["targetWeights"] = FiWire.ToNode(targets),
                ["supportingClaimIds"] = new JsonArray(),
                ["supportingCalculationIds"] = new JsonArray(),
            },
            "completed_hold" => new JsonObject
            {
                ["action"] = "HOLD",
                ["targetWeights"] = new JsonArray(),
                ["supportingClaimIds"] = new JsonArray(),
                ["supportingCalculationIds"] = new JsonArray(),
            },
            _ => null,
        };

        var result = new JsonObject
        {
            ["schemaVersion"] = "1.0",
            ["runId"] = request.RunId,
            ["cycleId"] = request.CycleId,
            ["decisionId"] = request.DecisionId,
            ["strategyId"] = request.StrategyId,
            ["strategyKind"] = request.StrategyId == "cash" ? "cash_reference" : request.StrategyId.StartsWith("llm", StringComparison.Ordinal) ? "single_agent" : "quant_policy",
            ["repetition"] = request.Repetition,
            ["requestHash"] = EchoedRequestHash(request, request.DecisionId),
            ["inputHashes"] = new JsonObject { ["portfolioState"] = request.PortfolioSnapshot.ContentHash },
            ["outcome"] = outcome,
            ["completedAt"] = request.DecisionAsOf,
            ["reasons"] = outcome is "completed_hold" or "completed_proposal" ? new JsonArray() : new JsonArray(outcome),
            ["proposal"] = proposal,
            ["researchNote"] = null,
            ["validation"] = new JsonArray(),
            ["policyEvaluation"] = null,
            ["attempts"] = new JsonArray(),
            ["toolTraces"] = new JsonArray(),
            ["specialistTasks"] = new JsonArray(),
            ["usage"] = new JsonObject
            {
                ["generationCalls"] = 1,
                ["toolCalls"] = 0,
                ["evidenceCalls"] = 0,
                ["uniqueEvidenceChunks"] = 0,
                ["evidenceTokens"] = 0,
                ["inputTokens"] = 100,
                ["outputTokens"] = 50,
                ["durationMs"] = 5,
                ["estimatedCostUsd"] = null,
                ["priceScheduleId"] = null,
                ["budgetExhausted"] = behaviour.Kind == FakeDecisionKind.Budget ? "maxGenerationCalls" : null,
            },
            ["versions"] = new JsonObject
            {
                ["provider"] = null,
                ["model"] = null,
                ["promptVersion"] = null,
                ["toolSchemaVersion"] = null,
                ["engineVersion"] = EngineVersion,
                ["evidenceSnapshotId"] = null,
                ["indexBuildId"] = null,
                ["retrievalMode"] = "none",
                ["strategyConfigHash"] = null,
            },
            ["evidenceBundleIds"] = new JsonArray(),
            ["resultHash"] = null,
            ["signature"] = null,
        };
        var hash = CanonicalJson.EnvelopeHash(result, "resultHash");
        result["resultHash"] = hash;
        result["signature"] = behaviour.Kind == FakeDecisionKind.BadSignature
            ? CanonicalJson.Sign(hash, System.Text.Encoding.UTF8.GetBytes("not-the-platform-key"))
            : CanonicalJson.Sign(hash, System.Text.Encoding.UTF8.GetBytes(SigningKey));
        return Task.FromResult(RawContractJson.Parse(result.ToJsonString()));
    }

    // ------------------------------------------------------------------ transitions

    /// <summary>Awaited before a transition is computed (e.g. a concurrent writer committing first).</summary>
    public Func<TransitionRequestDto, Task>? BeforeTransition { get; set; }

    public async Task<RawContractJson> ProposeTransitionAsync(TransitionRequestDto request, CancellationToken cancellationToken = default)
    {
        TransitionCommandIds.Enqueue(request.CommandId);
        TransitionRequestHashes.Enqueue((request.CommandId, ReceivedBodyHash(request)));
        if (FailTransition?.Invoke(request) is { } failure)
        {
            throw failure;
        }

        if (BeforeTransition is { } before)
        {
            await before(request);
        }

        var state = (JsonObject)JsonNode.Parse(request.PortfolioState.GetRawText())!;
        if (CanonicalJson.ContentHash(state) != request.PortfolioStateHash)
        {
            throw new ResearchEngineValidationException("portfolioStateHash mismatch", 422, "{}");
        }

        var stale = _staleOnce.Keys.FirstOrDefault(k => request.CommandId.Contains(k, StringComparison.Ordinal));
        if (stale is not null && _staleOnce.TryRemove(stale, out _))
        {
            // Computed against an older snapshot of the portfolio: the commit must report Stale.
            state["version"] = Fi.VersionOf(state) - 1;
        }

        lock (_gate)
        {
            return RawContractJson.Parse(Build(request, state).ToJsonString());
        }
    }

    private JsonObject Build(TransitionRequestDto request, JsonObject state)
    {
        var version = Fi.VersionOf(state);
        var newState = (JsonObject)state.DeepClone();
        var events = new JsonArray();
        var journals = new JsonArray();
        var ordersCreated = new JsonArray();
        var statusChanges = new JsonArray();
        var fills = new JsonArray();
        var settlementsCreated = new JsonArray();
        var settlementsCompleted = new JsonArray();
        var cashFlows = new JsonArray();
        JsonObject? policy = null;
        JsonObject? valuation = null;

        var cash = Dec(newState["cashUsd"]);
        var reserved = Dec(newState["reservedCashUsd"]);
        var advanceTo = FiWire.ParseInstant(request.AdvanceTo, "advanceTo");
        var nyDate = DateOnly.FromDateTime(FiMarketClock.ToLocal(advanceTo));
        var effectiveAt = request.AdvanceTo;
        var positions = (JsonArray)newState["positions"]!;
        var openOrders = (JsonArray)newState["openOrders"]!;
        var pending = (JsonArray)newState["pendingSettlements"]!;
        var n = 0;
        string Id(string prefix) => Short(prefix, request.CommandId + "#" + n++);

        switch (request.CommandType)
        {
            case "capital_flow":
            {
                var amount = Dec(request.CapitalAmountUsd);
                cash += amount;
                newState["externalCapitalUsd"] = Cents(Dec(newState["externalCapitalUsd"]) + amount);
                var eventId = Id("evt-cap");
                events.Add(Event(eventId, "capital_flow", effectiveAt, 0, ("amountUsd", Cents(amount))));
                journals.Add(Journal(Id("jr"), eventId, "capital_flow", "capital_flow_v1", effectiveAt,
                    ("CASH", Cents(amount), "0"), ("CAPITAL", "0", Cents(amount))));
                cashFlows.Add(new JsonObject
                {
                    ["cashFlowId"] = Id("cf"),
                    ["securityId"] = FiContract.CashSecurityId,
                    ["kind"] = "CAPITAL",
                    ["paymentDate"] = FiWire.FormatDate(nyDate),
                    ["entitledFace"] = "0",
                    ["amountUsd"] = Cents(amount),
                });
                break;
            }

            case "process_events":
            {
                foreach (var settlement in pending.OfType<JsonObject>().ToList())
                {
                    if (FiWire.ParseDate(Str(settlement["settlementDate"]), "settlementDate") > nyDate)
                    {
                        continue;
                    }

                    var amount = Dec(settlement["cashUsd"]);
                    cash -= amount;
                    var position = Position(positions, Str(settlement["securityId"]));
                    position["settledFace"] = Face(Dec(position["settledFace"]) + Dec(settlement["face"]));
                    var eventId = Id("evt-stl");
                    events.Add(Event(eventId, "settlement", effectiveAt, 10, ("settlementId", Str(settlement["settlementId"]))));
                    journals.Add(Journal(Id("jr"), eventId, "settlement", "buy_settlement_v1", effectiveAt,
                        ("SETTLEMENT_PAYABLE", Cents(amount), "0"), ("CASH", "0", Cents(amount))));
                    settlementsCompleted.Add(Str(settlement["settlementId"]));
                    pending.Remove(settlement);
                }

                foreach (var order in openOrders.OfType<JsonObject>().ToList())
                {
                    if (FiWire.ParseDate(Str(order["eligibleSessionDate"]), "eligibleSessionDate") > nyDate)
                    {
                        continue;
                    }

                    var face = Dec(order["face"]);
                    var security = Str(order["securityId"]);
                    var orderId = Str(order["orderId"]);
                    reserved -= Dec(order["reservedCashUsd"]);
                    var fillId = Short("fill", orderId);
                    var settlementId = Short("stl", fillId);
                    var consideration = Cents(face);
                    var settlementDate = FiWire.FormatDate(nyDate.AddDays(1));
                    var position = Position(positions, security);
                    position["economicFace"] = Face(Dec(position["economicFace"]) + face);

                    var filled = (JsonObject)order.DeepClone();
                    filled["status"] = "FILLED";
                    filled["reservedCashUsd"] = "0";
                    statusChanges.Add(filled);
                    fills.Add(new JsonObject
                    {
                        ["fillId"] = fillId,
                        ["orderId"] = orderId,
                        ["securityId"] = security,
                        ["side"] = "BUY",
                        ["face"] = Face(face),
                        ["executedAt"] = effectiveAt,
                        ["observationId"] = "obs-" + FiWire.FormatDate(nyDate),
                        ["quoteKind"] = "synthetic_model",
                        ["referenceCleanPricePer100"] = "100.00",
                        ["executionCleanPricePer100"] = "100.00",
                        ["accruedPer100"] = "0",
                        ["dirtyPricePer100"] = "100.00",
                        ["halfSpreadPer100"] = "0",
                        ["settlementDate"] = settlementDate,
                        ["considerationUsd"] = consideration,
                        ["feesUsd"] = "0.00",
                        ["spreadCostUsd"] = "0.00",
                        ["timingLabel"] = "next_session_close_daily",
                    });
                    var settlement = new JsonObject
                    {
                        ["settlementId"] = settlementId,
                        ["fillId"] = fillId,
                        ["securityId"] = security,
                        ["side"] = "BUY",
                        ["face"] = Face(face),
                        ["settlementDate"] = settlementDate,
                        ["cashUsd"] = consideration,
                    };
                    settlementsCreated.Add(settlement);
                    pending.Add(settlement.DeepClone());
                    var eventId = Id("evt-exec");
                    events.Add(Event(eventId, "execution_observation", effectiveAt, 40, ("orderId", orderId)));
                    journals.Add(Journal(Id("jr"), eventId, "execution_observation", "buy_fill_v1", effectiveAt,
                        ("BOND_PRINCIPAL", consideration, "0"), ("SETTLEMENT_PAYABLE", "0", consideration)));
                    openOrders.Remove(order);
                }

                break;
            }

            case "submit_decision":
            {
                var decisionId = request.DecisionId!;
                var bootstrap = request.Action == FiDecisionAction.Bootstrap;
                var strategyId = Str(state["strategyId"]);
                var sessionDate = request.MarketSnapshot is { } snapshot
                    ? FiWire.ParseDate(snapshot.SessionDate, "sessionDate")
                    : nyDate;
                var rejected = bootstrap && RejectBootstrapFor.Contains(strategyId);
                var created = new List<JsonObject>();
                if (!rejected)
                {
                    foreach (var target in request.TargetWeights.Where(t => t.SecurityId != FiContract.CashSecurityId))
                    {
                        var targetFace = Math.Floor(Dec(target.Weight) * 1_000_000m / 1000m) * 1000m;
                        var current = Dec(Position(positions, target.SecurityId, create: false)?["economicFace"]) +
                                      openOrders.OfType<JsonObject>().Where(o => Str(o["securityId"]) == target.SecurityId).Sum(o => Dec(o["face"]));
                        var delta = targetFace - current;
                        if (delta < 1000m)
                        {
                            continue;
                        }

                        var order = new JsonObject
                        {
                            ["orderId"] = Short("ord", decisionId + ":" + target.SecurityId),
                            ["decisionId"] = decisionId,
                            ["securityId"] = target.SecurityId,
                            ["side"] = "BUY",
                            ["face"] = Face(delta),
                            ["submittedAt"] = effectiveAt,
                            ["eligibleSessionDate"] = FiWire.FormatDate(sessionDate.AddDays(1)),
                            ["expiresAt"] = FiWire.FormatInstant(FiMarketClock.At(sessionDate.AddDays(1), new TimeOnly(17, 0))),
                            ["status"] = "ACCEPTED",
                            ["reservedCashUsd"] = Cents(delta),
                            ["batchPriority"] = created.Count,
                            ["statusReason"] = null,
                            ["bootstrap"] = bootstrap,
                        };
                        created.Add(order);
                        reserved += delta;
                    }
                }

                foreach (var order in created)
                {
                    ordersCreated.Add(order.DeepClone());
                    openOrders.Add(order.DeepClone());
                }

                var eventId = Id(rejected ? "evt-rej" : "evt-sub");
                events.Add(Event(eventId, rejected ? "decision_rejected" : "orders_submitted", effectiveAt, 70, ("decisionId", decisionId)));
                policy = Policy(request, decisionId, created.Count, bootstrap, rejected);
                break;
            }

            case "value_portfolio":
            {
                var complete = request.MarketSnapshot is not null;
                var bonds = positions.OfType<JsonObject>().Sum(p => Dec(p["economicFace"]));
                var payables = pending.OfType<JsonObject>().Sum(s => Dec(s["cashUsd"]));
                var valuationId = Short("val", request.CommandId);
                var eventId = Id("evt-val");
                events.Add(Event(eventId, "valuation_mark", effectiveAt, 90, ("valuationId", valuationId)));
                newState["lastValuationId"] = valuationId;
                valuation = new JsonObject
                {
                    ["valuationId"] = valuationId,
                    ["portfolioId"] = Str(state["portfolioId"]),
                    ["stateVersion"] = version + 1,
                    ["valuationAt"] = effectiveAt,
                    ["dataMode"] = "synthetic_curve",
                    ["curveSnapshotId"] = request.MarketSnapshot?.CurveSnapshotId,
                    ["markPolicy"] = "synthetic_curve_model_v1",
                    ["complete"] = complete,
                    ["incompleteReasons"] = complete ? new JsonArray() : new JsonArray("no_market_snapshot"),
                    ["cashUsd"] = Cents(cash),
                    ["bondValueUsd"] = complete ? Cents(bonds) : null,
                    ["receivablesPvUsd"] = complete ? "0.00" : null,
                    ["payablesPvUsd"] = complete ? Cents(payables) : null,
                    ["equityUsd"] = complete ? Cents(cash + bonds - payables) : null,
                    ["marks"] = new JsonArray(),
                    ["parallelDv01Usd"] = complete ? "0" : null,
                    ["effectiveDurationYears"] = complete ? "0" : null,
                    ["calculationIds"] = new JsonArray(),
                };
                break;
            }

            default:
                throw new ResearchEngineValidationException($"unsupported command {request.CommandType}", 422, "{}");
        }

        var noOp = events.Count == 0;
        if (noOp)
        {
            newState = (JsonObject)state.DeepClone();
        }
        else
        {
            newState["cashUsd"] = Cents(cash);
            newState["reservedCashUsd"] = Cents(reserved);
            newState["version"] = version + 1;
            newState["asOf"] = request.AdvanceTo;
        }

        var proposal = new JsonObject
        {
            ["schemaVersion"] = "1.0",
            ["proposalId"] = Short("prop", request.CommandId + version),
            ["commandId"] = request.CommandId,
            ["commandType"] = request.CommandType,
            ["portfolioId"] = Str(state["portfolioId"]),
            ["strategyId"] = Str(state["strategyId"]),
            ["runId"] = Str(state["runId"]),
            ["expectedVersion"] = version,
            ["newVersion"] = noOp ? version : version + 1,
            ["noOp"] = noOp,
            ["engineVersion"] = EngineVersion,
            ["eventPriorityTable"] = FiContract.EventPriorityTable,
            ["requestHash"] = EchoedRequestHash(request, request.CommandId),
            ["inputHashes"] = new JsonObject
            {
                ["portfolioState"] = CanonicalJson.ContentHash(state),
                ["riskPolicy"] = CanonicalJson.ContentHash(FiWire.ToNode(request.RiskPolicy)),
                ["executionModel"] = CanonicalJson.ContentHash(FiWire.ToNode(request.ExecutionModel)),
            },
            ["events"] = events,
            ["journals"] = journals,
            ["newState"] = newState,
            ["newStateHash"] = null,
            ["ordersCreated"] = ordersCreated,
            ["orderStatusChanges"] = statusChanges,
            ["fills"] = fills,
            ["settlementsCreated"] = settlementsCreated,
            ["settlementsCompleted"] = settlementsCompleted,
            ["cashFlows"] = cashFlows,
            ["policyEvaluation"] = policy,
            ["valuation"] = valuation,
            ["reconciliation"] = new JsonObject
            {
                ["ok"] = true,
                ["journalsBalanced"] = true,
                ["ledgerCashUsd"] = Cents(cash),
                ["stateCashUsd"] = Cents(cash),
                ["ledgerPrincipalFaceCheck"] = true,
                ["bookEquityUsd"] = Cents(cash),
                ["economicEquityUsd"] = null,
                ["differenceUsd"] = null,
                ["messages"] = new JsonArray(),
            },
            ["proposalHash"] = null,
            ["signature"] = null,
        };
        return Fi.Seal(proposal, SigningKey);
    }

    private static JsonObject Policy(TransitionRequestDto request, string decisionId, int orders, bool bootstrap, bool rejected) => new()
    {
        ["policyId"] = request.RiskPolicy.PolicyId,
        ["decisionId"] = decisionId,
        ["action"] = request.Action,
        ["passed"] = !rejected,
        ["breachMode"] = false,
        ["bootstrapExemptionApplied"] = bootstrap && !rejected,
        ["originalTargets"] = FiWire.ToNode(request.TargetWeights),
        ["normalizedTargets"] = FiWire.ToNode(request.TargetWeights),
        ["normalizationNotes"] = new JsonArray(),
        ["sizedOrders"] = new JsonArray(),
        ["rejectedReasons"] = rejected ? new JsonArray("min_cash_ratio: post-trade cash below the 5% reserve") : new JsonArray(),
        ["checks"] = new JsonArray(new JsonObject
        {
            ["checkId"] = "min_cash_ratio",
            ["limit"] = request.RiskPolicy.MinCashRatio,
            ["observed"] = rejected ? "0.01" : "0.06",
            ["unit"] = "RATIO",
            ["passed"] = !rejected,
            ["reason"] = null,
        }),
        ["postTradeNavUsd"] = "1000000",
        ["postTradeCashRatio"] = rejected ? "0.01" : "0.06",
        ["postTradeMaxSecurityRatio"] = "0.35",
        ["postTradeParallelDv01Usd"] = "350",
        ["turnoverRatio"] = bootstrap ? "0.94" : "0.05",
        ["orderCount"] = orders,
        ["calculationIds"] = new JsonArray(),
    };

    private static JsonObject Event(string eventId, string type, string effectiveAt, int priority, (string Key, string Value) extra) => new()
    {
        ["eventId"] = eventId,
        ["type"] = type,
        ["effectiveAt"] = effectiveAt,
        ["priority"] = priority,
        [extra.Key] = extra.Value,
    };

    private static JsonObject Journal(string journalId, string eventId, string eventType, string template, string effectiveAt,
        params (string Account, string Debit, string Credit)[] lines)
    {
        var array = new JsonArray();
        var i = 0;
        foreach (var (account, debit, credit) in lines)
        {
            array.Add(new JsonObject
            {
                ["lineId"] = $"{journalId}-l{i++}",
                ["account"] = account,
                ["securityId"] = null,
                ["debitUsd"] = debit,
                ["creditUsd"] = credit,
                ["memo"] = null,
            });
        }

        return new JsonObject
        {
            ["journalId"] = journalId,
            ["eventId"] = eventId,
            ["eventType"] = eventType,
            ["effectiveAt"] = effectiveAt,
            ["template"] = template,
            ["lines"] = array,
        };
    }

    private static JsonObject? Position(JsonArray positions, string securityId, bool create = true)
    {
        var existing = positions.OfType<JsonObject>().FirstOrDefault(p => Str(p["securityId"]) == securityId);
        if (existing is not null || !create)
        {
            return existing;
        }

        var position = new JsonObject
        {
            ["securityId"] = securityId,
            ["economicFace"] = "0",
            ["settledFace"] = "0",
            ["lots"] = new JsonArray(),
        };
        positions.Add(position);
        return position;
    }

    private static string Short(string prefix, string seed) =>
        prefix + "-" + CanonicalJson.Sha256(seed)["sha256:".Length..][..20];

    private static string Str(JsonNode? node) => node?.GetValue<string>() ?? string.Empty;

    private static decimal Dec(JsonNode? node) => node is null ? 0m : Dec(node.GetValue<string>());

    private static decimal Dec(string? value) =>
        string.IsNullOrEmpty(value) ? 0m : decimal.Parse(value, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture);

    private static string Cents(decimal value) => value.ToString("0.00", CultureInfo.InvariantCulture);

    private static string Face(decimal value) => value.ToString("0", CultureInfo.InvariantCulture);

    // ------------------------------------------------------------------ analytics (canned shapes)

    public ConcurrentQueue<PerformanceRequestDto> PerformanceRequests { get; } = new();

    public ConcurrentQueue<PaymentCalendarRequestDto> PaymentCalendarRequests { get; } = new();

    /// <summary>
    /// Echoes a fixed metrics-v1 shape (counts of what was sent, no financial arithmetic):
    /// the real metrics are computed by the Python engine and covered by its tests.
    /// </summary>
    public Task<ResearchEngineDocument> GetPerformanceAsync(PerformanceRequestDto request, CancellationToken cancellationToken = default)
    {
        PerformanceRequests.Enqueue(request);
        var portfolios = new JsonArray(request.Portfolios.Select(p => (JsonNode)new JsonObject
        {
            ["portfolioId"] = p.PortfolioId,
            ["strategyId"] = p.StrategyId,
            ["repetition"] = p.Repetition,
            ["metrics"] = new JsonObject
            {
                ["metricsVersion"] = "metrics-v1",
                ["valuationCount"] = p.Valuations.Count,
                ["fillCount"] = p.Fills.Count,
                ["decisionCount"] = p.DecisionOutcomes.Values.Sum(),
                ["sharpe"] = new JsonObject { ["value"] = null, ["unavailableReason"] = "missing_risk_free_series" },
            },
        }).ToArray());
        var pairs = new JsonArray(request.Pairs.Select(p => (JsonNode)new JsonObject
        {
            ["portfolioId"] = p.PortfolioId,
            ["versusPortfolioId"] = p.VersusPortfolioId,
            ["available"] = false,
            ["reason"] = "too_few_observations",
        }).ToArray());
        return Task.FromResult(new ResearchEngineDocument(200, new JsonObject
        {
            ["metricsVersion"] = "metrics-v1",
            ["engineVersion"] = EngineVersion,
            ["portfolios"] = portfolios,
            ["pairedComparisons"] = pairs,
        }));
    }

    public Task<ResearchEngineDocument> GetPaymentCalendarAsync(PaymentCalendarRequestDto request, CancellationToken cancellationToken = default)
    {
        PaymentCalendarRequests.Enqueue(request);
        var state = FiWire.Deserialize<PortfolioStateDto>(JsonNode.Parse(request.PortfolioState.GetRawText())!);
        var items = new JsonArray(state.Positions.Select(p => (JsonNode)new JsonObject
        {
            ["securityId"] = p.SecurityId,
            ["kind"] = "COUPON",
            ["paymentDate"] = "2099-01-15",
            ["projectedEntitledFaceUsd"] = p.SettledFace,
            ["projectedAmountUsd"] = "1.00",
        }).ToArray());
        return Task.FromResult(new ResearchEngineDocument(200, new JsonObject
        {
            ["portfolioId"] = state.PortfolioId,
            ["portfolioVersion"] = state.Version,
            ["basis"] = "projected_from_current_state_v1",
            ["items"] = items,
        }));
    }

    // ------------------------------------------------------------------ unused passthroughs

    private static Task<ResearchEngineDocument> Doc(object body) =>
        Task.FromResult(new ResearchEngineDocument(200, JsonSerializer.SerializeToNode(body)));

    public Task<ResearchEngineDocument> PriceAsync(PriceRequestDto request, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> RiskAsync(RiskRequestDto request, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> RetrieveEvidenceAsync(EvidenceRetrieveRequestDto request, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> CreateResearchNoteAsync(ResearchNoteRequestDto request, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> GetInstrumentsAsync(InstrumentQuery query, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> GetCurveAsync(string snapshotId, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> GetEvidenceBundleAsync(string bundleId, PageQuery page, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> StartIngestionAsync(IngestionRequestDto request, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> StartIndexBuildAsync(IndexBuildRequestDto request, CancellationToken cancellationToken = default) => Doc(new { });
    public Task<ResearchEngineDocument> GetEvidenceChunkAsync(string chunkId, CancellationToken cancellationToken = default) => Doc(new { chunkId });
    public Task<ResearchEngineDocument> GetEvidenceGraphAsync(string bundleId, CancellationToken cancellationToken = default) => Doc(new { bundleId });
    public Task<ResearchEngineDocument> GetInstrumentValuationAsync(string securityId, DateOnly? date, CancellationToken cancellationToken = default) => Doc(new { securityId });
    public Task<ResearchEngineDocument> GetAdminJobAsync(string jobId, CancellationToken cancellationToken = default) => Doc(new { jobId });
}
