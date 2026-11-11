using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Database.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.EntityFrameworkCore.Migrations.Operations;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>Locates repository files by walking up to AiTradingRace.sln.</summary>
public static class FiRepo
{
    public static string Root { get; } = FindRoot();

    public static string PathOf(params string[] parts) => Path.Combine(new[] { Root }.Concat(parts).ToArray());

    private static string FindRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "AiTradingRace.sln")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        throw new InvalidOperationException("Could not locate AiTradingRace.sln above " + AppContext.BaseDirectory);
    }
}

/// <summary>
/// SQLite in-memory database with only the fi tables created from the EF model
/// (real transactions, unique constraints and foreign keys).
/// </summary>
public sealed class FiSqliteDatabase : IDisposable
{
    private readonly SqliteConnection _connection;

    public FiSqliteDatabase()
    {
        _connection = new SqliteConnection("DataSource=:memory:");
        _connection.Open();
        using var db = CreateContext();
        CreateFixedIncomeTables(db);
    }

    public TradingDbContext CreateContext() =>
        new(new DbContextOptionsBuilder<TradingDbContext>().UseSqlite(_connection).Options);

    public void Dispose() => _connection.Dispose();

    private static void CreateFixedIncomeTables(TradingDbContext db)
    {
        var model = db.GetService<IDesignTimeModel>().Model;
        var differ = db.GetService<IMigrationsModelDiffer>();
        var operations = differ.GetDifferences(null, model.GetRelationalModel())
            .Where(op => op switch
            {
                CreateTableOperation table => table.Schema == FixedIncomeModelConfiguration.Schema,
                CreateIndexOperation index => index.Schema == FixedIncomeModelConfiguration.Schema,
                _ => false,
            })
            .ToList();
        var commands = db.GetService<IMigrationsSqlGenerator>().Generate(operations, model);
        foreach (var command in commands)
        {
            db.Database.ExecuteSqlRaw(command.CommandText);
        }
    }
}

/// <summary>Shared configuration and signed-fixture construction for fixed income tests.</summary>
public static class Fi
{
    public const string SigningKey = "unit-test-signing-key";
    public const string EngineVersion = "research-engine/0.1.0";
    public const string PolicyId = "treasury-long-only-v1";
    public const string PortfolioId = "pf-run-test-llm_graph-r0";
    public const string StrategyId = "llm_graph";
    public const string RunId = "run-test";
    public const string Security = "SYN-USD-NOTE-001";

    public static readonly DateTimeOffset GenesisAsOf = new(2025, 1, 2, 0, 0, 0, TimeSpan.Zero);

    public static long VersionOf(JsonNode state) =>
        long.Parse(state["version"]!.ToJsonString(), System.Globalization.CultureInfo.InvariantCulture);

    public static byte[] KeyBytes => System.Text.Encoding.UTF8.GetBytes(SigningKey);

    public static IOptions<ResearchEngineOptions> EngineOptions(string signingKey = SigningKey) =>
        Options.Create(new ResearchEngineOptions
        {
            SigningKey = signingKey,
            AllowedEngineVersions = new List<string> { "research-engine/0.1.*" },
        });

    public static IRiskPolicyProvider Policies(Dictionary<string, RiskPolicyOptions>? extra = null) =>
        new RiskPolicyProvider(Options.Create(new FixedIncomeOptions
        {
            RiskPolicies = extra ?? new Dictionary<string, RiskPolicyOptions>(),
        }));

    public static ProposalVerifier Verifier() => new(EngineOptions());

    public static TransitionCommitService CommitService(TradingDbContext db, IRiskPolicyProvider? policies = null) =>
        new(db, Verifier(), policies ?? Policies(), NullLogger<TransitionCommitService>.Instance);

    public static string PolicyHash(string policyId = PolicyId, RiskPolicyOptions? policy = null) =>
        CanonicalJson.ContentHash(FiWire.ToNode((policy ?? new RiskPolicyOptions()).ToWire(policyId)));

    public static JsonObject Genesis() => PortfolioGenesis.Build(PortfolioId, StrategyId, RunId, GenesisAsOf);

