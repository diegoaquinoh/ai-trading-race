using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddCustomMlAgent : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Unspecified).AddTicks(2650), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Unspecified).AddTicks(2650), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Unspecified).AddTicks(2650), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.InsertData(
                table: "Agents",
                columns: new[] { "Id", "CreatedAt", "Instructions", "IsActive", "ModelProvider", "Name", "Strategy" },
                values: new object[] { new Guid("44444444-0000-4444-0000-444444444444"), new DateTimeOffset(new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Unspecified).AddTicks(2650), new TimeSpan(0, 0, 0, 0, 0)), "ML model using technical indicators for trading decisions with explainability signals.", true, "CustomML", "Custom ML", "Technical indicator-driven ML model with RSI, MACD, and Bollinger signals" });

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 16, 16, 25, 26, 747, DateTimeKind.Utc).AddTicks(2690));
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DeleteData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("44444444-0000-4444-0000-444444444444"));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Unspecified).AddTicks(7950), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Unspecified).AddTicks(7950), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Unspecified).AddTicks(7950), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 11, 32, 26, 563, DateTimeKind.Utc).AddTicks(7990));
        }
    }
}
