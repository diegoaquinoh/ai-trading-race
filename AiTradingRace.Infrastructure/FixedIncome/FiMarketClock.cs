namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Proposed platform schedule (<c>schedule-ny-v1</c>, spec 6.4) expressed in
/// America/New_York through the IANA time-zone database, so daylight-saving
/// transitions need no configuration. Pure functions: no wall-clock reads. These
/// are schedule instants only; .NET never derives prices or accruals from them.
/// </summary>
public static class FiMarketClock
{
    public const string MarketTimeZoneId = "America/New_York";

    public static readonly TimeOnly CapitalFlowTime = new(8, 0);
    public static readonly TimeOnly DecisionTime = new(19, 0);
    public static readonly TimeOnly ValuationTime = new(20, 0);

    private static readonly Lazy<TimeZoneInfo> Market = new(() => Resolve(MarketTimeZoneId));

    public static TimeZoneInfo MarketTimeZone => Market.Value;

    public static TimeZoneInfo Resolve(string timeZoneId)
    {
        try
        {
            return TimeZoneInfo.FindSystemTimeZoneById(timeZoneId);
        }
        catch (TimeZoneNotFoundException) when (timeZoneId == MarketTimeZoneId)
        {
            // Windows hosts without ICU time-zone data.
            return TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
        }
    }

    /// <summary>UTC instant of a wall-clock time on a date in <paramref name="zone"/>.</summary>
    public static DateTimeOffset At(DateOnly date, TimeOnly time, TimeZoneInfo? zone = null)
    {
        var tz = zone ?? MarketTimeZone;
        var local = date.ToDateTime(time, DateTimeKind.Unspecified);
        var offset = tz.GetUtcOffset(local);
        return new DateTimeOffset(local, offset).ToUniversalTime();
    }

    public static DateTimeOffset CapitalFlowAt(DateOnly sessionDate) => At(sessionDate, CapitalFlowTime);

    public static DateTimeOffset DecisionAt(DateOnly sessionDate) => At(sessionDate, DecisionTime);

    public static DateTimeOffset ValuationAt(DateOnly sessionDate) => At(sessionDate, ValuationTime);

    /// <summary>Local wall-clock time of a UTC instant in <paramref name="zone"/>.</summary>
    public static DateTime ToLocal(DateTimeOffset instant, TimeZoneInfo? zone = null) =>
        TimeZoneInfo.ConvertTime(instant, zone ?? MarketTimeZone).DateTime;
}

/// <summary>
/// Forward paper-cycle trigger decision. The Functions timer fires hourly at minute 0
/// (NCRONTAB <c>0 0 * * * *</c>, UTC); this check fires once per day when the New York
/// local hour equals the configured decision hour (19:00) on a weekday. Exchange holidays
/// are resolved by the research engine's session calendar: a non-session date yields no
/// cycle. Using UTC + IANA conversion (instead of WEBSITE_TIME_ZONE) keeps the schedule
/// correct across daylight-saving changes and on Linux plans.
/// </summary>
public static class PaperCycleSchedule
{
    public static bool ShouldTrigger(DateTimeOffset utcNow, int decisionHour, TimeZoneInfo zone, out DateOnly sessionDate)
    {
        var local = FiMarketClock.ToLocal(utcNow, zone);
        sessionDate = DateOnly.FromDateTime(local);
        if (local.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday)
        {
            return false;
        }

        return local.Hour == decisionHour;
    }

    /// <summary>Latest session date whose decision time has passed at <paramref name="utcNow"/> (forward catch-up bound).</summary>
    public static DateOnly LatestDueSessionDate(DateTimeOffset utcNow, int decisionHour, TimeZoneInfo zone)
    {
        var local = FiMarketClock.ToLocal(utcNow, zone);
        var today = DateOnly.FromDateTime(local);
        return local.Hour >= decisionHour ? today : today.AddDays(-1);
    }
}
