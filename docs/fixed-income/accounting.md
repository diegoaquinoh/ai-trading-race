# Portfolio accounting

Implements spec §9.1 and §16.5 (accounting rows). Code: `ai-trading-race-ml/research_engine/simulation/ledger.py`
(posting templates, reconciliation) and `valuation.py` (economic equity). Contracts:
`research_engine/contracts/portfolio.py` (`AccountCode`, `Journal`, `JournalLine`, `PortfolioState`).

## Units and rounding

- Face is USD face amount. Prices are per 100 face. Money is `Decimal` USD.
- Numerical outputs (prices, PVs, discount factors, DV01) come from the pricing port and are never rounded
  inside the engine. Money is rounded to **cents, ROUND_HALF_UP** (`contracts.common.money`) only at these
  posting boundaries:
  - fill consideration `face/100 × dirty execution price`; clean principal `face/100 × clean execution price`
    (accrued paid/received = consideration − clean principal, so the split sums exactly);
  - fees `face/1e6 × commission`, analytic spread cost `face/100 × |execution − reference|`;
  - coupon `entitled face/100 × coupon per 100`, redemption `entitled face/100 × redemption per 100`;
  - FIFO relief of a partially sold lot (pro rata on remaining cost, rounded); a fully consumed lot releases
    its exact remaining balances, so no residual cents remain;
  - each position PV, each discounted pending settlement, each entitlement adjustment;
  - the mark-to-market delta (economic equity − book equity, after the components above are rounded).
- Every journal line has exactly one non-zero side in cents; every journal balances (contract validators).

## Chart of accounts

| Account | Type | Balance mirrored in `PortfolioState` |
|---|---|---|
| `CASH` | asset | `cash_usd` (settled cash) |
| `BOND_PRINCIPAL` | asset | Σ `lot.principal_cost_usd` (remaining clean cost) |
| `ACCRUED_INTEREST_PURCHASED` | asset | Σ `lot.accrued_purchased_usd` |
| `SETTLEMENT_RECEIVABLE` | asset | Σ pending SELL settlement cash |
| `SETTLEMENT_PAYABLE` | liability | Σ pending BUY settlement cash (consideration + fees) |
| `MARK_ADJUSTMENT` | asset (contra) | `booked_unrealized_usd` |
| `CAPITAL` | equity | `external_capital_usd` |
| `INTEREST_INCOME` | income | `interest_income_usd` |
| `REALIZED_GAIN_LOSS` | income | `realized_gain_loss_usd` |
| `UNREALIZED_GAIN_LOSS` | income | `booked_unrealized_usd` (always equal and opposite to `MARK_ADJUSTMENT`) |
| `TRANSACTION_FEES` | expense | `transaction_fees_usd` |

`spread_cost_usd` is analytic only: the spread is embedded in execution prices and therefore already inside
realized/unrealized results. Reserved cash for ACCEPTED purchase orders (`reserved_cash_usd`) is a funding
control, not a ledger balance.

Book equity = capital + interest income + realized + unrealized − fees
= cash + principal + accrued purchased + receivables − payables + mark adjustment.

## Posting templates

Signs: Dr = debit, Cr = credit. A zero amount produces no line. Journal id `jnl:<event_id>`; the cash-interest
journal under a valuation event is `jnl:<event_id>:cash-interest`; line ids `<journal_id>:<nn>` (digest-tailed by `make_id` past 160 characters).

### `capital_flow_v1` (event `capital_flow`)
| Dr | Cr | Amount |
|---|---|---|
| CASH | CAPITAL | flow amount (withdrawal: reversed sides; cannot exceed settled cash − reserved cash − committed settlement payables, else `withdrawal_exceeds_available_cash`) |

### `buy_fill_v1` (event `execution_observation`, side BUY)
| Dr | Cr | Amount |
|---|---|---|
| BOND_PRINCIPAL | | clean principal `face/100 × (ask + slippage)` |
| ACCRUED_INTEREST_PURCHASED | | consideration − clean principal |
| | SETTLEMENT_PAYABLE | consideration |
| TRANSACTION_FEES | SETTLEMENT_PAYABLE | fees |

Creates a FIFO lot (`lot:<fill_id>`, trade date = session, settlement date = T+lag), raises economic face,
leaves settled face and cash unchanged, releases the order reservation and creates
`PendingSettlement(stl:<fill_id>)` for consideration + fees.

### `buy_settlement_v1` (event `settlement_due`)
| Dr | Cr | Amount |
|---|---|---|
| SETTLEMENT_PAYABLE | CASH | payable |

Settled face += face. Settlement that would make settled cash negative is an invariant error (no leverage).

### `sell_fill_v1` (event `execution_observation`, side SELL)
FIFO relief removes `face` from the oldest lots: relieved principal P and relieved purchased accrued A.
Clean proceeds C = `face/100 × (bid − slippage)`; accrued received R = consideration − C.

| Dr | Cr | Amount |
|---|---|---|
| SETTLEMENT_RECEIVABLE | | consideration − fees |
| TRANSACTION_FEES | | fees |
| | BOND_PRINCIPAL | P |
| | ACCRUED_INTEREST_PURCHASED | A (purchased-accrued recovery) |
| | REALIZED_GAIN_LOSS | C − P (Dr if negative) |
| | INTEREST_INCOME | R − A (Dr if negative) |

Economic face −= face; settled face unchanged until settlement. Long-only: selling more than economic face is
an invariant error.

