using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

#pragma warning disable CA1814 // Prefer jagged arrays over multidimensional

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class Phase10_KnowledgeGraph : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "DecisionLogs",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    AgentId = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Timestamp = table.Column<DateTime>(type: "datetime2", nullable: false),
                    Action = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    Asset = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: true),
                    Quantity = table.Column<decimal>(type: "decimal(18,8)", nullable: true),
                    Rationale = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    CitedRuleIds = table.Column<string>(type: "nvarchar(500)", maxLength: 500, nullable: false),
                    DetectedRegime = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                    SubgraphSnapshot = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    PortfolioValueBefore = table.Column<decimal>(type: "decimal(18,2)", nullable: false),
                    PortfolioValueAfter = table.Column<decimal>(type: "decimal(18,2)", nullable: false),
                    MarketConditions = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    WasValidated = table.Column<bool>(type: "bit", nullable: false, defaultValue: true),
                    ValidationErrors = table.Column<string>(type: "nvarchar(max)", nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false, defaultValueSql: "SYSUTCDATETIME()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DecisionLogs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_DecisionLogs_Agents_AgentId",
                        column: x => x.AgentId,
                        principalTable: "Agents",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "DetectedRegimes",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    RegimeId = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                    DetectedAt = table.Column<DateTime>(type: "datetime2", nullable: false),
                    EndedAt = table.Column<DateTime>(type: "datetime2", nullable: true),
                    Volatility = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    MA7 = table.Column<decimal>(type: "decimal(18,2)", nullable: true),
                    MA30 = table.Column<decimal>(type: "decimal(18,2)", nullable: true),
                    Asset = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false, defaultValueSql: "SYSUTCDATETIME()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DetectedRegimes", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "RegimeNodes",
                columns: table => new
                {
                    Id = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: false),
                    Condition = table.Column<string>(type: "nvarchar(500)", maxLength: 500, nullable: false),
                    LookbackDays = table.Column<int>(type: "int", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false, defaultValueSql: "SYSUTCDATETIME()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RegimeNodes", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "RuleEdges",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    SourceNodeId = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                    TargetNodeId = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                    Type = table.Column<int>(type: "int", nullable: false),
                    Parameters = table.Column<string>(type: "nvarchar(4000)", maxLength: 4000, nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false, defaultValueSql: "SYSUTCDATETIME()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleEdges", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "RuleNodes",
                columns: table => new
                {
                    Id = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(200)", maxLength: 200, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(1000)", maxLength: 1000, nullable: false),
                    Category = table.Column<int>(type: "int", nullable: false),
                    Severity = table.Column<int>(type: "int", nullable: false),
                    Threshold = table.Column<decimal>(type: "decimal(18,8)", nullable: true),
                    Unit = table.Column<string>(type: "nvarchar(50)", maxLength: 50, nullable: true),
                    IsActive = table.Column<bool>(type: "bit", nullable: false, defaultValue: true),
                    CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false, defaultValueSql: "SYSUTCDATETIME()"),
                    UpdatedAt = table.Column<DateTime>(type: "datetime2", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RuleNodes", x => x.Id);
                });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Unspecified).AddTicks(9710), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Unspecified).AddTicks(9710), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Unspecified).AddTicks(9710), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.InsertData(
                table: "RegimeNodes",
                columns: new[] { "Id", "Condition", "CreatedAt", "Description", "LookbackDays", "Name" },
                values: new object[,]
                {
                    { "BEARISH", "ma_7d < ma_30d", new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "7-day MA < 30-day MA", 30, "Bearish Trend" },
                    { "BULLISH", "ma_7d > ma_30d", new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "7-day MA > 30-day MA", 30, "Bullish Trend" },
                    { "STABLE", "volatility_7d < 0.02", new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "Daily volatility < 2%", 7, "Stable Market" },
                    { "VOLATILE", "volatility_7d > 0.05", new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "Daily volatility > 5%", 7, "Volatile Market" }
                });

            migrationBuilder.InsertData(
                table: "RuleEdges",
                columns: new[] { "Id", "CreatedAt", "Parameters", "SourceNodeId", "TargetNodeId", "Type" },
                values: new object[,]
                {
                    { 1, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), null, "VOLATILE", "R003", 0 },
                    { 2, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "{\"threshold\": 200.0}", "VOLATILE", "R002", 2 },
                    { 3, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "{\"threshold\": 0.6}", "BULLISH", "R001", 1 },
                    { 4, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "{\"threshold\": 0.3}", "BEARISH", "R001", 2 },
                    { 5, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), null, "Asset:BTC", "R001", 4 },
                    { 6, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), null, "Asset:ETH", "R001", 4 }
                });

            migrationBuilder.InsertData(
                table: "RuleNodes",
                columns: new[] { "Id", "Category", "CreatedAt", "Description", "IsActive", "Name", "Severity", "Threshold", "Unit", "UpdatedAt" },
                values: new object[,]
                {
                    { "R001", 0, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "No single position should exceed 50% of total portfolio value", true, "MaxPositionSize", 1, 0.5m, "percentage", null },
                    { "R002", 1, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "Maintain minimum $100 cash buffer for trading costs", true, "MinCashReserve", 2, 100.0m, "dollars", null },
                    { "R003", 0, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "Reduce exposure when daily volatility exceeds 5%", true, "VolatilityStop", 1, 0.05m, "percentage", null },
                    { "R004", 4, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "Exit all positions if portfolio drops 20% from peak", true, "MaxDrawdown", 0, 0.2m, "percentage", null },
                    { "R005", 2, new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750), "Hold at least 2 different assets when invested", true, "DiversificationRule", 2, 2.0m, "count", null }
                });

            migrationBuilder.CreateIndex(
                name: "IX_DecisionLogs_AgentId_Timestamp",
                table: "DecisionLogs",
                columns: new[] { "AgentId", "Timestamp" });

            migrationBuilder.CreateIndex(
                name: "IX_DecisionLogs_DetectedRegime",
                table: "DecisionLogs",
                column: "DetectedRegime");

            migrationBuilder.CreateIndex(
                name: "IX_DetectedRegimes_Asset_DetectedAt",
                table: "DetectedRegimes",
                columns: new[] { "Asset", "DetectedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_RuleEdges_SourceNodeId",
                table: "RuleEdges",
                column: "SourceNodeId");

            migrationBuilder.CreateIndex(
                name: "IX_RuleEdges_TargetNodeId",
                table: "RuleEdges",
                column: "TargetNodeId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "DecisionLogs");

            migrationBuilder.DropTable(
                name: "DetectedRegimes");

            migrationBuilder.DropTable(
                name: "RegimeNodes");

            migrationBuilder.DropTable(
                name: "RuleEdges");

            migrationBuilder.DropTable(
                name: "RuleNodes");

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 1, 20, 22, 54, 29, 982, DateTimeKind.Unspecified).AddTicks(5650), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 1, 20, 22, 54, 29, 982, DateTimeKind.Unspecified).AddTicks(5650), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 1, 20, 22, 54, 29, 982, DateTimeKind.Unspecified).AddTicks(5650), new TimeSpan(0, 0, 0, 0, 0)));
        }
    }
}
