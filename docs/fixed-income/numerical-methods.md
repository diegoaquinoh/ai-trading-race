# Numerical methods: instruments, curves, pricing, risk

Workstream A (milestone M1) of the Fixed Income Research Lab. This document records the
conventions implemented in `ai-trading-race-ml/research_engine/{instruments,market,pricing,risk}`
and the reasoning behind each tolerance. It implements spec sections 6, 7 and 8. All numbers
here are engineering choices for synthetic-curve research, not investment advice or measured
market properties.

Engine version: `1.0.0+quantlib-1.44` (`research_engine.pricing.quantlib_env.ENGINE_VERSION`).
Conventions version: `usd-treasury-conventions-v1`.

## 1. Units

| Quantity | Internal unit | Contract representation |
|---|---|---|
| Face / quantity | USD face | `DecimalStr` |
| Price | per 100 face | `DecimalStr`, 10 dp |
| Rate, yield | decimal annual rate (0.0469 = 4.69%) | `DecimalStr`, 12 dp |
| USD value in calculation outputs | USD | `DecimalStr`, 6 dp (ledger cents are applied by the simulation engine at posting) |
| Durations, convexity, years | years | `DecimalStr`, 10 dp |
| Discount factor | ratio | `DecimalStr`, 14 dp |

Solvers use binary floats. Floats are converted to decimals at the contract boundary through
`Decimal(repr(x))` and then quantized (`research_engine/pricing/units.py`). Percentages from
sources (Treasury CSV) become decimal rates in the adapter.

## 2. Instruments and conventions

Security master: `contracts/instruments.py::SecurityTerms` holds the spec 8.1 field groups:
identity, economics, dates, schedule rules, conventions, trading units, provenance, plus
`terms_version` and its effective dates.

* **Schedule**: QuantLib `Schedule`, generated backward from maturity, semiannual, on the
  `UnitedStates(GovernmentBond)` calendar (calendar id `US-GovernmentBond`, version
  `quantlib-1.44`).
* **Accrual periods** use **unadjusted** coupon dates. **Payment dates** are adjusted
  **Following**.
* **Day count**: ACT/ACT (ICMA). A regular period pays exactly `100 * c / 2`. A short first
  stub pays `100 * c / 2 * days(start, end) / days(end - 6M, end)`. Long stubs are rejected
  (`UnsupportedTermsError`).
* **Accrued interest** at `s`: `100 * c / 2 * days(period_start, s) / days(quasi_start,
  period_end)`, computed exactly in `Decimal`.
* **Settlement**: T + `settlement_lag_business_days` (1) business days on the calendar.
* **Outstanding** at date `d`: `issue_date <= d < final_payment_date`. **Tradable** on trade
  date `d`: issued, and the standard settlement date falls strictly before the final payment
  date.

### Entitlement (`settlement_strictly_before_payment_v1`)

A cash flow belongs to the holder whose **settlement date is strictly before its adjusted
payment date**. The dirty price at settlement `s` therefore includes exactly the flows with
`payment_date > s`. A buyer who settles on a payment date does not receive that coupon, and
accrued interest restarts on the unadjusted coupon date. Under Following adjustment, every
day between an unadjusted coupon date and its payment date is a non-business day. So for any
business-day settlement, `accrual_end <= s` implies `payment_date <= s`, and accrual and
entitlement cannot disagree. Fixtures cover this: the 2023-01-15 coupon, a Sunday followed by
the MLK Day holiday, is paid on 2023-01-17. A trade on 2023-01-13 settles on 2023-01-17 and is
not entitled to that coupon.

### Synthetic universe

`fixtures/instruments/synthetic_universe_v1.json` contains ten **hypothetical** notes,
`SYN-USD-NOTE-001` to `010`:

* original maturities of 2, 5 and 10 years;
* issue dates between 2020 and 2024, so that during the 2023–2024 dataset notes 001 and 002
  mature and notes 003, 004, 007 and 010 are issued;
* coupons that are deliberately not multiples of 1/8%;
* 1,000 USD minimum face and increment;
* terms assumed announced 7 days before issue (`provenance.available_at`).

