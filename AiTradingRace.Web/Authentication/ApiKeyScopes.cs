using AiTradingRace.Domain.Entities;

namespace AiTradingRace.Web.Authentication;

/// <summary>
/// API key scopes and the role they grant. A key never acts above the scope it was issued
/// with, nor above its owner's current role: a "read" key created by an admin is a User.
/// </summary>
public static class ApiKeyScopes
{
    public const string Read = "read";
    public const string Write = "write";
    public const string Admin = "admin";

    private static readonly Dictionary<string, UserRole> RoleByScope = new(StringComparer.OrdinalIgnoreCase)
    {
        [Read] = UserRole.User,
        [Write] = UserRole.Operator,
        [Admin] = UserRole.Admin,
    };

    public static IReadOnlyCollection<string> All => RoleByScope.Keys;

    /// <summary>Splits a comma-separated scope list, trimming entries.</summary>
    public static IReadOnlyList<string> Parse(string? scopes) =>
        (scopes ?? string.Empty)
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    /// <summary>Scopes in <paramref name="scopes"/> that are not recognised.</summary>
    public static IReadOnlyList<string> Unknown(string? scopes) =>
        Parse(scopes).Where(s => !RoleByScope.ContainsKey(s)).ToList();

    /// <summary>Normalises a valid scope list to lower case without duplicates.</summary>
    public static string Normalize(string? scopes) =>
        string.Join(',', Parse(scopes).Select(s => s.ToLowerInvariant()).Distinct());

    /// <summary>
    /// The role an API key acts with: the highest role its recognised scopes grant, capped at
    /// the owner's role. Null when no recognised scope is present (the key gets no role).
    /// </summary>
    public static UserRole? EffectiveRole(UserRole ownerRole, string? scopes)
    {
        UserRole? granted = null;
        foreach (var scope in Parse(scopes))
        {
            if (RoleByScope.TryGetValue(scope, out var role) && (granted is null || role > granted))
            {
                granted = role;
            }
        }

        if (granted is null)
        {
            return null;
        }

        return granted.Value < ownerRole ? granted.Value : ownerRole;
    }
}
