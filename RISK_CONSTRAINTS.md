# Server-Side Risk Constraints

> **Philosophy:** Zero Trust. Never trust the AI agent to follow trading rules. All constraints must be enforced deterministically by the server before any trade is executed.

---

## 1. Risk Configuration

The risk validator is configured via `RiskValidatorOptions` in `appsettings.json`. These settings define the hard boundaries for all agents.

| Setting                    | Default Value    | Description                                                            |
| :------------------------- | :--------------- | :--------------------------------------------------------------------- |
| **MaxPositionSizePercent** | `0.50` (50%)     | Maximum percentage of total portfolio value allowed in a single asset. |
| **MinCashReserve**         | `$100`           | Minimum cash amount that must be kept liquid at all times.             |
| **MaxSingleTradeValue**    | `$5,000`         | Maximum value (USD) for a single buy order.                            |
| **MinOrderValue**          | `$10`            | Minimum value (USD) for an order to be accepted (avoids "dust").       |
| **AllowedAssets**          | `["BTC", "ETH"]` | Whitelist of assets that can be traded. All others are rejected.       |
| **MaxOrdersPerCycle**      | `5`              | Maximum number of orders an agent can submit in one execution cycle.   |
| **AllowLeverage**          | `false`          | Whether short selling or margin trading is permitted.                  |
| **MaxSlippagePercent**     | `0.02` (2%)      | (Future use) Maximum price deviation accepted.                         |

---

## 2. Validation Rules & Actions

The `RiskValidator` processes every order proposed by the AI. It applies rules in the following order:

### A. Hard Rejections (Order is Dropped)

These violations cause the specific order to be completely rejected.

1.  **Disallowed Asset**

    - **Rule:** The asset symbol is not in `AllowedAssets`.
    - **Action:** `REJECTED`.
    - **Reason:** "Asset 'XYZ' not in allowed list".

2.  **Zero/Negative Quantity**

    - **Rule:** `Quantity <= 0`.
    - **Action:** `REJECTED`.
    - **Reason:** "Quantity must be positive".

3.  **Dust Trade**

    - **Rule:** `OrderValue < MinOrderValue`.
    - **Action:** `REJECTED`.
    - **Reason:** "Order value $X below minimum $Y".

4.  **No Price Available**

    - **Rule:** Market data for the asset is missing or zero.
    - **Action:** `REJECTED`.
    - **Reason:** "No price available for 'XYZ'".

5.  **Selling What You Don't Own**

    - **Rule:** `Side == Sell` AND (`Position == null` OR `Position.Quantity <= 0`).
    - **Action:** `REJECTED`.
    - **Reason:** "No XYZ position to sell".

6.  **Short Selling** (if `AllowLeverage == false`)
    - **Rule:** `Side == Sell` AND `OrderQuantity > Position.Quantity`.
    - **Action:** `ADJUSTED` (see below) OR `REJECTED` if adjusted amount is too small.

---

### B. Adjustments (Order is Modified)

Instead of cancelling the trade, the system attempts to "fix" it to comply with safe limits.

1.  **Max Single Trade Value Exceeded**

    - **Rule:** `OrderValue > MaxSingleTradeValue`.
    - **Action:** `ADJUSTED`. Quantity is reduced so `OrderValue == MaxSingleTradeValue`.
    - **Reason:** "Quantity reduced from X to Y (max trade value)".

2.  **Insufficient Cash (Buy)**

    - **Rule:** `OrderValue > (AvailableCash - MinCashReserve)`.
    - **Action:** `ADJUSTED`. Quantity is reduced to match available cash.
    - **Exception:** If the adjusted value is below `MinOrderValue`, the order is `REJECTED`.

3.  **Position Size Limit (Buy)**

    - **Rule:** `NewPositionValue > (TotalPortfolioValue * MaxPositionSizePercent)`.
    - **Action:** `ADJUSTED`. Quantity is reduced so the final position size equals the limit.
    - **Exception:** If the allowed buy amount is below `MinOrderValue`, value is `REJECTED` ("Position limit reached").

4.  **Selling Too Much (Sell)**
    - **Rule:** `OrderQuantity > Position.Quantity` (and Leverage disabled).
    - **Action:** `ADJUSTED`. Quantity is reduced to `Position.Quantity` (sell 100%).

---

### C. Execution cycle Limits

1.  **Max Orders Per Cycle**
    - **Rule:** Agent submits more than `MaxOrdersPerCycle` orders.
    - **Action:** **Orders Truncated**. Only the first N orders are processed; the rest are ignored.
    - **Log:** Warning logged "Agent submitted X orders, truncated to Y".

---

## 3. Data Structures

### `TradeValidationResult`

Returned by `IRiskValidator.ValidateDecisionAsync`:

```csharp
public record TradeValidationResult(
    AgentDecision ValidatedDecision,      // Contains only VALID/ADJUSTED orders
    IReadOnlyList<RejectedOrder> RejectedOrders, // List of dropped orders with reasons
    bool HasWarnings                      // True if any orders were rejected/adjusted
);
```

### `RejectedOrder`

```csharp
public record RejectedOrder(
    TradeOrder OriginalOrder,
    string RejectionReason
);
```

---

## 4. Operational Logging

The system must log risk events to allow debugging of AI behavior:

- **Warning:** Logged when any order is **Rejected**.
  - _Format:_ "Order rejected for agent {Id}: {Asset} {Side} {Qty} - {Reason}"
- **Info/Warning:** Logged when an order is **Adjusted**.
  - _Format:_ "Order adjusted for agent {Id}: {Reason}"
- **Warning:** Logged when order list is **Truncated**.

This ensures that we can distinguish between "AI decided not to trade" vs "AI tried to trade but was blocked".