The notes have no external identifiers. The contract rejects synthetic IDs outside the
`SYN-USD-NOTE-NNN` pattern and synthetic terms that carry a CUSIP or ISIN.

## 3. Market data and time fields

### Treasury daily par yield curve

`market/treasury.py` reads raw CSVs saved under `fixtures/market/treasury/`. The 2023 and 2024
files were retrieved on 2026-11-05 and are listed in a sha256 `manifest.json`. They are U.S.
government data and in the public domain.

* **Parsing**: columns are mapped dynamically by header (`N Mo`, `N Yr`, and the 2025
  `1.5 Month` column read as 6 weeks). Unknown columns are flagged. Blank and `N/A` cells stay
  missing (`missing_tenors`) and are never zero-filled or forward-filled. Values above 25% are
  kept but flagged `rate_out_of_range`, and the curve builder excludes them.
* **Idempotency**: re-storing identical bytes is a no-op. Different bytes for a stored year
  raise `ArtifactConflictError` unless `allow_revision=True`. In that case both artifacts are
  kept and the session is reported as a conflict. The first-retrieved value wins and the
  revision is never silently merged. A checksum mismatch on import is fatal.
* **Fetching** (CLI `market fetch-treasury` only; tests never touch the network): host
  allowlist `home.treasury.gov` (https only), validated redirects, at most 3 attempts with
  exponential backoff on 408, 425, 429 and 5xx responses.
* **Labelling**: `quote_basis = indicative_bid_side_par_yield`, `executable = false`. Treasury
  par yields are reference-curve inputs derived from indicative bid-side quotations, never
  execution quotes.

| Field | Value (assumption, policy `reconstructed_publication_plus_lag_v1`) |
|---|---|
| `observed_at` | session date 15:30 America/New_York (declared measurement convention) |
| `published_at` | `null`: the historical publication instant is unknown |
| `available_at` | session date 18:00 America/New_York, **reconstructed**, not verified |
| `ingested_at` | retrieval time of the raw artifact |

The 2023–2024 Treasury sessions coincide exactly with QuantLib's government-bond business days
(500 sessions, no missing tenors).

### ALFRED (FRED) vintages

`market/fred.py` requests all vintages (`realtime_start=1776-07-04`, `realtime_end=9999-12-31`).
The API key comes from `FRED_API_KEY` and is stripped from stored URIs. Allowed host:
`api.stlouisfed.org`. Availability policy `alfred_realtime_date_next_business_day_v1`: ALFRED
dates have day precision, so a vintage is usable from 00:00 America/New_York on the next
business day after its `realtime_start`. `vintage_as_of(observations, known_at)` returns, for
each reference period, the latest vintage available at `known_at`. A revision is therefore
invisible before its availability, including on its own `realtime_start` date. The offline
test fixture `fixtures/market/fred/alfred_illustrative_unrate.json` uses a fictitious series id
and **illustrative values**, not published data.

### Observed quotes (gated)

`market/quotes.py::validate_observed_quote` checks:

* a non-crossed market, with mid consistent with bid and ask;
* finite values and price scale (1–200 per 100);
* currency and instrument status;
* timestamp order (`observed <= published <= available`, ingestion after observation) and
  availability at `as_of`;
* stale age;
* settlement date inside the instrument's life, and the clean/dirty basis;
* indicative quotes not marked executable;
* model prices never accepted as observed quotes.

`admit_observed_security` always returns `admitted=false` with the reason
`no_licensed_quote_source_configured`, because no licensed source is registered
(`LICENSED_QUOTE_SOURCES` is empty).

### Dataset release gate (`market/admission.py`)

`build_dataset_admission_report` produces the spec 7.3 artifacts:

* a coverage summary and per-tenor missingness;
* the revision policy;
* the timestamp-confidence table;
* the market-mode label (`SYNTHETIC CURVE SIMULATION ...`);
* a re-verified checksum manifest and a curve-build summary.

`eligible_for_benchmark` requires all of the following:

* every checksum verifies;
* session coverage is at least 98%;
* missing values are at most 2%;
* no revision conflicts;
* at least 98% of curves are READY.

The 2023–2024 fixture dataset passes: 500 of 500 sessions, all READY.

## 4. Curve specification `usd-tsy-par-bootstrap-v1`

* **Reference date** v = session date, with D(v, v) = 1. Treasury's curve refers to next-day
  settlement; the one-day offset is ignored (declared simplification).
* **Short end (tenors up to 12 months)**: zero-coupon instruments from v to v + tenor, adjusted
  Following. The published bond-equivalent par yield is read as a **simple ACT/365F** rate:
  `D(T) = 1 / (1 + y * days(v, T) / 365)` (QuantLib `DepositRateHelper` with 0 fixing days and
  `Actual365Fixed`). This is an approximation of Treasury's bill-equivalent convention,
  particularly at 12 months.
* **Tenors of 2 years and above**: semiannual par bonds with coupon equal to the par yield.
  Accrual is ACT/ACT-ICMA on unadjusted dates, payments are Following, the bond starts at v,
  and it is priced at 100 (`FixedRateBondHelper`). The end-of-month rule applies when v is a
  month end, so a 29 February session keeps regular coupon dates.
* **Bootstrap**: QuantLib `PiecewiseLogLinearDiscount` with `IterativeBootstrap`, accuracy
  1e-12 and at most 100 evaluations.
* **Interpolation**: linear in ln D over ACT/365F time between nodes. Before the first node,
  ln D is linear from 0 at v (flat continuous forward).
* **Negative rates**: permitted. There is no monotone-discount constraint; QuantLib is built
  with negative-rate support, and a test builds a negative short end with discount factors
  above 1 that are not monotone.
* **Extrapolation**: rejected beyond `validated_horizon_date`, the last node, and before v
  (`ExtrapolationError`).
* **Required inputs**: the 2Y, 5Y and 10Y tenors, at least one zero-coupon tenor, at least 4
  nodes, and node coverage up to the latest final payment date among instruments outstanding
  at the session.
* **Published output** (`CurveSnapshot`):
  * nodes with date, ACT/365F time, discount factor and continuous zero rate;
  * calibration residuals for every input;
  * input observation ids and hashes;
  * the full specification;
  * `status` READY or FAILED with `failure_reasons`.
* **FAILED** is returned for a missing or excluded required tenor, a missing short end, too few
  nodes, a QuantLib calibration error (`calibration_failed:`), a residual out of tolerance, or
  an insufficient horizon. A FAILED curve can never be used for pricing (`CurveNotReadyError`).
* **Identity**: `curve_snapshot_id` is a hash of the observation hash, the specification, the
  engine version, the required horizon and the data mode. `content_hash` covers the whole
  snapshot. There is no `generated_at`, so rebuilds are byte-identical.
* **Pricing uses only the published nodes**: QuantLib `DiscountCurve` with `LogLinear`
  interpolation on the quantized nodes reproduces the bootstrap exactly between nodes.

**Residual tolerances.** Each input is repriced from the *published, quantized* nodes,
independently of the QuantLib helpers. The limits are 1e-6 per 100 for par-bond prices and
1e-7 (0.001 bp) for rates. The bootstrap accuracy (1e-12) and discount-factor quantization
(1e-14) imply residuals around 1e-10, so the limits leave four orders of magnitude of margin.
They still catch real failures: a bootstrap at 1e-2 accuracy produces residuals around 0.2 per
100 and is rejected. The worst residual across all 500 fixture sessions is below 1e-9 per 100.

This builder does **not** reproduce Treasury's proprietary curve methodology. Sparse par
inputs do not determine intermediate discount factors uniquely; our assumptions (simple
short-end reading, log-linear discount interpolation, spot-start instruments) are published
with each snapshot together with its residuals.

## 5. Pricing contract (spec 8.3)

Notation: v is the curve reference date, s the settlement date, u the valuation date with
u ≥ v, and t_i the payment dates.

