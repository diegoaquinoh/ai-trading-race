using AiTradingRace.Domain.Entities.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace AiTradingRace.Infrastructure.Database.FixedIncome;

/// <summary>
/// EF Core mapping for the application-owned fixed income tables (spec 14.7).
/// Every table lives in SQL schema <c>fi</c>; legacy crypto tables are untouched.
/// Unique constraints enforce one financial effect per economic event.
/// </summary>
public static class FixedIncomeModelConfiguration
{
    public const string Schema = "fi";

    // Column types. Ledger money is posted in cents; analytics keep more precision.
    internal const string MoneyCents = "decimal(19,2)";
    internal const string FaceAmount = "decimal(19,2)";
    internal const string AnalyticUsd = "decimal(28,8)";
    internal const string PricePer100 = "decimal(28,12)";
    internal const string Ratio = "decimal(28,12)";

    private const int IdLength = 160;
    private const int HashLength = 80;
    private const int SignatureLength = 100;
    private const int CodeLength = 64;
    private const int ReasonLength = 2000;

    public static void Apply(ModelBuilder modelBuilder)
    {
        ConfigureExperimentDefinitions(modelBuilder.Entity<ExperimentDefinition>());
        ConfigureExperimentRuns(modelBuilder.Entity<ExperimentRun>());
        ConfigureStrategyInstances(modelBuilder.Entity<StrategyInstance>());
        ConfigureCycles(modelBuilder.Entity<Cycle>());
        ConfigurePortfolios(modelBuilder.Entity<FiPortfolio>());
        ConfigureStateVersions(modelBuilder.Entity<PortfolioStateVersion>());
        ConfigurePortfolioEvents(modelBuilder.Entity<PortfolioEvent>());
        ConfigureOrderIntents(modelBuilder.Entity<OrderIntent>());
        ConfigureFills(modelBuilder.Entity<Fill>());
        ConfigureSettlements(modelBuilder.Entity<Settlement>());
        ConfigureJournals(modelBuilder.Entity<Journal>());
        ConfigureJournalEntries(modelBuilder.Entity<JournalEntry>());
        ConfigureCashFlows(modelBuilder.Entity<CashFlowEvent>());
        ConfigureValuations(modelBuilder.Entity<ValuationSnapshot>());
        ConfigureDecisions(modelBuilder.Entity<Decision>());
        ConfigureDecisionAttempts(modelBuilder.Entity<DecisionAttempt>());
        ConfigurePolicyEvaluations(modelBuilder.Entity<PolicyEvaluation>());
        ConfigureToolTraces(modelBuilder.Entity<ToolTrace>());
        ConfigureUsageRecords(modelBuilder.Entity<UsageRecord>());
        ConfigureCommandRecords(modelBuilder.Entity<CommandRecord>());
    }

