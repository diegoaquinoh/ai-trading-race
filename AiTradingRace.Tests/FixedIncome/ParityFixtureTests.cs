using System.Globalization;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Contracts;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Offline-replay vs application-path parity (spec 5.3). The Python simulation
/// workstream writes signed proposals under contracts/fixtures/parity/&lt;scenario&gt;/
/// (shape documented in contracts/fixtures/parity/README.md). Each proposal is applied
/// in order through the real commit service; final state hashes and ledger totals
/// must equal the expected file. Skipped until a manifest.json exists.
/// </summary>
public class ParityFixtureTests
{
    [ParityFixturesFact]
    public async Task PythonParityFixtures_ReplayThroughCommitService()
    {
        var manifests = ParityHarness.ManifestPaths(ParityHarness.FixturesDirectory);
        Assert.NotEmpty(manifests);
        foreach (var manifest in manifests)
        {
            await ParityHarness.RunScenarioAsync(manifest);
        }
    }

    [Fact]
    public async Task Harness_ReplaysASelfGeneratedScenario()
    {
        var directory = Directory.CreateTempSubdirectory("fi-parity-");
        try
        {
            ParityHarness.WriteSampleScenario(directory.FullName);
            await ParityHarness.RunScenarioAsync(Path.Combine(directory.FullName, "manifest.json"));
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }
}

public sealed class ParityFixturesFactAttribute : FactAttribute
{
    public ParityFixturesFactAttribute()
    {
        try
        {
            if (ParityHarness.ManifestPaths(ParityHarness.FixturesDirectory).Count == 0)
            {
                Skip = "No parity fixtures yet: expected contracts/fixtures/parity/<scenario>/manifest.json (see README.md there).";
            }
        }
        catch (Exception ex)
        {
            Skip = "Parity fixtures unavailable: " + ex.Message;
        }
    }
}

public static class ParityHarness
{
    public static string FixturesDirectory => FiRepo.PathOf("contracts", "fixtures", "parity");

    public static IReadOnlyList<string> ManifestPaths(string directory) =>
        Directory.Exists(directory)
            ? Directory.GetFiles(directory, "manifest.json", SearchOption.AllDirectories).OrderBy(p => p, StringComparer.Ordinal).ToList()
            : new List<string>();

