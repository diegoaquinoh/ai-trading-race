# Offline replay ↔ application path parity fixtures

Consumed by `AiTradingRace.Tests/FixedIncome/ParityFixtureTests.cs` (spec §5.3).
The test is skipped until at least one `manifest.json` exists below this directory.
Each scenario is replayed through the real .NET `TransitionCommitService`
(SQLite, real transactions and unique constraints): every proposal must commit,
and the final state hash and ledger totals must equal `expected.json`.

## Layout

```
contracts/fixtures/parity/
  <scenarioId>/
    manifest.json
    expected.json
    proposals/0001.json   # signed TransitionProposal, exact research_engine to_wire() JSON
    proposals/0002.json
    ...
```

## manifest.json

```json
{
  "schemaVersion": "1.0",
  "scenarioId": "synthetic-bootstrap-coupon-v1",
  "description": "free text",
  "signingKeyUtf8": "parity-fixture-signing-key",
  "engineVersion": "research-engine/0.1.0",
  "portfolio": {
    "portfolioId": "pf-parity-1",
    "strategyId": "quant_duration",
    "runId": "run-parity-1",
    "repetition": 0,
    "riskPolicyId": "treasury-long-only-v1",
    "dataMode": "synthetic_curve"
  },
  "riskPolicy": { "...": "optional RiskPolicy wire object (camelCase, decimal strings)" },
  "genesisState": { "...": "PortfolioState wire object, version 0" },
  "proposals": ["proposals/0001.json", "proposals/0002.json"],
  "expected": "expected.json"
}
```

- `signingKeyUtf8` is a fixture-only HMAC key; proposals must be signed with it.
- `engineVersion` is allowed exactly for the scenario.
- `riskPolicy` (optional) becomes the platform policy for `riskPolicyId`. When
  absent the .NET defaults for `treasury-long-only-v1` (spec §9.3) apply. Its
  decimal strings must be the ones the engine hashed: .NET recomputes
  `inputHashes.riskPolicy` from this object for `submit_decision` proposals.
- `genesisState` is stored verbatim (after canonicalisation) as version 0; its
  hash must equal `inputHashes.portfolioState` of the first proposal. .NET's own
  genesis (`PortfolioGenesis`) emits every PortfolioState field with defaults
  (`cashUsd: "0"`, empty arrays, `null` optionals, `asOf` without fractional seconds).
- Proposals are applied in listed order with `ExpectedCommandId = proposal.commandId`.

## Proposal requirements (what .NET verifies)

- Body is exactly `TransitionProposal.to_wire()` (nulls included). `proposalHash`
  = `sha256:` + hex SHA-256 of canonical JSON of the body without `proposalHash`
  and `signature`; `signature` = `hmac-sha256:` + hex HMAC-SHA256(key, ASCII hash string).
- `newStateHash` = SHA-256 of canonical `newState`; `newState.version == newVersion
  == expectedVersion + 1` (or equal for `noOp`).
- `inputHashes.portfolioState` = hash of the previous committed state;
  `inputHashes.riskPolicy` required for `submit_decision`.
- Every journal balanced, lines one-sided and in cents; fill consideration/fees,
  settlement cash and cash-flow amounts in cents.
- `submit_decision`: `policyEvaluation` present; `policyId` equals the portfolio
  policy; post-trade metrics (`postTradeNavUsd`, `postTradeCashRatio`,
  `postTradeMaxSecurityRatio`, `postTradeParallelDv01Usd`, `turnoverRatio`) present
  whenever orders are created; `orderCount == len(ordersCreated)`; turnover above
  the cap only with `bootstrapExemptionApplied`, action `BOOTSTRAP`, all orders
  `bootstrap: true`, from an uninvested state.
- Event ids, journal ids, fill ids (one per order), settlement ids (one per fill),
  cash-flow ids and valuation ids are unique per portfolio across the scenario.
- `reconciliation.ok` and `journalsBalanced` true and `newState.blockedReason` null.

## expected.json

```json
{
  "finalVersion": 12,
  "finalStateHash": "sha256:<64 hex>",
  "stateHashes": { "0": "sha256:...", "1": "sha256:..." },
  "ledgerTotals": {
    "CASH": { "debitUsd": "1000000.00", "creditUsd": "940123.45" },
    "BOND_PRINCIPAL": { "debitUsd": "...", "creditUsd": "..." }
  },
  "counts": { "journals": 20, "orders": 4, "fills": 4, "settlements": 4, "cashFlows": 3, "valuations": 6 }
}
```

`stateHashes`, `ledgerTotals` (per account, summed over all committed journal
lines) and `counts` are optional; `finalVersion` and `finalStateHash` are required.
