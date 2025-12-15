using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace AiTradingRace.Infrastructure.Database;

/// <summary>
/// Design-time factory to create the DbContext for EF Core CLI commands.
/// Uses ConnectionStrings:TradingDb if provided via environment or falls back to LocalDB.
/// </summary>
public sealed class TradingDbContextFactory : IDesignTimeDbContextFactory<TradingDbContext>
{
    public TradingDbContext CreateDbContext(string[] args)
    {
        var optionsBuilder = new DbContextOptionsBuilder<TradingDbContext>();

        // Prefer environment variable (compatible with ASP.NET Core naming)
        var connectionString = Environment.GetEnvironmentVariable("ConnectionStrings__TradingDb");

        if (!string.IsNullOrWhiteSpace(connectionString))
        {
            optionsBuilder.UseSqlServer(connectionString);
        }
        else
        {
            // Cross-platform fallback for design-time tooling when no SQL Server connection is provided.
            var sqlitePath = Path.Combine(AppContext.BaseDirectory, "design.db");
            optionsBuilder.UseSqlite($"Data Source={sqlitePath}");
        }

        return new TradingDbContext(optionsBuilder.Options);
    }
}

