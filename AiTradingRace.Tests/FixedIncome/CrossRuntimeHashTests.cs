using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Hashes pinned from the Python contracts (research_engine.contracts, 2026-11-06):
/// content_hash(RiskPolicy()), content_hash(ExecutionModel()) and the version-0
/// PortfolioState for the test portfolio. They prove .NET sends the exact policy
/// documents the engine hashes and that .NET's genesis state equals Python's.
/// </summary>
public class CrossRuntimeHashTests
{
    private const string PythonDefaultRiskPolicyHash = "sha256:9fad814adb712358027210d8a4eb8b572da99cbf0ac74718e632f964726b5e23";
    private const string PythonDefaultExecutionModelHash = "sha256:d3f9bd5e39ee45dc8e845e76f05c96cfd8a606e6c546d66b15c707b7eefc7887";
    private const string PythonGenesisHash = "sha256:a0d701fdf2b68fd6821e3958e5e24fd59c16e8f16b0d9752bc24f83ef6a24c9b";

    [Fact]
    public void DefaultRiskPolicy_HashesLikePython() =>
        Assert.Equal(PythonDefaultRiskPolicyHash, Fi.PolicyHash());

    [Fact]
    public void DefaultExecutionModel_HashesLikePython() =>
        Assert.Equal(PythonDefaultExecutionModelHash,
            CanonicalJson.ContentHash(FiWire.ToNode(new ExecutionModelOptions().ToWire(FixedIncomeOptions.DefaultExecutionModelId))));

    [Fact]
    public void Genesis_HashesLikePythonPortfolioState() =>
        Assert.Equal(PythonGenesisHash, CanonicalJson.ContentHash(Fi.Genesis()));

    [Fact]
    public void AppSettingsPolicy_BindsToTheSameDocument()
    {
        var configuration = new ConfigurationBuilder()
            .AddJsonFile(FiRepo.PathOf("AiTradingRace.Web", "appsettings.json"))
            .Build();
        var options = configuration.GetSection(FixedIncomeOptions.SectionName).Get<FixedIncomeOptions>()!;
        var engine = configuration.GetSection(ResearchEngineOptions.SectionName).Get<ResearchEngineOptions>()!;
        var provider = new RiskPolicyProvider(Options.Create(options));

        var policy = provider.FindRiskPolicy(FixedIncomeOptions.DefaultRiskPolicyId)!;
        var model = provider.FindExecutionModel(FixedIncomeOptions.DefaultExecutionModelId)!;

        Assert.Equal(PythonDefaultRiskPolicyHash, Fi.PolicyHash(FixedIncomeOptions.DefaultRiskPolicyId, policy));
        Assert.Equal(PythonDefaultExecutionModelHash,
            CanonicalJson.ContentHash(FiWire.ToNode(model.ToWire(FixedIncomeOptions.DefaultExecutionModelId))));
        Assert.Equal(120, engine.TimeoutSeconds);
        Assert.Equal(new[] { "research-engine/0.1.*" }, engine.AllowedEngineVersions);
    }
}
