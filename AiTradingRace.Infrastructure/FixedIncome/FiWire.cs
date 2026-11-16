using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>Strict, culture-invariant parsing/formatting of contract wire values.</summary>
public static partial class FiWire
{
    [GeneratedRegex(@"^-?\d+(\.\d+)?$", RegexOptions.CultureInvariant)]
    private static partial Regex DecimalPattern();

    [GeneratedRegex(FiContract.ContentHashPattern, RegexOptions.CultureInvariant)]
    private static partial Regex ContentHashRegex();

    [GeneratedRegex(FiContract.OpaqueIdPattern, RegexOptions.CultureInvariant)]
    private static partial Regex OpaqueIdRegex();

    [GeneratedRegex(FiContract.StrategyIdPattern, RegexOptions.CultureInvariant)]
    private static partial Regex StrategyIdRegex();

    public static bool IsContentHash(string? value) => value is not null && ContentHashRegex().IsMatch(value);

    public static bool IsOpaqueId(string? value) => value is not null && OpaqueIdRegex().IsMatch(value);

    public static bool IsStrategyId(string? value) => value is not null && StrategyIdRegex().IsMatch(value);

    /// <summary>Parses a decimal string (no exponent, no locale). Throws <see cref="FormatException"/>.</summary>
    public static decimal ParseDecimal(string? value, string field)
    {
        if (!TryParseDecimal(value, out var result))
        {
            throw new FormatException($"Field '{field}' is not a decimal string: '{value}'.");
        }

        return result;
    }

    public static bool TryParseDecimal(string? value, out decimal result)
    {
        result = 0m;
        if (string.IsNullOrEmpty(value) || !DecimalPattern().IsMatch(value))
        {
            return false;
        }

        return decimal.TryParse(value, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint,
            CultureInfo.InvariantCulture, out result);
    }

    public static decimal? ParseOptionalDecimal(string? value, string field) =>
        value is null ? null : ParseDecimal(value, field);

    /// <summary>True when the decimal string has at most two fractional digits (ledger cents).</summary>
    public static bool IsCents(string? value)
    {
        if (!TryParseDecimal(value, out _))
        {
            return false;
        }

        var dot = value!.IndexOf('.');
        return dot < 0 || value.Length - dot - 1 <= 2;
    }

    public static DateTimeOffset ParseInstant(string? value, string field)
    {
        if (string.IsNullOrEmpty(value) ||
            !DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var result))
        {
            throw new FormatException($"Field '{field}' is not an ISO-8601 instant: '{value}'.");
        }

        return result.ToUniversalTime();
    }

    public static DateOnly ParseDate(string? value, string field)
    {
        if (string.IsNullOrEmpty(value) ||
            !DateOnly.TryParseExact(value, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var result))
        {
            throw new FormatException($"Field '{field}' is not a YYYY-MM-DD date: '{value}'.");
        }

        return result;
    }

    /// <summary>Python utc_to_str: seconds precision unless sub-second component exists.</summary>
    public static string FormatInstant(DateTimeOffset value)
    {
        var utc = value.ToUniversalTime();
        var micro = (utc.Ticks % TimeSpan.TicksPerSecond) / 10;
        return micro == 0
            ? utc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)
            : utc.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", CultureInfo.InvariantCulture);
    }

    public static string FormatDate(DateOnly value) => value.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    public static string FormatDecimal(decimal value) => value.ToString(CultureInfo.InvariantCulture);

    public static string? FormatDecimal(decimal? value) => value?.ToString(CultureInfo.InvariantCulture);

    /// <summary>Serializes a wire DTO to a JSON node using the contract options.</summary>
    public static JsonNode ToNode<T>(T value) =>
        JsonSerializer.SerializeToNode(value, FiContract.WireOptions)
        ?? throw new InvalidOperationException("Serialization produced null.");

    public static T Deserialize<T>(JsonNode node) =>
        node.Deserialize<T>(FiContract.WireOptions)
        ?? throw new FormatException($"Payload could not be read as {typeof(T).Name}.");

    /// <summary>Canonical JSON text of a node, or "[]"/"{}" fallbacks for audit columns.</summary>
    public static string CanonicalOr(JsonNode? node, string fallback) =>
        node is null ? fallback : CanonicalJson.Serialize(node);

    public static JsonNode? TryParseNode(string? json)
    {
        if (string.IsNullOrEmpty(json))
        {
            return null;
        }

        try
        {
            return JsonNode.Parse(json);
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
