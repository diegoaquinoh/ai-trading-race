namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>
/// Immutable experiment definition version (spec 14.7, 16.1). A new configuration
/// is a new version; an existing (ExperimentId, Version) is never rewritten.
/// </summary>
public class ExperimentDefinition
{
    public long Id { get; set; }

    /// <summary>Stable opaque experiment identifier.</summary>
    public string ExperimentId { get; set; } = string.Empty;

    public int Version { get; set; }

    public string Name { get; set; } = string.Empty;

    public string? Description { get; set; }

    /// <summary>synthetic_curve | observed_security. Runs of different modes are never ranked together.</summary>
    public string DataMode { get; set; } = FiDataMode.SyntheticCurve;

    public string RiskPolicyId { get; set; } = string.Empty;

    public string ExecutionModelId { get; set; } = string.Empty;

    public string InstrumentUniverseVersion { get; set; } = string.Empty;

    public DateOnly StartDate { get; set; }

    public DateOnly EndDate { get; set; }

    public int Repetitions { get; set; } = 1;

    /// <summary>Canonical JSON text of the full definition as validated.</summary>
    public string DefinitionJson { get; set; } = string.Empty;

    /// <summary>sha256:&lt;hex&gt; of <see cref="DefinitionJson"/>.</summary>
    public string DefinitionHash { get; set; } = string.Empty;

    public string? CreatedBy { get; set; }

    public DateTimeOffset CreatedAt { get; set; }
}
