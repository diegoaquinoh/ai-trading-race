namespace AiTradingRace.Domain.Entities.FixedIncome;

/// <summary>One competitor (strategy x repetition) inside a run, with its own isolated portfolio.</summary>
public class StrategyInstance
{
    public long Id { get; set; }

    public string RunId { get; set; } = string.Empty;

    public string StrategyId { get; set; } = string.Empty;

    /// <summary>cash_reference | quant_policy | single_agent | specialist_team.</summary>
    public string StrategyKind { get; set; } = string.Empty;

    public string StrategyConfigId { get; set; } = string.Empty;

    public int Repetition { get; set; }

    public string PortfolioId { get; set; } = string.Empty;

    public string? Label { get; set; }
}
