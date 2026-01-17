using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace AiTradingRace.Infrastructure.Database;

/// <summary>
/// Design-time factory to create the DbContext for EF Core CLI commands.
/// Requires ConnectionStrings__TradingDb environment variable to be set.
/// </summary>
/// <remarks>
/// Usage: export ConnectionStrings__TradingDb='Server=localhost,1433;...'
///        dotnet ef migrations add MigrationName -p AiTradingRace.Infrastructure -s AiTradingRace.Web
/// </remarks>
public sealed class TradingDbContextFactory : IDesignTimeDbContextFactory<TradingDbContext>
{
    public TradingDbContext CreateDbContext(string[] args)
    {
        var optionsBuilder = new DbContextOptionsBuilder<TradingDbContext>();

        // Require environment variable - no fallback to prevent wrong DB provider in migrations
        var connectionString = Environment.GetEnvironmentVariable("ConnectionStrings__TradingDb");

        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new InvalidOperationException(
                "EF Core design-time: ConnectionStrings__TradingDb environment variable is required. " +
                "Set it before running EF commands:\n\n" +
                "  export ConnectionStrings__TradingDb='Server=localhost,1433;Database=AiTradingRace;" +
                "User Id=sa;Password=YourPassword;Encrypt=True;TrustServerCertificate=True;'\n\n" +
                "Then run: dotnet ef migrations add <Name> -p AiTradingRace.Infrastructure -s AiTradingRace.Web");
        }

        optionsBuilder.UseSqlServer(connectionString);
        return new TradingDbContext(optionsBuilder.Options);
    }
}


