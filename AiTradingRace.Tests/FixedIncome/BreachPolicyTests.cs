using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Infrastructure.FixedIncome;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Breach policy re-check (spec 9.3, block_risk_increasing_v1): during a breach the engine may pass
/// an explicitly validated risk-reducing order set; the platform accepts a post-trade value outside
/// its limit only in breach mode, with the pre-trade value reported, already outside that limit,
/// and not worsened. Missing pre-trade values fail closed. Default policy: min cash 0.05, max single
/// security 0.40, DV01 600 USD per 1,000,000 NAV.
/// </summary>
public class BreachPolicyTests
{
    public enum Metric
    {
        Cash,
        MaxSecurity,
        Dv01,
    }

    private static JsonObject Funded() => Fi.NextState(Fi.CapitalFlow(Fi.Genesis(), "cmd-capital"));

    private static ProposalVerificationResult VerifySubmission(Metric metric, string post, string? pre, bool breachMode,
        string? preNav = null)
    {
        var funded = Funded();
        var evaluation = metric switch
        {
            Metric.Cash => Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, cashRatio: post),
            Metric.MaxSecurity => Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, maxSecurity: post),
            _ => Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, dv01: post, nav: "1000000"),
        };
        evaluation["breachMode"] = breachMode;
        var preField = metric switch
        {
            Metric.Cash => "preTradeCashRatio",
            Metric.MaxSecurity => "preTradeMaxSecurityRatio",
            _ => "preTradeParallelDv01Usd",
        };
        if (pre is not null)
        {
            evaluation[preField] = pre;
        }

        if (preNav is not null)
        {
            evaluation["preTradeNavUsd"] = preNav;
        }

        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation));
        return Fi.Verifier().Verify(Fi.Raw(proposal), new ProposalVerificationContext
        {
            CurrentVersion = Fi.VersionOf(funded),
            CurrentStateHash = CanonicalJson.ContentHash(funded),
            CurrentStateJson = CanonicalJson.Serialize(funded),
            RiskPolicyId = Fi.PolicyId,
            RiskPolicy = new RiskPolicyOptions(),
            ExpectedPortfolioId = Fi.PortfolioId,
        });
    }

    private static string Describe(ProposalVerificationResult result) =>
        string.Join("; ", result.Issues.Select(i => $"{i.Code}: {i.Message}"));

    [Theory]
    [InlineData(Metric.Cash, "0.04", "0.02")] // cash below the 5% minimum, but raised from 2%
    [InlineData(Metric.Cash, "0.03", "0.03")] // not worsened (unchanged)
    [InlineData(Metric.MaxSecurity, "0.45", "0.52")] // concentration above 40%, reduced from 52%
    [InlineData(Metric.Dv01, "650", "720")] // DV01 above 600/1M NAV, reduced from 720
    [InlineData(Metric.Dv01, "-650", "-720")] // sign-insensitive magnitude comparison
    public void RiskReducingPartialCure_DuringBreach_IsAccepted(Metric metric, string post, string pre)
    {
        var result = VerifySubmission(metric, post, pre, breachMode: true);

        Assert.True(result.IsValid, Describe(result));
    }

    [Theory]
    [InlineData(Metric.Cash, "0.02", "0.03")] // cash reduced further below the minimum
    [InlineData(Metric.MaxSecurity, "0.48", "0.45")] // concentration increased
    [InlineData(Metric.Dv01, "700", "650")] // DV01 increased
    public void RiskIncreasing_DuringBreach_IsRejected(Metric metric, string post, string pre)
    {
        var result = VerifySubmission(metric, post, pre, breachMode: true);

        Assert.Contains(result.Issues, i => i.Code == VerificationCodes.PolicyLimitExceeded && i.Message.Contains("breach mode"));
    }

    [Theory]
    [InlineData(Metric.Cash, "0.04")]
    [InlineData(Metric.MaxSecurity, "0.45")]
    [InlineData(Metric.Dv01, "650")]
    public void Breach_WithoutPreTradeValues_FailsClosed(Metric metric, string post)
    {
        var result = VerifySubmission(metric, post, pre: null, breachMode: true);

        Assert.Contains(result.Issues, i => i.Code == VerificationCodes.PolicyLimitExceeded && i.Message.Contains("pre-trade value is missing"));
    }

    [Theory]
    [InlineData(Metric.Cash, "0.04", "0.06")] // pre-trade compliant: the order set creates a new breach
    [InlineData(Metric.MaxSecurity, "0.45", "0.35")]
    [InlineData(Metric.Dv01, "650", "500")]
    public void NewBreach_FromACompliantPreTradeState_IsRejected(Metric metric, string post, string pre)
    {
        var result = VerifySubmission(metric, post, pre, breachMode: true);

        Assert.True(result.HasIssue(VerificationCodes.PolicyLimitExceeded), Describe(result));
    }

    [Fact]
    public void Dv01PreTradeLimit_IsScaledByPreTradeNav()
    {
        // Post: DV01 650 on NAV 1,000,000 breaches the 600/1M cap. Pre: DV01 655 on NAV 1,100,000 is
        // within its own cap (660), so this is a new breach and must be rejected. Scaling the pre-trade
        // DV01 by the post-trade NAV instead would wrongly see "breach not worsened" (655 > 600).
        var scaled = VerifySubmission(Metric.Dv01, "650", "655", breachMode: true, preNav: "1100000");
        Assert.False(scaled.IsValid, "pre-trade state was compliant under pre-trade NAV");
        Assert.Contains(scaled.Issues, i => i.Message.Contains("DV01"));

        var legacy = VerifySubmission(Metric.Dv01, "650", "655", breachMode: true);
        Assert.True(legacy.IsValid, Describe(legacy));
    }

    [Fact]
    public void ImprovingMetric_WithoutBreachMode_IsStillRejected()
    {
        var result = VerifySubmission(Metric.Cash, "0.04", "0.02", breachMode: false);

        Assert.True(result.HasIssue(VerificationCodes.PolicyLimitExceeded), Describe(result));
    }

    [Fact]
    public void MalformedPreTradeValue_IsRejected()
    {
        var result = VerifySubmission(Metric.Cash, "0.04", "not-a-number", breachMode: true);

        Assert.False(result.IsValid);
        Assert.True(result.HasIssue(VerificationCodes.Malformed), Describe(result));
    }

    [Fact]
    public void BreachMode_DoesNotRelaxOtherChecks()
    {
        var funded = Funded();
        var evaluation = Fi.PolicyEvaluation("dec-1", "REBALANCE", 1, cashRatio: "0.04", turnover: "0.35");
        evaluation["breachMode"] = true;
        evaluation["preTradeCashRatio"] = "0.02";
        var proposal = Fi.Seal(Fi.SubmitDecision(funded, "cmd-dec", policyEvaluation: evaluation));

        var result = Fi.Verifier().Verify(Fi.Raw(proposal), new ProposalVerificationContext
        {
            CurrentVersion = Fi.VersionOf(funded),
            CurrentStateHash = CanonicalJson.ContentHash(funded),
            CurrentStateJson = CanonicalJson.Serialize(funded),
            RiskPolicyId = Fi.PolicyId,
            RiskPolicy = new RiskPolicyOptions(),
            ExpectedPortfolioId = Fi.PortfolioId,
        });

        var issue = Assert.Single(result.Issues);
        Assert.Equal(VerificationCodes.PolicyLimitExceeded, issue.Code);
        Assert.Contains("Turnover", issue.Message);
    }
}
