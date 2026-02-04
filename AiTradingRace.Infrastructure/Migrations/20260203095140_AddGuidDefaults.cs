using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddGuidDefaults : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<Guid>(
                name: "Id",
                table: "Portfolios",
                type: "uniqueidentifier",
                nullable: false,
                defaultValueSql: "NEWID()",
                oldClrType: typeof(Guid),
                oldType: "uniqueidentifier");

            migrationBuilder.AlterColumn<Guid>(
                name: "Id",
                table: "Agents",
                type: "uniqueidentifier",
                nullable: false,
                defaultValueSql: "NEWID()",
                oldClrType: typeof(Guid),
                oldType: "uniqueidentifier");

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

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterColumn<Guid>(
                name: "Id",
                table: "Portfolios",
                type: "uniqueidentifier",
                nullable: false,
                oldClrType: typeof(Guid),
                oldType: "uniqueidentifier",
                oldDefaultValueSql: "NEWID()");

            migrationBuilder.AlterColumn<Guid>(
                name: "Id",
                table: "Agents",
                type: "uniqueidentifier",
                nullable: false,
                oldClrType: typeof(Guid),
                oldType: "uniqueidentifier",
                oldDefaultValueSql: "NEWID()");

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

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BEARISH",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "BULLISH",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "STABLE",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RegimeNodes",
                keyColumn: "Id",
                keyValue: "VOLATILE",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 1,
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 2,
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 3,
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 4,
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 5,
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleEdges",
                keyColumn: "Id",
                keyValue: 6,
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R001",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R002",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R003",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R004",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));

            migrationBuilder.UpdateData(
                table: "RuleNodes",
                keyColumn: "Id",
                keyValue: "R005",
                column: "CreatedAt",
                value: new DateTime(2026, 1, 21, 0, 40, 12, 25, DateTimeKind.Utc).AddTicks(9750));
        }
    }
}
