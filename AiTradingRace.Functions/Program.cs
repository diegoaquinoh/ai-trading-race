using AiTradingRace.Application.DependencyInjection;
using AiTradingRace.Infrastructure.DependencyInjection;
using Microsoft.Extensions.Hosting;

var host = new HostBuilder()
    .ConfigureFunctionsWorkerDefaults()
    .ConfigureServices(services =>
    {
        services.AddApplicationServices();
        services.AddInfrastructureServices();
    })
    .Build();

host.Run();

