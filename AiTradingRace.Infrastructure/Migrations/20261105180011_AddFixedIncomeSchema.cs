using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddFixedIncomeSchema : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.EnsureSchema(
                name: "fi");

            migrationBuilder.CreateTable(
                name: "CommandRecords",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    CommandId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    CommandType = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    RequestHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    ProposalHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    ProposalId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    EngineVersion = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    ExpectedVersion = table.Column<long>(type: "bigint", nullable: false),
                    CommittedVersion = table.Column<long>(type: "bigint", nullable: true),
                    Status = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    Reason = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true),
                    ResultJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CommandRecords", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Decisions",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DecisionId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    RunId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    CycleId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    StrategyId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Repetition = table.Column<int>(type: "int", nullable: false),
                    StrategyKind = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: true),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    Outcome = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Action = table.Column<string>(type: "nvarchar(16)", maxLength: 16, nullable: true),
                    CompletedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    ReasonsJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    ProposalJson = table.Column<string>(type: "nvarchar(max)", nullable: true),
                    ResearchNoteJson = table.Column<string>(type: "nvarchar(max)", nullable: true),
                    ValidationJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    SpecialistTasksJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    VersionsJson = table.Column<string>(type: "nvarchar(max)", nullable: true),
                    EvidenceBundleIdsJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    RequestHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: true),
                    InputHashesJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    ResultHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: true),
                    Signature = table.Column<string>(type: "nvarchar(100)", maxLength: 100, nullable: true),
                    Integrity = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    EngineVersion = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: true),
                    Provider = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: true),
                    Model = table.Column<string>(type: "nvarchar(128)", maxLength: 128, nullable: true),
                    ResultJson = table.Column<string>(type: "nvarchar(max)", nullable: true),
                    RecordedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Decisions", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "ExperimentDefinitions",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    ExperimentId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    Version = table.Column<int>(type: "int", nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(4000)", maxLength: 4000, nullable: true),
                    DataMode = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    RiskPolicyId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    ExecutionModelId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    InstrumentUniverseVersion = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    StartDate = table.Column<DateOnly>(type: "date", nullable: false),
                    EndDate = table.Column<DateOnly>(type: "date", nullable: false),
                    Repetitions = table.Column<int>(type: "int", nullable: false),
                    DefinitionJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    DefinitionHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    CreatedBy = table.Column<string>(type: "nvarchar(256)", maxLength: 256, nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExperimentDefinitions", x => x.Id);
                    table.CheckConstraint("CK_FiExperimentDefinition_Version", "[Version] >= 1");
                });

            migrationBuilder.CreateTable(
                name: "Portfolios",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    RunId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    StrategyId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Repetition = table.Column<int>(type: "int", nullable: false),
                    RiskPolicyId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    DataMode = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    CurrentVersion = table.Column<long>(type: "bigint", nullable: false),
                    CurrentStateHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    BlockedReason = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true),
                    BlockedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true),
                    BlockedByCommandId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    UpdatedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    ConcurrencyStamp = table.Column<Guid>(type: "uniqueidentifier", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Portfolios", x => x.Id);
                    table.UniqueConstraint("AK_Portfolios_PortfolioId", x => x.PortfolioId);
                    table.CheckConstraint("CK_FiPortfolio_Version", "[CurrentVersion] >= 0");
                });

            migrationBuilder.CreateTable(
                name: "DecisionAttempts",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DecisionDbId = table.Column<long>(type: "bigint", nullable: false),
                    AttemptId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    AttemptNumber = table.Column<int>(type: "int", nullable: false),
                    AgentRole = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Purpose = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Provider = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Model = table.Column<string>(type: "nvarchar(128)", maxLength: 128, nullable: false),
                    InputTokens = table.Column<int>(type: "int", nullable: false),
                    OutputTokens = table.Column<int>(type: "int", nullable: false),
                    StartedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    DurationMs = table.Column<int>(type: "int", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    RecordedResponseId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    Error = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DecisionAttempts", x => x.Id);
                    table.ForeignKey(
                        name: "FK_DecisionAttempts_Decisions_DecisionDbId",
                        column: x => x.DecisionDbId,
                        principalSchema: "fi",
                        principalTable: "Decisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "PolicyEvaluations",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DecisionDbId = table.Column<long>(type: "bigint", nullable: true),
                    DecisionId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    CommandId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    Source = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    PolicyId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    Action = table.Column<string>(type: "nvarchar(16)", maxLength: 16, nullable: false),
                    Passed = table.Column<bool>(type: "bit", nullable: false),
                    BreachMode = table.Column<bool>(type: "bit", nullable: false),
                    BootstrapExemptionApplied = table.Column<bool>(type: "bit", nullable: false),
                    PostTradeNavUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    PostTradeCashRatio = table.Column<decimal>(type: "decimal(28,12)", nullable: true),
                    PostTradeMaxSecurityRatio = table.Column<decimal>(type: "decimal(28,12)", nullable: true),
                    PostTradeParallelDv01Usd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    TurnoverRatio = table.Column<decimal>(type: "decimal(28,12)", nullable: true),
                    OrderCount = table.Column<int>(type: "int", nullable: false),
                    RejectedReasonsJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    PlatformRecheckPassed = table.Column<bool>(type: "bit", nullable: true),
                    PlatformRecheckReasonsJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    EvaluationJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    RecordedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PolicyEvaluations", x => x.Id);
                    table.ForeignKey(
                        name: "FK_PolicyEvaluations_Decisions_DecisionDbId",
                        column: x => x.DecisionDbId,
                        principalSchema: "fi",
                        principalTable: "Decisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "ToolTraces",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DecisionDbId = table.Column<long>(type: "bigint", nullable: false),
                    TraceId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    AgentRole = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    ToolName = table.Column<string>(type: "nvarchar(128)", maxLength: 128, nullable: false),
                    RequestJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    ResponseSummaryJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    OutputRef = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    StartedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    DurationMs = table.Column<int>(type: "int", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    Error = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ToolTraces", x => x.Id);
                    table.ForeignKey(
                        name: "FK_ToolTraces_Decisions_DecisionDbId",
                        column: x => x.DecisionDbId,
                        principalSchema: "fi",
                        principalTable: "Decisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "UsageRecords",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    DecisionDbId = table.Column<long>(type: "bigint", nullable: false),
                    GenerationCalls = table.Column<int>(type: "int", nullable: false),
                    ToolCalls = table.Column<int>(type: "int", nullable: false),
                    EvidenceCalls = table.Column<int>(type: "int", nullable: false),
                    UniqueEvidenceChunks = table.Column<int>(type: "int", nullable: false),
                    EvidenceTokens = table.Column<int>(type: "int", nullable: false),
                    InputTokens = table.Column<int>(type: "int", nullable: false),
                    OutputTokens = table.Column<int>(type: "int", nullable: false),
                    DurationMs = table.Column<int>(type: "int", nullable: false),
                    EstimatedCostUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    PriceScheduleId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    BudgetExhausted = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_UsageRecords", x => x.Id);
                    table.ForeignKey(
                        name: "FK_UsageRecords_Decisions_DecisionDbId",
                        column: x => x.DecisionDbId,
                        principalSchema: "fi",
                        principalTable: "Decisions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "ExperimentRuns",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    RunId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    ExperimentDefinitionId = table.Column<long>(type: "bigint", nullable: false),
                    ExperimentId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    ExperimentVersion = table.Column<int>(type: "int", nullable: false),
                    RunType = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    ResponseMode = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    DataMode = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    RiskPolicyId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    ExecutionModelId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    JobState = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    StatusReason = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true),
                    ManifestJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    ManifestHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    RequestHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    EngineVersion = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: true),
                    CompletedCycles = table.Column<int>(type: "int", nullable: false),
                    TotalCycles = table.Column<int>(type: "int", nullable: true),
                    SimulatedClock = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true),
                    RequestedBy = table.Column<string>(type: "nvarchar(256)", maxLength: 256, nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    StartedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true),
                    CompletedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true),
                    ConcurrencyStamp = table.Column<Guid>(type: "uniqueidentifier", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ExperimentRuns", x => x.Id);
                    table.UniqueConstraint("AK_ExperimentRuns_RunId", x => x.RunId);
                    table.CheckConstraint("CK_FiExperimentRun_JobState", "[JobState] IN ('queued','running','completed','failed','cancelled')");
                    table.CheckConstraint("CK_FiExperimentRun_ResponseMode", "[ResponseMode] IN ('recorded_replay','fresh_inference')");
                    table.CheckConstraint("CK_FiExperimentRun_RunType", "[RunType] IN ('replay','forward')");
                    table.ForeignKey(
                        name: "FK_ExperimentRuns_ExperimentDefinitions_ExperimentDefinitionId",
                        column: x => x.ExperimentDefinitionId,
                        principalSchema: "fi",
                        principalTable: "ExperimentDefinitions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "CashFlowEvents",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    CashFlowId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    SecurityId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Kind = table.Column<string>(type: "nvarchar(16)", maxLength: 16, nullable: false),
                    PaymentDate = table.Column<DateOnly>(type: "date", nullable: false),
                    EntitledFace = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    AmountUsd = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    CommittedVersion = table.Column<long>(type: "bigint", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CashFlowEvents", x => x.Id);
                    table.ForeignKey(
                        name: "FK_CashFlowEvents_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "Fills",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    FillId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    OrderId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    SecurityId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Side = table.Column<string>(type: "nvarchar(8)", maxLength: 8, nullable: false),
                    Face = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    ExecutedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    ObservationId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    QuoteKind = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    ReferenceCleanPricePer100 = table.Column<decimal>(type: "decimal(28,12)", nullable: false),
                    ExecutionCleanPricePer100 = table.Column<decimal>(type: "decimal(28,12)", nullable: false),
                    AccruedPer100 = table.Column<decimal>(type: "decimal(28,12)", nullable: false),
                    DirtyPricePer100 = table.Column<decimal>(type: "decimal(28,12)", nullable: false),
                    HalfSpreadPer100 = table.Column<decimal>(type: "decimal(28,12)", nullable: false),
                    SettlementDate = table.Column<DateOnly>(type: "date", nullable: false),
                    ConsiderationUsd = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    FeesUsd = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    SpreadCostUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: false),
                    TimingLabel = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    CommittedVersion = table.Column<long>(type: "bigint", nullable: false),
                    FillJson = table.Column<string>(type: "nvarchar(max)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Fills", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Fills_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "Journals",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    JournalId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    EventId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    EventType = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    EffectiveAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    Template = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    CommittedVersion = table.Column<long>(type: "bigint", nullable: false),
                    CommandId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Journals", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Journals_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "OrderIntents",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    OrderId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    DecisionId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    SecurityId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Side = table.Column<string>(type: "nvarchar(8)", maxLength: 8, nullable: false),
                    Face = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    SubmittedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    EligibleSessionDate = table.Column<DateOnly>(type: "date", nullable: false),
                    ExpiresAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(16)", maxLength: 16, nullable: false),
                    StatusReason = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true),
                    ReservedCashUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: false),
                    BatchPriority = table.Column<int>(type: "int", nullable: false),
                    Bootstrap = table.Column<bool>(type: "bit", nullable: false),
                    CreatedInVersion = table.Column<long>(type: "bigint", nullable: false),
                    LastUpdatedVersion = table.Column<long>(type: "bigint", nullable: false),
                    OrderJson = table.Column<string>(type: "nvarchar(max)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_OrderIntents", x => x.Id);
                    table.CheckConstraint("CK_FiOrderIntent_Side", "[Side] IN ('BUY','SELL')");
                    table.CheckConstraint("CK_FiOrderIntent_Status", "[Status] IN ('ACCEPTED','FILLED','EXPIRED','CANCELLED','REJECTED')");
                    table.ForeignKey(
                        name: "FK_OrderIntents_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "PortfolioEvents",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    EventId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    EventType = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    EffectiveAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true),
                    Priority = table.Column<int>(type: "int", nullable: true),
                    CommittedVersion = table.Column<long>(type: "bigint", nullable: false),
                    CommandId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    EventJson = table.Column<string>(type: "nvarchar(max)", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PortfolioEvents", x => x.Id);
                    table.ForeignKey(
                        name: "FK_PortfolioEvents_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "PortfolioStateVersions",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    Version = table.Column<long>(type: "bigint", nullable: false),
                    StateJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    StateHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: false),
                    AsOf = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    CommandId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    ProposalHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PortfolioStateVersions", x => x.Id);
                    table.ForeignKey(
                        name: "FK_PortfolioStateVersions_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "Settlements",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    SettlementId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    FillId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    SecurityId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Side = table.Column<string>(type: "nvarchar(8)", maxLength: 8, nullable: false),
                    Face = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    SettlementDate = table.Column<DateOnly>(type: "date", nullable: false),
                    CashUsd = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(16)", maxLength: 16, nullable: false),
                    CreatedInVersion = table.Column<long>(type: "bigint", nullable: false),
                    CompletedInVersion = table.Column<long>(type: "bigint", nullable: true),
                    SettlementJson = table.Column<string>(type: "nvarchar(max)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Settlements", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Settlements_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "ValuationSnapshots",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    ValuationId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    StateVersion = table.Column<long>(type: "bigint", nullable: false),
                    ValuationAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    DataMode = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    CurveSnapshotId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    MarkPolicy = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Complete = table.Column<bool>(type: "bit", nullable: false),
                    IncompleteReasonsJson = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    CashUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: false),
                    BondValueUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    ReceivablesPvUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    PayablesPvUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    EquityUsd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    ParallelDv01Usd = table.Column<decimal>(type: "decimal(28,8)", nullable: true),
                    EffectiveDurationYears = table.Column<decimal>(type: "decimal(28,12)", nullable: true),
                    CommittedVersion = table.Column<long>(type: "bigint", nullable: false),
                    ValuationJson = table.Column<string>(type: "nvarchar(max)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ValuationSnapshots", x => x.Id);
                    table.ForeignKey(
                        name: "FK_ValuationSnapshots_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalSchema: "fi",
                        principalTable: "Portfolios",
                        principalColumn: "PortfolioId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "Cycles",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    RunId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    CycleId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    Sequence = table.Column<int>(type: "int", nullable: false),
                    SessionDate = table.Column<DateOnly>(type: "date", nullable: false),
                    DecisionAsOf = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    SkipReason = table.Column<string>(type: "nvarchar(2000)", maxLength: 2000, nullable: true),
                    MarketSnapshotId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    MarketSnapshotHash = table.Column<string>(type: "nvarchar(80)", maxLength: 80, nullable: true),
                    CurveSnapshotId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: true),
                    StartedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true),
                    CompletedAt = table.Column<DateTimeOffset>(type: "datetimeoffset", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Cycles", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Cycles_ExperimentRuns_RunId",
                        column: x => x.RunId,
                        principalSchema: "fi",
                        principalTable: "ExperimentRuns",
                        principalColumn: "RunId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "StrategyInstances",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    RunId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    StrategyId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    StrategyKind = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    StrategyConfigId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    Repetition = table.Column<int>(type: "int", nullable: false),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    Label = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_StrategyInstances", x => x.Id);
                    table.ForeignKey(
                        name: "FK_StrategyInstances_ExperimentRuns_RunId",
                        column: x => x.RunId,
                        principalSchema: "fi",
                        principalTable: "ExperimentRuns",
                        principalColumn: "RunId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "JournalEntries",
                schema: "fi",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    JournalDbId = table.Column<long>(type: "bigint", nullable: false),
                    PortfolioId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    LineId = table.Column<string>(type: "nvarchar(160)", maxLength: 160, nullable: false),
                    LineNumber = table.Column<int>(type: "int", nullable: false),
                    Account = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    SecurityId = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: true),
                    DebitUsd = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    CreditUsd = table.Column<decimal>(type: "decimal(19,2)", nullable: false),
                    Memo = table.Column<string>(type: "nvarchar(500)", maxLength: 500, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_JournalEntries", x => x.Id);
                    table.CheckConstraint("CK_FiJournalEntry_NonNegative", "[DebitUsd] >= 0 AND [CreditUsd] >= 0");
                    table.ForeignKey(
                        name: "FK_JournalEntries_Journals_JournalDbId",
                        column: x => x.JournalDbId,
                        principalSchema: "fi",
                        principalTable: "Journals",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CashFlowEvents_PortfolioId_CashFlowId",
                schema: "fi",
                table: "CashFlowEvents",
                columns: new[] { "PortfolioId", "CashFlowId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_CommandRecords_CommandId",
                schema: "fi",
                table: "CommandRecords",
                column: "CommandId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_CommandRecords_PortfolioId",
                schema: "fi",
                table: "CommandRecords",
                column: "PortfolioId");

            migrationBuilder.CreateIndex(
                name: "IX_Cycles_RunId_CycleId",
                schema: "fi",
                table: "Cycles",
                columns: new[] { "RunId", "CycleId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Cycles_RunId_Sequence",
                schema: "fi",
                table: "Cycles",
                columns: new[] { "RunId", "Sequence" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_DecisionAttempts_DecisionDbId_AttemptId",
                schema: "fi",
                table: "DecisionAttempts",
                columns: new[] { "DecisionDbId", "AttemptId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Decisions_DecisionId",
                schema: "fi",
                table: "Decisions",
                column: "DecisionId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Decisions_RunId_CycleId_StrategyId_Repetition",
                schema: "fi",
                table: "Decisions",
                columns: new[] { "RunId", "CycleId", "StrategyId", "Repetition" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Decisions_RunId_Outcome",
                schema: "fi",
                table: "Decisions",
                columns: new[] { "RunId", "Outcome" });

            migrationBuilder.CreateIndex(
                name: "IX_ExperimentDefinitions_ExperimentId_Version",
                schema: "fi",
                table: "ExperimentDefinitions",
                columns: new[] { "ExperimentId", "Version" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ExperimentRuns_ExperimentDefinitionId",
                schema: "fi",
                table: "ExperimentRuns",
                column: "ExperimentDefinitionId");

            migrationBuilder.CreateIndex(
                name: "IX_ExperimentRuns_ExperimentId_ExperimentVersion",
                schema: "fi",
                table: "ExperimentRuns",
                columns: new[] { "ExperimentId", "ExperimentVersion" });

            migrationBuilder.CreateIndex(
                name: "IX_ExperimentRuns_JobState",
                schema: "fi",
                table: "ExperimentRuns",
                column: "JobState");

            migrationBuilder.CreateIndex(
                name: "IX_Fills_PortfolioId_FillId",
                schema: "fi",
                table: "Fills",
                columns: new[] { "PortfolioId", "FillId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Fills_PortfolioId_OrderId",
                schema: "fi",
                table: "Fills",
                columns: new[] { "PortfolioId", "OrderId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_JournalEntries_JournalDbId_LineId",
                schema: "fi",
                table: "JournalEntries",
                columns: new[] { "JournalDbId", "LineId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_JournalEntries_PortfolioId_Account",
                schema: "fi",
                table: "JournalEntries",
                columns: new[] { "PortfolioId", "Account" });

            migrationBuilder.CreateIndex(
                name: "IX_Journals_PortfolioId_EventId",
                schema: "fi",
                table: "Journals",
                columns: new[] { "PortfolioId", "EventId" });

            migrationBuilder.CreateIndex(
                name: "IX_Journals_PortfolioId_JournalId",
                schema: "fi",
                table: "Journals",
                columns: new[] { "PortfolioId", "JournalId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_OrderIntents_DecisionId",
                schema: "fi",
                table: "OrderIntents",
                column: "DecisionId");

            migrationBuilder.CreateIndex(
                name: "IX_OrderIntents_PortfolioId_OrderId",
                schema: "fi",
                table: "OrderIntents",
                columns: new[] { "PortfolioId", "OrderId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_OrderIntents_PortfolioId_Status",
                schema: "fi",
                table: "OrderIntents",
                columns: new[] { "PortfolioId", "Status" });

            migrationBuilder.CreateIndex(
                name: "IX_PolicyEvaluations_CommandId",
                schema: "fi",
                table: "PolicyEvaluations",
                column: "CommandId");

            migrationBuilder.CreateIndex(
                name: "IX_PolicyEvaluations_DecisionDbId",
                schema: "fi",
                table: "PolicyEvaluations",
                column: "DecisionDbId");

            migrationBuilder.CreateIndex(
                name: "IX_PolicyEvaluations_DecisionId",
                schema: "fi",
                table: "PolicyEvaluations",
                column: "DecisionId");

            migrationBuilder.CreateIndex(
                name: "IX_PortfolioEvents_PortfolioId_CommittedVersion",
                schema: "fi",
                table: "PortfolioEvents",
                columns: new[] { "PortfolioId", "CommittedVersion" });

            migrationBuilder.CreateIndex(
                name: "IX_PortfolioEvents_PortfolioId_EventId",
                schema: "fi",
                table: "PortfolioEvents",
                columns: new[] { "PortfolioId", "EventId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Portfolios_RunId_StrategyId_Repetition",
                schema: "fi",
                table: "Portfolios",
                columns: new[] { "RunId", "StrategyId", "Repetition" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_PortfolioStateVersions_PortfolioId_Version",
                schema: "fi",
                table: "PortfolioStateVersions",
                columns: new[] { "PortfolioId", "Version" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Settlements_PortfolioId_FillId",
                schema: "fi",
                table: "Settlements",
                columns: new[] { "PortfolioId", "FillId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Settlements_PortfolioId_SettlementId",
                schema: "fi",
                table: "Settlements",
                columns: new[] { "PortfolioId", "SettlementId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_StrategyInstances_PortfolioId",
                schema: "fi",
                table: "StrategyInstances",
                column: "PortfolioId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_StrategyInstances_RunId_StrategyId_Repetition",
                schema: "fi",
                table: "StrategyInstances",
                columns: new[] { "RunId", "StrategyId", "Repetition" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ToolTraces_DecisionDbId_TraceId",
                schema: "fi",
                table: "ToolTraces",
                columns: new[] { "DecisionDbId", "TraceId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_UsageRecords_DecisionDbId",
                schema: "fi",
                table: "UsageRecords",
                column: "DecisionDbId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ValuationSnapshots_PortfolioId_ValuationId",
                schema: "fi",
                table: "ValuationSnapshots",
                columns: new[] { "PortfolioId", "ValuationId" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CashFlowEvents",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "CommandRecords",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "Cycles",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "DecisionAttempts",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "Fills",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "JournalEntries",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "OrderIntents",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "PolicyEvaluations",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "PortfolioEvents",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "PortfolioStateVersions",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "Settlements",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "StrategyInstances",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "ToolTraces",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "UsageRecords",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "ValuationSnapshots",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "Journals",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "ExperimentRuns",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "Decisions",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "Portfolios",
                schema: "fi");

            migrationBuilder.DropTable(
                name: "ExperimentDefinitions",
                schema: "fi");

        }
    }
}