    public static async Task RunScenarioAsync(string manifestPath)
    {
        var root = Path.GetDirectoryName(manifestPath)!;
        var manifest = (JsonObject)JsonNode.Parse(await File.ReadAllTextAsync(manifestPath))!;
        var scenario = manifest["scenarioId"]?.GetValue<string>() ?? root;
        Assert.True(ProposalVerifier.IsSupportedSchema(manifest["schemaVersion"]?.GetValue<string>()), $"{scenario}: schema version");

        var portfolio = manifest["portfolio"]!;
        var portfolioId = portfolio["portfolioId"]!.GetValue<string>();
        var riskPolicyId = portfolio["riskPolicyId"]?.GetValue<string>() ?? FixedIncomeOptions.DefaultRiskPolicyId;
        var policies = new Dictionary<string, RiskPolicyOptions>(StringComparer.Ordinal);
        if (manifest["riskPolicy"] is JsonObject wirePolicy)
        {
            policies[riskPolicyId] = FromWire(wirePolicy);
        }

        var engineOptions = Options.Create(new ResearchEngineOptions
        {
            SigningKey = manifest["signingKeyUtf8"]!.GetValue<string>(),
            AllowedEngineVersions = new List<string> { manifest["engineVersion"]!.GetValue<string>() },
        });
        var provider = new RiskPolicyProvider(Options.Create(new FixedIncomeOptions { RiskPolicies = policies }));

        using var database = new FiSqliteDatabase();
        await using (var db = database.CreateContext())
        {
            var service = new TransitionCommitService(db, new ProposalVerifier(engineOptions), provider,
                NullLogger<TransitionCommitService>.Instance);
            await service.CreatePortfolioAsync(new CreateFiPortfolioRequest
            {
                PortfolioId = portfolioId,
                RunId = portfolio["runId"]!.GetValue<string>(),
                StrategyId = portfolio["strategyId"]!.GetValue<string>(),
                Repetition = portfolio["repetition"]?.GetValue<int>() ?? 0,
                RiskPolicyId = riskPolicyId,
                DataMode = portfolio["dataMode"]?.GetValue<string>() ?? "synthetic_curve",
                InitialStateJson = manifest["genesisState"]!.ToJsonString(),
            });
        }

        foreach (var relative in manifest["proposals"]!.AsArray().Select(p => p!.GetValue<string>()))
        {
            var raw = RawContractJson.Parse(await File.ReadAllTextAsync(Path.Combine(root, relative)));
            await using var db = database.CreateContext();
            var service = new TransitionCommitService(db, new ProposalVerifier(engineOptions), provider,
                NullLogger<TransitionCommitService>.Instance);
            // ExpectedRequestHash is deliberately left unset: parity fixtures are produced offline by the
            // Python replay without any .NET TransitionRequest, so there is no platform-sent body whose
            // canonical hash could be compared with the fixture's requestHash. The application path
            // always binds it (FixedIncomeCycleRunner → FiRequestBody; see RequestBindingTests).
            var result = await service.CommitAsync(raw, new TransitionCommitContext
            {
                ExpectedCommandId = raw.Node["commandId"]!.GetValue<string>(),
            });
            Assert.True(result.Status == TransitionCommitStatus.Committed,
                $"{scenario}/{relative}: {result.Status} {result.Message} " +
                string.Join("; ", result.Issues.Select(i => $"{i.Code}: {i.Message}")));
        }

        var expected = (JsonObject)JsonNode.Parse(await File.ReadAllTextAsync(
            Path.Combine(root, manifest["expected"]?.GetValue<string>() ?? "expected.json")))!;
        await using (var db = database.CreateContext())
        {
            var stored = await db.FiPortfolios.SingleAsync(p => p.PortfolioId == portfolioId);
            Assert.Equal(expected["finalVersion"]!.GetValue<long>(), stored.CurrentVersion);
            Assert.Equal(expected["finalStateHash"]!.GetValue<string>(), stored.CurrentStateHash);

            if (expected["stateHashes"] is JsonObject stateHashes)
            {
                var versions = await db.FiPortfolioStateVersions.Where(v => v.PortfolioId == portfolioId).ToListAsync();
                foreach (var (version, hash) in stateHashes)
                {
                    var row = versions.SingleOrDefault(v => v.Version == long.Parse(version, CultureInfo.InvariantCulture));
                    Assert.True(row is not null, $"{scenario}: missing state version {version}");
                    Assert.Equal(hash!.GetValue<string>(), row!.StateHash);
                    Assert.Equal(row.StateHash, CanonicalJson.Sha256(row.StateJson));
                }
            }

            if (expected["ledgerTotals"] is JsonObject totals)
            {
                var entries = await db.FiJournalEntries.Where(e => e.PortfolioId == portfolioId).ToListAsync();
                foreach (var (account, value) in totals)
                {
                    var own = entries.Where(e => e.Account == account).ToList();
                    Assert.Equal(Dec(value!["debitUsd"]), own.Sum(e => e.DebitUsd));
                    Assert.Equal(Dec(value["creditUsd"]), own.Sum(e => e.CreditUsd));
                }

                Assert.Equal(entries.Sum(e => e.DebitUsd), entries.Sum(e => e.CreditUsd));
            }

            if (expected["counts"] is JsonObject counts)
            {
                await AssertCount(counts, "journals", db.FiJournals.CountAsync(j => j.PortfolioId == portfolioId));
                await AssertCount(counts, "orders", db.FiOrderIntents.CountAsync(o => o.PortfolioId == portfolioId));
                await AssertCount(counts, "fills", db.FiFills.CountAsync(f => f.PortfolioId == portfolioId));
                await AssertCount(counts, "settlements", db.FiSettlements.CountAsync(s => s.PortfolioId == portfolioId));
                await AssertCount(counts, "cashFlows", db.FiCashFlowEvents.CountAsync(c => c.PortfolioId == portfolioId));
                await AssertCount(counts, "valuations", db.FiValuationSnapshots.CountAsync(v => v.PortfolioId == portfolioId));
            }
        }
    }

