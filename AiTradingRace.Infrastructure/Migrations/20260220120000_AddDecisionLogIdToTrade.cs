using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class AddDecisionLogIdToTrade : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "DecisionLogId",
                table: "Trades",
                type: "int",
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_Trades_DecisionLogId",
                table: "Trades",
                column: "DecisionLogId");

            migrationBuilder.AddForeignKey(
                name: "FK_Trades_DecisionLogs_DecisionLogId",
                table: "Trades",
                column: "DecisionLogId",
                principalTable: "DecisionLogs",
                principalColumn: "Id",
                onDelete: ReferentialAction.SetNull);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_Trades_DecisionLogs_DecisionLogId",
                table: "Trades");

            migrationBuilder.DropIndex(
                name: "IX_Trades_DecisionLogId",
                table: "Trades");

            migrationBuilder.DropColumn(
                name: "DecisionLogId",
                table: "Trades");
        }
    }
}