```text
dirty_per_100(s)  = SUM_{t_i > s} CF_i * D(v, t_i) / D(v, s)        anchor: settlement s
clean_per_100(s)  = dirty_per_100(s) - accrued_per_100(s)            ACT/ACT-ICMA
pv_per_100(u)     = SUM_{t_i > u} CF_i * D(v, t_i) / D(v, u)        anchor: valuation u
pv_usd(u)         = face / 100 * pv_per_100(u)
```

`PricingPort.price` returns settlement-anchored values. `value_position` returns the
valuation-date PV and is what NAV uses (spec 9.1). Every output records its anchor and anchor
date. The two values differ by `D(v,s)/D(v,u)` and by any flow paid in (u, s]. A test covers a
coupon paid on the settlement date that is in the PV but not in the dirty price. In the
published decimals, `clean + accrued == dirty` holds exactly.

When a note is no longer tradable at standard settlement (its final payment falls on or before
s), settlement-anchored prices are `null` in `PositionRisk`. `PositionValuationResult` then
shows valuation-date anchored clean and accrued values, and a diagnostic records the fallback.

**Yield to maturity** (`street_semiannual_act_act_icma_v1`) is a quote-conversion tool:

* semiannual compounding, also in the final period;
* the exponent of the k-th remaining flow is `w + k`, where
  `w = days(s, next_coupon) / days(quasi_start, next_coupon)` on unadjusted dates;
* `P(y) = SUM CF_k / (1 + y/2)^(w+k)`.

The solver is bisection with Newton steps, accurate to about 1e-12 in price. Yield-based
modified duration `-(1/P) dP/dy` and convexity `(1/P) d²P/dy²` are analytic and are labelled
separately from curve effective duration.

**QuantLib global state**: `pricing/quantlib_env.evaluation_date(d)` takes one process-wide
re-entrant lock, sets `Settings.evaluationDate`, and restores the previous value on exit, even
when an exception is raised. Tests cover:

* concurrent curve builds and prices matching sequential results;
* each guarded block seeing only its own date across sleeps;
* a second thread blocking while another holds the lock;
* restoration after an exception.

## 6. Risk (spec 8.5)

Shocks are applied to the continuous ACT/365F zero rate at the curve nodes:
`ln D'(t_i) = ln D(t_i) - shift(t_i) * t_i`, followed by the usual log-linear interpolation. A
constant shift is therefore an exact parallel shift of the zero curve at every date.

* **Parallel DV01** (face-scaled):
  `(PV(-1bp) - PV(+1bp)) / 2`. **Positive means a gain if rates fall**, and the first-order PnL
  of an upward x bp shift is `-DV01 * x`.
* **Effective duration** (curve-based): `(PV_down - PV_up) / (2 * PV * 1bp)`. **Effective
  convexity**: `(PV_down + PV_up - 2 PV) / (PV * 1bp²)`.
* **Key-rate DV01** (`krd-triangular-1-2-5-10-30-v1`):
  * triangular ("tent") zero-rate bumps at 1, 2, 5, 10 and 30 years;
  * the 1y bump is flat back to v, giving short-end support for notes shorter than 2y;
  * the 30y bump is flat out to the horizon (end-point support);
  * the weights sum to 1 at every t (partition of unity).
* **Portfolio aggregation**: face is summed per security, each position is face-scaled exactly
  once, and portfolio DV01 is the sum of position DV01s. Portfolio effective duration is
  `total DV01 / (total PV * 1bp)`. Concentration weights are reported against bond value and
  NAV. Remaining-maturity buckets are 0–1, 1–3, 3–5, 5–7, 7–10 and 10+ years. Cash, pending
  settlement payables/receivables and turnover are passed through from the portfolio state.
* **Relative value**: in synthetic same-curve mode, every `RiskReport` and `PositionRisk`
  carries `relative_value.status = mechanically_neutral`. The contract forbids residual values
  in that state, so the identity "execution marks = valuation model" cannot be presented as a
  signal (spec 3.2, 8.4).

