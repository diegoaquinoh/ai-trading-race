using System.Globalization;
using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Application.FixedIncome.Options;

/// <summary>Fixed income platform configuration (section "FixedIncome").</summary>
public sealed class FixedIncomeOptions
{
    public const string SectionName = "FixedIncome";

    public const string DefaultRiskPolicyId = "treasury-long-only-v1";
    public const string DefaultExecutionModelId = "synthetic-half-spread-0.02-v1";

    /// <summary>
    /// Risk policies keyed by policy id. The platform always knows
    /// "treasury-long-only-v1" with the spec 9.3 defaults; configuration may
    /// override it or add new ids (changing a value requires a new id).
    /// </summary>
    public Dictionary<string, RiskPolicyOptions> RiskPolicies { get; set; } = new(StringComparer.Ordinal);

    /// <summary>Execution models keyed by id (spec 9.4).</summary>
    public Dictionary<string, ExecutionModelOptions> ExecutionModels { get; set; } = new(StringComparer.Ordinal);

    /// <summary>Capacity of the in-process run queue.</summary>
    public int RunQueueCapacity { get; set; } = 100;

    /// <summary>Application-mode run executor settings (spec 15.1).</summary>
    public FixedIncomeExecutionOptions Execution { get; set; } = new();

    /// <summary>Scheduled forward (paper) cycle settings (spec 6.4).</summary>
    public PaperTradingOptions PaperTrading { get; set; } = new();
}

/// <summary>Run executor settings. Never strategy behaviour: limits and plumbing only.</summary>
public sealed class FixedIncomeExecutionOptions
{
    public const string WebHost = "web";
    public const string FunctionsHost = "functions";

    /// <summary>
    /// Which host executes queued runs: "web" (hosted queue in the API process, default)
    /// or "functions" (durable FixedIncomeReplayOrchestrator). Exactly one host executes.
    /// </summary>
    public string RunExecutionHost { get; set; } = WebHost;

    /// <summary>Bounded parallelism of the per-cycle strategy decision fan-out.</summary>
    public int MaxParallelDecisions { get; set; } = 4;

    /// <summary>Recompute attempts after a stale-version commit result (spec 9.5 step 6).</summary>
    public int StaleRecomputeAttempts { get; set; } = 1;

    /// <summary>Extra attempts for a transition request when the engine is unreachable (pure computation; safe to repeat).</summary>
    public int TransientRetryAttempts { get; set; } = 2;

    /// <summary>Base backoff between transient retries (milliseconds, doubled per attempt).</summary>
    public int TransientRetryDelayMs { get; set; } = 1000;

    /// <summary>Cycle-level retries by the Web executor before the run fails as resumable.</summary>
    public int CycleRetryAttempts { get; set; } = 1;
}

/// <summary>
/// Forward paper cycle schedule: 19:00 America/New_York on supported market business
/// days (spec 6.4), conditional on complete inputs. The timer fires hourly in UTC and the
/// New York wall-clock check uses the IANA time-zone database, so daylight-saving changes
/// need no configuration.
/// </summary>
public sealed class PaperTradingOptions
{
    public bool Enabled { get; set; }

    /// <summary>Forward experiment whose run receives the daily paper cycles.</summary>
    public string? ExperimentId { get; set; }

    public int? ExperimentVersion { get; set; }

    /// <summary>Stable logical run id of the forward run (created on first use).</summary>
    public string? RunId { get; set; }

    public string ResponseMode { get; set; } = "recorded_replay";

    public string TimeZoneId { get; set; } = "America/New_York";

    /// <summary>Local decision hour (24h) in <see cref="TimeZoneId"/>.</summary>
    public int DecisionHour { get; set; } = 19;
}

/// <summary>Platform-owned copy of a risk policy (spec 9.3). The model cannot select or alter it.</summary>
public sealed class RiskPolicyOptions
{
    public decimal InitialCapitalUsd { get; set; } = 1_000_000m;
    public bool LongOnly { get; set; } = true;
    public bool LeverageAllowed { get; set; }
    public decimal MinCashRatio { get; set; } = 0.05m;
    public decimal MaxSingleSecurityRatio { get; set; } = 0.40m;
    public decimal MaxParallelDv01UsdPerMillionNav { get; set; } = 600m;
    public decimal MaxDailyTurnoverRatio { get; set; } = 0.20m;
    public int MaxOrdersPerDecision { get; set; } = 6;
    public decimal MinWeightChange { get; set; } = 0.02m;
    public decimal WeightSumTolerance { get; set; } = 0.000001m;
    public int MaxMarkAgeBusinessDays { get; set; } = 1;
    public bool BootstrapTurnoverExemption { get; set; } = true;
    public string ProjectionMode { get; set; } = "disabled";
    public string BreachPolicy { get; set; } = "block_risk_increasing_v1";

    /// <summary>Wire form sent to the engine (decimal strings, Python field names).</summary>
    public RiskPolicyDto ToWire(string policyId) => new()
    {
        PolicyId = policyId,
        InitialCapitalUsd = Dec(InitialCapitalUsd),
        LongOnly = LongOnly,
        LeverageAllowed = LeverageAllowed,
        MinCashRatio = Dec(MinCashRatio),
        MaxSingleSecurityRatio = Dec(MaxSingleSecurityRatio),
        MaxParallelDv01UsdPerMillionNav = Dec(MaxParallelDv01UsdPerMillionNav),
        MaxDailyTurnoverRatio = Dec(MaxDailyTurnoverRatio),
        MaxOrdersPerDecision = MaxOrdersPerDecision,
        MinWeightChange = Dec(MinWeightChange),
        WeightSumTolerance = Dec(WeightSumTolerance),
        MaxMarkAgeBusinessDays = MaxMarkAgeBusinessDays,
        BootstrapTurnoverExemption = BootstrapTurnoverExemption,
        ProjectionMode = ProjectionMode,
        BreachPolicy = BreachPolicy,
    };

    internal static string Dec(decimal value) => value.ToString(CultureInfo.InvariantCulture);
}

/// <summary>Platform-owned execution/fill assumptions (spec 9.4). Illustrative, not measured costs.</summary>
public sealed class ExecutionModelOptions
{
    public decimal HalfSpreadPer100 { get; set; } = 0.02m;
    public decimal SlippagePer100 { get; set; } = 0m;
    public decimal CommissionUsdPerMillionFace { get; set; } = 0m;
    public string TimeInForce { get; set; } = "next_session_only";
    public string FillTiming { get; set; } = "next_session_close_daily";
    public string FundingRule { get; set; } = "settled_cash_reserve_commitments_v1";
    public string BatchPriority { get; set; } = "sells_first_then_security_id_v1";
    public decimal CashInterestRate { get; set; } = 0m;
    public string FaceSizing { get; set; } = "fixed_at_submission_v1";

    public ExecutionModelDto ToWire(string executionModelId) => new()
    {
        ExecutionModelId = executionModelId,
        HalfSpreadPer100 = RiskPolicyOptions.Dec(HalfSpreadPer100),
        SlippagePer100 = RiskPolicyOptions.Dec(SlippagePer100),
        CommissionUsdPerMillionFace = RiskPolicyOptions.Dec(CommissionUsdPerMillionFace),
        TimeInForce = TimeInForce,
        FillTiming = FillTiming,
        FundingRule = FundingRule,
        BatchPriority = BatchPriority,
        CashInterestRate = RiskPolicyOptions.Dec(CashInterestRate),
        FaceSizing = FaceSizing,
    };
}
