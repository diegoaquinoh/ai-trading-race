using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.DependencyInjection;

public static class FixedIncomeServiceCollectionExtensions
{
    /// <summary>
    /// Registers the fixed income transactional authority (spec 5.1): research-engine
    /// client, proposal verifier, commit service, decision audit, experiments and
    /// dashboard queries, and the application-mode run executor. Additive: legacy crypto
    /// services are untouched.
    /// </summary>
    public static IServiceCollection AddFixedIncomeServices(this IServiceCollection services, IConfiguration configuration)
    {
        services.Configure<ResearchEngineOptions>(configuration.GetSection(ResearchEngineOptions.SectionName));
        services.Configure<FixedIncomeOptions>(configuration.GetSection(FixedIncomeOptions.SectionName));

        services.TryAddSingleton(TimeProvider.System);
        services.TryAddSingleton<IRiskPolicyProvider, RiskPolicyProvider>();
        services.TryAddSingleton<IProposalVerifier, ProposalVerifier>();

        services.TryAddScoped<ITransitionCommitService, TransitionCommitService>();
        services.TryAddScoped<IDecisionAuditService, DecisionAuditService>();
        services.TryAddScoped<IExperimentService, ExperimentService>();
        // Engine-computed analytics (metrics-v1, payment calendars) cached per committed state.
        services.TryAddSingleton<FiAnalyticsCache>();
        services.TryAddScoped<IFixedIncomeQueryService, FixedIncomeQueryService>();
        // Application-mode executor (spec 15.1): shared cycle logic for the Web hosted queue and
        // the Functions durable activities; one scope (DbContext) per cycle step.
        services.TryAddSingleton<FixedIncomeMetrics>();
        services.TryAddScoped<IFixedIncomeCycleRunner, FixedIncomeCycleRunner>();
        services.TryAddScoped<IFixedIncomeRunExecutor, FixedIncomeRunExecutor>();

        // No retry/circuit-breaker handlers: POST commands must not be replayed implicitly.
        services.AddHttpClient<IResearchEngineClient, ResearchEngineClient>((sp, client) =>
        {
            var options = sp.GetRequiredService<IOptions<ResearchEngineOptions>>().Value;
            client.BaseAddress = ResearchEngineClient.BuildBaseAddress(options.BaseUrl);
            client.Timeout = options.EffectiveTimeout;
        });

        return services;
    }
}
