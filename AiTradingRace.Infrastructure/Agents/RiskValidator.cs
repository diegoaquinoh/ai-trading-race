using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using AiTradingRace.Domain.Entities;
using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Validates agent trading decisions against server-side risk constraints.
/// Adjusts or rejects orders that violate position limits, cash reserves, or allowed assets.
/// </summary>
public sealed class RiskValidator : IRiskValidator
{
    private readonly RiskValidatorOptions _options;
    private readonly TradingDbContext _dbContext;
    private readonly ILogger<RiskValidator> _logger;

    public RiskValidator(
        IOptions<RiskValidatorOptions> options,
        TradingDbContext dbContext,
        ILogger<RiskValidator> logger)
    {
        _options = options.Value;
        _dbContext = dbContext;
        _logger = logger;
    }

    /// <inheritdoc />
    public async Task<TradeValidationResult> ValidateDecisionAsync(
        AgentDecision decision,
        PortfolioState portfolio,
        CancellationToken cancellationToken = default)
    {
        _logger.LogDebug("Validating {OrderCount} orders for agent {AgentId}",
            decision.Orders.Count, decision.AgentId);

        var validOrders = new List<TradeOrder>();
        var rejectedOrders = new List<RejectedOrder>();

        // Get latest prices for validation
        var latestPrices = await GetLatestPricesAsync(cancellationToken);

        // Limit orders per cycle
        var ordersToProcess = decision.Orders.Take(_options.MaxOrdersPerCycle).ToList();
        if (decision.Orders.Count > _options.MaxOrdersPerCycle)
        {
            _logger.LogWarning("Agent {AgentId} submitted {Count} orders, truncated to {Max}",
                decision.AgentId, decision.Orders.Count, _options.MaxOrdersPerCycle);
        }

        // Track simulated portfolio state for multi-order validation
        var simulatedCash = portfolio.Cash;
        var simulatedPositions = portfolio.Positions.ToDictionary(
            p => p.AssetSymbol.ToUpperInvariant(),
            p => p.Quantity);

        foreach (var order in ordersToProcess)
        {
            var validationResult = ValidateSingleOrder(
                order,
                simulatedCash,
                simulatedPositions,
                portfolio.TotalValue,
                latestPrices);

            if (validationResult.IsValid)
            {
                var finalOrder = validationResult.AdjustedOrder ?? order;
                validOrders.Add(finalOrder);

                // Update simulated state for next order
                var price = latestPrices.GetValueOrDefault(order.AssetSymbol.ToUpperInvariant(), 0m);
                var notional = finalOrder.Quantity * price;

                if (finalOrder.Side == TradeSide.Buy)
                {
                    simulatedCash -= notional;
                    simulatedPositions.TryGetValue(finalOrder.AssetSymbol.ToUpperInvariant(), out var qty);
                    simulatedPositions[finalOrder.AssetSymbol.ToUpperInvariant()] = qty + finalOrder.Quantity;
                }
                else if (finalOrder.Side == TradeSide.Sell)
                {
                    simulatedCash += notional;
                    simulatedPositions.TryGetValue(finalOrder.AssetSymbol.ToUpperInvariant(), out var qty);
                    simulatedPositions[finalOrder.AssetSymbol.ToUpperInvariant()] = qty - finalOrder.Quantity;
                }

                if (validationResult.WasAdjusted)
                {
                    _logger.LogInformation("Order adjusted for agent {AgentId}: {Asset} {Side} {OldQty} → {NewQty}",
                        decision.AgentId, order.AssetSymbol, order.Side, order.Quantity, finalOrder.Quantity);
                }
            }
            else
            {
                rejectedOrders.Add(new RejectedOrder(order, validationResult.Reason!));
                _logger.LogWarning("Order rejected for agent {AgentId}: {Asset} {Side} {Qty} - {Reason}",
                    decision.AgentId, order.AssetSymbol, order.Side, order.Quantity, validationResult.Reason);
            }
        }

        var validatedDecision = new AgentDecision(
            decision.AgentId,
            decision.CreatedAt,
            validOrders);

        _logger.LogInformation("Agent {AgentId}: {ValidCount} orders validated, {RejectedCount} rejected",
            decision.AgentId, validOrders.Count, rejectedOrders.Count);

        return new TradeValidationResult(
            validatedDecision,
            rejectedOrders,
            rejectedOrders.Count > 0);
    }

