using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

#pragma warning disable CA1814 // Prefer jagged arrays over multidimensional

namespace AiTradingRace.Infrastructure.Migrations
{
    /// <inheritdoc />
    public partial class InitialCreate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Agents",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    Name = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    Provider = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    IsActive = table.Column<bool>(type: "INTEGER", nullable: false, defaultValue: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false, defaultValueSql: "SYSUTCDATETIME()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Agents", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "MarketAssets",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    Symbol = table.Column<string>(type: "TEXT", maxLength: 16, nullable: false),
                    Name = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    QuoteCurrency = table.Column<string>(type: "TEXT", maxLength: 16, nullable: false),
                    IsEnabled = table.Column<bool>(type: "INTEGER", nullable: false, defaultValue: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MarketAssets", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Portfolios",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    AgentId = table.Column<Guid>(type: "TEXT", nullable: false),
                    Cash = table.Column<decimal>(type: "decimal(18,8)", nullable: false, defaultValue: 0m),
                    BaseCurrency = table.Column<string>(type: "TEXT", maxLength: 16, nullable: false, defaultValue: "USD")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Portfolios", x => x.Id);
                    table.CheckConstraint("CK_Portfolio_Cash_NonNegative", "[Cash] >= 0");
                    table.ForeignKey(
                        name: "FK_Portfolios_Agents_AgentId",
                        column: x => x.AgentId,
                        principalTable: "Agents",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "MarketCandles",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    MarketAssetId = table.Column<Guid>(type: "TEXT", nullable: false),
                    TimestampUtc = table.Column<DateTimeOffset>(type: "TEXT", nullable: false),
                    Open = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    High = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    Low = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    Close = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    Volume = table.Column<decimal>(type: "decimal(18,8)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MarketCandles", x => x.Id);
                    table.CheckConstraint("CK_MarketCandle_PricesPositive", "[Open] > 0 AND [High] > 0 AND [Low] > 0 AND [Close] > 0");
                    table.CheckConstraint("CK_MarketCandle_VolumeNonNegative", "[Volume] >= 0");
                    table.ForeignKey(
                        name: "FK_MarketCandles_MarketAssets_MarketAssetId",
                        column: x => x.MarketAssetId,
                        principalTable: "MarketAssets",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "EquitySnapshots",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    PortfolioId = table.Column<Guid>(type: "TEXT", nullable: false),
                    CapturedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false),
                    TotalValue = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    UnrealizedPnL = table.Column<decimal>(type: "decimal(18,8)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_EquitySnapshots", x => x.Id);
                    table.ForeignKey(
                        name: "FK_EquitySnapshots_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalTable: "Portfolios",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Positions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    PortfolioId = table.Column<Guid>(type: "TEXT", nullable: false),
                    MarketAssetId = table.Column<Guid>(type: "TEXT", nullable: false),
                    Quantity = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    AverageEntryPrice = table.Column<decimal>(type: "decimal(18,8)", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Positions", x => x.Id);
                    table.CheckConstraint("CK_Position_AverageEntryPrice_NonNegative", "[AverageEntryPrice] >= 0");
                    table.CheckConstraint("CK_Position_Quantity_NonNegative", "[Quantity] >= 0");
                    table.ForeignKey(
                        name: "FK_Positions_MarketAssets_MarketAssetId",
                        column: x => x.MarketAssetId,
                        principalTable: "MarketAssets",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_Positions_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalTable: "Portfolios",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Trades",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    PortfolioId = table.Column<Guid>(type: "TEXT", nullable: false),
                    MarketAssetId = table.Column<Guid>(type: "TEXT", nullable: false),
                    ExecutedAt = table.Column<DateTimeOffset>(type: "TEXT", nullable: false),
                    Quantity = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    Price = table.Column<decimal>(type: "decimal(18,8)", nullable: false),
                    Side = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Trades", x => x.Id);
                    table.CheckConstraint("CK_Trade_Price_Positive", "[Price] > 0");
                    table.CheckConstraint("CK_Trade_Quantity_Positive", "[Quantity] > 0");
                    table.ForeignKey(
                        name: "FK_Trades_MarketAssets_MarketAssetId",
                        column: x => x.MarketAssetId,
                        principalTable: "MarketAssets",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_Trades_Portfolios_PortfolioId",
                        column: x => x.PortfolioId,
                        principalTable: "Portfolios",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.InsertData(
                table: "Agents",
                columns: new[] { "Id", "CreatedAt", "IsActive", "Name", "Provider" },
                values: new object[,]
                {
                    { new Guid("11111111-1111-1111-1111-111111111111"), new DateTimeOffset(new DateTime(2025, 12, 7, 12, 34, 26, 792, DateTimeKind.Unspecified).AddTicks(4940), new TimeSpan(0, 0, 0, 0, 0)), true, "GPT", "AzureOpenAI" },
                    { new Guid("22222222-2222-2222-2222-222222222222"), new DateTimeOffset(new DateTime(2025, 12, 7, 12, 34, 26, 792, DateTimeKind.Unspecified).AddTicks(4940), new TimeSpan(0, 0, 0, 0, 0)), true, "Claude", "Anthropic" },
                    { new Guid("33333333-3333-3333-3333-333333333333"), new DateTimeOffset(new DateTime(2025, 12, 7, 12, 34, 26, 792, DateTimeKind.Unspecified).AddTicks(4940), new TimeSpan(0, 0, 0, 0, 0)), true, "Grok", "xAI" }
                });

            migrationBuilder.InsertData(
                table: "MarketAssets",
                columns: new[] { "Id", "IsEnabled", "Name", "QuoteCurrency", "Symbol" },
                values: new object[,]
                {
                    { new Guid("b1fa9f8a-626b-4253-9a5d-0c9c9fb5c9fd"), true, "Ethereum", "USD", "ETH" },
                    { new Guid("c3d4b060-55bb-4e48-8f04-3452ec0c9d4c"), true, "Bitcoin", "USD", "BTC" }
                });

            migrationBuilder.InsertData(
                table: "MarketCandles",
                columns: new[] { "Id", "Close", "High", "Low", "MarketAssetId", "Open", "TimestampUtc", "Volume" },
                values: new object[,]
                {
                    { new Guid("44444444-4444-4444-4444-444444444444"), 47200m, 47500m, 46500m, new Guid("c3d4b060-55bb-4e48-8f04-3452ec0c9d4c"), 47000m, new DateTimeOffset(new DateTime(2024, 1, 1, 0, 0, 0, 0, DateTimeKind.Unspecified), new TimeSpan(0, 0, 0, 0, 0)), 1250m },
                    { new Guid("55555555-5555-5555-5555-555555555555"), 3235m, 3250m, 3150m, new Guid("b1fa9f8a-626b-4253-9a5d-0c9c9fb5c9fd"), 3200m, new DateTimeOffset(new DateTime(2024, 1, 1, 0, 0, 0, 0, DateTimeKind.Unspecified), new TimeSpan(0, 0, 0, 0, 0)), 8500m }
                });

            migrationBuilder.CreateIndex(
                name: "IX_EquitySnapshots_PortfolioId_CapturedAt",
                table: "EquitySnapshots",
                columns: new[] { "PortfolioId", "CapturedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_MarketAssets_Symbol",
                table: "MarketAssets",
                column: "Symbol",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_MarketCandles_MarketAssetId_TimestampUtc",
                table: "MarketCandles",
                columns: new[] { "MarketAssetId", "TimestampUtc" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Portfolios_AgentId",
                table: "Portfolios",
                column: "AgentId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Positions_MarketAssetId",
                table: "Positions",
                column: "MarketAssetId");

            migrationBuilder.CreateIndex(
                name: "IX_Positions_PortfolioId_MarketAssetId",
                table: "Positions",
                columns: new[] { "PortfolioId", "MarketAssetId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Trades_MarketAssetId",
                table: "Trades",
                column: "MarketAssetId");

            migrationBuilder.CreateIndex(
                name: "IX_Trades_PortfolioId",
                table: "Trades",
                column: "PortfolioId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "EquitySnapshots");

            migrationBuilder.DropTable(
                name: "MarketCandles");

            migrationBuilder.DropTable(
                name: "Positions");

            migrationBuilder.DropTable(
                name: "Trades");

            migrationBuilder.DropTable(
                name: "MarketAssets");

            migrationBuilder.DropTable(
                name: "Portfolios");

            migrationBuilder.DropTable(
                name: "Agents");
        }
    }
}
