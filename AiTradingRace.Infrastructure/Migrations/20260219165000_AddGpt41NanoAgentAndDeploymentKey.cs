using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddGpt41NanoAgentAndDeploymentKey : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "DeploymentKey",
                table: "Agents",
                type: "nvarchar(64)",
                maxLength: 64,
                nullable: true);

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                columns: new[] { "CreatedAt", "DeploymentKey" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Unspecified).AddTicks(410), new TimeSpan(0, 0, 0, 0, 0)), null });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                columns: new[] { "CreatedAt", "DeploymentKey" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Unspecified).AddTicks(410), new TimeSpan(0, 0, 0, 0, 0)), null });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                columns: new[] { "CreatedAt", "DeploymentKey" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Unspecified).AddTicks(410), new TimeSpan(0, 0, 0, 0, 0)), null });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("44444444-0000-4444-0000-444444444444"),
                columns: new[] { "CreatedAt", "DeploymentKey" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Unspecified).AddTicks(410), new TimeSpan(0, 0, 0, 0, 0)), null });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("55555555-0000-5555-0000-555555555555"),
                columns: new[] { "CreatedAt", "DeploymentKey", "Name" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Unspecified).AddTicks(410), new TimeSpan(0, 0, 0, 0, 0)), "GPT4oMini", "GPT-4o-mini" });

            migrationBuilder.InsertData(
                table: "Agents",
                columns: new[] { "Id", "CreatedAt", "DeploymentKey", "Instructions", "IsActive", "ModelProvider", "Name", "Strategy" },
                values: new object[] { new Guid("66666666-0000-6666-0000-666666666666"), new DateTimeOffset(new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Unspecified).AddTicks(420), new TimeSpan(0, 0, 0, 0, 0)), "GPT41Nano", "You are a fast-acting trader. Use technical indicators to make quick, data-driven trading decisions. Favor clear signals over complex analysis.", true, "AzureOpenAI", "GPT-4.1-nano", "Fast, cost-efficient trading with technical signal focus" });

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 19, 16, 50, 0, 48, DateTimeKind.Utc).AddTicks(450));
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DeleteData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("66666666-0000-6666-0000-666666666666"));

            migrationBuilder.DropColumn(
                name: "DeploymentKey",
                table: "Agents");

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Unspecified).AddTicks(3500), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Unspecified).AddTicks(3510), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Unspecified).AddTicks(3510), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("44444444-0000-4444-0000-444444444444"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Unspecified).AddTicks(3510), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("55555555-0000-5555-0000-555555555555"),
                columns: new[] { "CreatedAt", "Name" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Unspecified).AddTicks(3510), new TimeSpan(0, 0, 0, 0, 0)), "GPT-4o" });

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 17, 16, 24, 36, 426, DateTimeKind.Utc).AddTicks(3550));
        }
    }
}