### `sell_settlement_v1` (event `settlement_due`)
| Dr | Cr | Amount |
|---|---|---|
| CASH | SETTLEMENT_RECEIVABLE | receivable |

Settled face −= face.

### `coupon_payment_v1` (event `coupon_payment`)
Entitled face = face **settled strictly before the payment date** (see Entitlement). Amount K =
`entitled/100 × coupon per 100`. Recovery Q = Σ remaining purchased accrued of held lots whose settlement date
is strictly before the payment date (those balances are then zeroed).

| Dr | Cr | Amount |
|---|---|---|
| CASH | | K |
| | ACCRUED_INTEREST_PURCHASED | Q |
| | INTEREST_INCOME | K − Q (Dr if negative) |

### `redemption_v1` (event `redemption`)
Principal is credited exactly once: entitled face F (settled before the payment date), cash
`F/100 × redemption per 100`, clean cost of all relieved lots P.

| Dr | Cr | Amount |
|---|---|---|
| CASH | | redemption cash |
| | BOND_PRINCIPAL | P |
| | REALIZED_GAIN_LOSS | cash − P (Dr if negative) |

Economic and settled face fall by F. The redemption (priority 20) precedes the final coupon (priority 30) at
the same instant; relieved lots keep their purchased-accrued balance at zero face so the final coupon recovers
it, after which the empty lot and position are removed. Instruments are not tradable when a fill would settle on
or after maturity, so no settlement can straddle the redemption.

### `mark_to_market_v1` (event `valuation_mark`, complete valuations only)
Δ = economic equity − book equity (cents).

| Dr | Cr | Amount |
|---|---|---|
| MARK_ADJUSTMENT | UNREALIZED_GAIN_LOSS | Δ (reversed when negative) |

After this posting book equity equals economic NAV exactly; the reconciliation requires a zero difference for
complete valuations. Incomplete or stale valuations post nothing.

### `cash_interest_v1` (event `valuation_mark`)
| Dr | Cr | Amount |
|---|---|---|
| CASH | INTEREST_INCOME | settled cash × `ExecutionModel.cash_interest_rate` × days / 360 |

Days run from `cash_flows_processed_through` (the previous valuation date) to the valuation date. The default
and the reproducible fixture use a zero rate, so no journal is produced.

## Entitlement

A holder is entitled to a payment on adjusted payment date P for face whose settlement date is strictly before
P. Settlements and payments are effective at 09:00 New York on their date, with settlements sorting first;
the engine therefore measures entitlement as current settled face, undoing same-day deliveries:
`settled now − buys settled on P + sells settled on P + face redeemed on P`. Consequences:

- a purchase that settles on P is not entitled (its price at settlement P excludes the payment and accrued
  restarts at zero);
- a sale that settles on or after P leaves the seller entitled;
- a purchase that settled before P is entitled.

Valuation applies the same rule to unsettled trades: a pending purchase removes the PV of payments in
`(valuation date, settlement date]`, a pending sale adds it back.

## Lots and realized results

Lot method `fifo_v1`. Realized clean gain/loss = clean proceeds − relieved clean cost (sales) or redemption
cash − relieved clean cost. Accrued interest is never realized as price gain: it flows to interest income net
of the purchased-accrued recovery.

## Economic equity (valuation)

`equity = settled cash + economic bond value + PV(receivables) − PV(payables)`.

- Economic bond value = Σ valuation-date dirty PV of each position's economic face
  (`PricingPort.value_position`) plus entitlement adjustments. Accrued interest is inside the PV and is never
  added separately.
- Pending settlement cash is discounted from its settlement date to the valuation date with
  `PricingPort.discount_factor`; if unavailable, the valuation is incomplete (no silent anchor mixing).
- A coupon moves value from the bond PV into cash on the payment date, so NAV has no artificial jump.
- Mark policy is immutable per experiment: `synthetic_curve_model_v1` in synthetic mode; under an observed
  policy the mark source supplies quotes and a missing quote makes the valuation incomplete rather than
  substituting the model. Settlement-based quotes are normalized to the valuation anchor with the discount
  factor.
- Mark age above `RiskPolicy.max_mark_age_business_days` marks the position stale and the valuation
  incomplete; stale marks block dependent discretionary decisions.
- Portfolio effective duration = DV01 × 10,000 / equity (cash at zero duration); DV01 is the sum of position
  parallel DV01s (positive = gain for a 1 bp fall).

## Reconciliation report

Every proposal carries a `ReconciliationReport`:

1. every journal balances and has at least two lines;
2. prior state balances + Σ journal lines = new state balances, for **every** account, and the new trial
   balance sums to zero;
3. per position, Σ lot face = economic face and settled face = economic − pending buys + pending sells;
   no pending settlement without a position; reserved cash = Σ open order reservations;
4. for `VALUE_PORTFOLIO` with a complete valuation, book equity = economic equity exactly.

A failed reconciliation blocks the portfolio in the commit path (`OfflineStateStore`, mirrored by .NET).

## Attribution (reporting, `metrics-v1`)

Total = equity change − external flows = carry + price + costs + residual, with carry = Δ interest income +
Δ economic accrued value − Δ purchased-accrued balance, costs = −(Δ fees + Δ spread cost), price = Δ realized +
Δ unrealized − accrual component + Δ spread cost, residual = remainder (zero when book equity reconciles).