    /// <summary>Writes a three-step scenario (capital, decision, fill) built with the test fixtures.</summary>
    public static void WriteSampleScenario(string directory)
    {
        Directory.CreateDirectory(Path.Combine(directory, "proposals"));
        var genesis = Fi.Genesis();
        var capital = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        var decision = Fi.Seal(Fi.SubmitDecision(Fi.NextState(capital), "cmd-2"));
        var fill = Fi.Seal(Fi.FillOrder(Fi.NextState(decision), "cmd-3"));
        var proposals = new[] { capital, decision, fill };
        var names = new JsonArray();
        for (var i = 0; i < proposals.Length; i++)
        {
            var name = $"proposals/{i + 1:0000}.json";
            File.WriteAllText(Path.Combine(directory, name), proposals[i].ToJsonString());
            names.Add(name);
        }

        File.WriteAllText(Path.Combine(directory, "manifest.json"), new JsonObject
        {
            ["schemaVersion"] = "1.0",
            ["scenarioId"] = "self-generated",
            ["signingKeyUtf8"] = Fi.SigningKey,
            ["engineVersion"] = Fi.EngineVersion,
            ["portfolio"] = new JsonObject
            {
                ["portfolioId"] = Fi.PortfolioId,
                ["strategyId"] = Fi.StrategyId,
                ["runId"] = Fi.RunId,
                ["riskPolicyId"] = Fi.PolicyId,
                ["dataMode"] = "synthetic_curve",
            },
            ["riskPolicy"] = FiWire.ToNode(new RiskPolicyOptions().ToWire(Fi.PolicyId)),
            ["genesisState"] = genesis,
            ["proposals"] = names,
            ["expected"] = "expected.json",
        }.ToJsonString());

        File.WriteAllText(Path.Combine(directory, "expected.json"), new JsonObject
        {
            ["finalVersion"] = 3,
            ["finalStateHash"] = fill["newStateHash"]!.GetValue<string>(),
            ["stateHashes"] = new JsonObject
            {
                ["0"] = CanonicalJson.ContentHash(genesis),
                ["1"] = capital["newStateHash"]!.GetValue<string>(),
                ["2"] = decision["newStateHash"]!.GetValue<string>(),
                ["3"] = fill["newStateHash"]!.GetValue<string>(),
            },
            ["ledgerTotals"] = new JsonObject
            {
                ["CASH"] = new JsonObject { ["debitUsd"] = "1000000.00", ["creditUsd"] = "0" },
                ["CAPITAL"] = new JsonObject { ["debitUsd"] = "0", ["creditUsd"] = "1000000.00" },
                ["BOND_PRINCIPAL"] = new JsonObject { ["debitUsd"] = "100120.00", ["creditUsd"] = "0" },
                ["ACCRUED_INTEREST_PURCHASED"] = new JsonObject { ["debitUsd"] = "400.00", ["creditUsd"] = "0" },
                ["SETTLEMENT_PAYABLE"] = new JsonObject { ["debitUsd"] = "0", ["creditUsd"] = "100520.00" },
            },
            ["counts"] = new JsonObject
            {
                ["journals"] = 2, ["orders"] = 1, ["fills"] = 1, ["settlements"] = 1, ["cashFlows"] = 1, ["valuations"] = 0,
            },
        }.ToJsonString());
    }

    private static async Task AssertCount(JsonObject counts, string key, Task<int> actual)
    {
        if (counts[key] is { } expected)
        {
            Assert.Equal(expected.GetValue<int>(), await actual);
        }
    }

    private static decimal Dec(JsonNode? node) =>
        decimal.Parse(node!.GetValue<string>(), NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture);

    private static RiskPolicyOptions FromWire(JsonObject wire)
    {
        decimal D(string name) => Dec(wire[name]);
        return new RiskPolicyOptions
        {
            InitialCapitalUsd = D("initialCapitalUsd"),
            LongOnly = wire["longOnly"]!.GetValue<bool>(),
            LeverageAllowed = wire["leverageAllowed"]!.GetValue<bool>(),
            MinCashRatio = D("minCashRatio"),
            MaxSingleSecurityRatio = D("maxSingleSecurityRatio"),
            MaxParallelDv01UsdPerMillionNav = D("maxParallelDv01UsdPerMillionNav"),
            MaxDailyTurnoverRatio = D("maxDailyTurnoverRatio"),
            MaxOrdersPerDecision = wire["maxOrdersPerDecision"]!.GetValue<int>(),
            MinWeightChange = D("minWeightChange"),
            WeightSumTolerance = D("weightSumTolerance"),
            MaxMarkAgeBusinessDays = wire["maxMarkAgeBusinessDays"]!.GetValue<int>(),
            BootstrapTurnoverExemption = wire["bootstrapTurnoverExemption"]!.GetValue<bool>(),
            ProjectionMode = wire["projectionMode"]!.GetValue<string>(),
            BreachPolicy = wire["breachPolicy"]!.GetValue<string>(),
        };
    }
}