    private OrderValidation ValidateSingleOrder(
        TradeOrder order,
        decimal availableCash,
        Dictionary<string, decimal> positions,
        decimal totalPortfolioValue,
        Dictionary<string, decimal> latestPrices)
    {
        var symbol = order.AssetSymbol.ToUpperInvariant();

        // 1. Check allowed assets
        if (!_options.AllowedAssets.Contains(symbol))
        {
            return OrderValidation.Rejected($"Asset '{symbol}' not in allowed list");
        }

        // 2. Check quantity is positive
        if (order.Quantity <= 0)
        {
            return OrderValidation.Rejected("Quantity must be positive");
        }

        // 3. Get price
        if (!latestPrices.TryGetValue(symbol, out var price) || price <= 0)
        {
            return OrderValidation.Rejected($"No price available for '{symbol}'");
        }

        var orderValue = order.Quantity * price;

        // 4. Check minimum order value (dust prevention)
        if (orderValue < _options.MinOrderValue)
        {
            return OrderValidation.Rejected($"Order value ${orderValue:F2} below minimum ${_options.MinOrderValue:F2}");
        }

        positions.TryGetValue(symbol, out var currentPosition);

        if (order.Side == TradeSide.Buy)
        {
            return ValidateBuyOrder(order, symbol, price, orderValue, availableCash, currentPosition, totalPortfolioValue);
        }
        else if (order.Side == TradeSide.Sell)
        {
            return ValidateSellOrder(order, symbol, price, currentPosition);
        }

        // HOLD - no validation needed
        return OrderValidation.Valid();
    }

    private OrderValidation ValidateBuyOrder(
        TradeOrder order,
        string symbol,
        decimal price,
        decimal orderValue,
        decimal availableCash,
        decimal currentPosition,
        decimal totalPortfolioValue)
    {
        var adjustedQuantity = order.Quantity;
        var wasAdjusted = false;

        // Check max single trade value
        if (orderValue > _options.MaxSingleTradeValue)
        {
            adjustedQuantity = _options.MaxSingleTradeValue / price;
            orderValue = adjustedQuantity * price;
            wasAdjusted = true;
        }

        // Check cash availability (respecting reserve)
        var usableCash = availableCash - _options.MinCashReserve;
        if (orderValue > usableCash)
        {
            if (usableCash <= 0)
            {
                return OrderValidation.Rejected("Insufficient cash after reserve");
            }

            adjustedQuantity = usableCash / price;
            orderValue = adjustedQuantity * price;
            wasAdjusted = true;
        }

        // Check position size limit
        var newPositionValue = (currentPosition + adjustedQuantity) * price;
        var maxPositionValue = totalPortfolioValue * _options.MaxPositionSizePercent;

        if (newPositionValue > maxPositionValue)
        {
            var allowedQuantity = (maxPositionValue / price) - currentPosition;
            if (allowedQuantity <= 0)
            {
                return OrderValidation.Rejected($"Position limit reached for {symbol}");
            }

            adjustedQuantity = allowedQuantity;
            orderValue = adjustedQuantity * price;
            wasAdjusted = true;
        }

        // Final check on minimum order value after adjustments
        if (orderValue < _options.MinOrderValue)
        {
            return OrderValidation.Rejected($"Adjusted order value ${orderValue:F2} below minimum");
        }

        if (wasAdjusted)
        {
            var adjustedOrder = order with { Quantity = adjustedQuantity };
            return OrderValidation.Adjusted(adjustedOrder);
        }

        return OrderValidation.Valid();
    }

    private OrderValidation ValidateSellOrder(
        TradeOrder order,
        string symbol,
        decimal price,
        decimal currentPosition)
    {
        // Check if position exists
        if (currentPosition <= 0)
        {
            return OrderValidation.Rejected($"No {symbol} position to sell");
        }

        var adjustedQuantity = order.Quantity;
        var wasAdjusted = false;

        // Prevent short selling (if leverage not allowed)
        if (!_options.AllowLeverage && order.Quantity > currentPosition)
        {
            adjustedQuantity = currentPosition;
            wasAdjusted = true;
        }

        // Check minimum order value
        var orderValue = adjustedQuantity * price;
        if (orderValue < _options.MinOrderValue && adjustedQuantity < currentPosition)
        {
            // Allow selling entire position even if below minimum
            return OrderValidation.Rejected($"Order value ${orderValue:F2} below minimum");
        }

        if (wasAdjusted)
        {
            var adjustedOrder = order with { Quantity = adjustedQuantity };
            return OrderValidation.Adjusted(adjustedOrder);
        }

        return OrderValidation.Valid();
    }

    private async Task<Dictionary<string, decimal>> GetLatestPricesAsync(CancellationToken cancellationToken)
    {
        // Get all enabled assets
        var enabledAssets = await _dbContext.MarketAssets
            .AsNoTracking()
            .Where(a => a.IsEnabled)
            .ToListAsync(cancellationToken);

        var result = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);

        foreach (var asset in enabledAssets)
        {
            var latestCandle = await _dbContext.MarketCandles
                .AsNoTracking()
                .Where(c => c.MarketAssetId == asset.Id)
                .OrderByDescending(c => c.TimestampUtc)
                .FirstOrDefaultAsync(cancellationToken);

            if (latestCandle != null)
            {
                result[asset.Symbol] = latestCandle.Close;
            }
        }

        return result;
    }

    /// <summary>
    /// Internal result for single order validation.
    /// </summary>
    private sealed record OrderValidation(
        bool IsValid,
        bool WasAdjusted,
        TradeOrder? AdjustedOrder,
        string? Reason)
    {
        public static OrderValidation Valid() => new(true, false, null, null);
        public static OrderValidation Adjusted(TradeOrder adjustedOrder) => new(true, true, adjustedOrder, null);
        public static OrderValidation Rejected(string reason) => new(false, false, null, reason);
    }
}