    private static void ConfigureExperimentDefinitions(EntityTypeBuilder<ExperimentDefinition> b)
    {
        b.ToTable("ExperimentDefinitions", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.ExperimentId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.Name).IsRequired().HasMaxLength(200);
        b.Property(x => x.Description).HasMaxLength(4000);
        b.Property(x => x.DataMode).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.RiskPolicyId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.ExecutionModelId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.InstrumentUniverseVersion).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.DefinitionJson).IsRequired();
        b.Property(x => x.DefinitionHash).IsRequired().HasMaxLength(HashLength);
        b.Property(x => x.CreatedBy).HasMaxLength(256);
        b.HasIndex(x => new { x.ExperimentId, x.Version }).IsUnique();
        b.ToTable(t => t.HasCheckConstraint("CK_FiExperimentDefinition_Version", "[Version] >= 1"));
    }

    private static void ConfigureExperimentRuns(EntityTypeBuilder<ExperimentRun> b)
    {
        b.ToTable("ExperimentRuns", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.RunId).IsRequired().HasMaxLength(IdLength);
        b.HasAlternateKey(x => x.RunId);
        b.Property(x => x.ExperimentId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.RunType).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.ResponseMode).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.DataMode).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.RiskPolicyId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.ExecutionModelId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.JobState).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.StatusReason).HasMaxLength(ReasonLength);
        b.Property(x => x.ManifestJson).IsRequired();
        b.Property(x => x.ManifestHash).IsRequired().HasMaxLength(HashLength);
        b.Property(x => x.RequestHash).IsRequired().HasMaxLength(HashLength);
        b.Property(x => x.EngineVersion).HasMaxLength(CodeLength);
        b.Property(x => x.RequestedBy).HasMaxLength(256);
        b.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        b.HasIndex(x => new { x.ExperimentId, x.ExperimentVersion });
        b.HasIndex(x => x.JobState);
        b.HasOne(x => x.ExperimentDefinition)
            .WithMany()
            .HasForeignKey(x => x.ExperimentDefinitionId)
            .OnDelete(DeleteBehavior.Restrict);
        b.HasMany(x => x.Strategies)
            .WithOne()
            .HasForeignKey(x => x.RunId)
            .HasPrincipalKey(x => x.RunId)
            .OnDelete(DeleteBehavior.Restrict);
        b.ToTable(t =>
        {
            t.HasCheckConstraint("CK_FiExperimentRun_JobState",
                "[JobState] IN ('queued','running','completed','failed','cancelled')");
            t.HasCheckConstraint("CK_FiExperimentRun_RunType", "[RunType] IN ('replay','forward')");
            t.HasCheckConstraint("CK_FiExperimentRun_ResponseMode",
                "[ResponseMode] IN ('recorded_replay','fresh_inference')");
        });
    }

    private static void ConfigureStrategyInstances(EntityTypeBuilder<StrategyInstance> b)
    {
        b.ToTable("StrategyInstances", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.RunId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.StrategyId).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.StrategyKind).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.StrategyConfigId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.Label).HasMaxLength(200);
        b.HasIndex(x => new { x.RunId, x.StrategyId, x.Repetition }).IsUnique();
        b.HasIndex(x => x.PortfolioId).IsUnique();
    }

    private static void ConfigureCycles(EntityTypeBuilder<Cycle> b)
    {
        b.ToTable("Cycles", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.RunId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.CycleId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.Status).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.SkipReason).HasMaxLength(ReasonLength);
        b.Property(x => x.MarketSnapshotId).HasMaxLength(IdLength);
        b.Property(x => x.MarketSnapshotHash).HasMaxLength(HashLength);
        b.Property(x => x.CurveSnapshotId).HasMaxLength(IdLength);
        b.HasIndex(x => new { x.RunId, x.CycleId }).IsUnique();
        b.HasIndex(x => new { x.RunId, x.Sequence }).IsUnique();
        b.HasOne<ExperimentRun>()
            .WithMany()
            .HasForeignKey(x => x.RunId)
            .HasPrincipalKey(x => x.RunId)
            .OnDelete(DeleteBehavior.Restrict);
    }

    private static void ConfigurePortfolios(EntityTypeBuilder<FiPortfolio> b)
    {
        b.ToTable("Portfolios", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.HasAlternateKey(x => x.PortfolioId);
        b.Property(x => x.RunId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.StrategyId).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.RiskPolicyId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.DataMode).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.CurrentStateHash).IsRequired().HasMaxLength(HashLength);
        b.Property(x => x.BlockedReason).HasMaxLength(ReasonLength);
        b.Property(x => x.BlockedByCommandId).HasMaxLength(IdLength);
        b.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        b.HasIndex(x => new { x.RunId, x.StrategyId, x.Repetition }).IsUnique();
        b.ToTable(t => t.HasCheckConstraint("CK_FiPortfolio_Version", "[CurrentVersion] >= 0"));
    }

    private static void ConfigureStateVersions(EntityTypeBuilder<PortfolioStateVersion> b)
    {
        b.ToTable("PortfolioStateVersions", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.StateJson).IsRequired();
        b.Property(x => x.StateHash).IsRequired().HasMaxLength(HashLength);
        b.Property(x => x.CommandId).HasMaxLength(IdLength);
        b.Property(x => x.ProposalHash).HasMaxLength(HashLength);
        b.HasIndex(x => new { x.PortfolioId, x.Version }).IsUnique();
        PortfolioChild(b, x => x.PortfolioId);
    }

    private static void ConfigurePortfolioEvents(EntityTypeBuilder<PortfolioEvent> b)
    {
        b.ToTable("PortfolioEvents", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.EventId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.EventType).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.CommandId).IsRequired().HasMaxLength(IdLength);
        b.HasIndex(x => new { x.PortfolioId, x.EventId }).IsUnique();
        b.HasIndex(x => new { x.PortfolioId, x.CommittedVersion });
        PortfolioChild(b, x => x.PortfolioId);
    }

    private static void ConfigureOrderIntents(EntityTypeBuilder<OrderIntent> b)
    {
        b.ToTable("OrderIntents", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.OrderId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.DecisionId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.SecurityId).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Side).IsRequired().HasMaxLength(8);
        b.Property(x => x.Face).HasColumnType(FaceAmount);
        b.Property(x => x.Status).IsRequired().HasMaxLength(16);
        b.Property(x => x.StatusReason).HasMaxLength(ReasonLength);
        b.Property(x => x.ReservedCashUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.OrderJson).IsRequired();
        b.HasIndex(x => new { x.PortfolioId, x.OrderId }).IsUnique();
        b.HasIndex(x => x.DecisionId);
        b.HasIndex(x => new { x.PortfolioId, x.Status });
        PortfolioChild(b, x => x.PortfolioId);
        b.ToTable(t =>
        {
            t.HasCheckConstraint("CK_FiOrderIntent_Side", "[Side] IN ('BUY','SELL')");
            t.HasCheckConstraint("CK_FiOrderIntent_Status",
                "[Status] IN ('ACCEPTED','FILLED','EXPIRED','CANCELLED','REJECTED')");
        });
    }

    private static void ConfigureFills(EntityTypeBuilder<Fill> b)
    {
        b.ToTable("Fills", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.FillId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.OrderId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.SecurityId).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Side).IsRequired().HasMaxLength(8);
        b.Property(x => x.Face).HasColumnType(FaceAmount);
        b.Property(x => x.ObservationId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.QuoteKind).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.ReferenceCleanPricePer100).HasColumnType(PricePer100);
        b.Property(x => x.ExecutionCleanPricePer100).HasColumnType(PricePer100);
        b.Property(x => x.AccruedPer100).HasColumnType(PricePer100);
        b.Property(x => x.DirtyPricePer100).HasColumnType(PricePer100);
        b.Property(x => x.HalfSpreadPer100).HasColumnType(PricePer100);
        b.Property(x => x.ConsiderationUsd).HasColumnType(MoneyCents);
        b.Property(x => x.FeesUsd).HasColumnType(MoneyCents);
        b.Property(x => x.SpreadCostUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.TimingLabel).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.FillJson).IsRequired();
        b.HasIndex(x => new { x.PortfolioId, x.FillId }).IsUnique();
        // One fill per order.
        b.HasIndex(x => new { x.PortfolioId, x.OrderId }).IsUnique();
        PortfolioChild(b, x => x.PortfolioId);
    }

    private static void ConfigureSettlements(EntityTypeBuilder<Settlement> b)
    {
        b.ToTable("Settlements", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.SettlementId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.FillId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.SecurityId).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Side).IsRequired().HasMaxLength(8);
        b.Property(x => x.Face).HasColumnType(FaceAmount);
        b.Property(x => x.CashUsd).HasColumnType(MoneyCents);
        b.Property(x => x.Status).IsRequired().HasMaxLength(16);
        b.Property(x => x.SettlementJson).IsRequired();
        b.HasIndex(x => new { x.PortfolioId, x.SettlementId }).IsUnique();
        // One settlement per fill.
        b.HasIndex(x => new { x.PortfolioId, x.FillId }).IsUnique();
        PortfolioChild(b, x => x.PortfolioId);
    }

    private static void ConfigureJournals(EntityTypeBuilder<Journal> b)
    {
        b.ToTable("Journals", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.JournalId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.EventId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.EventType).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Template).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.CommandId).IsRequired().HasMaxLength(IdLength);
        b.HasIndex(x => new { x.PortfolioId, x.JournalId }).IsUnique();
        b.HasIndex(x => new { x.PortfolioId, x.EventId });
        b.HasMany(x => x.Entries)
            .WithOne(x => x.Journal)
            .HasForeignKey(x => x.JournalDbId)
            .OnDelete(DeleteBehavior.Restrict);
        PortfolioChild(b, x => x.PortfolioId);
    }

    private static void ConfigureJournalEntries(EntityTypeBuilder<JournalEntry> b)
    {
        b.ToTable("JournalEntries", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.LineId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.Account).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.SecurityId).HasMaxLength(CodeLength);
        b.Property(x => x.DebitUsd).HasColumnType(MoneyCents);
        b.Property(x => x.CreditUsd).HasColumnType(MoneyCents);
        b.Property(x => x.Memo).HasMaxLength(500);
        b.HasIndex(x => new { x.JournalDbId, x.LineId }).IsUnique();
        b.HasIndex(x => new { x.PortfolioId, x.Account });
        b.ToTable(t => t.HasCheckConstraint("CK_FiJournalEntry_NonNegative",
            "[DebitUsd] >= 0 AND [CreditUsd] >= 0"));
    }

    private static void ConfigureCashFlows(EntityTypeBuilder<CashFlowEvent> b)
    {
        b.ToTable("CashFlowEvents", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.CashFlowId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.SecurityId).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Kind).IsRequired().HasMaxLength(16);
        b.Property(x => x.EntitledFace).HasColumnType(FaceAmount);
        b.Property(x => x.AmountUsd).HasColumnType(MoneyCents);
        b.HasIndex(x => new { x.PortfolioId, x.CashFlowId }).IsUnique();
        PortfolioChild(b, x => x.PortfolioId);
    }

    private static void ConfigureValuations(EntityTypeBuilder<ValuationSnapshot> b)
    {
        b.ToTable("ValuationSnapshots", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.ValuationId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.DataMode).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.CurveSnapshotId).HasMaxLength(IdLength);
        b.Property(x => x.MarkPolicy).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.IncompleteReasonsJson).IsRequired();
        b.Property(x => x.CashUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.BondValueUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.ReceivablesPvUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.PayablesPvUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.EquityUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.ParallelDv01Usd).HasColumnType(AnalyticUsd);
        b.Property(x => x.EffectiveDurationYears).HasColumnType(Ratio);
        b.Property(x => x.ValuationJson).IsRequired();
        b.HasIndex(x => new { x.PortfolioId, x.ValuationId }).IsUnique();
        PortfolioChild(b, x => x.PortfolioId);
    }

    private static void ConfigureDecisions(EntityTypeBuilder<Decision> b)
    {
        b.ToTable("Decisions", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.DecisionId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.RunId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.CycleId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.StrategyId).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.StrategyKind).HasMaxLength(CodeLength);
        b.Property(x => x.PortfolioId).HasMaxLength(IdLength);
        b.Property(x => x.Outcome).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Action).HasMaxLength(16);
        b.Property(x => x.ReasonsJson).IsRequired();
        b.Property(x => x.ValidationJson).IsRequired();
        b.Property(x => x.SpecialistTasksJson).IsRequired();
        b.Property(x => x.EvidenceBundleIdsJson).IsRequired();
        b.Property(x => x.InputHashesJson).IsRequired();
        b.Property(x => x.RequestHash).HasMaxLength(HashLength);
        b.Property(x => x.ResultHash).HasMaxLength(HashLength);
        b.Property(x => x.Signature).HasMaxLength(SignatureLength);
        b.Property(x => x.Integrity).IsRequired().HasMaxLength(32);
        b.Property(x => x.EngineVersion).HasMaxLength(CodeLength);
        b.Property(x => x.Provider).HasMaxLength(CodeLength);
        b.Property(x => x.Model).HasMaxLength(128);
        b.HasIndex(x => x.DecisionId).IsUnique();
        // Logical decision identity (spec 14.6): run + cycle + strategy + repetition.
        b.HasIndex(x => new { x.RunId, x.CycleId, x.StrategyId, x.Repetition }).IsUnique();
        b.HasIndex(x => new { x.RunId, x.Outcome });
        b.HasMany(x => x.Attempts).WithOne().HasForeignKey(x => x.DecisionDbId).OnDelete(DeleteBehavior.Restrict);
        b.HasMany(x => x.ToolTraces).WithOne().HasForeignKey(x => x.DecisionDbId).OnDelete(DeleteBehavior.Restrict);
        b.HasMany(x => x.PolicyEvaluations).WithOne().HasForeignKey(x => x.DecisionDbId).OnDelete(DeleteBehavior.Restrict);
        b.HasOne(x => x.Usage).WithOne().HasForeignKey<UsageRecord>(x => x.DecisionDbId).OnDelete(DeleteBehavior.Restrict);
    }

    private static void ConfigureDecisionAttempts(EntityTypeBuilder<DecisionAttempt> b)
    {
        b.ToTable("DecisionAttempts", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.AttemptId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.AgentRole).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Purpose).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Provider).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Model).IsRequired().HasMaxLength(128);
        b.Property(x => x.Status).IsRequired().HasMaxLength(32);
        b.Property(x => x.RecordedResponseId).HasMaxLength(IdLength);
        b.Property(x => x.Error).HasMaxLength(ReasonLength);
        b.HasIndex(x => new { x.DecisionDbId, x.AttemptId }).IsUnique();
    }

    private static void ConfigurePolicyEvaluations(EntityTypeBuilder<PolicyEvaluation> b)
    {
        b.ToTable("PolicyEvaluations", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.DecisionId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.PortfolioId).HasMaxLength(IdLength);
        b.Property(x => x.CommandId).HasMaxLength(IdLength);
        b.Property(x => x.Source).IsRequired().HasMaxLength(32);
        b.Property(x => x.PolicyId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.Action).IsRequired().HasMaxLength(16);
        b.Property(x => x.PostTradeNavUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.PostTradeCashRatio).HasColumnType(Ratio);
        b.Property(x => x.PostTradeMaxSecurityRatio).HasColumnType(Ratio);
        b.Property(x => x.PostTradeParallelDv01Usd).HasColumnType(AnalyticUsd);
        b.Property(x => x.TurnoverRatio).HasColumnType(Ratio);
        b.Property(x => x.RejectedReasonsJson).IsRequired();
        b.Property(x => x.PlatformRecheckReasonsJson).IsRequired();
        b.Property(x => x.EvaluationJson).IsRequired();
        b.HasIndex(x => x.DecisionId);
        b.HasIndex(x => x.CommandId);
    }

    private static void ConfigureToolTraces(EntityTypeBuilder<ToolTrace> b)
    {
        b.ToTable("ToolTraces", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.TraceId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.AgentRole).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.ToolName).IsRequired().HasMaxLength(128);
        b.Property(x => x.RequestJson).IsRequired();
        b.Property(x => x.ResponseSummaryJson).IsRequired();
        b.Property(x => x.OutputRef).HasMaxLength(IdLength);
        b.Property(x => x.Status).IsRequired().HasMaxLength(32);
        b.Property(x => x.Error).HasMaxLength(ReasonLength);
        b.HasIndex(x => new { x.DecisionDbId, x.TraceId }).IsUnique();
    }

    private static void ConfigureUsageRecords(EntityTypeBuilder<UsageRecord> b)
    {
        b.ToTable("UsageRecords", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.EstimatedCostUsd).HasColumnType(AnalyticUsd);
        b.Property(x => x.PriceScheduleId).HasMaxLength(IdLength);
        b.Property(x => x.BudgetExhausted).HasMaxLength(CodeLength);
        b.HasIndex(x => x.DecisionDbId).IsUnique();
    }

    private static void ConfigureCommandRecords(EntityTypeBuilder<CommandRecord> b)
    {
        b.ToTable("CommandRecords", Schema);
        b.HasKey(x => x.Id);
        b.Property(x => x.CommandId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.CommandType).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.PortfolioId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.RequestHash).IsRequired().HasMaxLength(HashLength);
        b.Property(x => x.ProposalHash).IsRequired().HasMaxLength(HashLength);
        b.Property(x => x.ProposalId).IsRequired().HasMaxLength(IdLength);
        b.Property(x => x.EngineVersion).IsRequired().HasMaxLength(CodeLength);
        b.Property(x => x.Status).IsRequired().HasMaxLength(32);
        b.Property(x => x.Reason).HasMaxLength(ReasonLength);
        b.Property(x => x.ResultJson).IsRequired();
        b.HasIndex(x => x.CommandId).IsUnique();
        b.HasIndex(x => x.PortfolioId);
    }

    private static void PortfolioChild<T>(EntityTypeBuilder<T> b, System.Linq.Expressions.Expression<Func<T, object?>> fk)
        where T : class
    {
        b.HasOne<FiPortfolio>()
            .WithMany()
            .HasForeignKey(fk!)
            .HasPrincipalKey(p => p.PortfolioId)
            .OnDelete(DeleteBehavior.Restrict);
    }
}
