using AiTradingRace.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace AiTradingRace.Infrastructure.Database;

public sealed class TradingDbContext : DbContext
{
    public TradingDbContext(DbContextOptions<TradingDbContext> options)
        : base(options)
    {
    }

    public DbSet<Agent> Agents => Set<Agent>();
    public DbSet<MarketAsset> MarketAssets => Set<MarketAsset>();
    public DbSet<MarketCandle> MarketCandles => Set<MarketCandle>();
    public DbSet<Portfolio> Portfolios => Set<Portfolio>();
    public DbSet<Position> Positions => Set<Position>();
    public DbSet<Trade> Trades => Set<Trade>();
    public DbSet<EquitySnapshot> EquitySnapshots => Set<EquitySnapshot>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        ConfigureAgents(modelBuilder);
        ConfigureMarketAssets(modelBuilder);
        ConfigureMarketCandles(modelBuilder);
        ConfigurePortfolios(modelBuilder);
        ConfigurePositions(modelBuilder);
        ConfigureTrades(modelBuilder);
        ConfigureEquitySnapshots(modelBuilder);
        SeedData.Configure(modelBuilder);
    }

    private static void ConfigureAgents(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Agent>(builder =>
        {
            builder.ToTable("Agents");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Name).IsRequired().HasMaxLength(128);
            builder.Property(x => x.Strategy).HasMaxLength(512);
            builder.Property(x => x.Instructions).HasMaxLength(4000);
            builder.Property(x => x.ModelProvider)
                .HasConversion<string>()
                .HasMaxLength(32)
                .HasDefaultValue(ModelProvider.Llama);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("SYSUTCDATETIME()");
            builder.Property(x => x.IsActive).HasDefaultValue(true);

            // One-to-one with Portfolio
            builder.HasOne(x => x.Portfolio)
                .WithOne()
                .HasForeignKey<Portfolio>(p => p.AgentId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }

    private static void ConfigureMarketAssets(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<MarketAsset>(builder =>
        {
            builder.ToTable("MarketAssets");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Symbol).IsRequired().HasMaxLength(16);
            builder.HasIndex(x => x.Symbol).IsUnique();
            builder.Property(x => x.Name).IsRequired().HasMaxLength(128);
            builder.Property(x => x.QuoteCurrency).IsRequired().HasMaxLength(16);
            builder.Property(x => x.ExternalId).IsRequired().HasMaxLength(64);
            builder.Property(x => x.IsEnabled).HasDefaultValue(true);
        });
    }

    private static void ConfigureMarketCandles(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<MarketCandle>(builder =>
        {
            builder.ToTable("MarketCandles");
            builder.HasKey(x => x.Id);

            builder.Property(x => x.Open).HasColumnType("decimal(18,8)");
            builder.Property(x => x.High).HasColumnType("decimal(18,8)");
            builder.Property(x => x.Low).HasColumnType("decimal(18,8)");
            builder.Property(x => x.Close).HasColumnType("decimal(18,8)");
            builder.Property(x => x.Volume).HasColumnType("decimal(18,8)");

            builder.HasIndex(x => new { x.MarketAssetId, x.TimestampUtc }).IsUnique();

            builder.HasOne<MarketAsset>()
                .WithMany()
                .HasForeignKey(x => x.MarketAssetId)
                .OnDelete(DeleteBehavior.Cascade);

            builder.HasCheckConstraint("CK_MarketCandle_PricesPositive", "[Open] > 0 AND [High] > 0 AND [Low] > 0 AND [Close] > 0");
            builder.HasCheckConstraint("CK_MarketCandle_VolumeNonNegative", "[Volume] >= 0");
        });
    }

    private static void ConfigurePortfolios(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Portfolio>(builder =>
        {
            builder.ToTable("Portfolios");
            builder.HasKey(x => x.Id);

            builder.Property(x => x.Cash).HasColumnType("decimal(18,8)").HasDefaultValue(0m);
            builder.Property(x => x.BaseCurrency).IsRequired().HasMaxLength(16).HasDefaultValue("USD");

            builder.HasIndex(x => x.AgentId).IsUnique();

            // Note: Agent-Portfolio relationship configured in ConfigureAgents()

            builder.HasMany(x => x.Positions)
                .WithOne()
                .HasForeignKey(x => x.PortfolioId)
                .OnDelete(DeleteBehavior.Cascade);

            builder.Navigation(x => x.Positions).AutoInclude(false);

            builder.HasCheckConstraint("CK_Portfolio_Cash_NonNegative", "[Cash] >= 0");
        });
    }

    private static void ConfigurePositions(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Position>(builder =>
        {
            builder.ToTable("Positions");
            builder.HasKey(x => x.Id);

            builder.Property(x => x.Quantity).HasColumnType("decimal(18,8)");
            builder.Property(x => x.AverageEntryPrice).HasColumnType("decimal(18,8)");

            builder.HasIndex(x => new { x.PortfolioId, x.MarketAssetId }).IsUnique();

            builder.HasOne<Portfolio>()
                .WithMany(p => p.Positions)
                .HasForeignKey(x => x.PortfolioId)
                .OnDelete(DeleteBehavior.Cascade);

            builder.HasOne<MarketAsset>()
                .WithMany()
                .HasForeignKey(x => x.MarketAssetId)
                .OnDelete(DeleteBehavior.Restrict);

            builder.HasCheckConstraint("CK_Position_Quantity_NonNegative", "[Quantity] >= 0");
            builder.HasCheckConstraint("CK_Position_AverageEntryPrice_NonNegative", "[AverageEntryPrice] >= 0");
        });
    }

    private static void ConfigureTrades(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Trade>(builder =>
        {
            builder.ToTable("Trades");
            builder.HasKey(x => x.Id);

            builder.Property(x => x.Quantity).HasColumnType("decimal(18,8)");
            builder.Property(x => x.Price).HasColumnType("decimal(18,8)");

            builder.HasIndex(x => x.PortfolioId);
            builder.HasIndex(x => x.MarketAssetId);

            builder.HasOne(x => x.Portfolio)
                .WithMany()
                .HasForeignKey(x => x.PortfolioId)
                .OnDelete(DeleteBehavior.Cascade);

            builder.HasOne(x => x.MarketAsset)
                .WithMany()
                .HasForeignKey(x => x.MarketAssetId)
                .OnDelete(DeleteBehavior.Restrict);

            builder.ToTable(t =>
            {
                t.HasCheckConstraint("CK_Trade_Quantity_Positive", "[Quantity] > 0");
                t.HasCheckConstraint("CK_Trade_Price_Positive", "[Price] > 0");
            });
        });
    }

    private static void ConfigureEquitySnapshots(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<EquitySnapshot>(builder =>
        {
            builder.ToTable("EquitySnapshots");
            builder.HasKey(x => x.Id);

            builder.Property(x => x.TotalValue).HasColumnType("decimal(18,8)");
            builder.Property(x => x.CashValue).HasColumnType("decimal(18,8)");
            builder.Property(x => x.PositionsValue).HasColumnType("decimal(18,8)");
            builder.Property(x => x.UnrealizedPnL).HasColumnType("decimal(18,8)");

            builder.HasIndex(x => new { x.PortfolioId, x.CapturedAt });

            builder.HasOne(x => x.Portfolio)
                .WithMany()
                .HasForeignKey(x => x.PortfolioId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }

    private static class SeedData
    {
        private static readonly Guid BtcId = Guid.Parse("c3d4b060-55bb-4e48-8f04-3452ec0c9d4c");
        private static readonly Guid EthId = Guid.Parse("b1fa9f8a-626b-4253-9a5d-0c9c9fb5c9fd");

        private static readonly Guid AgentGptId = Guid.Parse("11111111-1111-1111-1111-111111111111");
        private static readonly Guid AgentClaudeId = Guid.Parse("22222222-2222-2222-2222-222222222222");
        private static readonly Guid AgentGrokId = Guid.Parse("33333333-3333-3333-3333-333333333333");

        private static readonly Guid CandleBtcSeedId = Guid.Parse("44444444-4444-4444-4444-444444444444");
        private static readonly Guid CandleEthSeedId = Guid.Parse("55555555-5555-5555-5555-555555555555");

        internal static void Configure(ModelBuilder modelBuilder)
        {
            modelBuilder.Entity<MarketAsset>().HasData(
                new MarketAsset
                {
                    Id = BtcId,
                    Symbol = "BTC",
                    Name = "Bitcoin",
                    ExternalId = "bitcoin",
                    QuoteCurrency = "USD",
                    IsEnabled = true
                },
                new MarketAsset
                {
                    Id = EthId,
                    Symbol = "ETH",
                    Name = "Ethereum",
                    ExternalId = "ethereum",
                    QuoteCurrency = "USD",
                    IsEnabled = true
                });

            modelBuilder.Entity<Agent>().HasData(
                new Agent
                {
                    Id = AgentGptId,
                    Name = "Llama-70B",
                    Strategy = "Momentum-based trading with risk management",
                    Instructions = "You are a conservative trader. Focus on momentum signals and always maintain diversification.",
                    ModelProvider = ModelProvider.Llama,
                    IsActive = true
                },
                new Agent
                {
                    Id = AgentClaudeId,
                    Name = "Claude",
                    Strategy = "Value-oriented with technical analysis",
                    Instructions = "You are a value investor. Look for undervalued opportunities and use technical indicators for timing.",
                    ModelProvider = ModelProvider.Mock,  // Using Mock until Anthropic integration
                    IsActive = true
                },
                new Agent
                {
                    Id = AgentGrokId,
                    Name = "Grok",
                    Strategy = "Aggressive trend following",
                    Instructions = "You are an aggressive trader. Follow trends and capitalize on momentum, but respect position limits.",
                    ModelProvider = ModelProvider.Mock,  // Using Mock until xAI integration
                    IsActive = true
                });

            modelBuilder.Entity<MarketCandle>().HasData(
                new MarketCandle
                {
                    Id = CandleBtcSeedId,
                    MarketAssetId = BtcId,
                    TimestampUtc = new DateTimeOffset(2024, 1, 1, 0, 0, 0, TimeSpan.Zero),
                    Open = 47000m,
                    High = 47500m,
                    Low = 46500m,
                    Close = 47200m,
                    Volume = 1_250m
                },
                new MarketCandle
                {
                    Id = CandleEthSeedId,
                    MarketAssetId = EthId,
                    TimestampUtc = new DateTimeOffset(2024, 1, 1, 0, 0, 0, TimeSpan.Zero),
                    Open = 3200m,
                    High = 3250m,
                    Low = 3150m,
                    Close = 3235m,
                    Volume = 8_500m
                });
        }
    }
}

