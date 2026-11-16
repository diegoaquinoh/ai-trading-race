using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Canonical JSON identical to Python
/// <c>json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)</c>
/// as used by research_engine.contracts.common.canonical_json:
/// <list type="bullet">
/// <item>object keys sorted by Unicode code point (Python str ordering);</item>
/// <item>compact separators, no whitespace;</item>
/// <item>strings escape <c>"</c> <c>\</c> <c>\b \f \n \r \t</c>; every other character outside
/// printable ASCII 0x20-0x7E (control characters, DEL, non-ASCII) becomes a lowercase
/// <c>\uXXXX</c> escape, using UTF-16 surrogate pairs above the BMP; <c>/</c> is not escaped;</item>
/// <item>integers are emitted as-is; non-integer numbers are rejected (contracts use decimal strings).</item>
/// </list>
/// Pinned by contracts/test-vectors/canonical-json.json.
/// </summary>
public static class CanonicalJson
{
    private const string HexDigits = "0123456789abcdef";

    public static string Serialize(JsonNode? node)
    {
        var builder = new StringBuilder();
        try
        {
            Write(node, builder, "$");
        }
        catch (ArgumentException ex)
        {
            // JsonObject materializes lazily and throws on duplicate property names.
            throw new FormatException($"Invalid JSON object: {ex.Message}", ex);
        }

        return builder.ToString();
    }

    /// <summary>Parses JSON text and returns its canonical form.</summary>
    public static string Canonicalize(string jsonText)
    {
        JsonNode? node;
        try
        {
            node = JsonNode.Parse(jsonText);
        }
        catch (JsonException ex)
        {
            throw new FormatException($"Invalid JSON: {ex.Message}", ex);
        }

        return Serialize(node);
    }

    /// <summary>sha256:&lt;lowercase hex&gt; of the UTF-8 bytes of the text.</summary>
    public static string Sha256(string text)
    {
        var digest = SHA256.HashData(Encoding.UTF8.GetBytes(text));
        return FiContract.HashPrefix + Convert.ToHexString(digest).ToLowerInvariant();
    }

    /// <summary>Content hash of a node: sha256 over its canonical JSON.</summary>
    public static string ContentHash(JsonNode? node) => Sha256(Serialize(node));

    /// <summary>hmac-sha256:&lt;hex&gt; over the ASCII bytes of the hash string (Python sign_hash).</summary>
    public static string Sign(string hashValue, byte[] key)
    {
        if (key is null || key.Length == 0)
        {
            throw new InvalidOperationException("Signing key must be configured.");
        }

        var mac = HMACSHA256.HashData(key, Encoding.ASCII.GetBytes(hashValue));
        return FiContract.SignaturePrefix + Convert.ToHexString(mac).ToLowerInvariant();
    }

    /// <summary>Constant-time signature verification.</summary>
    public static bool VerifySignature(string hashValue, string? signature, byte[] key)
    {
        if (key is null || key.Length == 0 || string.IsNullOrEmpty(signature))
        {
            return false;
        }

        var expected = Encoding.ASCII.GetBytes(Sign(hashValue, key));
        var actual = Encoding.ASCII.GetBytes(signature);
        return CryptographicOperations.FixedTimeEquals(expected, actual);
    }

    /// <summary>
    /// Hash payload of a signed envelope: a copy of the object without the hash and
    /// signature fields (TransitionProposal: proposalHash/signature; StrategyResult:
    /// resultHash/signature).
    /// </summary>
    public static string EnvelopeHash(JsonObject envelope, string hashField, string signatureField = "signature")
    {
        var copy = (JsonObject)envelope.DeepClone();
        copy.Remove(hashField);
        copy.Remove(signatureField);
        return ContentHash(copy);
    }

    private static void Write(JsonNode? node, StringBuilder builder, string path)
    {
        switch (node)
        {
            case null:
                builder.Append("null");
                return;
            case JsonObject obj:
                WriteObject(obj, builder, path);
                return;
            case JsonArray array:
                builder.Append('[');
                for (var i = 0; i < array.Count; i++)
                {
                    if (i > 0)
                    {
                        builder.Append(',');
                    }

                    Write(array[i], builder, $"{path}[{i}]");
                }

                builder.Append(']');
                return;
            case JsonValue value:
                WriteValue(value, builder, path);
                return;
            default:
                throw new FormatException($"Unsupported JSON node at {path}.");
        }
    }

