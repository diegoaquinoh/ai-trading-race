using System.Text.Json.Nodes;

namespace AiTradingRace.Application.FixedIncome.Contracts;

/// <summary>
/// A contract payload exactly as received over the wire. Hashes and signatures are
/// always verified against <see cref="Node"/> parsed from <see cref="Text"/>, never
/// against a re-serialized DTO.
/// </summary>
public sealed class RawContractJson
{
    public RawContractJson(string text, JsonObject node)
    {
        Text = text ?? throw new ArgumentNullException(nameof(text));
        Node = node ?? throw new ArgumentNullException(nameof(node));
    }

    public string Text { get; }

    public JsonObject Node { get; }

    /// <summary>Parses JSON text into an object node; throws <see cref="FormatException"/> for non-objects.</summary>
    public static RawContractJson Parse(string text)
    {
        JsonNode? node;
        try
        {
            node = JsonNode.Parse(text);
        }
        catch (Exception ex) when (ex is System.Text.Json.JsonException or ArgumentException)
        {
            throw new FormatException($"Invalid JSON payload: {ex.Message}", ex);
        }

        if (node is not JsonObject obj)
        {
            throw new FormatException("Contract payload must be a JSON object.");
        }

        return new RawContractJson(text, obj);
    }
}
