using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Tests.FixedIncome;

public class ProposalVerifierTests
{
    private static ProposalVerificationContext Context(JsonObject state, RiskPolicyOptions? policy = null,
        string policyId = Fi.PolicyId, long? version = null) => new()
    {
        CurrentVersion = version ?? Fi.VersionOf(state),
        CurrentStateHash = CanonicalJson.ContentHash(state),
        CurrentStateJson = CanonicalJson.Serialize(state),
        RiskPolicyId = policyId,
        RiskPolicy = policy ?? new RiskPolicyOptions(),
        ExpectedPortfolioId = Fi.PortfolioId,
    };

    private static ProposalVerificationResult Verify(JsonObject proposal, ProposalVerificationContext context) =>
        Fi.Verifier().Verify(Fi.Raw(proposal), context);

    private static JsonObject Funded()
    {
        var genesis = Fi.Genesis();
        return Fi.NextState(Fi.CapitalFlow(genesis, "cmd-capital"));
    }

    [Fact]
    public void ValidCapitalFlow_IsAccepted()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));

        var result = Verify(proposal, Context(genesis) with { ExpectedCommandId = "cmd-1" });

        Assert.True(result.IsValid, string.Join("; ", result.Issues.Select(i => i.Message)));
        Assert.True(result.IsAuthentic);
        Assert.Equal(proposal["proposalHash"]!.GetValue<string>(), result.ComputedProposalHash);
        Assert.Equal(CanonicalJson.Serialize(proposal["newState"]), result.CanonicalNewStateJson);
    }

    [Fact]
    public void TamperedField_IsRejectedAsHashMismatch()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        proposal["newState"]!["cashUsd"] = "2000000.00";

        var result = Verify(proposal, Context(genesis));

        Assert.False(result.IsAuthentic);
        Assert.True(result.HasIssue(VerificationCodes.HashMismatch));
        Assert.True(result.HasIssue(VerificationCodes.SignatureInvalid));
        Assert.True(result.HasIssue(VerificationCodes.NewStateHashMismatch));
    }

    [Fact]
    public void BadSignature_IsRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"), signingKey: "attacker-key");

        var result = Verify(proposal, Context(genesis));

        Assert.False(result.IsAuthentic);
        Assert.True(result.HasIssue(VerificationCodes.SignatureInvalid));
        Assert.False(result.HasIssue(VerificationCodes.HashMismatch));
    }

    [Fact]
    public void MissingSigningKey_IsRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        var verifier = new ProposalVerifier(Fi.EngineOptions(signingKey: ""));

        var result = verifier.Verify(Fi.Raw(proposal), Context(genesis));

        Assert.True(result.HasIssue(VerificationCodes.SigningKeyMissing));
        Assert.False(result.IsAuthentic);
    }

    [Theory]
    [InlineData("2.0")]
    [InlineData("0.9")]
    [InlineData("x")]
    public void UnknownSchemaMajor_IsRejected(string schemaVersion)
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1");
        proposal["schemaVersion"] = schemaVersion;
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.HasIssue(VerificationCodes.SchemaVersion));
        Assert.Null(result.Proposal);
    }

    [Fact]
    public void EngineVersionOutsideAllowlist_IsRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1");
        proposal["engineVersion"] = "research-engine/9.9.9";
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.HasIssue(VerificationCodes.EngineVersion));
        Assert.False(result.IsAuthentic);
    }

    [Fact]
    public void StaleVersion_IsReportedAsStaleOnly()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        var funded = Funded();

        var result = Verify(proposal, Context(funded));

        Assert.True(result.IsAuthentic);
        Assert.True(result.HasIssue(VerificationCodes.StaleVersion));
        Assert.True(result.HasIssue(VerificationCodes.StateHashMismatch));
        Assert.True(result.IsStaleOnly);
    }

    [Fact]
    public void CommandIdMismatch_IsRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));

        var result = Verify(proposal, Context(genesis) with { ExpectedCommandId = "cmd-other" });

        Assert.True(result.HasIssue(VerificationCodes.CommandIdMismatch));
    }

    [Fact]
    public void UnbalancedJournal_IsRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1");
        proposal["journals"]![0]!["lines"]![1]!["creditUsd"] = "999999.99";
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.IsAuthentic);
        Assert.True(result.HasIssue(VerificationCodes.JournalUnbalanced));
    }

    [Fact]
    public void JournalAmountNotInCents_IsRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1", amount: "1000000.001");
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.HasIssue(VerificationCodes.AmountNotCents));
    }

    [Fact]
    public void NewStateHashMismatch_IsRejectedEvenWhenSigned()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.Seal(Fi.CapitalFlow(genesis, "cmd-1"));
        proposal["newStateHash"] = CanonicalJson.Sha256("{\"other\":true}");
        Fi.Resign(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.IsAuthentic);
        Assert.True(result.HasIssue(VerificationCodes.NewStateHashMismatch));
    }

    [Fact]
    public void VersionInconsistency_IsRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1");
        proposal["newVersion"] = 5;
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.HasIssue(VerificationCodes.VersionInconsistent));
    }

    [Fact]
    public void ReconciliationFailure_IsFlagged()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1");
        proposal["reconciliation"] = Fi.Reconciliation(false);
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.IsAuthentic);
        Assert.True(result.ReconciliationFailed);
    }

    [Fact]
    public void ValidDecisionSubmission_IsAccepted()
    {
        var funded = Funded();
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec"));

        var result = Verify(proposal, Context(funded));

        Assert.True(result.IsValid, string.Join("; ", result.Issues.Select(i => i.Message)));
    }

    [Fact]
    public void PolicyLimitExceeded_EvenWhenEngineSaysPassed()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, maxSecurity: "0.55");
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation));

        var result = Verify(proposal, Context(funded));

        Assert.True(result.HasIssue(VerificationCodes.PolicyLimitExceeded));
    }

    [Fact]
    public void PolicyLimit_UsesPlatformConfigurationNotEngineDefaults()
    {
        // The platform policy is tighter (10% minimum cash). The engine evaluated this exact
        // policy document but reports a 6% post-trade cash ratio and claims success.
        var tight = new RiskPolicyOptions { MinCashRatio = 0.10m };
        const string tightId = "treasury-tight-v1";
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, cashRatio: "0.06", policyId: tightId);
        evaluation["checks"] = new JsonArray();
        var proposal = Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation);
        proposal["inputHashes"]!["riskPolicy"] = Fi.PolicyHash(tightId, tight);
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(funded, tight, tightId));
        var underDefault = Verify(proposal, Context(funded, new RiskPolicyOptions(), tightId));

        Assert.True(result.HasIssue(VerificationCodes.PolicyLimitExceeded));
        Assert.Contains(result.Issues, i => i.Message.Contains("minCashRatio 0.10"));
        Assert.True(underDefault.HasIssue(VerificationCodes.PolicyInputHashMismatch));
    }

    [Fact]
    public void EngineUsingADifferentPolicyDocument_IsRejected()
    {
        var funded = Funded();
        var proposal = Fi.SubmitDecision(funded, "cmd-dec");
        proposal["inputHashes"]!["riskPolicy"] = Fi.PolicyHash(Fi.PolicyId, new RiskPolicyOptions { MaxSingleSecurityRatio = 0.90m });
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(funded));

        Assert.True(result.HasIssue(VerificationCodes.PolicyInputHashMismatch));
    }

    [Fact]
    public void PolicyIdChosenByEngine_IsRejected()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, policyId: "loose-policy-v9");
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation));

        var result = Verify(proposal, Context(funded));

        Assert.True(result.HasIssue(VerificationCodes.PolicyIdMismatch));
    }

    [Fact]
    public void PassedFlagInconsistentWithOrders_IsRejected()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, passed: false);
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation));

        var result = Verify(proposal, Context(funded));

        Assert.True(result.HasIssue(VerificationCodes.PolicyFlagInconsistent));
    }

    [Fact]
    public void MissingRiskMetric_BlocksOrders()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1);
        evaluation["postTradeParallelDv01Usd"] = null;
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation));

        var result = Verify(proposal, Context(funded));

        Assert.True(result.HasIssue(VerificationCodes.PolicyMetricMissing));
    }

    [Fact]
    public void Dv01AboveCapPerMillionNav_IsRejected()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, dv01: "601", nav: "1000000");
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation));

        var result = Verify(proposal, Context(funded));

        Assert.Contains(result.Issues, i => i.Code == VerificationCodes.PolicyLimitExceeded && i.Message.Contains("DV01"));
    }

    [Fact]
    public void MissingPolicyEvaluation_OnSubmitDecision_IsRejected()
    {
        var funded = Funded();
        var proposal = Fi.SubmitDecision(funded, "cmd-dec");
        proposal["policyEvaluation"] = null;
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(funded));

        Assert.True(result.HasIssue(VerificationCodes.PolicyMissing));
    }

    [Fact]
    public void BootstrapExemption_HonouredWhenFlaggedFromUninvestedState()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "BOOTSTRAP", 1, turnover: "0.94", bootstrapExemption: true);
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation, bootstrap: true, action: "BOOTSTRAP"));

        var result = Verify(proposal, Context(funded));

        Assert.True(result.IsValid, string.Join("; ", result.Issues.Select(i => i.Message)));
    }

    [Fact]
    public void HighTurnover_WithoutBootstrapFlag_IsRejected()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "BOOTSTRAP", 1, turnover: "0.94", bootstrapExemption: false);
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation, bootstrap: true, action: "BOOTSTRAP"));

        var result = Verify(proposal, Context(funded));

        Assert.Contains(result.Issues, i => i.Code == VerificationCodes.PolicyLimitExceeded && i.Message.Contains("Turnover"));
    }

    [Fact]
    public void BootstrapFlag_OnInvestedPortfolio_IsRejected()
    {
        var invested = Funded();
        invested["positions"] = new JsonArray(new JsonObject
        {
            ["securityId"] = Fi.Security,
            ["economicFace"] = "100000",
            ["settledFace"] = "100000",
            ["lots"] = new JsonArray(),
        });
        var evaluation = Fi.PolicyEvaluation("dec-1", "BOOTSTRAP", 1, turnover: "0.94", bootstrapExemption: true);
        var proposal = Fi.Seal(Fi.SubmitDecision(invested, "cmd-dec", policyEvaluation: evaluation, bootstrap: true, action: "BOOTSTRAP"));

        var result = Verify(proposal, Context(invested));

        Assert.True(result.HasIssue(VerificationCodes.BootstrapExemptionInvalid));
        Assert.True(result.HasIssue(VerificationCodes.PolicyLimitExceeded));
    }

    [Fact]
    public void BootstrapFlag_DisabledByPlatformPolicy_IsRejected()
    {
        var noBootstrap = new RiskPolicyOptions { BootstrapTurnoverExemption = false };
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "BOOTSTRAP", 1, turnover: "0.94", bootstrapExemption: true);
        var proposal = Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation, bootstrap: true, action: "BOOTSTRAP");
        proposal["inputHashes"]!["riskPolicy"] = Fi.PolicyHash(Fi.PolicyId, noBootstrap);
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(funded, noBootstrap));

        Assert.True(result.HasIssue(VerificationCodes.BootstrapExemptionInvalid));
    }

    [Fact]
    public void NegativeFace_IsRejectedAsLongOnlyViolation()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1");
        proposal["newState"]!["positions"] = new JsonArray(new JsonObject
        {
            ["securityId"] = Fi.Security,
            ["economicFace"] = "-1000",
            ["settledFace"] = "0",
            ["lots"] = new JsonArray(),
        });
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.HasIssue(VerificationCodes.LongOnlyViolation));
    }

    [Fact]
    public void OrdersOutsideSubmitDecision_AreRejected()
    {
        var genesis = Fi.Genesis();
        var proposal = Fi.CapitalFlow(genesis, "cmd-1");
        proposal["ordersCreated"] = new JsonArray(Fi.Order("ord-x", "dec-x"));
        Fi.Seal(proposal);

        var result = Verify(proposal, Context(genesis));

        Assert.True(result.HasIssue(VerificationCodes.PolicyFlagInconsistent));
    }

    [Fact]
    public void EngineAllowlist_SupportsWildcardAndExactEntries()
    {
        var options = new ResearchEngineOptions { AllowedEngineVersions = new List<string> { "research-engine/0.1.*", "custom/2.0.0" } };

        Assert.True(options.IsEngineVersionAllowed("research-engine/0.1.7"));
        Assert.True(options.IsEngineVersionAllowed("custom/2.0.0"));
        Assert.False(options.IsEngineVersionAllowed("custom/2.0.1"));
        Assert.False(options.IsEngineVersionAllowed(null));
        Assert.True(new ResearchEngineOptions().IsEngineVersionAllowed("research-engine/0.1.0"));
        Assert.Equal(TimeSpan.FromSeconds(120), new ResearchEngineOptions().EffectiveTimeout);
        Assert.Equal(TimeSpan.FromSeconds(ResearchEngineOptions.MinimumTimeoutSeconds),
            new ResearchEngineOptions { TimeoutSeconds = 30 }.EffectiveTimeout);
    }
}
