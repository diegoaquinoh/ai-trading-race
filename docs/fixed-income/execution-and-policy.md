# Execution, policy, event ordering and replay

Implements spec §6.4–6.5, §9.2–9.6, §10.1, §15 and §16.6 (duplicate/timeout/malformed rows). Code:
`ai-trading-race-ml/research_engine/simulation/{clock,engine,fills,policy,store}.py` and
`research_engine/experiments/{strategy,baselines,runner,manifest,metrics,report,parity}.py`.

## Schedule (`schedule-ny-v1`, America/New_York, stored as UTC)

| Time | Event |
|---|---|
| 08:00 | capital flow (first session) |
| 09:00 | settlements, coupons, redemptions on their business-day-adjusted date |
| 15:30 | session curve observation = execution observation for eligible orders |
| 17:00 | session end: next-session-only orders without a valid observation expire |
| 18:00 | reconstructed availability of the session curve |
| 19:00 | scheduled decision; `PROCESS_EVENTS` and `SUBMIT_DECISION` run at this instant |
| 20:00 | end-of-day `VALUE_PORTFOLIO` |

Calendar gaps (weekends/holidays) come from the pricing port's business-day calendar, never from 24-hour steps.
Fills are labelled `next_session_close_daily`; no next-open execution is claimed.

## Event ordering (`event-priority-v1`)

Events sort by (effective instant, type priority, stable event id). Priorities: capital 0, settlement 10,
redemption 20, coupon 30, execution observation 40, order expiry 45, valuation mark 50, cancellation 60,
orders submitted 70. Content-derived ids:

| Item | Id |
|---|---|
| order | `ord:<decision_id>:<security>` |
| fill / settlement / lot | `fill:<order_id>`, `stl:<fill_id>`, `lot:<fill_id>` |
| observation | `evt:obs:<session>:<batch priority 000>:<order_id>` (sorts sells first, then security) |
| expiry | `evt:expiry:<session>:<batch priority>:<order_id>` |
| settlement | `evt:settle:<settlement_id>` |
| coupon / redemption | `evt:coupon:<portfolio>:<security>:<payment date>`, `evt:redeem:...` |
| cancellation / submission | `evt:cancel:<order_id>:<new decision>`, `evt:submit:<decision_id>` |
| valuation | `val:<portfolio>:<UTC compact instant>`, event `evt:mark:<valuation_id>` |
| journal / line | `jnl:<event_id>[:suffix]`, `<journal_id>:<nn>` |
| cash flow | `cf:<event_id>` |
| runner command | `cmd:<run>:<strategy>:<session>:{process,decision,value}`, `...:init:capital` |
| decision | `dec:<run>:<strategy>:<session>:r<repetition>` |

Ids longer than 160 characters keep their first 127 characters verbatim (readable and order-preserving)
and replace only the tail with a 32-hex digest of the full text. Execution batches are not ordered by id text:
observations and expiries sort by session, batch priority (sells first), security id, then order id; the
zero-padded priority leads the event id, so the published `(effective_at, priority, event_id)` order agrees.

**The clock never moves backward.** `advance_to < state.as_of` is rejected. A transition derives only events in
`(state.as_of, horizon]`. If an order's eligible observation time has passed but that curve is not yet
available at `advance_to`, `PROCESS_EVENTS` stops just before the observation (new `as_of` clamped; the order is
neither filled nor expired) and other commands raise `DataNotYetAvailable`. A later session's quote is never
exposed early, and a no-op transition leaves state and version unchanged.

## Transition engine

`propose_transition(request, pricing, market, signing_key, *, mark_source=None, request_hash_override=None)
-> TransitionProposal` is pure (`request_hash_override`: the API binds `request_hash` to the exact JSON body
received; offline replay hashes the request model):

1. verify schema major, `portfolio_state_hash == portfolio_state.compute_hash()`, portfolio not blocked,
   monotonic clock, data mode;
2. derive and apply due events (settlements, entitled coupons/redemptions of held or ordered securities,
   observations/expiries of ACCEPTED orders; fill-created settlements are inserted dynamically);
3. apply the command: `CAPITAL_FLOW` (capital event), `SUBMIT_DECISION` (sizing + policy; on pass, cancel all
   unfilled intents, then submit new ones), `VALUE_PORTFOLIO` (valuation, MTM, breach list),
   `PROCESS_EVENTS` (step 2 only);
4. emit events, journals, orders, status changes, fills, settlements, cash flows, policy evaluation,
   valuation, reconciliation, `new_state` (version + 1, or `no_op` with the same version and state),
   `input_hashes` (`portfolioState`, `marketSnapshot` — `content_hash(None)` when absent — `riskPolicy`,
   `executionModel`), `request_hash`, `new_state_hash`, `proposal_hash = content_hash(hash_payload())`,
   `signature = sign_hash(proposal_hash, key)`.

