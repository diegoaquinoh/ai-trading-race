using AiTradingRace.Application.FixedIncome;

namespace AiTradingRace.Web.FixedIncome;

public static class FixedIncomeWebServiceCollectionExtensions
{
    /// <summary>Background run queue (Channel + hosted worker) for fixed income runs.</summary>
    public static IServiceCollection AddFixedIncomeRunQueue(this IServiceCollection services)
    {
        services.AddSingleton<FixedIncomeRunQueue>();
        services.AddSingleton<IFixedIncomeRunQueue>(sp => sp.GetRequiredService<FixedIncomeRunQueue>());
        services.AddHostedService<FixedIncomeRunWorker>();
        return services;
    }
}
