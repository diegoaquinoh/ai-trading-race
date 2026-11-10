using System.Text.Json;
using System.Text.Json.Nodes;
using AiTradingRace.Infrastructure.FixedIncome;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>Cross-runtime parity with Python canonical_json (contracts/test-vectors/canonical-json.json).</summary>
public class CanonicalJsonTests
{
    private static readonly JsonObject Vectors =
        (JsonObject)JsonNode.Parse(File.ReadAllText(FiRepo.PathOf("contracts", "test-vectors", "canonical-json.json")))!;

    public static IEnumerable<object[]> VectorIndexes() =>
        Enumerable.Range(0, ((JsonArray)Vectors["vectors"]!).Count).Select(i => new object[] { i });

    [Theory]
    [MemberData(nameof(VectorIndexes))]
    public void Serialize_MatchesPythonVector(int index)
    {
        var vector = Vectors["vectors"]![index]!;
        var canonical = CanonicalJson.Serialize(vector["input"]);

        Assert.Equal(vector["canonical"]!.GetValue<string>(), canonical);
    }

    [Theory]
    [MemberData(nameof(VectorIndexes))]
    public void HashAndSignature_MatchPythonVector(int index)
    {
        var vector = Vectors["vectors"]![index]!;
        var key = System.Text.Encoding.UTF8.GetBytes(Vectors["signingKeyUtf8"]!.GetValue<string>());

        var hash = CanonicalJson.ContentHash(vector["input"]);

        Assert.Equal(vector["sha256"]!.GetValue<string>(), hash);
        Assert.Equal(vector["signature"]!.GetValue<string>(), CanonicalJson.Sign(hash, key));
        Assert.True(CanonicalJson.VerifySignature(hash, vector["signature"]!.GetValue<string>(), key));
    }

    [Theory]
    [InlineData("{\"a\":1.5}")]
    [InlineData("{\"a\":1.0}")]
    [InlineData("{\"a\":1e3}")]
    public void Serialize_RejectsNonIntegerNumbers(string json)
    {
        Assert.Throws<FormatException>(() => CanonicalJson.Canonicalize(json));
    }

    [Fact]
    public void Serialize_RejectsDuplicateKeys()
    {
        Assert.Throws<FormatException>(() => CanonicalJson.Canonicalize("{\"a\":1,\"a\":2}"));
    }

    [Fact]
    public void Serialize_EscapesLikePythonEnsureAscii()
    {
        var node = new JsonObject { ["s"] = "/\u007f\b\f\u2028\U0001F4C8\"\\" };

        Assert.Equal("{\"s\":\"/\\u007f\\b\\f\\u2028\\ud83d\\udcc8\\\"\\\\\"}", CanonicalJson.Serialize(node));
    }

    [Fact]
    public void Serialize_SortsKeysByCodePointNotUtf16()
    {
        // U+FF61 (BMP, above the surrogate range) sorts before U+1F600 by code point,
        // although its UTF-16 code unit is greater than the high surrogate 0xD83D.
        var node = new JsonObject { ["\U0001F600"] = 1, ["\uFF61"] = 2 };

        Assert.Equal("{\"\\uff61\":2,\"\\ud83d\\ude00\":1}", CanonicalJson.Serialize(node));
    }

    [Fact]
    public void Serialize_NormalizesNegativeZeroIntegerAndKeepsBigIntegers()
    {
        Assert.Equal("{\"a\":0,\"b\":123456789012345678901234567890}",
            CanonicalJson.Canonicalize("{\"b\":123456789012345678901234567890,\"a\":-0}"));
    }

    [Fact]
    public void EnvelopeHash_ExcludesHashAndSignatureFields()
    {
        var a = new JsonObject { ["x"] = "1", ["proposalHash"] = "sha256:aa", ["signature"] = "sig" };
        var b = new JsonObject { ["x"] = "1", ["proposalHash"] = null, ["signature"] = null };

        Assert.Equal(CanonicalJson.EnvelopeHash(a, "proposalHash"), CanonicalJson.EnvelopeHash(b, "proposalHash"));
        Assert.Equal(CanonicalJson.ContentHash(new JsonObject { ["x"] = "1" }), CanonicalJson.EnvelopeHash(a, "proposalHash"));
    }

    [Fact]
    public void VerifySignature_RejectsWrongKeyAndMissingSignature()
    {
        var hash = CanonicalJson.Sha256("{}");
        var signature = CanonicalJson.Sign(hash, "k1"u8.ToArray());

        Assert.False(CanonicalJson.VerifySignature(hash, signature, "k2"u8.ToArray()));
        Assert.False(CanonicalJson.VerifySignature(hash, null, "k1"u8.ToArray()));
        Assert.False(CanonicalJson.VerifySignature(hash, signature, Array.Empty<byte>()));
    }

    [Fact]
    public void Genesis_RoundTripsThroughParsingWithStableHash()
    {
        var genesis = Fi.Genesis();
        var text = CanonicalJson.Serialize(genesis);

        Assert.Equal(text, CanonicalJson.Canonicalize(text));
        Assert.Contains("\"blockedReason\":null", text);
        Assert.Contains("\"asOf\":\"2025-01-02T00:00:00Z\"", text);
        Assert.Equal(JsonValueKind.Number, JsonDocument.Parse(text).RootElement.GetProperty("version").ValueKind);
    }
}