The engine version string is `research-engine/<v>+simulation-v1+pricing:<pricing engine version>`.

## Decision sizing (spec 9.2)

- Weights must be finite, non-negative, reference the frozen universe at the decision session
  (`PricingPort.universe`) or `CASH-USD`, be unique, and sum to 1 ± 1e-6. Held securities omitted from the target
  are normalized to 0 and recorded in `normalization_notes`; a held security that is no longer tradable (e.g. its
fill would settle at or after maturity) is instead kept until redemption with no order
(`held_untradable_security_kept_until_redemption:<id>`). An explicit target that would require trading an
untradable security is rejected (`instrument_not_tradable:<id>`).
- Decision snapshot: own-portfolio valuation at decision time on the market snapshot's curve (NAV), and model
  dirty prices at the decision session's standard settlement. The market snapshot must be READY, available by
  decision time, hash-identical to `MarketDataPort.market_snapshot_id`, and no older than
  `max_mark_age_business_days`; otherwise discretionary decisions are rejected.
- Target face = `floor(weight × NAV × 100 / dirty / increment) × increment`; below minimum face → 0.
- |target weight − current weight| < 2 pp → no order, unless it is a sale that restores a breached limit.
- Order sequence: sells by security id, then buys by security id (`batch_priority`).
- Estimated execution price: model dirty ± (half-spread + slippage). Purchase reservation =
  `face/100 × (estimated ask dirty + 0.25)` + fees (0.25 points absorbs one session of price drift).

## Policy evaluation (spec 9.3)

The whole order set and the projected post-trade state are evaluated, including pending commitments
(filled-but-unsettled trades). Open intents are treated as cancelled because a passing target replaces them.

| Check id | Rule |
|---|---|
| `max_orders_per_decision` | ≤ 6 orders |
| `funding_settled_cash` | Σ purchase reservations ≤ settled cash − remaining reservations − committed payables (receivables never fund) |
| `long_only` | no sale beyond economic face |
| `max_daily_turnover_ratio` | Σ estimated consideration / NAV ≤ 20%; `BOOTSTRAP` on an uninitialized portfolio is exempt (flagged) |
| `min_cash_ratio` | (settled cash + receivables − payables − buys + sells − fees) / post-trade NAV ≥ 5% |
| `max_single_security_ratio:<id>` | post-trade economic dirty PV / NAV ≤ 40% |
| `parallel_dv01_usd` | post-trade Σ DV01 ≤ 600 × NAV / 1,000,000 |

Post-trade NAV = NAV − estimated spread cost − fees. Missing risk output for any projected position blocks the
decision (`missing_risk_output:<id>`), never zero risk. A security valued only through an entitlement adjustment
(no economic face, e.g. sold but still entitled to a payment before the sale settles) is a known cash amount and
carries an explicit zero DV01/duration, not a missing output. Projection mode is not implemented: a policy with
`projection_mode != disabled` is rejected explicitly, and failures always return reasons. The
`PolicyEvaluation` carries original and normalized targets, sized orders, every check, and the post-trade NAV,
cash ratio, max security ratio, DV01, turnover and order count for the .NET re-check, plus the same metrics on
the pre-trade state including pending commitments (`preTradeCashRatio`, `preTradeMaxSecurityRatio`,
`preTradeParallelDv01Usd`), populated whenever the post-trade metrics are. Every limit decision compares the
reported values (ratios at 8 dp, USD at cents; DV01 as `|dv01| × 1,000,000 > 600 × NAV`).

**Breach policy (`block_risk_increasing_v1`).** Pre-trade breaches (from the decision snapshot) put the
evaluation in breach mode. A limit already breached passes only if the order set does not worsen it
(`breach_not_worsened`); otherwise it fails with `risk_increasing_during_breach`. New breaches always fail.
On the reported values: upper limits pass when `post <= limit or (pre > limit and post <= pre)`; the minimum
cash ratio passes when `post >= min or (pre < min and post >= pre)` - the rule the .NET gate applies to the
published pre/post metrics.
Mandatory flows — settlements, entitled coupons, redemptions, eligible fills of already-authorized orders — are
processed regardless of breaches or evidence availability. `VALUE_PORTFOLIO` records current breaches in
`PortfolioState.risk_breaches`.

## Fills (spec 9.4)

- Time in force: next supported business day strictly after the submission date (`eligible_session_date`),
  expiring at 17:00 that day. A decision on day D can never fill at D's observation.
- A fill needs a READY curve for exactly that session whose observation is after submission and before expiry.
  No such curve → `ORDER_EXPIRY` (`EXPIRED`); a quote from a later session never executes the intent.
- Quote (synthetic mode): model clean price from that session's curve at the fill settlement date; buy at
  ask = mid + half-spread (+ slippage), sell at bid = mid − half-spread (− slippage); `quote_kind =
  synthetic_model`. Observed-quote execution is out of scope until M8 (orders are rejected as invalid data).
