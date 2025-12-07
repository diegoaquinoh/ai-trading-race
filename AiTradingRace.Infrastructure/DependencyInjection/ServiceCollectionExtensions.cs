using AiTradingRace.Application.Agents;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Infrastructure.Agents;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.MarketData;
using AiTradingRace.Infrastructure.Portfolios;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace AiTradingRace.Infrastructure.DependencyInjection;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddInfrastructureServices(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        services.AddDbContext<TradingDbContext>(options =>
        {
            var connectionString = configuration.GetConnectionString("TradingDb");

            if (string.IsNullOrWhiteSpace(connectionString))
            {
                options.UseInMemoryDatabase("AiTradingRace");
            }
            else
            {
                options.UseSqlServer(connectionString);
            }
        });

        services.TryAddScoped<IMarketDataProvider, EfMarketDataProvider>();
        services.TryAddScoped<IPortfolioService, EfPortfolioService>();
        services.TryAddSingleton<IAgentModelClient, EchoAgentModelClient>();
        services.TryAddScoped<IAgentRunner, NoOpAgentRunner>();
        return services;
    }
}

