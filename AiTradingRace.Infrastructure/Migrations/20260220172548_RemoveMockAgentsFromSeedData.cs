using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

#pragma warning disable CA1814 // Prefer jagged arrays over multidimensional

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class RemoveMockAgentsFromSeedData : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DeleteData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"));

            migrationBuilder.DeleteData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"));

            migrationBuilder.DeleteData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("44444444-0000-4444-0000-444444444444"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Unspecified).AddTicks(1490), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("55555555-0000-5555-0000-555555555555"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Unspecified).AddTicks(1490), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("66666666-0000-6666-0000-666666666666"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Unspecified).AddTicks(1500), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 17, 25, 48, 213, DateTimeKind.Utc).AddTicks(1530));
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("44444444-0000-4444-0000-444444444444"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Unspecified).AddTicks(7920), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("55555555-0000-5555-0000-555555555555"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Unspecified).AddTicks(7920), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("66666666-0000-6666-0000-666666666666"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Unspecified).AddTicks(7920), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.InsertData(
                table: "Agents",
                columns: new[] { "Id", "CreatedAt", "DeploymentKey", "Instructions", "ModelProvider", "Name", "Strategy" },
                values: new object[,]
                {
                    { new Guid("11111111-1111-1111-1111-111111111111"), new DateTimeOffset(new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Unspecified).AddTicks(7910), new TimeSpan(0, 0, 0, 0, 0)), null, "You are a conservative trader. Focus on momentum signals and always maintain diversification.", "Llama", "Llama-70B", "Momentum-based trading with risk management" },
                    { new Guid("22222222-2222-2222-2222-222222222222"), new DateTimeOffset(new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Unspecified).AddTicks(7910), new TimeSpan(0, 0, 0, 0, 0)), null, "You are a value investor. Look for undervalued opportunities and use technical indicators for timing.", "Mock", "Claude", "Value-oriented with technical analysis" },
                    { new Guid("33333333-3333-3333-3333-333333333333"), new DateTimeOffset(new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Unspecified).AddTicks(7910), new TimeSpan(0, 0, 0, 0, 0)), null, "You are an aggressive trader. Follow trends and capitalize on momentum, but respect position limits.", "Mock", "Grok", "Aggressive trend following" }
                });

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 20, 13, 4, 22, 657, DateTimeKind.Utc).AddTicks(7950));
        }
    }
}
