using AiTradingRace.Application.Agents;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Infrastructure.Agents;
using AiTradingRace.Infrastructure.MarketData;
using AiTradingRace.Infrastructure.Portfolios;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace AiTradingRace.Infrastructure.DependencyInjection;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddInfrastructureServices(this IServiceCollection services)
    {
        services.TryAddSingleton<IMarketDataProvider, InMemoryMarketDataProvider>();
        services.TryAddSingleton<IPortfolioService, InMemoryPortfolioService>();
        services.TryAddSingleton<IAgentModelClient, EchoAgentModelClient>();
        services.TryAddSingleton<IAgentRunner, NoOpAgentRunner>();
        return services;
    }
}

