using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddBatchIdToEquitySnapshot : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "BatchId",
                table: "EquitySnapshots",
                type: "uniqueidentifier",
                nullable: true);

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

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "BatchId",
                table: "EquitySnapshots");

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Unspecified).AddTicks(7820), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Unspecified).AddTicks(7820), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                column: "CreatedAt",
                value: new DateTimeOffset(new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Unspecified).AddTicks(7820), new TimeSpan(0, 0, 0, 0, 0)));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 2, 3, 9, 51, 40, 644, DateTimeKind.Utc).AddTicks(7870));
        }
    }
}
