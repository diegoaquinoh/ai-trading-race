namespace AiTradingRace.Application.FixedIncome.Models;

public sealed record PagedResult<T>(IReadOnlyList<T> Items, int Page, int PageSize, int TotalCount)
{
    public const int DefaultPageSize = 50;
    public const int MaxPageSize = 200;

    public static (int Page, int PageSize) Normalize(int page, int pageSize)
    {
        var p = page < 1 ? 1 : page;
        var s = pageSize < 1 ? DefaultPageSize : Math.Min(pageSize, MaxPageSize);
        return (p, s);
    }
}
