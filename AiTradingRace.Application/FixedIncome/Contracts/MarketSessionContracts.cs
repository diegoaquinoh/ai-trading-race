using System.Text.Json.Nodes;

namespace AiTradingRace.Application.FixedIncome.Contracts;

// Wire shapes of the research-engine market-session and bootstrap endpoints
// (GET /internal/v1/market/sessions, POST /internal/v1/simulation/bootstrap-allocation).
// Instants are UTC strings ending in "Z", dates "YYYY-MM-DD", decimals strings.

/// <summary>GET /internal/v1/market/sessions?start=&amp;end= response.</summary>
public sealed record MarketSessionsDto
{
    public string DataMode { get; init; } = string.Empty;
    public string UniverseVersion { get; init; } = string.Empty;

    /// <summary>Stable universe id; experiments may reference the universe by id or by version.</summary>
    public string? UniverseId { get; init; }

    public List<MarketSessionDto> Sessions { get; init; } = new();
}

/// <summary>
/// One supported market session and its frozen common inputs. A session whose curve is
/// not READY, not available by <see cref="DecisionAsOf"/>, or flagged as a gap skips the
/// matched decision cycle for every competitor (spec 15.3).
/// </summary>
public sealed record MarketSessionDto
{
    public string SessionDate { get; init; } = string.Empty;
    public string? MarketSnapshotId { get; init; }
    public string? MarketSnapshotHash { get; init; }
    public string? CurveSnapshotId { get; init; }
    public string? CurveStatus { get; init; }
    public string? ObservedAt { get; init; }
    public string? AvailableAt { get; init; }
    public string? DecisionAsOf { get; init; }
    public string? ExecutionObservationAt { get; init; }

    /// <summary>Optional end-of-day valuation instant; .NET derives 20:00 America/New_York when absent.</summary>
    public string? ValuationAt { get; init; }

    public bool Gap { get; init; }
    public string? GapReason { get; init; }
}

/// <summary>POST /internal/v1/simulation/bootstrap-allocation request.</summary>
public sealed record BootstrapAllocationRequestDto
{
    public string SchemaVersion { get; init; } = FiContract.SchemaVersion;
    public string SessionDate { get; init; } = string.Empty;
    public string UniverseVersion { get; init; } = string.Empty;
    public RiskPolicyDto RiskPolicy { get; init; } = new();
}

/// <summary>
/// Common bootstrap allocation (spec 10.1) computed once by the engine and applied
/// identically to every actively invested competitor. <see cref="Raw"/> keeps the exact
/// response for the audit trail.
/// </summary>
public sealed record BootstrapAllocationDto
{
    public string Version { get; init; } = string.Empty;
    public string SessionDate { get; init; } = string.Empty;
    public List<TargetWeightDto> Targets { get; init; } = new();
    public JsonNode? Buckets { get; init; }
    public JsonObject Raw { get; init; } = new();
}
