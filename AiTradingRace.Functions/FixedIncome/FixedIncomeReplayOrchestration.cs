using AiTradingRace.Application.FixedIncome;

namespace AiTradingRace.Functions.FixedIncome;

/// <summary>Activity names of the fixed income durable orchestrations.</summary>
public static class FiActivityNames
{
    public const string PrepareRun = "FiPrepareRunActivity";
    public const string PreparePaperCycle = "FiPreparePaperCycleActivity";
    public const string ExecuteCycle = "FiExecuteCycleActivity";
    public const string FinalizeRun = "FiFinalizeRunActivity";
}

public sealed record FiReplayInput(string RunId);

public sealed record FiCycleActivityInput(string RunId, string CycleId);

/// <summary>Paper-cycle input; <see cref="SessionDate"/> is the America/New_York session date (YYYY-MM-DD).</summary>
public sealed record FiPaperCycleInput(string RunId, string SessionDate);

public sealed record FiFinalizeInput(string RunId, bool Succeeded, bool Cancelled, bool KeepRunning, string? Reason);

public sealed record FiOrchestrationOutcome(string RunId, string Status, int CyclesExecuted, string? Reason);

/// <summary>
/// The only orchestration capability the fixed income workflow needs: calling an activity
/// (with the host's retry policy). No clock, random or I/O access is exposed, which keeps
/// the orchestration deterministic under Durable Functions replay.
/// </summary>
public interface IFiOrchestrationContext
{
    Task<T> CallActivityAsync<T>(string activityName, object input);
}

/// <summary>
/// Deterministic workflow of <see cref="FixedIncomeReplayOrchestrator"/> and
/// <see cref="FixedIncomePaperCycleOrchestrator"/> (spec 15.1, 15.4): prepare → one activity
/// per cycle (each a checkpoint) → finalize. It reads no wall clock and generates no ids;
/// all ids come from the run plan, and every activity is idempotent through deterministic
/// command ids, so a retried activity cannot duplicate a financial effect.
/// </summary>
public static class FixedIncomeReplayOrchestration
{
    public static async Task<FiOrchestrationOutcome> RunReplayAsync(IFiOrchestrationContext context, FiReplayInput input)
    {
        FiRunPlan plan;
        try
        {
            plan = await context.CallActivityAsync<FiRunPlan>(FiActivityNames.PrepareRun, input.RunId);
        }
        catch (Exception ex)
        {
            var reason = $"{FiErrorScope.Source}: run preparation failed after retries (resumable): {Describe(ex)}";
            await FinalizeAsync(context, input.RunId, succeeded: false, cancelled: false, keepRunning: false, reason);
            return new FiOrchestrationOutcome(input.RunId, "failed", 0, reason);
        }

        return await ExecutePlanAsync(context, input.RunId, plan);
    }

    public static async Task<FiOrchestrationOutcome> RunPaperCycleAsync(IFiOrchestrationContext context, FiPaperCycleInput input)
    {
        FiRunPlan plan;
        try
        {
            plan = await context.CallActivityAsync<FiRunPlan>(FiActivityNames.PreparePaperCycle, input);
        }
        catch (Exception ex)
        {
            // A paper cycle with incomplete inputs is skipped; the forward run stays open.
            return new FiOrchestrationOutcome(input.RunId, "skipped", 0, $"{FiErrorScope.Source}: {Describe(ex)}");
        }

        return await ExecutePlanAsync(context, input.RunId, plan);
    }

    private static async Task<FiOrchestrationOutcome> ExecutePlanAsync(IFiOrchestrationContext context, string runId, FiRunPlan plan)
    {
        var forward = plan.RunType == "forward";
        switch (plan.Status)
        {
            case FiPlanStatus.Cancelled:
                return new FiOrchestrationOutcome(runId, "cancelled", 0, plan.Reason);
            case FiPlanStatus.Failed:
                await FinalizeAsync(context, runId, false, false, false, plan.Reason);
                return new FiOrchestrationOutcome(runId, "failed", 0, plan.Reason);
            case FiPlanStatus.NothingToDo:
                await FinalizeAsync(context, runId, true, false, forward && !plan.WindowComplete, plan.Reason);
                return new FiOrchestrationOutcome(runId, "nothing_to_do", 0, plan.Reason);
        }

        var executed = 0;
        foreach (var cycleId in plan.PendingCycleIds)
        {
            FiCycleResult result;
            try
            {
                result = await context.CallActivityAsync<FiCycleResult>(FiActivityNames.ExecuteCycle, new FiCycleActivityInput(runId, cycleId));
            }
            catch (Exception ex)
            {
                var reason = $"{FiErrorScope.Source}: cycle {cycleId} failed after retries (resumable from the last checkpoint): {Describe(ex)}";
                await FinalizeAsync(context, runId, false, false, false, reason);
                return new FiOrchestrationOutcome(runId, "failed", executed, reason);
            }

            executed++;
            if (result.Status == FiCycleRunStatus.Cancelled)
            {
                return new FiOrchestrationOutcome(runId, "cancelled", executed, result.Reason);
            }

            if (result.Status == FiCycleRunStatus.Failed)
            {
                await FinalizeAsync(context, runId, false, false, false, result.Reason);
                return new FiOrchestrationOutcome(runId, "failed", executed, result.Reason);
            }
        }

        var keepRunning = forward && !plan.WindowComplete;
        await FinalizeAsync(context, runId, true, false, keepRunning, null);
        return new FiOrchestrationOutcome(runId, keepRunning ? "running" : "completed", executed, null);
    }

    private static Task<bool> FinalizeAsync(IFiOrchestrationContext context, string runId, bool succeeded, bool cancelled, bool keepRunning, string? reason) =>
        context.CallActivityAsync<bool>(FiActivityNames.FinalizeRun, new FiFinalizeInput(runId, succeeded, cancelled, keepRunning, reason));

    private static string Describe(Exception ex) => ex.InnerException is { } inner ? $"{ex.Message} ({inner.Message})" : ex.Message;
}
