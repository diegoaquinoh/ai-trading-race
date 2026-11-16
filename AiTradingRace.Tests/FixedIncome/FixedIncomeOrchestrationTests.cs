using System.Text.Json;
using AiTradingRace.Application.FixedIncome;
using AiTradingRace.Application.FixedIncome.Options;
using AiTradingRace.Domain.Entities.FixedIncome;
using AiTradingRace.Functions.FixedIncome;
using AiTradingRace.Infrastructure.FixedIncome;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// Durable workflow logic without the Functions host: determinism under replay, one
/// activity per cycle, retry safety of activities, failure finalization, and the
/// 19:00 America/New_York paper-cycle schedule across daylight-saving changes.
/// </summary>
public sealed class FixedIncomeOrchestrationTests
{
    /// <summary>Scripted context recording every activity call (what a durable history would contain).</summary>
    private sealed class ScriptedContext : IFiOrchestrationContext
    {
        private readonly Func<string, object, object?> _respond;

        public ScriptedContext(Func<string, object, object?> respond) => _respond = respond;

        public List<string> Calls { get; } = new();

        public Task<T> CallActivityAsync<T>(string activityName, object input)
        {
            Calls.Add(activityName + " " + JsonSerializer.Serialize(input));
            var response = _respond(activityName, input);
            return response is Exception ex ? Task.FromException<T>(ex) : Task.FromResult((T)response!);
        }
    }

    /// <summary>Context that runs the real activities (new DI scope per activity, like the isolated worker).</summary>
    private sealed class ActivityContext : IFiOrchestrationContext
    {
        private readonly FiRunHarness _harness;

        public ActivityContext(FiRunHarness harness) => _harness = harness;

        public List<string> Calls { get; } = new();

        public bool DuplicateDeliveries { get; init; }

        public async Task<T> CallActivityAsync<T>(string activityName, object input)
        {
            if (DuplicateDeliveries && activityName != FiActivityNames.FinalizeRun)
            {
                await InvokeAsync<T>(activityName, input);
            }

            return await InvokeAsync<T>(activityName, input);
        }

        private async Task<T> InvokeAsync<T>(string activityName, object input)
        {
            Calls.Add(activityName + " " + JsonSerializer.Serialize(input));
            using var scope = _harness.Provider.CreateScope();
            var activities = new FixedIncomeActivities(
                scope.ServiceProvider.GetRequiredService<IFixedIncomeCycleRunner>(),
                scope.ServiceProvider.GetRequiredService<IExperimentService>(),
                NullLogger<FixedIncomeActivities>.Instance);

            // Durable payloads are JSON: round-trip inputs and outputs like the runtime does.
            object result = activityName switch
            {
                FiActivityNames.PrepareRun => await activities.PrepareRun(RoundTrip<string>(input), CancellationToken.None),
                FiActivityNames.PreparePaperCycle => await activities.PreparePaperCycle(RoundTrip<FiPaperCycleInput>(input), CancellationToken.None),
                FiActivityNames.ExecuteCycle => await activities.ExecuteCycle(RoundTrip<FiCycleActivityInput>(input), CancellationToken.None),
                FiActivityNames.FinalizeRun => await activities.FinalizeRun(RoundTrip<FiFinalizeInput>(input), CancellationToken.None),
                _ => throw new InvalidOperationException(activityName),
            };
            return RoundTrip<T>(result);
        }

        private static T RoundTrip<T>(object value) => JsonSerializer.Deserialize<T>(JsonSerializer.Serialize(value))!;
    }

    private static FiRunPlan ReadyPlan(params string[] cycles) => new()
    {
        RunId = "run-o",
        Status = FiPlanStatus.Ready,
        CycleIds = cycles.ToList(),
        PendingCycleIds = cycles.ToList(),
        WindowComplete = true,
    };

    private static object? Respond(string name, object input, FiRunPlan plan, Func<string, FiCycleResult>? cycle = null) => name switch
    {
        FiActivityNames.PrepareRun => plan,
        FiActivityNames.ExecuteCycle => cycle?.Invoke(((FiCycleActivityInput)input).CycleId) ?? new FiCycleResult
        {
            RunId = "run-o",
            CycleId = ((FiCycleActivityInput)input).CycleId,
            Status = FiCycleRunStatus.Completed,
        },
        FiActivityNames.FinalizeRun => true,
        _ => throw new InvalidOperationException(name),
    };

    [Fact]
    public async Task ReplayOrchestration_IsDeterministic_OneActivityPerCycle_ThenFinalize()
    {
        var plan = ReadyPlan("cycle-2025-01-06", "cycle-2025-01-07", "cycle-2025-01-08");
        var first = new ScriptedContext((n, i) => Respond(n, i, plan));
        var replay = new ScriptedContext((n, i) => Respond(n, i, plan));

        var outcome = await FixedIncomeReplayOrchestration.RunReplayAsync(first, new FiReplayInput("run-o"));
        var replayed = await FixedIncomeReplayOrchestration.RunReplayAsync(replay, new FiReplayInput("run-o"));

        Assert.Equal(first.Calls, replay.Calls);
        Assert.Equal(outcome, replayed);
        Assert.Equal("completed", outcome.Status);
        Assert.Equal(3, outcome.CyclesExecuted);
        Assert.Equal(5, first.Calls.Count);
        Assert.StartsWith(FiActivityNames.PrepareRun, first.Calls[0]);
        Assert.All(first.Calls.Skip(1).Take(3), c => Assert.StartsWith(FiActivityNames.ExecuteCycle, c));
        Assert.Contains("\"Succeeded\":true", first.Calls[^1]);
    }

