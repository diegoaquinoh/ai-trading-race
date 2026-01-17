using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddAgentInstructionsAndModelProvider : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Provider",
                table: "Agents");

            migrationBuilder.AddColumn<string>(
                name: "Instructions",
                table: "Agents",
                type: "nvarchar(4000)",
                maxLength: 4000,
                nullable: false,
                defaultValue: "");

            migrationBuilder.AddColumn<string>(
                name: "ModelProvider",
                table: "Agents",
                type: "nvarchar(32)",
                maxLength: 32,
                nullable: false,
                defaultValue: "AzureOpenAI");

            migrationBuilder.AddColumn<string>(
                name: "Strategy",
                table: "Agents",
                type: "nvarchar(512)",
                maxLength: 512,
                nullable: false,
                defaultValue: "");

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                columns: new[] { "CreatedAt", "Instructions", "Name", "Strategy" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 1, 17, 16, 0, 3, 213, DateTimeKind.Unspecified).AddTicks(3890), new TimeSpan(0, 0, 0, 0, 0)), "You are a conservative trader. Focus on momentum signals and always maintain diversification.", "GPT-4o", "Momentum-based trading with risk management" });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                columns: new[] { "CreatedAt", "Instructions", "ModelProvider", "Strategy" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 1, 17, 16, 0, 3, 213, DateTimeKind.Unspecified).AddTicks(3890), new TimeSpan(0, 0, 0, 0, 0)), "You are a value investor. Look for undervalued opportunities and use technical indicators for timing.", "Mock", "Value-oriented with technical analysis" });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                columns: new[] { "CreatedAt", "Instructions", "ModelProvider", "Strategy" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 1, 17, 16, 0, 3, 213, DateTimeKind.Unspecified).AddTicks(3900), new TimeSpan(0, 0, 0, 0, 0)), "You are an aggressive trader. Follow trends and capitalize on momentum, but respect position limits.", "Mock", "Aggressive trend following" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Instructions",
                table: "Agents");

            migrationBuilder.DropColumn(
                name: "ModelProvider",
                table: "Agents");

            migrationBuilder.DropColumn(
                name: "Strategy",
                table: "Agents");

            migrationBuilder.AddColumn<string>(
                name: "Provider",
                table: "Agents",
                type: "nvarchar(128)",
                maxLength: 128,
                nullable: false,
                defaultValue: "");

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("11111111-1111-1111-1111-111111111111"),
                columns: new[] { "CreatedAt", "Name", "Provider" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 1, 17, 11, 38, 51, 415, DateTimeKind.Unspecified).AddTicks(2710), new TimeSpan(0, 0, 0, 0, 0)), "GPT", "AzureOpenAI" });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("22222222-2222-2222-2222-222222222222"),
                columns: new[] { "CreatedAt", "Provider" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 1, 17, 11, 38, 51, 415, DateTimeKind.Unspecified).AddTicks(2710), new TimeSpan(0, 0, 0, 0, 0)), "Anthropic" });

            migrationBuilder.UpdateData(
                table: "Agents",
                keyColumn: "Id",
                keyValue: new Guid("33333333-3333-3333-3333-333333333333"),
                columns: new[] { "CreatedAt", "Provider" },
                values: new object[] { new DateTimeOffset(new DateTime(2026, 1, 17, 11, 38, 51, 415, DateTimeKind.Unspecified).AddTicks(2720), new TimeSpan(0, 0, 0, 0, 0)), "xAI" });
        }
    }
}
