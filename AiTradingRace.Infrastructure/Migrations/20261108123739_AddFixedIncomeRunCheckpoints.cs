using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <summary>
    /// Additive fi-schema change: frozen cycle inputs, completion checkpoints and classified
    /// run/cycle errors for the application-mode run executor (spec 15.4, 18.3).
    /// </summary>
    public partial class AddFixedIncomeRunCheckpoints : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "ErrorsJson",
                schema: "fi",
                table: "ExperimentRuns",
                type: "nvarchar(max)",
                nullable: true);

            migrationBuilder.AddColumn<DateTimeOffset>(
                name: "LastCheckpointAt",
                schema: "fi",
                table: "ExperimentRuns",
                type: "datetimeoffset",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "CheckpointJson",
                schema: "fi",
                table: "Cycles",
                type: "nvarchar(max)",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ErrorsJson",
                schema: "fi",
                table: "Cycles",
                type: "nvarchar(max)",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "InputsJson",
                schema: "fi",
                table: "Cycles",
                type: "nvarchar(max)",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "ErrorsJson",
                schema: "fi",
                table: "ExperimentRuns");

            migrationBuilder.DropColumn(
                name: "LastCheckpointAt",
                schema: "fi",
                table: "ExperimentRuns");

            migrationBuilder.DropColumn(
                name: "CheckpointJson",
                schema: "fi",
                table: "Cycles");

            migrationBuilder.DropColumn(
                name: "ErrorsJson",
                schema: "fi",
                table: "Cycles");

            migrationBuilder.DropColumn(
                name: "InputsJson",
                schema: "fi",
                table: "Cycles");
        }
    }
}