    [Fact]
    public async Task FailedCycle_FinalizesTheRunAsFailed_AndStopsBeforeLaterCycles()
    {
        var plan = ReadyPlan("c1", "c2", "c3");
        var context = new ScriptedContext((n, i) => Respond(n, i, plan, id => new FiCycleResult
        {
            RunId = "run-o",
            CycleId = id,
            Status = id == "c2" ? FiCycleRunStatus.Failed : FiCycleRunStatus.Completed,
            Reason = id == "c2" ? "initialization_failed: llm_rag: bootstrap rejected" : null,
        }));

        var outcome = await FixedIncomeReplayOrchestration.RunReplayAsync(context, new FiReplayInput("run-o"));

        Assert.Equal("failed", outcome.Status);
        Assert.DoesNotContain(context.Calls, c => c.Contains("\"c3\""));
        Assert.Contains("\"Succeeded\":false", context.Calls[^1]);
        Assert.Contains("initialization_failed", context.Calls[^1]);
    }

    [Fact]
    public async Task ActivityFailingAfterRetries_FinalizesAsResumableSourceFailure()
    {
        var plan = ReadyPlan("c1", "c2");
        var context = new ScriptedContext((n, i) => n == FiActivityNames.ExecuteCycle && ((FiCycleActivityInput)i).CycleId == "c2"
            ? new InvalidOperationException("activity failed after 3 attempts")
            : Respond(n, i, plan));

        var outcome = await FixedIncomeReplayOrchestration.RunReplayAsync(context, new FiReplayInput("run-o"));

        Assert.Equal("failed", outcome.Status);
        Assert.Equal(1, outcome.CyclesExecuted);
        Assert.StartsWith("source:", outcome.Reason);
        Assert.Contains("resumable", context.Calls[^1]);
    }

    [Fact]
    public async Task CancelledCycle_StopsWithoutOverwritingTheCancellation()
    {
        var plan = ReadyPlan("c1", "c2");
        var context = new ScriptedContext((n, i) => Respond(n, i, plan, id => new FiCycleResult
        {
            RunId = "run-o",
            CycleId = id,
            Status = FiCycleRunStatus.Cancelled,
        }));

        var outcome = await FixedIncomeReplayOrchestration.RunReplayAsync(context, new FiReplayInput("run-o"));

        Assert.Equal("cancelled", outcome.Status);
        Assert.DoesNotContain(context.Calls, c => c.StartsWith(FiActivityNames.FinalizeRun));
    }

    [Fact]
    public async Task ForwardPlan_KeepsTheRunOpenUntilItsWindowEnds()
    {
        var plan = ReadyPlan("c1") with { RunType = "forward", WindowComplete = false };
        var context = new ScriptedContext((n, i) => n == FiActivityNames.PreparePaperCycle ? plan : Respond(n, i, plan));

        var outcome = await FixedIncomeReplayOrchestration.RunPaperCycleAsync(context, new FiPaperCycleInput("run-o", "2025-01-06"));

        Assert.Equal("running", outcome.Status);
        Assert.Contains("\"KeepRunning\":true", context.Calls[^1]);
    }

    [Fact]
    public async Task EndToEnd_WithRealActivities_DuplicateActivityDeliveries_AndAReplayedOrchestrationAddNoEffects()
    {
        RunFootprint reference;
        using (var single = new FiRunHarness())
        {
            single.AddWeek();
            await single.StartRunAsync("run-durable", markRunning: false);
            var outcome = await FixedIncomeReplayOrchestration.RunReplayAsync(new ActivityContext(single), new FiReplayInput("run-durable"));
            Assert.Equal("completed", outcome.Status);
            Assert.Equal(5, outcome.CyclesExecuted);
            reference = await single.FootprintAsync("run-durable");
        }

        using var harness = new FiRunHarness();
        harness.AddWeek();
        await harness.StartRunAsync("run-durable", markRunning: false);

        // At-least-once delivery: every activity runs twice; the second run must be a no-op.
        var context = new ActivityContext(harness) { DuplicateDeliveries = true };
        var result = await FixedIncomeReplayOrchestration.RunReplayAsync(context, new FiReplayInput("run-durable"));

        Assert.Equal("completed", result.Status);
        await using (var db = harness.Db())
        {
            Assert.Equal(FiJobState.Completed, (await db.FiExperimentRuns.SingleAsync()).JobState);
        }

        var footprint = await harness.FootprintAsync("run-durable");
        Assert.True(footprint.SameAs(reference), $"{footprint} != {reference}");

        // Replaying the whole orchestration after completion changes nothing.
        var replay = await FixedIncomeReplayOrchestration.RunReplayAsync(new ActivityContext(harness), new FiReplayInput("run-durable"));
        Assert.Equal("nothing_to_do", replay.Status);
        Assert.True(footprint.SameAs(await harness.FootprintAsync("run-durable")));
        await harness.AssertJournalsBalanceAsync("run-durable");
    }