### Risk tolerances and their justification

| Check | Tolerance | Why |
|---|---|---|
| Price vs closed form (flat curve) | 0.0001 per 100 | spec 16.5; observed error is about 1e-10 |
| Parallel DV01 vs closed form | 1e-5 USD per 1mm face | engine and oracle compute the same central difference; only float and 6-dp quantization noise remain |
| Effective duration vs `SUM t PV / PV` | 1e-6 relative | central-difference error `(δt)²/6` is about 1.4e-7 for δ = 1bp and t = 9y |
| Key-rate sum vs parallel | 1e-6 relative | partition of unity plus linear ln D interpolation make the first-order terms sum exactly; the remaining third-order cross terms are about `(δT)² ≤ (1e-4·10)² = 1e-6`; observed values are about 5e-8 |
| Key-rate oracle for a single flow on a node | 1e-12 per 100 | exact: `100 e^{-rt} sinh(δ w_k(t) t)` |
| Bump stability (0.5, 1 and 2 bp) | 2e-6 relative | the O(δ²) term at 2bp and 9y is about 5e-7 |
| Steepener: key-rate approximation vs full repricing | 2% of PnL | first order only; the remaining error is convexity and is reported, not hidden |

## 7. Scenarios `scenario_library_v1` (spec 8.6)

| ID | Shift (zero-rate nodes) |
|---|---|
| `parallel_up_25` / `parallel_down_25` | ±25 bp everywhere |
| `parallel_up_100` / `parallel_down_100` | ±100 bp everywhere |
| `steepener_v1` | −25 bp at 2y, 0 at 5y, +25 bp at 10y |
| `flattener_v1` | reverse of `steepener_v1` |

* Shifts are linear in time between scenario nodes, and the nearest node's shift is extended
  flat outside them: before 2y the 2y shift applies, after 10y the 10y shift.
* Scenarios are instantaneous at the valuation date, with holdings fixed, and valued as
  valuation-date PV (no settlement lag).
* **Full repricing is authoritative.** Each `ScenarioResult` also reports a first-order
  approximation (parallel DV01, or key-rate DV01 weighted by the scenario shift at the key
  tenors) and, for parallel scenarios, a duration-plus-convexity approximation. Both are given
  with their error against full repricing (`approx - full`).
* The scenarios are hypothetical shocks, not forecasts.

## 8. Calculation results and verification

Every price, valuation, risk and scenario output is registered in
`pricing/calc_store.CalculationStore` as a `CalculationResult`:

* `calculation_id = calc-<16 hex>`, a hash of the payload without id, hash and signature;
* `content_hash` = sha256 over the canonical JSON;
* `signature` = HMAC-SHA256 over that hash, using `RESEARCH_SIGNING_KEY`. If the key is unset,
  a development key is used and a warning is logged.

Each result carries input hashes (curve snapshot, security terms, and the scenario or
holdings), `as_of` (the curve's `available_at`), valuation and settlement anchors,
per-100 vs face-scaled basis, completeness, diagnostics, tolerances and engine provenance.
Results can be persisted to JSONL. `verify(calc_id)` rejects unknown ids, tampered payloads and
foreign keys.

## 9. Known limitations

* Not Treasury's proprietary curve. The short-end simple-rate reading, the spot-start
  instruments (ignoring T+1) and log-linear discount interpolation are declared assumptions.
* Availability times are reconstructed (18:00 New York), not verified publication instants.
* Treasury CSVs have no vintage history, so historical revisions cannot be reconstructed.
* The yield convention compounds inside the final coupon period; some street conventions use
  simple interest there.
* Only regular schedules and short first stubs are supported. There is no ex-coupon period and
  no reopenings.
* Observed-security mode is gated closed: no licensed quote source exists. Relative value is
  mechanically neutral in synthetic mode.
* The ALFRED fixture is illustrative. Live ALFRED access needs `FRED_API_KEY`.
* Fixtures resolve from `ai-trading-race-ml/fixtures` (override with `RESEARCH_FIXTURES_DIR`).
  The container image must include them.
