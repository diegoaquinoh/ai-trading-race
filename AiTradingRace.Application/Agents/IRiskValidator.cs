using AiTradingRace.Application.Common.Models;

namespace AiTradingRace.Application.Agents;

/// <summary>
/// Validates agent trading decisions against server-side risk constraints.
/// Ensures trades comply with position limits, cash reserves, and allowed assets.
/// </summary>
public interface IRiskValidator
{
    /// <summary>
    /// Validates an agent's decision against risk constraints.
    /// Invalid orders are rejected, oversized orders are adjusted.
    /// </summary>
    /// <param name="decision">The raw decision from the AI agent.</param>
    /// <param name="portfolio">Current portfolio state.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Validation result with adjusted decision and rejected orders.</returns>
    Task<TradeValidationResult> ValidateDecisionAsync(
        AgentDecision decision,
        PortfolioState portfolio,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Result of validating an agent's trading decision.
/// </summary>
/// <param name="ValidatedDecision">The decision with only valid/adjusted orders.</param>
/// <param name="RejectedOrders">Orders that were rejected with reasons.</param>
/// <param name="HasWarnings">True if any orders were rejected or adjusted.</param>
public record TradeValidationResult(
    AgentDecision ValidatedDecision,
    IReadOnlyList<RejectedOrder> RejectedOrders,
    bool HasWarnings);

/// <summary>
/// An order that was rejected during validation.
/// </summary>
/// <param name="OriginalOrder">The original order that was rejected.</param>
/// <param name="Reason">The reason for rejection.</param>
public record RejectedOrder(
    TradeOrder OriginalOrder,
    string Reason);
