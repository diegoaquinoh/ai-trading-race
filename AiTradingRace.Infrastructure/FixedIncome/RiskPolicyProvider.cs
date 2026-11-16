using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Platform-owned risk policies and execution models. The spec 9.3 defaults are
/// always available under "treasury-long-only-v1" and the 9.4 synthetic profile
/// under "synthetic-half-spread-0.02-v1" unless configuration overrides them.
/// </summary>
public sealed class RiskPolicyProvider : IRiskPolicyProvider
{
    private readonly IReadOnlyDictionary<string, RiskPolicyOptions> _policies;
    private readonly IReadOnlyDictionary<string, ExecutionModelOptions> _executionModels;

    public RiskPolicyProvider(IOptions<FixedIncomeOptions> options)
    {
        var value = options.Value;

        var policies = new Dictionary<string, RiskPolicyOptions>(StringComparer.Ordinal)
        {
            [FixedIncomeOptions.DefaultRiskPolicyId] = new RiskPolicyOptions(),
        };
        foreach (var (id, policy) in value.RiskPolicies)
        {
            policies[id] = policy;
        }

        var models = new Dictionary<string, ExecutionModelOptions>(StringComparer.Ordinal)
        {
            [FixedIncomeOptions.DefaultExecutionModelId] = new ExecutionModelOptions(),
        };
        foreach (var (id, model) in value.ExecutionModels)
        {
            models[id] = model;
        }

        _policies = policies;
        _executionModels = models;
    }

    public IReadOnlyCollection<string> RiskPolicyIds => _policies.Keys.ToList();

    public IReadOnlyCollection<string> ExecutionModelIds => _executionModels.Keys.ToList();

    public RiskPolicyOptions? FindRiskPolicy(string policyId) =>
        _policies.TryGetValue(policyId, out var policy) ? policy : null;

    public ExecutionModelOptions? FindExecutionModel(string executionModelId) =>
        _executionModels.TryGetValue(executionModelId, out var model) ? model : null;
}