    public static RawContractJson Raw(JsonObject node) => RawContractJson.Parse(node.ToJsonString());

    /// <summary>Recomputes newStateHash, proposalHash and the HMAC signature (what the engine does).</summary>
    public static JsonObject Seal(JsonObject proposal, string signingKey = SigningKey, bool updateStateHash = true)
    {
        if (updateStateHash)
        {
            proposal["newStateHash"] = CanonicalJson.ContentHash(proposal["newState"]);
        }

        var hash = CanonicalJson.EnvelopeHash(proposal, "proposalHash");
        proposal["proposalHash"] = hash;
        proposal["signature"] = CanonicalJson.Sign(hash, System.Text.Encoding.UTF8.GetBytes(signingKey));
        return proposal;
    }

    /// <summary>Re-signs a proposal without touching its declared hashes (for targeted mismatch tests).</summary>
    public static JsonObject Resign(JsonObject proposal) => Seal(proposal, SigningKey, updateStateHash: false);

    public static string RequestHash(string commandId, string salt = "") =>
        CanonicalJson.ContentHash(new JsonObject { ["commandId"] = commandId, ["salt"] = salt });

    private static JsonObject BaseProposal(JsonObject currentState, string commandId, string commandType, string requestSalt)
    {
        var expected = Fi.VersionOf(currentState);
        var newState = (JsonObject)currentState.DeepClone();
        newState["version"] = expected + 1;
        return new JsonObject
        {
            ["schemaVersion"] = "1.0",
            ["proposalId"] = "prop-" + commandId,
            ["commandId"] = commandId,
            ["commandType"] = commandType,
            ["portfolioId"] = PortfolioId,
            ["strategyId"] = StrategyId,
            ["runId"] = RunId,
            ["expectedVersion"] = expected,
            ["newVersion"] = expected + 1,
            ["noOp"] = false,
            ["engineVersion"] = EngineVersion,
            ["eventPriorityTable"] = "event-priority-v1",
            ["requestHash"] = RequestHash(commandId, requestSalt),
            ["inputHashes"] = new JsonObject
            {
                ["portfolioState"] = CanonicalJson.ContentHash(currentState),
                ["riskPolicy"] = PolicyHash(),
            },
            ["events"] = new JsonArray(),
            ["journals"] = new JsonArray(),
            ["newState"] = newState,
            ["newStateHash"] = null,
            ["ordersCreated"] = new JsonArray(),
            ["orderStatusChanges"] = new JsonArray(),
            ["fills"] = new JsonArray(),
            ["settlementsCreated"] = new JsonArray(),
            ["settlementsCompleted"] = new JsonArray(),
            ["cashFlows"] = new JsonArray(),
            ["policyEvaluation"] = null,
            ["valuation"] = null,
            ["reconciliation"] = Reconciliation(true),
            ["proposalHash"] = null,
            ["signature"] = null,
        };
    }

    public static JsonObject Reconciliation(bool ok, string cash = "0") => new()
    {
        ["ok"] = ok,
        ["journalsBalanced"] = true,
        ["ledgerCashUsd"] = cash,
        ["stateCashUsd"] = cash,
        ["ledgerPrincipalFaceCheck"] = true,
        ["bookEquityUsd"] = cash,
        ["economicEquityUsd"] = null,
        ["differenceUsd"] = null,
        ["messages"] = ok ? new JsonArray() : new JsonArray("ledger cash 1000000.00 != state cash 999999.99"),
    };

