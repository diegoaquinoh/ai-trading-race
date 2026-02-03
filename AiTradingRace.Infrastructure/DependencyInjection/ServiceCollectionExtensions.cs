using System;
using System.Net;
using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Decisions;
using AiTradingRace.Application.Equity;
using AiTradingRace.Application.Knowledge;
using AiTradingRace.Application.MarketData;
using AiTradingRace.Application.Portfolios;
using AiTradingRace.Infrastructure.Agents;
using AiTradingRace.Infrastructure.Database;
using AiTradingRace.Infrastructure.Decisions;
using AiTradingRace.Infrastructure.Equity;
using AiTradingRace.Infrastructure.Knowledge;
using AiTradingRace.Infrastructure.MarketData;
using AiTradingRace.Infrastructure.Portfolios;
using Azure;
using Azure.AI.OpenAI;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Options;
using Polly;
using Polly.Extensions.Http;

namespace AiTradingRace.Infrastructure.DependencyInjection;

public static class ServiceCollectionExtensions
{
    /// <summary>
    /// Adds all infrastructure services with full AI model client support.
    /// </summary>
    public static IServiceCollection AddInfrastructureServices(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Add common services
        services.AddCoreInfrastructureServices(configuration);

        // AI Agent Integration (Phase 5 & 8)
        services.Configure<AzureOpenAiOptions>(configuration.GetSection(AzureOpenAiOptions.SectionName));
        services.Configure<CustomMlAgentOptions>(configuration.GetSection(CustomMlAgentOptions.SectionName));
        services.Configure<LlamaOptions>(configuration.GetSection(LlamaOptions.SectionName));

        // Azure OpenAI Client - create singleton from options (only if configured)
        services.AddSingleton<AzureOpenAIClient>(sp =>
        {
            var options = sp.GetRequiredService<IOptions<AzureOpenAiOptions>>().Value;

            if (string.IsNullOrWhiteSpace(options.Endpoint) || string.IsNullOrWhiteSpace(options.ApiKey))
            {
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

        // Llama API client with rate limiting and resilience policies (Phase 8)
        services.AddTransient<LlamaRateLimitingHandler>();
        services.AddHttpClient<LlamaAgentModelClient>((sp, client) =>
        {
            var options = sp.GetRequiredService<IOptions<LlamaOptions>>().Value;
            client.BaseAddress = new Uri(options.BaseUrl);
            client.Timeout = TimeSpan.FromSeconds(options.TimeoutSeconds);

            if (!string.IsNullOrWhiteSpace(options.ApiKey))
            {
                client.DefaultRequestHeaders.Authorization =
                    new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", options.ApiKey);
            }
        })
        .AddHttpMessageHandler<LlamaRateLimitingHandler>()
        .AddPolicyHandler(GetLlamaRetryPolicy())
        .AddPolicyHandler(GetLlamaCircuitBreakerPolicy());

        // Agent services
        services.TryAddScoped<IAgentModelClientFactory, AgentModelClientFactory>();

        return services;
    }

    /// <summary>
    /// Adds infrastructure services with a mock AI model client (for testing/development).
    /// Uses EchoAgentModelClient which always returns HOLD.
    /// </summary>
    public static IServiceCollection AddInfrastructureServicesWithMockAI(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Add common services
        services.AddCoreInfrastructureServices(configuration);

        // Mock client - always returns HOLD
        services.TryAddScoped<IAgentModelClient, EchoAgentModelClient>();

        return services;
    }

    /// <summary>
    /// Adds infrastructure services with TestAgentModelClient that generates aggressive orders.
    /// Use this for E2E testing of risk validation.
    /// All model providers are redirected to TestAgentModelClient (no API keys needed).
    /// </summary>
    public static IServiceCollection AddInfrastructureServicesWithTestAI(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Add common services
        services.AddCoreInfrastructureServices(configuration);

        // Test client for aggressive order generation
        services.TryAddScoped<TestAgentModelClient>();

        // Use TestAgentModelClientFactory which ignores the agent's ModelProvider
        // and always returns TestAgentModelClient (no API keys required)
        services.TryAddScoped<IAgentModelClientFactory, TestAgentModelClientFactory>();

        return services;
    }

    /// <summary>
    /// Adds core infrastructure services shared by all configurations.
    /// </summary>
    private static IServiceCollection AddCoreInfrastructureServices(
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

        // Risk validation
        services.Configure<RiskValidatorOptions>(configuration.GetSection(RiskValidatorOptions.SectionName));
        services.TryAddScoped<IRiskValidator, RiskValidator>();

        // Agent services
        services.TryAddScoped<IAgentContextBuilder, AgentContextBuilder>();
        services.TryAddScoped<IAgentRunner, AgentRunner>();

        // Phase 10: Knowledge Graph & Decision Logs
        services.TryAddScoped<IKnowledgeGraphService, InMemoryKnowledgeGraphService>();
        services.TryAddScoped<IRegimeDetector, VolatilityBasedRegimeDetector>();
        services.TryAddScoped<IDecisionLogService, DecisionLogService>();

        return services;
    }

    /// <summary>
    /// Creates a retry policy for Llama API calls with exponential backoff.
    /// Handles transient HTTP errors and rate limiting (429).
    /// </summary>
    private static IAsyncPolicy<HttpResponseMessage> GetLlamaRetryPolicy()
    {
        return HttpPolicyExtensions
            .HandleTransientHttpError()
            .OrResult(response => response.StatusCode == HttpStatusCode.TooManyRequests)
            .WaitAndRetryAsync(
                retryCount: 3,
                sleepDurationProvider: attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt)), // 2s, 4s, 8s
                onRetry: (outcome, timespan, retryAttempt, context) =>
                {
                    // Logging handled by the client
                });
    }

    /// <summary>
    /// Creates a circuit breaker policy for Llama API calls.
    /// Opens circuit after 5 consecutive failures, stays open for 30 seconds.
    /// </summary>
    private static IAsyncPolicy<HttpResponseMessage> GetLlamaCircuitBreakerPolicy()
    {
        return HttpPolicyExtensions
            .HandleTransientHttpError()
            .OrResult(response => response.StatusCode == HttpStatusCode.TooManyRequests)
            .CircuitBreakerAsync(
                handledEventsAllowedBeforeBreaking: 5,
                durationOfBreak: TimeSpan.FromSeconds(30));
    }
}
