using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Version-0 portfolio state with every field of the Python <c>PortfolioState</c>
/// wire form (including null/empty defaults), so the engine's content hash of the
/// parsed state equals the hash .NET stores. Contains no financial computation:
/// zero cash, no positions; initial capital arrives through a capital_flow command.
/// </summary>
public static class PortfolioGenesis
{
    public static JsonObject Build(string portfolioId, string strategyId, string runId, DateTimeOffset asOf) => new()
    {
        ["schemaVersion"] = FiContract.SchemaVersion,
        ["portfolioId"] = portfolioId,
        ["strategyId"] = strategyId,
        ["runId"] = runId,
        ["version"] = 0,
        ["asOf"] = FiWire.FormatInstant(asOf),
        ["currency"] = "USD",
        ["cashUsd"] = "0",
        ["reservedCashUsd"] = "0",
        ["positions"] = new JsonArray(),
        ["openOrders"] = new JsonArray(),
        ["pendingSettlements"] = new JsonArray(),
        ["externalCapitalUsd"] = "0",
        ["interestIncomeUsd"] = "0",
        ["realizedGainLossUsd"] = "0",
        ["transactionFeesUsd"] = "0",
        ["spreadCostUsd"] = "0",
        ["bookedUnrealizedUsd"] = "0",
        ["cashFlowsProcessedThrough"] = null,
        ["lastValuationId"] = null,
        ["riskBreaches"] = new JsonArray(),
        ["blockedReason"] = null,
    };
}
