using System;
using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Equity;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Infrastructure.Agents;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Equity;
using AiTradingRace.Infrastructure.MarketData;
using AiTradingRace.Infrastructure.Portfolios;
using Azure;
using Azure.AI.OpenAI;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.DependencyInjection;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddInfrastructureServices(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Database
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

        // Core services
        services.TryAddScoped<IMarketDataProvider, EfMarketDataProvider>();
        services.TryAddScoped<IPortfolioService, EfPortfolioService>();
        services.TryAddScoped<IEquityService, EquityService>();

        // Market data ingestion
        services.Configure<CoinGeckoOptions>(configuration.GetSection(CoinGeckoOptions.SectionName));
        services.AddHttpClient<IExternalMarketDataClient, CoinGeckoMarketDataClient>();
        services.TryAddScoped<IMarketDataIngestionService, MarketDataIngestionService>();

        // AI Agent Integration (Phase 5)
        services.Configure<AzureOpenAiOptions>(configuration.GetSection(AzureOpenAiOptions.SectionName));
        services.Configure<CustomMlAgentOptions>(configuration.GetSection(CustomMlAgentOptions.SectionName));
        services.Configure<RiskValidatorOptions>(configuration.GetSection(RiskValidatorOptions.SectionName));

        // Azure OpenAI Client - create singleton from options (only if configured)
        services.AddSingleton<AzureOpenAIClient>(sp =>
        {
            var options = sp.GetRequiredService<IOptions<AzureOpenAiOptions>>().Value;

            if (string.IsNullOrWhiteSpace(options.Endpoint) || string.IsNullOrWhiteSpace(options.ApiKey))
            {
                // Return null - will throw when actually used
                throw new InvalidOperationException(
                    "Azure OpenAI not configured. Set AzureOpenAI:Endpoint and AzureOpenAI:ApiKey in appsettings or user-secrets.");
            }

            return new AzureOpenAIClient(
                new Uri(options.Endpoint),
                new AzureKeyCredential(options.ApiKey));
        });

        // Register all AI model clients as concrete types for factory resolution
        services.TryAddScoped<AzureOpenAiAgentModelClient>();
        services.TryAddScoped<TestAgentModelClient>();
        services.TryAddScoped<EchoAgentModelClient>();

        // Custom ML client with dedicated HttpClient
        services.AddHttpClient<CustomMlAgentModelClient>((sp, client) =>
        {
            var options = sp.GetRequiredService<IOptions<CustomMlAgentOptions>>().Value;
            client.BaseAddress = new Uri(options.BaseUrl);
            client.Timeout = TimeSpan.FromSeconds(options.TimeoutSeconds);
        });

        // Agent services
        services.TryAddScoped<IAgentContextBuilder, AgentContextBuilder>();
        services.TryAddScoped<IAgentModelClientFactory, AgentModelClientFactory>();
        services.TryAddScoped<IRiskValidator, RiskValidator>();
        services.TryAddScoped<IAgentRunner, AgentRunner>();

        return services;
    }

    /// <summary>
    /// Adds infrastructure services with a mock AI model client (for testing/development).
    /// </summary>
    public static IServiceCollection AddInfrastructureServicesWithMockAI(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Database
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

        // Core services
        services.TryAddScoped<IMarketDataProvider, EfMarketDataProvider>();
        services.TryAddScoped<IPortfolioService, EfPortfolioService>();
        services.TryAddScoped<IEquityService, EquityService>();

        // Market data ingestion
        services.Configure<CoinGeckoOptions>(configuration.GetSection(CoinGeckoOptions.SectionName));
        services.AddHttpClient<IExternalMarketDataClient, CoinGeckoMarketDataClient>();
        services.TryAddScoped<IMarketDataIngestionService, MarketDataIngestionService>();

        // AI Agent Integration with Mock client
        services.Configure<RiskValidatorOptions>(configuration.GetSection(RiskValidatorOptions.SectionName));
        services.TryAddScoped<IAgentContextBuilder, AgentContextBuilder>();
        services.TryAddScoped<IAgentModelClient, EchoAgentModelClient>(); // Mock client - always HOLD
        services.TryAddScoped<IRiskValidator, RiskValidator>();
        services.TryAddScoped<IAgentRunner, AgentRunner>();

        return services;
    }

    /// <summary>
    /// Adds infrastructure services with TestAgentModelClient that generates aggressive orders.
    /// Use this for E2E testing of risk validation.
    /// </summary>
    public static IServiceCollection AddInfrastructureServicesWithTestAI(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Database
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

        // Core services
        services.TryAddScoped<IMarketDataProvider, EfMarketDataProvider>();
        services.TryAddScoped<IPortfolioService, EfPortfolioService>();
        services.TryAddScoped<IEquityService, EquityService>();

        // Market data ingestion
        services.Configure<CoinGeckoOptions>(configuration.GetSection(CoinGeckoOptions.SectionName));
        services.AddHttpClient<IExternalMarketDataClient, CoinGeckoMarketDataClient>();
        services.TryAddScoped<IMarketDataIngestionService, MarketDataIngestionService>();

        // AI Agent Integration with Test client (generates aggressive orders)
        services.Configure<RiskValidatorOptions>(configuration.GetSection(RiskValidatorOptions.SectionName));
        services.TryAddScoped<IAgentContextBuilder, AgentContextBuilder>();
        services.TryAddScoped<IAgentModelClient, TestAgentModelClient>(); // Test client - generates orders
        services.TryAddScoped<IRiskValidator, RiskValidator>();
        services.TryAddScoped<IAgentRunner, AgentRunner>();

        return services;
    }
}