    private static void WriteObject(JsonObject obj, StringBuilder builder, string path)
    {
        var properties = obj.ToList();
        properties.Sort((a, b) => CompareCodePoints(a.Key, b.Key));

        builder.Append('{');
        for (var i = 0; i < properties.Count; i++)
        {
            if (i > 0)
            {
                builder.Append(',');
                if (string.Equals(properties[i].Key, properties[i - 1].Key, StringComparison.Ordinal))
                {
                    throw new FormatException($"Duplicate key '{properties[i].Key}' at {path}.");
                }
            }

            WriteString(properties[i].Key, builder);
            builder.Append(':');
            Write(properties[i].Value, builder, $"{path}.{properties[i].Key}");
        }

        builder.Append('}');
    }

    private static void WriteValue(JsonValue value, StringBuilder builder, string path)
    {
        switch (value.GetValueKind())
        {
            case JsonValueKind.String:
                WriteString(ReadString(value), builder);
                return;
            case JsonValueKind.True:
                builder.Append("true");
                return;
            case JsonValueKind.False:
                builder.Append("false");
                return;
            case JsonValueKind.Null:
                builder.Append("null");
                return;
            case JsonValueKind.Number:
                WriteInteger(value, builder, path);
                return;
            default:
                throw new FormatException($"Unsupported JSON value at {path}.");
        }
    }

    private static string ReadString(JsonValue value)
    {
        if (value.TryGetValue<string>(out var text))
        {
            return text;
        }

        // Values created from other CLR types (char, Guid, DateTime...) - read their JSON string form.
        using var document = JsonDocument.Parse(value.ToJsonString());
        return document.RootElement.GetString() ?? string.Empty;
    }

    private static void WriteInteger(JsonValue value, StringBuilder builder, string path)
    {
        var raw = value.ToJsonString();
        if (raw.Length == 0 || raw.IndexOfAny(new[] { '.', 'e', 'E' }) >= 0 ||
            !BigInteger.TryParse(raw, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var integer))
        {
            throw new FormatException(
                $"Non-integer JSON number '{raw}' at {path}: hashed contract payloads must use decimal strings.");
        }

        builder.Append(integer.ToString(CultureInfo.InvariantCulture));
    }

    private static void WriteString(string text, StringBuilder builder)
    {
        builder.Append('"');
        foreach (var c in text)
        {
            switch (c)
            {
                case '"':
                    builder.Append("\\\"");
                    break;
                case '\\':
                    builder.Append("\\\\");
                    break;
                case '\b':
                    builder.Append("\\b");
                    break;
                case '\f':
                    builder.Append("\\f");
                    break;
                case '\n':
                    builder.Append("\\n");
                    break;
                case '\r':
                    builder.Append("\\r");
                    break;
                case '\t':
                    builder.Append("\\t");
                    break;
                default:
                    if (c >= 0x20 && c <= 0x7E)
                    {
                        builder.Append(c);
                    }
                    else
                    {
                        // UTF-16 code units: supplementary characters become surrogate pairs, as in Python.
                        builder.Append("\\u")
                            .Append(HexDigits[(c >> 12) & 0xF])
                            .Append(HexDigits[(c >> 8) & 0xF])
                            .Append(HexDigits[(c >> 4) & 0xF])
                            .Append(HexDigits[c & 0xF]);
                    }

                    break;
            }
        }

        builder.Append('"');
    }

    /// <summary>Orders strings by Unicode code point, matching Python's str comparison.</summary>
    internal static int CompareCodePoints(string a, string b)
    {
        var i = 0;
        var j = 0;
        while (i < a.Length && j < b.Length)
        {
            var ca = ReadCodePoint(a, ref i);
            var cb = ReadCodePoint(b, ref j);
            if (ca != cb)
            {
                return ca < cb ? -1 : 1;
            }
        }

        return (a.Length - i).CompareTo(b.Length - j);
    }

    private static int ReadCodePoint(string s, ref int index)
    {
        var c = s[index];
        if (char.IsHighSurrogate(c) && index + 1 < s.Length && char.IsLowSurrogate(s[index + 1]))
        {
            var cp = char.ConvertToUtf32(c, s[index + 1]);
            index += 2;
            return cp;
        }

        index++;
        return c;
    }
}