    [Theory]
    [InlineData("2025-01-15T00:00:00Z", true, "2025-01-14")]   // 19:00 EST (UTC-5), Tuesday
    [InlineData("2025-01-14T23:00:00Z", false, "2025-01-14")]  // 18:00 EST
    [InlineData("2025-07-15T23:00:00Z", true, "2025-07-15")]   // 19:00 EDT (UTC-4)
    [InlineData("2025-07-16T00:00:00Z", false, "2025-07-15")]  // 20:00 EDT
    [InlineData("2025-03-10T23:00:00Z", true, "2025-03-10")]   // first Monday after the spring change
    [InlineData("2025-11-04T00:00:00Z", true, "2025-11-03")]   // first Monday after the autumn change
    [InlineData("2025-01-18T00:00:00Z", true, "2025-01-17")]   // Friday evening
    [InlineData("2025-01-19T00:00:00Z", false, "2025-01-18")]  // Saturday: no session
    public void PaperSchedule_Fires_At1900NewYork_OnWeekdays_AcrossDaylightSaving(string utc, bool expected, string sessionDate)
    {
        var fired = PaperCycleSchedule.ShouldTrigger(DateTimeOffset.Parse(utc, System.Globalization.CultureInfo.InvariantCulture),
            19, FiMarketClock.MarketTimeZone, out var date);

        Assert.Equal(expected, fired);
        Assert.Equal(DateOnly.Parse(sessionDate, System.Globalization.CultureInfo.InvariantCulture), date);
    }

    [Fact]
    public void MarketClock_ResolvesScheduleInstantsWithDaylightSaving()
    {
        Assert.Equal(new DateTimeOffset(2025, 3, 8, 0, 0, 0, TimeSpan.Zero), FiMarketClock.DecisionAt(new DateOnly(2025, 3, 7)));
        Assert.Equal(new DateTimeOffset(2025, 3, 10, 23, 0, 0, TimeSpan.Zero), FiMarketClock.DecisionAt(new DateOnly(2025, 3, 10)));
        Assert.Equal(new DateTimeOffset(2025, 3, 11, 0, 0, 0, TimeSpan.Zero), FiMarketClock.ValuationAt(new DateOnly(2025, 3, 10)));
        Assert.Equal(new DateTimeOffset(2025, 1, 6, 13, 0, 0, TimeSpan.Zero), FiMarketClock.CapitalFlowAt(new DateOnly(2025, 1, 6)));
    }

    [Fact]
    public void PaperTriggerPlanner_RequiresConfiguration_AndUsesADeterministicInstanceId()
    {
        var due = DateTimeOffset.Parse("2025-01-15T00:00:00Z", System.Globalization.CultureInfo.InvariantCulture);

        Assert.False(PaperCycleTriggerPlanner.Plan(due, new PaperTradingOptions()).Trigger);

        var options = new PaperTradingOptions { Enabled = true, ExperimentId = "exp-paper", RunId = "run-paper" };
        var decision = PaperCycleTriggerPlanner.Plan(due, options);
        Assert.True(decision.Trigger);
        Assert.Equal("fi-paper-run-paper-2025-01-14", decision.InstanceId);
        Assert.Equal(decision, PaperCycleTriggerPlanner.Plan(due, options));
        Assert.False(PaperCycleTriggerPlanner.Plan(due.AddHours(1), options).Trigger);
    }

    [Fact]
    public void Ids_AreDeterministic_AndRespectTheOpaqueIdLimit()
    {
        Assert.Equal("cmd:run-1:cycle-2025-01-06:pf-1:process", FiIds.Command("run-1", "cycle-2025-01-06", "pf-1", "process"));
        Assert.Equal("dec:run-1:cycle-2025-01-06:llm_rag:0", FiIds.Decision("run-1", "cycle-2025-01-06", "llm_rag", 0));

        var longRun = new string('r', 80);
        var id = FiIds.Command(longRun, "cycle-2025-01-06", $"pf-{longRun}-llm_graph_specialist_team-r0", "process");
        Assert.True(id.Length <= FiIds.MaxLength);
        Assert.True(FiWire.IsOpaqueId(id));
        Assert.Equal(id, FiIds.Command(longRun, "cycle-2025-01-06", $"pf-{longRun}-llm_graph_specialist_team-r0", "process"));
        Assert.NotEqual(id, FiIds.Command(longRun, "cycle-2025-01-06", $"pf-{longRun}-llm_graph_specialist_team-r0", "value"));
    }
}
