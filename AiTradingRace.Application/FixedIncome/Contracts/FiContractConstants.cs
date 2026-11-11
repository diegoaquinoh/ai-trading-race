using System.Text.Json;
using System.Text.Json.Serialization;

namespace AiTradingRace.Application.FixedIncome.Contracts;

/// <summary>
/// Cross-runtime contract constants. Source of truth:
/// ai-trading-race-ml/research_engine/contracts/common.py.
/// </summary>
public static class FiContract
{
    public const string SchemaVersion = "1.0";
    public const int SchemaMajor = 1;
    public const string CashSecurityId = "CASH-USD";
    public const string HashPrefix = "sha256:";
    public const string SignaturePrefix = "hmac-sha256:";
    public const string EventPriorityTable = "event-priority-v1";

    /// <summary>Opaque identifier pattern shared with Python (OpaqueId).</summary>
    public const string OpaqueIdPattern = @"^[A-Za-z0-9][A-Za-z0-9_\-\.:]{0,159}$";

    /// <summary>Strategy identifier pattern shared with Python (StrategyId).</summary>
    public const string StrategyIdPattern = @"^[a-z][a-z0-9_]{1,63}$";

    /// <summary>Content hash pattern (ContentHash).</summary>
    public const string ContentHashPattern = @"^sha256:[0-9a-f]{64}$";

    /// <summary>
    /// Serializer options for wire DTOs: camelCase (web defaults), nulls omitted on
    /// write so Python defaults apply, enums never serialized as numbers.
    /// Hashing never uses these options - hashes are computed over canonical JSON
    /// of the exact received text.
    /// </summary>
    public static readonly JsonSerializerOptions WireOptions = CreateWireOptions();

    private static JsonSerializerOptions CreateWireOptions()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            NumberHandling = JsonNumberHandling.Strict,
        };
        options.MakeReadOnly(populateMissingResolver: true);
        return options;
    }
}

/// <summary>Decision actions (portfolio.py DecisionAction).</summary>
public static class FiDecisionAction
{
    public const string Hold = "HOLD";
    public const string Rebalance = "REBALANCE";
    public const string Bootstrap = "BOOTSTRAP";
}

/// <summary>Order sides (portfolio.py Side).</summary>
public static class FiSide
{
    public const string Buy = "BUY";
    public const string Sell = "SELL";
}
