using AiTradingRace.Application.FixedIncome.Options;

namespace AiTradingRace.Application.FixedIncome;

/// <summary>Resolves platform-owned risk policies and execution models by id.</summary>
public interface IRiskPolicyProvider
{
    IReadOnlyCollection<string> RiskPolicyIds { get; }

    IReadOnlyCollection<string> ExecutionModelIds { get; }

    RiskPolicyOptions? FindRiskPolicy(string policyId);

    ExecutionModelOptions? FindExecutionModel(string executionModelId);
}
