using System.Text.Json.Nodes;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Request binding for signed engine responses (spec 14.6). The research engine echoes
/// <c>requestHash = "sha256:" + hex SHA-256(canonical JSON of the request body it received)</c> on
/// TransitionProposal and StrategyResult. The HTTP client sends exactly <see cref="Create{T}"/>'s
/// canonical text (wire options: camelCase, nulls omitted), and callers compute the expected hash
/// with the same function, so a response computed for any other request is detected. Canonical JSON
/// is idempotent, so the engine re-canonicalizing the parsed body reproduces the same hash.
/// </summary>
public static class FiRequestBody
{
    /// <summary>Serializes the request once into its canonical body text and hashes that text.</summary>
    public static (string Text, string Hash) Create<T>(T request)
    {
        JsonNode node = FiWire.ToNode(request);
        var text = CanonicalJson.Serialize(node);
        return (text, CanonicalJson.Sha256(text));
    }

    /// <summary>Hash of the canonical body that the client sends for <paramref name="request"/>.</summary>
    public static string Hash<T>(T request) => Create(request).Hash;
}