    public static JsonObject Journal(string journalId, string eventId, string eventType, string template,
        params (string Account, string Debit, string Credit)[] lines)
    {
        var array = new JsonArray();
        var n = 0;
        foreach (var (account, debit, credit) in lines)
        {
            array.Add(new JsonObject
            {
                ["lineId"] = $"{journalId}-l{n++}",
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
            ["effectiveAt"] = "2025-01-02T00:00:00Z",
            ["template"] = template,
            ["lines"] = array,
        };
    }

    /// <summary>capital_flow command funding the portfolio (fixture values, not computed accounting).</summary>
    public static JsonObject CapitalFlow(JsonObject currentState, string commandId, string amount = "1000000.00",
        string eventId = "evt-capital-1", string requestSalt = "")
    {
        var proposal = BaseProposal(currentState, commandId, "capital_flow", requestSalt);
        var newState = (JsonObject)proposal["newState"]!;
        newState["cashUsd"] = amount;
        newState["externalCapitalUsd"] = amount;
        proposal["events"] = new JsonArray(new JsonObject
        {
            ["eventId"] = eventId,
            ["effectiveAt"] = "2025-01-02T00:00:00Z",
            ["priority"] = 0,
            ["type"] = "capital_flow",
            ["amountUsd"] = amount,
            ["reason"] = "initial_capital",
        });
        proposal["journals"] = new JsonArray(Journal("jr-" + eventId, eventId, "capital_flow", "capital_flow_v1",
            ("CASH", amount, "0"), ("CAPITAL", "0", amount)));
        proposal["cashFlows"] = new JsonArray(new JsonObject
        {
            ["cashFlowId"] = "cf-" + eventId,
            ["securityId"] = "CASH-USD",
            ["kind"] = "CAPITAL",
            ["paymentDate"] = "2025-01-02",
            ["entitledFace"] = "0",
            ["amountUsd"] = amount,
        });
        proposal["reconciliation"] = Reconciliation(true, amount);
        return proposal;
    }

    public static JsonObject Order(string orderId, string decisionId, string face = "100000", bool bootstrap = false) => new()
    {
        ["orderId"] = orderId,
        ["decisionId"] = decisionId,
        ["securityId"] = Security,
        ["side"] = "BUY",
        ["face"] = face,
        ["submittedAt"] = "2025-01-03T00:00:00Z",
        ["eligibleSessionDate"] = "2025-01-03",
        ["expiresAt"] = "2025-01-03T23:59:59Z",
        ["status"] = "ACCEPTED",
        ["reservedCashUsd"] = "101000.00",
        ["batchPriority"] = 0,
        ["statusReason"] = null,
        ["bootstrap"] = bootstrap,
    };

    public static JsonObject PolicyEvaluation(string decisionId, string action, int orderCount,
        string cashRatio = "0.80", string maxSecurity = "0.10", string dv01 = "90", string nav = "1000000",
        string turnover = "0.10", bool bootstrapExemption = false, bool passed = true, string policyId = PolicyId) => new()
    {
        ["policyId"] = policyId,
        ["decisionId"] = decisionId,
        ["action"] = action,
        ["passed"] = passed,
        ["breachMode"] = false,
        ["bootstrapExemptionApplied"] = bootstrapExemption,
        ["originalTargets"] = new JsonArray(),
        ["normalizedTargets"] = new JsonArray(),
        ["normalizationNotes"] = new JsonArray(),
        ["sizedOrders"] = new JsonArray(),
        ["rejectedReasons"] = new JsonArray(),
        ["checks"] = new JsonArray(new JsonObject
        {
            ["checkId"] = "min_cash_ratio",
            ["limit"] = "0.05",
            ["observed"] = cashRatio,
            ["unit"] = "RATIO",
            ["passed"] = passed,
            ["reason"] = null,
        }),
        ["postTradeNavUsd"] = nav,
        ["postTradeCashRatio"] = cashRatio,
        ["postTradeMaxSecurityRatio"] = maxSecurity,
        ["postTradeParallelDv01Usd"] = dv01,
        ["turnoverRatio"] = turnover,
        ["orderCount"] = orderCount,
        ["calculationIds"] = new JsonArray(),
    };

    /// <summary>submit_decision creating one BUY order with the given policy evaluation.</summary>
    public static JsonObject SubmitDecision(JsonObject currentState, string commandId, string decisionId = "dec-1",
        JsonObject? policyEvaluation = null, bool bootstrap = false, string action = "REBALANCE", string orderId = "ord-1")
    {
        var proposal = BaseProposal(currentState, commandId, "submit_decision", "");
        var order = Order(orderId, decisionId, bootstrap: bootstrap);
        var newState = (JsonObject)proposal["newState"]!;
        newState["reservedCashUsd"] = "101000.00";
        newState["openOrders"] = new JsonArray(order.DeepClone());
        proposal["events"] = new JsonArray(new JsonObject
        {
            ["eventId"] = "evt-submit-" + decisionId,
            ["effectiveAt"] = "2025-01-03T00:00:00Z",
            ["priority"] = 70,
            ["type"] = "orders_submitted",
            ["decisionId"] = decisionId,
            ["orders"] = new JsonArray(order.DeepClone()),
        });
        proposal["ordersCreated"] = new JsonArray(order);
        proposal["policyEvaluation"] = policyEvaluation ?? PolicyEvaluation(decisionId, action, 1);
        proposal["reconciliation"] = Reconciliation(true, newState["cashUsd"]!.GetValue<string>());
        return proposal;
    }

    /// <summary>process_events filling an accepted order and creating its settlement.</summary>
    public static JsonObject FillOrder(JsonObject currentState, string commandId, string orderId = "ord-1",
        string decisionId = "dec-1", string fillId = "fill-1", string settlementId = "stl-1", string eventId = "evt-exec-1")
    {
        var proposal = BaseProposal(currentState, commandId, "process_events", "");
        var newState = (JsonObject)proposal["newState"]!;
        newState["reservedCashUsd"] = "0";
        newState["openOrders"] = new JsonArray();
        newState["positions"] = new JsonArray(new JsonObject
        {
            ["securityId"] = Security,
            ["economicFace"] = "100000",
            ["settledFace"] = "0",
            ["lots"] = new JsonArray(),
        });
        var settlement = new JsonObject
        {
            ["settlementId"] = settlementId,
            ["fillId"] = fillId,
            ["securityId"] = Security,
            ["side"] = "BUY",
            ["face"] = "100000",
            ["settlementDate"] = "2025-01-06",
            ["cashUsd"] = "100520.00",
        };
        newState["pendingSettlements"] = new JsonArray(settlement.DeepClone());
        var filled = Order(orderId, decisionId);
        filled["status"] = "FILLED";
        filled["reservedCashUsd"] = "0";
        proposal["events"] = new JsonArray(new JsonObject
        {
            ["eventId"] = eventId,
            ["effectiveAt"] = "2025-01-03T20:30:00Z",
            ["priority"] = 40,
            ["type"] = "execution_observation",
            ["orderId"] = orderId,
            ["observationId"] = "obs-1",
        });
        proposal["orderStatusChanges"] = new JsonArray(filled);
        proposal["fills"] = new JsonArray(new JsonObject
        {
            ["fillId"] = fillId,
            ["orderId"] = orderId,
            ["securityId"] = Security,
            ["side"] = "BUY",
            ["face"] = "100000",
            ["executedAt"] = "2025-01-03T20:30:00Z",
            ["observationId"] = "obs-1",
            ["quoteKind"] = "synthetic_model",
            ["referenceCleanPricePer100"] = "100.10",
            ["executionCleanPricePer100"] = "100.12",
            ["accruedPer100"] = "0.40",
            ["dirtyPricePer100"] = "100.52",
            ["halfSpreadPer100"] = "0.02",
            ["settlementDate"] = "2025-01-06",
            ["considerationUsd"] = "100520.00",
            ["feesUsd"] = "0.00",
            ["spreadCostUsd"] = "20.00",
            ["timingLabel"] = "next_session_close_daily",
        });
        proposal["settlementsCreated"] = new JsonArray(settlement);
        proposal["journals"] = new JsonArray(Journal("jr-" + eventId, eventId, "execution_observation", "buy_fill_v1",
            ("BOND_PRINCIPAL", "100120.00", "0"), ("ACCRUED_INTEREST_PURCHASED", "400.00", "0"),
            ("SETTLEMENT_PAYABLE", "0", "100520.00")));
        proposal["reconciliation"] = Reconciliation(true, newState["cashUsd"]!.GetValue<string>());
        return proposal;
    }

    /// <summary>Parses the newState of a proposal as the next "current" state.</summary>
    public static JsonObject NextState(JsonObject proposal) => (JsonObject)proposal["newState"]!.DeepClone();
}
