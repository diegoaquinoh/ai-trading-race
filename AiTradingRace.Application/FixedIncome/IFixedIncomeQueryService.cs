using AiTradingRace.Application.FixedIncome.Models;

namespace AiTradingRace.Application.FixedIncome;

/// <summary>
/// Read-only dashboard queries. Methods scoped to a parent (run, portfolio)
/// return null when the parent does not exist. Comparisons never rank runs with
/// incompatible data modes, policies or execution models together.
/// </summary>
public interface IFixedIncomeQueryService
{
    Task<PagedResult<RunSummaryView>> ListRunsAsync(RunListFilter filter, CancellationToken cancellationToken = default);

    Task<RunDetailView?> GetRunAsync(string runId, CancellationToken cancellationToken = default);

    Task<PagedResult<CycleView>?> GetRunCyclesAsync(string runId, int page, int pageSize, CancellationToken cancellationToken = default);

    Task<RunComparisonView?> GetRunComparisonAsync(string runId, CancellationToken cancellationToken = default);

    Task<ExperimentComparisonView?> GetExperimentComparisonAsync(string experimentId, CancellationToken cancellationToken = default);

    Task<PagedResult<DecisionSummaryView>?> ListRunDecisionsAsync(string runId, DecisionListFilter filter, CancellationToken cancellationToken = default);

    Task<DecisionDetailView?> GetDecisionAsync(string decisionId, CancellationToken cancellationToken = default);

    Task<PortfolioView?> GetPortfolioAsync(string portfolioId, CancellationToken cancellationToken = default);

    Task<PagedResult<ValuationView>?> GetValuationsAsync(string portfolioId, int page, int pageSize, bool? completeOnly, CancellationToken cancellationToken = default);

    Task<PagedResult<JournalView>?> GetJournalAsync(string portfolioId, JournalFilter filter, CancellationToken cancellationToken = default);

    Task<PagedResult<OrderView>?> GetOrdersAsync(string portfolioId, OrderFilter filter, CancellationToken cancellationToken = default);
}