- Fill-time re-checks, in batch priority order with funding recomputed after each fill: instrument active
  (issued, settlement before maturity), data valid, long-only for sales, funding for purchases
  (consideration + fees ≤ settled cash − other reservations − payables), and post-fill limits for purchases
  (min cash, single security, DV01) on the observation curve. Any failure → `REJECTED` with reasons; the face is
  never changed.
- Settlement T+lag business days; spread cost recorded analytically. Cost sensitivity profiles: half-spread
  0.00 / 0.02 / 0.05 (`fills.cost_profiles`). These are illustrative assumptions, not measured costs.
- A passing non-HOLD decision emits `ORDER_CANCELLATION` for every unfilled intent before submitting new ones.
  A rejected decision leaves existing intents untouched. Fills and pending settlements are never cancelled.

## Commit protocol (`OfflineStateStore`, mirrors .NET)

Order of checks: proposal hash and HMAC signature, `new_state_hash`, balanced journals, required input
hashes → logical command id (same request hash returns the committed result; a different request hash raises
`IdempotencyConflict`) → blocked portfolio → expected version (`StaleStateVersion`; stale results are never
merged) → current state hash equals `input_hashes.portfolioState` → unique event and journal ids across all
commits → reconciliation (`ReconciliationFailed` blocks the portfolio). The optional JSONL log replays on start.

## Strategies and the common bootstrap

`Strategy.decide(StrategyContext) -> StrategyResult`. The context carries the `DecisionRequest`, the frozen own
`PortfolioState`, the common `MarketSnapshotRef`, the eligible universe, read-only pricing/market handles, the
policy/execution configuration, the recorded bootstrap targets and the previous session. Register strategies
with `register_strategy(id, factory)`.

Bootstrap `bootstrap-30-34-30-6-v2`: remaining maturity buckets short 0.5–3 y, intermediate 3–7 y, longer
> 7 y (ACT/365.25); equal weights inside a bucket floored to 6 dp, capped at the single-security limit; the
remainder goes to cash. Computed once on the first session with admitted data, recorded in the checkpoint and
manifest, and submitted as `BOOTSTRAP` by every invested competitor. If allocation fails, a bootstrap is
rejected, any bootstrap order does not fill, or invested competitors' bootstrap fills differ, the run fails
initialization for all matched variants.

Baselines: `cash` (always HOLD), `static_ladder` (bootstrap then HOLD; coupons and redemptions stay cash),
`quant_duration` (target 4.0 y; rebalance on the first session of a month or drift > 0.25 y; lexicographic
objective min squared duration error → min turnover → security id; one decision either sells longest-duration
holdings or buys longest-duration instruments with settled cash; moves below 2 pp are dropped; 1 pp safety
margins on turnover and cash).

## Replay runner (spec 15.1, 15.4)

Per session: `PROCESS_EVENTS` → bootstrap verification → shared-input check (no READY curve available by
19:00 ⇒ `skipped_stale_data` for every competitor) → freeze snapshot → strategies in sorted id order → persist
every outcome (`outcomes.jsonl`) → `SUBMIT_DECISION` for proposals → `VALUE_PORTFOLIO` → checkpoint
(`checkpoint.json`: cycle index, event position, portfolio versions and hashes, pending orders/settlements,
config hash, manifest reference, bootstrap state, failures, exclusions). Resume skips already committed command
ids and reuses persisted outcomes, so retries never duplicate trades or cash flows. Failures are isolated per
competitor (`failed_dependency`, `failed_invalid_output`); a malformed result is re-validated and cannot reach
`SUBMIT_DECISION`. `response_mode` distinguishes `recorded_replay` from `fresh_inference`; within
`recorded_replay`, `replay_source=stored_results` (default) makes AI strategies consume persisted results
only (missing ones are `failed_dependency`) and `replay_source=recorded_responses` re-runs them on
replay-only providers. The runner refuses provider/mode combinations that would mislabel a run, and the
manifest records `responseSource` per run and per strategy (see
[agents-and-validation.md](agents-and-validation.md#recorded-responses)).

Run directory: `config.json`, `commits.jsonl`, `outcomes.jsonl`, `checkpoint.json`, `manifest.json`, and
`report.{json,md}` after `fi-research replay report`. The manifest becomes immutable (hashed) when the run
completes or fails.

CLI: `fi-research replay run --config C --run-dir D [--ports module:callable]`, `replay resume --run-dir D`,
`replay report --run-dir D`, `parity export [--out DIR] [--config C] [--ports ...]`. Transition signing uses
`$FI_TRANSITION_SIGNING_KEY`; the default ports factory is `research_engine.market.store.load_default_market`.
Parity fixtures default to `contracts/fixtures/parity/` and use the published fixture key.
