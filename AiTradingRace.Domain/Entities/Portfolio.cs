namespace AiTradingRace.Domain.Entities;

public class Portfolio
{
    public Guid Id { get; init; }

    public Guid AgentId { get; set; }

    public decimal Cash { get; set; }

    public string BaseCurrency { get; set; } = "USD";

    public ICollection<Position> Positions { get; set; } = new List<Position>();
}

