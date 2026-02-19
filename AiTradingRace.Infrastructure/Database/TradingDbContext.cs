using AiTradingRace.Domain.Entities;
using AiTradingRace.Domain.Entities.Knowledge;
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
    
    // Authentication entities
    public DbSet<User> Users => Set<User>();
    public DbSet<ApiKey> ApiKeys => Set<ApiKey>();
    
    // Phase 10: Knowledge Graph & Decision Logs
    public DbSet<RuleNode> RuleNodes => Set<RuleNode>();
    public DbSet<RegimeNode> RegimeNodes => Set<RegimeNode>();
    public DbSet<RuleEdge> RuleEdges => Set<RuleEdge>();
    public DbSet<DecisionLog> DecisionLogs => Set<DecisionLog>();
    public DbSet<DetectedRegime> DetectedRegimes => Set<DetectedRegime>();

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
        ConfigureUsers(modelBuilder);
        ConfigureApiKeys(modelBuilder);
        
        // Phase 10: Knowledge Graph
        ConfigureRuleNodes(modelBuilder);
        ConfigureRegimeNodes(modelBuilder);
        ConfigureRuleEdges(modelBuilder);
        ConfigureDecisionLogs(modelBuilder);
        ConfigureDetectedRegimes(modelBuilder);
        
        SeedData.Configure(modelBuilder);
    }

    private static void ConfigureAgents(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Agent>(builder =>
        {
            builder.ToTable("Agents");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasDefaultValueSql("NEWID()");
            builder.Property(x => x.Name).IsRequired().HasMaxLength(128);
            builder.Property(x => x.Strategy).HasMaxLength(512);
            builder.Property(x => x.Instructions).HasMaxLength(4000);
            builder.Property(x => x.ModelProvider)
                .HasConversion<string>()
                .HasMaxLength(32)
                .IsRequired();
            builder.Property(x => x.DeploymentKey).HasMaxLength(64);
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
            builder.Property(x => x.Id).HasDefaultValueSql("NEWID()");

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

    private static void ConfigureUsers(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<User>(builder =>
        {
            builder.ToTable("Users");
            builder.HasKey(x => x.Id);
            
            builder.Property(x => x.Email)
                .IsRequired()
                .HasMaxLength(256);
            
            builder.HasIndex(x => x.Email).IsUnique();
            
            builder.Property(x => x.Name)
                .IsRequired()
                .HasMaxLength(100);
            
            builder.Property(x => x.Role)
                .HasConversion<int>();
            
            builder.Property(x => x.ExternalId)
                .HasMaxLength(256);
            
            builder.HasIndex(x => x.ExternalId);
            
            builder.Property(x => x.CreatedAt)
                .HasDefaultValueSql("SYSUTCDATETIME()");
            
            builder.HasMany(x => x.ApiKeys)
                .WithOne(k => k.User)
                .HasForeignKey(k => k.UserId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }

    private static void ConfigureApiKeys(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<ApiKey>(builder =>
        {
            builder.ToTable("ApiKeys");
            builder.HasKey(x => x.Id);
            
            builder.Property(x => x.KeyHash)
                .IsRequired()
                .HasMaxLength(256);
            
            builder.Property(x => x.KeyPrefix)
                .IsRequired()
                .HasMaxLength(8);
            
            builder.HasIndex(x => x.KeyPrefix);
            
            builder.Property(x => x.Name)
                .IsRequired()
                .HasMaxLength(100);
            
            builder.Property(x => x.Scopes)
                .HasMaxLength(500);
            
            builder.Property(x => x.CreatedAt)
                .HasDefaultValueSql("SYSUTCDATETIME()");
        });
    }

    private static class SeedData
    {
        private static readonly Guid BtcId = Guid.Parse("c3d4b060-55bb-4e48-8f04-3452ec0c9d4c");
        private static readonly Guid EthId = Guid.Parse("b1fa9f8a-626b-4253-9a5d-0c9c9fb5c9fd");

        private static readonly Guid AgentGptId = Guid.Parse("11111111-1111-1111-1111-111111111111");
        private static readonly Guid AgentClaudeId = Guid.Parse("22222222-2222-2222-2222-222222222222");
        private static readonly Guid AgentGrokId = Guid.Parse("33333333-3333-3333-3333-333333333333");
        private static readonly Guid AgentCustomMlId = Guid.Parse("44444444-0000-4444-0000-444444444444");
        private static readonly Guid AgentGpt4oId = Guid.Parse("55555555-0000-5555-0000-555555555555");
        private static readonly Guid AgentGpt41NanoId = Guid.Parse("66666666-0000-6666-0000-666666666666");

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
                    IsActive = false  // TODO: Re-enable once Groq/Together.ai API key is configured
                },
                new Agent
                {
                    Id = AgentClaudeId,
                    Name = "Claude",
                    Strategy = "Value-oriented with technical analysis",
                    Instructions = "You are a value investor. Look for undervalued opportunities and use technical indicators for timing.",
                    ModelProvider = ModelProvider.Mock,  // Using Mock until Anthropic integration
                    IsActive = false  // TODO: Re-enable once Anthropic API key is configured
                },
                new Agent
                {
                    Id = AgentGrokId,
                    Name = "Grok",
                    Strategy = "Aggressive trend following",
                    Instructions = "You are an aggressive trader. Follow trends and capitalize on momentum, but respect position limits.",
                    ModelProvider = ModelProvider.Mock,  // Using Mock until xAI integration
                    IsActive = false  // TODO: Re-enable once xAI API key is configured
                },
                new Agent
                {
                    Id = AgentCustomMlId,
                    Name = "Custom ML",
                    Strategy = "Technical indicator-driven ML model with RSI, MACD, and Bollinger signals",
                    Instructions = "ML model using technical indicators for trading decisions with explainability signals.",
                    ModelProvider = ModelProvider.CustomML,
                    IsActive = true
                },
                new Agent
                {
                    Id = AgentGpt4oId,
                    Name = "GPT-4o-mini",
                    Strategy = "Multi-factor analysis with sentiment and on-chain data",
                    Instructions = "You are a balanced trader. Combine fundamental analysis, market sentiment, and technical indicators to make well-rounded trading decisions.",
                    ModelProvider = ModelProvider.AzureOpenAI,
                    DeploymentKey = "GPT4oMini",
                    IsActive = true
                },
                new Agent
                {
                    Id = AgentGpt41NanoId,
                    Name = "GPT-4.1-nano",
                    Strategy = "Fast, cost-efficient trading with technical signal focus",
                    Instructions = "You are a fast-acting trader. Use technical indicators to make quick, data-driven trading decisions. Favor clear signals over complex analysis.",
                    ModelProvider = ModelProvider.AzureOpenAI,
                    DeploymentKey = "GPT41Nano",
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
            
            // Phase 10: Seed Knowledge Graph data
            var now = DateTime.UtcNow;
            
            modelBuilder.Entity<RuleNode>().HasData(
                new RuleNode
                {
                    Id = "R001",
                    Name = "MaxPositionSize",
                    Description = "No single position should exceed 50% of total portfolio value",
                    Category = RuleCategory.RiskManagement,
                    Severity = RuleSeverity.High,
                    Threshold = 0.5m,
                    Unit = "percentage",
                    IsActive = true,
                    CreatedAt = now
                },
                new RuleNode
                {
                    Id = "R002",
                    Name = "MinCashReserve",
                    Description = "Maintain minimum $100 cash buffer for trading costs",
                    Category = RuleCategory.Liquidity,
                    Severity = RuleSeverity.Medium,
                    Threshold = 100.0m,
                    Unit = "dollars",
                    IsActive = true,
                    CreatedAt = now
                },
                new RuleNode
                {
                    Id = "R003",
                    Name = "VolatilityStop",
                    Description = "Reduce exposure when daily volatility exceeds 5%",
                    Category = RuleCategory.RiskManagement,
                    Severity = RuleSeverity.High,
                    Threshold = 0.05m,
                    Unit = "percentage",
                    IsActive = true,
                    CreatedAt = now
                },
                new RuleNode
                {
                    Id = "R004",
                    Name = "MaxDrawdown",
                    Description = "Exit all positions if portfolio drops 20% from peak",
                    Category = RuleCategory.StopLoss,
                    Severity = RuleSeverity.Critical,
                    Threshold = 0.2m,
                    Unit = "percentage",
                    IsActive = true,
                    CreatedAt = now
                },
                new RuleNode
                {
                    Id = "R005",
                    Name = "DiversificationRule",
                    Description = "Hold at least 2 different assets when invested",
                    Category = RuleCategory.PositionSizing,
                    Severity = RuleSeverity.Medium,
                    Threshold = 2.0m,
                    Unit = "count",
                    IsActive = true,
                    CreatedAt = now
                });
            
            modelBuilder.Entity<RegimeNode>().HasData(
                new RegimeNode
                {
                    Id = "VOLATILE",
                    Name = "Volatile Market",
                    Description = "Daily volatility > 5%",
                    Condition = "volatility_7d > 0.05",
                    LookbackDays = 7,
                    CreatedAt = now
                },
                new RegimeNode
                {
                    Id = "BULLISH",
                    Name = "Bullish Trend",
                    Description = "7-day MA > 30-day MA",
                    Condition = "ma_7d > ma_30d",
                    LookbackDays = 30,
                    CreatedAt = now
                },
                new RegimeNode
                {
                    Id = "BEARISH",
                    Name = "Bearish Trend",
                    Description = "7-day MA < 30-day MA",
                    Condition = "ma_7d < ma_30d",
                    LookbackDays = 30,
                    CreatedAt = now
                },
                new RegimeNode
                {
                    Id = "STABLE",
                    Name = "Stable Market",
                    Description = "Daily volatility < 2%",
                    Condition = "volatility_7d < 0.02",
                    LookbackDays = 7,
                    CreatedAt = now
                });
            
            modelBuilder.Entity<RuleEdge>().HasData(
                // Volatile regime activates volatility stop
                new RuleEdge
                {
                    Id = 1,
                    SourceNodeId = "VOLATILE",
                    TargetNodeId = "R003",
                    Type = EdgeType.Activates,
                    CreatedAt = now
                },
                // Volatile regime increases cash reserve requirement
                new RuleEdge
                {
                    Id = 2,
                    SourceNodeId = "VOLATILE",
                    TargetNodeId = "R002",
                    Type = EdgeType.Tightens,
                    Parameters = "{\"threshold\": 200.0}",
                    CreatedAt = now
                },
                // Bullish regime relaxes max position size
                new RuleEdge
                {
                    Id = 3,
                    SourceNodeId = "BULLISH",
                    TargetNodeId = "R001",
                    Type = EdgeType.Relaxes,
                    Parameters = "{\"threshold\": 0.6}",
                    CreatedAt = now
                },
                // Bearish regime tightens max position size
                new RuleEdge
                {
                    Id = 4,
                    SourceNodeId = "BEARISH",
                    TargetNodeId = "R001",
                    Type = EdgeType.Tightens,
                    Parameters = "{\"threshold\": 0.3}",
                    CreatedAt = now
                },
                // Assets subject to position sizing
                new RuleEdge
                {
                    Id = 5,
                    SourceNodeId = "Asset:BTC",
                    TargetNodeId = "R001",
                    Type = EdgeType.SubjectTo,
                    CreatedAt = now
                },
                new RuleEdge
                {
                    Id = 6,
                    SourceNodeId = "Asset:ETH",
                    TargetNodeId = "R001",
                    Type = EdgeType.SubjectTo,
                    CreatedAt = now
                });
        }
    }
    
    // Phase 10: Knowledge Graph configurations
    private static void ConfigureRuleNodes(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<RuleNode>(builder =>
        {
            builder.ToTable("RuleNodes");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasMaxLength(50);
            builder.Property(x => x.Name).IsRequired().HasMaxLength(200);
            builder.Property(x => x.Description).IsRequired().HasMaxLength(1000);
            builder.Property(x => x.Category).HasConversion<int>();
            builder.Property(x => x.Severity).HasConversion<int>();
            builder.Property(x => x.Threshold).HasColumnType("decimal(18,8)");
            builder.Property(x => x.Unit).HasMaxLength(50);
            builder.Property(x => x.IsActive).HasDefaultValue(true);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("SYSUTCDATETIME()");
        });
    }
    
    private static void ConfigureRegimeNodes(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<RegimeNode>(builder =>
        {
            builder.ToTable("RegimeNodes");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Id).HasMaxLength(50);
            builder.Property(x => x.Name).IsRequired().HasMaxLength(200);
            builder.Property(x => x.Description).IsRequired().HasMaxLength(1000);
            builder.Property(x => x.Condition).IsRequired().HasMaxLength(500);
            builder.Property(x => x.LookbackDays).IsRequired();
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("SYSUTCDATETIME()");
        });
    }
    
    private static void ConfigureRuleEdges(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<RuleEdge>(builder =>
        {
            builder.ToTable("RuleEdges");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.SourceNodeId).IsRequired().HasMaxLength(50);
            builder.Property(x => x.TargetNodeId).IsRequired().HasMaxLength(50);
            builder.Property(x => x.Type).HasConversion<int>();
            builder.Property(x => x.Parameters).HasMaxLength(4000);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("SYSUTCDATETIME()");
            
            builder.HasIndex(x => x.SourceNodeId);
            builder.HasIndex(x => x.TargetNodeId);
        });
    }
    
    private static void ConfigureDecisionLogs(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<DecisionLog>(builder =>
        {
            builder.ToTable("DecisionLogs");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.Action).IsRequired().HasMaxLength(20);
            builder.Property(x => x.Asset).HasMaxLength(20);
            builder.Property(x => x.Quantity).HasColumnType("decimal(18,8)");
            builder.Property(x => x.Rationale).IsRequired();
            builder.Property(x => x.CitedRuleIds).IsRequired().HasMaxLength(500);
            builder.Property(x => x.DetectedRegime).IsRequired().HasMaxLength(50);
            builder.Property(x => x.SubgraphSnapshot).IsRequired();
            builder.Property(x => x.PortfolioValueBefore).HasColumnType("decimal(18,2)");
            builder.Property(x => x.PortfolioValueAfter).HasColumnType("decimal(18,2)");
            builder.Property(x => x.MarketConditions).IsRequired();
            builder.Property(x => x.WasValidated).HasDefaultValue(true);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("SYSUTCDATETIME()");
            
            builder.HasIndex(x => new { x.AgentId, x.Timestamp }).HasDatabaseName("IX_DecisionLogs_AgentId_Timestamp");
            builder.HasIndex(x => x.DetectedRegime).HasDatabaseName("IX_DecisionLogs_DetectedRegime");
            
            builder.HasOne(x => x.Agent)
                .WithMany()
                .HasForeignKey(x => x.AgentId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }
    
    private static void ConfigureDetectedRegimes(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<DetectedRegime>(builder =>
        {
            builder.ToTable("DetectedRegimes");
            builder.HasKey(x => x.Id);
            builder.Property(x => x.RegimeId).IsRequired().HasMaxLength(50);
            builder.Property(x => x.DetectedAt).IsRequired();
            builder.Property(x => x.Volatility).HasColumnType("decimal(18,8)");
            builder.Property(x => x.MA7).HasColumnType("decimal(18,2)");
            builder.Property(x => x.MA30).HasColumnType("decimal(18,2)");
            builder.Property(x => x.Asset).IsRequired().HasMaxLength(20);
            builder.Property(x => x.CreatedAt).HasDefaultValueSql("SYSUTCDATETIME()");
            
            builder.HasIndex(x => new { x.Asset, x.DetectedAt }).HasDatabaseName("IX_DetectedRegimes_Asset_DetectedAt");
        });
    }
}


