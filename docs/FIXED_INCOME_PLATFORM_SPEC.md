# Fixed Income Research and Agent Competition Platform

- **Status:** proposed implementation specification; no application changes are implemented by this document.
- **Specification version:** 1.0
- **Prepared:** 5 November 2026
- **Working name:** Fixed Income Research Lab
- **Repository strategy:** evolve the existing repository and deployment scaffolding.

## Navigation

- [Purpose and decisions](#1-purpose-and-governing-decisions)
- [Users and success criteria](#2-users-workflows-and-success-criteria)
- [Scope and data modes](#3-scope-data-modes-and-non-goals)
- [Repository migration](#4-existing-repository-and-migration-boundaries)
- [Architecture and ownership](#5-target-architecture-and-ownership)
- [Time and reproducibility](#6-time-data-availability-and-run-reproducibility)
- [Data sources](#7-market-sources-and-data-admission)
- [Bond valuation and risk](#8-bond-domain-valuation-and-numerical-risk)
- [Accounting and execution](#9-portfolio-accounting-execution-and-policy)
- [Strategies and subagents](#10-independent-strategies-and-internal-agent-delegation)
- [Document ingestion](#11-document-ingestion-and-canonical-evidence)
- [Knowledge graph and retrieval](#12-knowledge-graph-and-retrieval)
- [Citations and proposal validation](#13-research-notes-citations-and-proposal-validation)
- [APIs and persistence](#14-api-contracts-and-persistence)
- [Orchestration and recovery](#15-orchestration-failure-behavior-and-recoverability)
- [Evaluation and tests](#16-research-methodology-metrics-and-validation)
- [Interface and demo](#17-product-interface-and-demonstration)
- [Operations and maintenance](#18-operations-deployment-and-maintenance)
- [Delivery plan](#19-delivery-plan-and-milestone-acceptance)
- [Requirement traceability](#20-requirement-traceability-and-release-gates)
- [Open decisions](#21-open-implementation-decisions-and-known-limitations)
- [Repository deliverables](#22-required-repository-artifacts)

## 1. Purpose and governing decisions

Build a reproducible fixed income research and paper-trading platform that compares quantitative strategies and AI decision architectures. Each competitor manages an isolated portfolio using the same eligible instruments, information cutoff, market snapshots, execution model, and risk policy.

The platform combines:

- Deterministic Treasury bond pricing, cash-flow accounting, and risk analytics.
- Document RAG over dated official economic and monetary-policy material.
- Graph-assisted retrieval with source provenance and historical visibility.
- Independent competing strategies, including an optional lead agent with bounded specialist agents.
- Historical replay, forward paper trading, and a dashboard that explains both financial outcomes and the evidence behind decisions.

The scientific objective is to measure the contribution of retrieval and delegation. Profitability, graph superiority, and multi-agent superiority are hypotheses to evaluate, not acceptance requirements.

### 1.1 Decisions adopted for this specification

| Decision | Specification default | Reason |
|---|---|---|
| Application foundation | Adapt the current .NET, Functions, FastAPI, and React repository | Preserve working application and operational infrastructure |
| Initial asset class | USD nominal, non-callable, fixed-rate Treasury notes | Constrain instrument and credit complexity |
| Research frequency | One scheduled decision per trading day | Match an initial daily market-data implementation |
| Execution frequency | Only when an admissible order is generated and a later execution observation exists | A scheduled review may legitimately produce HOLD |
| Later frequency extension | Release-triggered decisions with a validated intraday feed | Data quality and timing gate the extension |
| Numerical implementation | One canonical Python pricing, risk, and simulation package | Reuse identical calculations in notebooks, replay, and the application |
| State authority | .NET owns transactional portfolio and ledger persistence | Preserve application authorization, concurrency control, and auditability |
| AI implementation | Python owns retrieval, graph indexing, model reasoning, and specialist coordination | Keep evidence processing and inference together |
| Competition | Independent strategy portfolios | Preserve the useful race infrastructure |
| Delegation | One optional competing strategy uses a lead and fixed specialists | Compare delegation against a matched single-agent strategy |
| Graph scope | Documents, events, topics, releases, entities, and stable instrument metadata | Avoid synchronizing every market or portfolio change into a graph |
| Graph and search backend | Proposed: one Neo4j deployment for graph, vector, and lexical indexes | Avoid a separate vector database in the initial design |
| Canonical evidence | Original source artifacts plus normalized, versioned evidence records | Graph/search indexes must be rebuildable |
| Initial data mode | Clearly labelled synthetic instruments priced from observed daily curves | Enable development before security-level quote access is resolved |
| Observed-bond mode | Separate gated capability requiring actual terms and independent historical quotes | Support defensible relative-value and execution research |
| Live brokerage | Outside this specification | The execution target is simulation and paper trading |

These are explicit project assumptions, not claims about existing capabilities. A change to an assumption requires a recorded architecture decision and an updated experiment manifest.

### 1.2 Requirement language

**MUST** identifies a release requirement. **SHOULD** identifies the preferred implementation unless a documented alternative meets the same objective. **MAY** identifies a later optional capability.

All numerical defaults in this specification are proposed experiment settings. They are not investment recommendations, calibrated strategy parameters, or measured performance claims.

## 2. Users, workflows, and success criteria

### 2.1 Primary users

1. **Researcher:** builds datasets, checks pricing, runs controlled experiments, and inspects unsuccessful hypotheses.
2. **Application reviewer:** uses the dashboard to inspect instruments, evidence, decisions, risk, and results.
3. **Operator:** starts the platform, monitors ingestion, retries failed jobs, restores data, and controls resource budgets.

A single developer may fill all three roles. The product MUST remain useful through a Python CLI and saved-data replay without requiring all cloud services to remain online.

### 2.2 Required end-to-end workflows

**Historical experiment:** choose a dataset manifest and date range; validate chronology and coverage; initialize matched portfolios; advance a simulation clock; freeze common inputs; run eligible competitors; validate proposals; queue later fills; apply settlements and cash flows; value portfolios; produce a report with evidence, financial metrics, and computation costs.

**Forward paper-trading cycle:** ingest published sources and market observations; record their actual availability; create an immutable decision snapshot; run independent competitors; validate decisions; simulate fills only when appropriate later quotes become available; persist every result; update the dashboard.

**Research question:** ask a question scoped to an information cutoff and portfolio snapshot; retrieve eligible passages and graph paths; join deterministic analytics; return a cited research note. This workflow MUST NOT submit orders.

**Failure investigation:** navigate from an experiment result to the decision, evidence bundle, graph traversal, tool outputs, policy checks, and ledger events that produced it.

### 2.3 Definition of a convincing initial release

- At least one deterministic strategy and three controlled LLM variants can complete the same replay.
- Pricing, coupons, maturity, settlement, and ledger reconciliation pass numerical fixtures and integration checks.
- Every trade has an immutable decision and policy audit trail.
- RAG answers reference actual delivered passages; graph traversal contributes inspectable evidence.
- Tests demonstrate that future documents, revised values, and future-derived graph content are excluded.
- Reports distinguish synthetic execution from observed-quote execution.
- Failed and missing decisions remain visible in results.
- A reviewer can reproduce deterministic results from a saved manifest and replay recorded AI responses.
- An unsuccessful trading or graph hypothesis can still produce a complete, valid research report.

## 3. Scope, data modes, and non-goals

### 3.1 Initial financial scope

- Single currency: USD.
- Initial universe: approximately 6–12 fixed-rate note instruments spanning short, intermediate, and longer exposures, initially around 2-, 5-, and 10-year original maturity categories.
- Instruments age and mature; their remaining maturity is never reset merely to keep a bucket constant.
- Fixed coupons, principal repayment, business-day calendars, settlement, and accrued interest.
- Long-only portfolios, cash, market orders, and explicitly modelled transaction costs.
- Coupons are retained as cash by default; a later strategy decision may reinvest them.
- No margin, short selling, derivatives, leverage, TIPS, floating-rate notes, callable bonds, corporate default models, or foreign-exchange exposure in the initial release.
- Bond ETFs MAY be an alternative early demonstration adapter. They have share accounting and distributions and MUST NOT be labelled individual-bond valuation.

### 3.2 Synthetic curve simulation

Synthetic instruments have explicitly specified hypothetical issue dates, maturity dates, coupons, calendars, and face amounts. They MUST use internal identifiers such as SYN-USD-NOTE-001 and MUST NOT impersonate actual securities.

Observed historical curves supply the discounting environment. Execution prices are generated by the configured pricing model, plus declared spread and slippage assumptions. Such prices are model observations, not actual market quotes.

This mode can test pipeline correctness, risk management, evidence quality, and decisions about exposure to subsequent curve changes. It cannot establish actual security mispricing or achievable trading performance.

If execution marks and a valuation benchmark use the same curve and model, any rich/cheap difference is zero apart from explicitly modelled effects. The application MUST NOT manufacture a relative-value signal from that identity.

### 3.3 Observed-security paper trading

This mode requires:

- Actual contractual terms and stable security identifiers.
- Independently sourced security-level historical quotes with observation and availability metadata.
- Declared quote type: bid, ask, mid, evaluated price, trade, or indicative quote.
- Documented historical coverage, permitted storage/use, and any display restrictions.
- Consistent units, clean/dirty convention, settlement date, and executable-versus-indicative status.
- A validated mapping between market quotes and security terms.

An indicative quote remains indicative. The simulator MUST expose assumptions when it treats such a quote as an execution proxy. Synthetic and observed-security runs MUST appear in separate result groups.

### 3.4 Explicit non-goals

- High-frequency trading or winning a latency race around scheduled announcements.
- Automatic deployment of real orders.
- An unrestricted web-browsing agent that can introduce unversioned evidence into a historical run.
- Unbounded agent spawning, recursive agent teams, or autonomous changes to risk policy.
- A general financial knowledge graph covering every instrument and institution.
- Recreating the full Microsoft GraphRAG community-summarization pipeline merely to use its name.
- A microservice per ingestion, embedding, graph, pricing, or specialist stage.
- Maintaining duplicate numerical pricing implementations in C# and Python.

## 4. Existing repository and migration boundaries

The current repository is a modular .NET application with shared domain/application/infrastructure libraries, a Functions worker, a separate Python prediction service, and React UI. It is not a fleet of isolated domain microservices.

| Existing component | Observed current behavior | Planned treatment |
|---|---|---|
| AiTradingRace.Domain/Entities/MarketAsset.cs | Symbol/name/currency/provider ID | Retain legacy entity; add explicit bond security master |
| AiTradingRace.Infrastructure/MarketData | CoinGecko OHLC ingestion and latest candles | Introduce point-in-time curve, quote, and macro adapters |
| AiTradingRace.Infrastructure/Portfolios/EfPortfolioService.cs | Quantity × price, cash, average entry price | Replace fixed income execution/accounting path through canonical simulation transitions |
| AiTradingRace.Infrastructure/Equity/EquityService.cs | Spot-style marks and equity snapshots | Consume reconciled bond valuation and ledger outputs |
| AiTradingRace.Infrastructure/Agents/AgentContextBuilder.cs | Recent candles and optional regime/rule graph | Build immutable as-of decision requests |
| AiTradingRace.Infrastructure/Agents/AgentRunner.cs | Context, inference, risk, execution, snapshots | Separate proposal generation from authoritative commit and delayed fills |
| AiTradingRace.Infrastructure/Agents/CustomMlAgentModelClient.cs | HTTP POST /predict; BTC/ETH-specific validation | Replace with versioned research/analytics client for the new path |
| AiTradingRace.Infrastructure/Knowledge/InMemoryKnowledgeGraphService.cs | Five curated rules and regime links | Preserve only for legacy mode; new evidence retrieval is a separate subsystem |
| AiTradingRace.Domain/Entities/DecisionLog.cs | Rationale, rule IDs, subgraph, market snapshot | Add normalized run, claim, evidence, policy, and multi-order records |
| AiTradingRace.Functions/Orchestrators/MarketCycleOrchestrator.cs | Five-minute market cycle and fifteen-minute decisions | Retain orchestration patterns; add explicit scheduled research and replay entry points |
| AiTradingRace.Functions/Activities/ExecuteTradesActivity.cs | Counts orders already executed by AgentRunner | Replace or rename so only one component performs execution |
| AiTradingRace.Application/Common/AgentOrchestrationClock.cs | TimeProvider wrapper exists | Reuse where appropriate; distinguish simulation time from operational wall time throughout |
| ai-trading-race-ml/app/main.py | FastAPI /predict and health endpoints | Keep service shell; introduce importable research engine and v1 endpoints |
| ai-trading-race-ml/app/ml/features.py | Technical indicators over OHLC | Replace fixed income path with curve, valuation, macro, and evidence features |
| ai-trading-race-web | Existing dashboard and charts | Extend with experiment, valuation, evidence, and data-quality views |
| Infrastructure, authentication, CI/CD | Working project scaffolding | Reuse and update only where required |

The current market-data query has no historical cutoff, context construction uses wall time in places, and decision logging currently depends on knowledge/regime availability. Those behaviors MUST NOT carry into the new experiment path.

Migration MUST be additive and reversible. Existing crypto records remain readable. New financial tables and endpoints MUST NOT reinterpret BTC/ETH units as bond face amounts or overwrite historical logs.

### 4.1 Runtime baseline

The repository currently targets .NET 8. At specification time, Microsoft's support table lists .NET 8 support ending on 10 November 2026. Choose a supported LTS compatible with the Functions isolated worker before a new public deployment; .NET 10 is the proposed target, subject to a host/package compatibility check. Treat that upgrade as a separate, reviewable migration. [Source: .NET support policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core).

## 5. Target architecture and ownership

~~~mermaid
flowchart TD
    UI[React dashboard] --> API[.NET application API]
    API --> SQL[(SQL Server)]
    FN[Functions orchestration] --> APP[.NET application services]
    API --> APP
    APP --> PY[Python FastAPI adapter]
    CLI[Research CLI and notebooks] --> CORE[Canonical Python research package]
    PY --> CORE
    CORE --> RAW[(Versioned raw artifacts)]
    CORE --> KG[(Neo4j graph and search indexes)]
    CORE --> EV[(Research metadata in SQL)]
    ING[Official-source adapters] --> RAW
    ING --> EV
    APP --> SQL
~~~

The diagram identifies logical ownership, not a requirement for a separate deployment for every box.

### 5.1 .NET responsibilities

- User identity, role authorization, public API, experiment management, and dashboard queries.
- Authoritative portfolio versions, financial ledger storage, order state, trade records, and immutable audit references.
- Scheduling and orchestration through the existing Functions boundary.
- Deterministic policy comparisons against verified analytics outputs.
- Optimistic concurrency checks and atomic application of approved state transitions.
- No independent implementation of curve bootstrapping, accrued interest, bond valuation, or numerical Greeks.

### 5.2 Python responsibilities

- Canonical instrument schedules, curves, pricing, risk, cost assumptions, and pure simulation/state-transition calculations.
- Official-source document/market normalization and research metadata.
- Chunking, embeddings, graph extraction, retrieval, reranking, citations, and research notes.
- LLM execution, bounded specialist coordination, offline experiments, and evaluation.
- CLI access to the same numerical and strategy code used by the API.
- No direct write access to application-owned portfolios, orders, or financial ledger rows.

### 5.3 Single numerical and accounting implementation

The canonical Python simulation function accepts a versioned portfolio state, a time-ordered event batch, market/curve snapshots, and policy configuration. It returns a proposed transition containing numerical outputs, balanced ledger entries, next-state values, and hashes of all inputs.

In application mode, .NET validates the transition contract and policy, verifies the expected portfolio version, and commits all authorized changes in one SQL transaction. It MUST NOT apply arbitrary state changes supplied by an LLM.

In offline research, an in-memory or file-backed state store applies the same transition objects. Financial arithmetic and event ordering remain identical. An integration fixture MUST prove parity between an offline replay and the application path.

This keeps numerical behavior unified while .NET retains transactional authority. Python results are trusted only from the authenticated internal analytics endpoint with matching versioned inputs; model-generated text is never an analytics response.

### 5.4 Persistence and search

- **SQL Server:** application state and canonical normalized research records, with separate logical schemas and writer permissions.
- **Blob/object storage:** immutable source bytes, normalized document artifacts, dataset exports, and large replay bundles. Reuse Azurite locally.
- **Neo4j:** derived graph, chunk embeddings, and lexical indexes. Python is the only writer.
- **Redis:** optional cache and existing infrastructure; correctness and duplicate-commit prevention MUST rely on SQL constraints, not cache TTLs.

Neo4j supports vector similarity and full-text indexing; the proposed design consolidates search there. Pin and test a supported image/driver combination during implementation. This spec does not require the newest search syntax or a specific commercial extension. [Sources: vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/), [full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/).

If the chosen edition cannot support the required temporal filtering, use eligible-set exact scoring for the initial small corpus or record an alternative backend decision. Do not silently weaken time filtering.

### 5.5 Proposed package layout

~~~text
ai-trading-race-ml/
  research_engine/
    contracts/       # schemas, units, identifiers, manifest versions
    instruments/     # security terms, schedules, calendars
    market/          # curves, quotes, macro vintages, adapters
    pricing/         # discounting and valuation models
    risk/            # duration, DV01, key-rate and scenario calculations
    simulation/      # event ordering, settlement, ledger transitions, fills
    evidence/        # raw artifacts, parsing, chunks, provenance
    knowledge/       # ontology, entity matching, graph projections
    retrieval/       # lexical, vector, fusion, graph expansion, ranking
    agents/          # single-agent policies and bounded specialist team
    experiments/     # runners, manifests, evaluation, reports
    cli/             # ingest, price, replay, evaluate, export
  app/               # FastAPI transport/auth/lifecycle adapters
  tests/             # numerical, temporal, retrieval, contract, integration
~~~

Module names are proposed. Existing package and service names MAY remain during migration. Rebranding is not a prerequisite for a working vertical slice.

## 6. Time, data availability, and run reproducibility

### 6.1 Time fields

| Field | Meaning |
|---|---|
| event_at | When the economic or financial event occurred |
| observed_at | When the quote or numerical measurement refers to |
| published_at | When a source made a document or release public |
| available_at | Earliest permitted use under the run's information policy |
| ingested_at | When this platform obtained the artifact |
| decision_as_of | Strict information cutoff for an agent decision |
| generated_at | Operational time a derived artifact was produced |
| order_submitted_at | When an authorized order enters the simulated market |
| executed_at | Time assigned to a later eligible fill |
| settlement_date | Date cash and security delivery settle |
| valuation_at | Time whose portfolio value is reported |

Store instants in UTC and retain source timezone and date precision. Use IANA market timezones for schedules. The application may display Europe/Madrid for this user's interface; U.S. market events retain their market timezone labels and daylight-saving conversion.

### 6.2 Visibility policy

For forward runs, available_at is at least the later of source publication and successful platform receipt. For historical reconstruction, available_at is the verified historical publication time plus a declared conservative acquisition/processing lag; the run MUST identify this as reconstructed availability.

Unknown intraday publication time means availability at the next permitted session under a conservative date-only policy. A revised web page with no archived historical version MUST NOT be treated as the original historical text.

Every document version, macro vintage, instrument term version, observation, graph relationship, summary, feature vector, and fitted-model input MUST satisfy its visibility policy at decision_as_of.

Economic reference periods and policy meeting dates are not publication times. FOMC minutes, for example, are published after the decision meeting. [Source: Federal Reserve meeting calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm).

### 6.3 Preventing derived-data leakage

- Graph edges and summaries inherit the latest availability time of all supporting inputs.
- A past-time graph query MUST NOT use global counts, community labels, descriptions, or embeddings whose contents were enriched with future documents.
- Historical lexical ranking statistics MUST use an eligible corpus snapshot or a declared frozen training-period vocabulary/statistics. Merely filtering final hits is insufficient if future corpus statistics affect ranking.
- Features, scalers, thresholds, query templates, curve forecasts, and entity-resolution rules learned from data MUST be fitted on training history only.
- Retrieval caches MUST include cutoff, evidence snapshot, index/model version, query, and permission scope.
- Source and index snapshots are immutable once attached to a completed run.
- Pretrained LLMs may know later historical outcomes. Time-filtered retrieval does not eliminate this. Label retrospective LLM trading tests accordingly and use forward paper evaluation as the stronger temporal test.

### 6.4 Daily chronology

The initial scheduled decision is at 19:00 America/New_York on supported market business days, conditional on complete inputs. This is a proposed platform schedule, not a claim about a guaranteed publication time.

With daily-only market data:

1. Process due settlements and cash flows under the configured event ordering.
2. Freeze all eligible market and evidence inputs for the decision.
3. Run agents after that day's usable data has become available.
4. Submit validated orders after the decision is complete.
5. Fill at the next eligible daily observation strictly after submission, with explicit costs.
6. Report the intervening exposure and pending orders honestly.

The platform MUST NOT use a closing price to generate a decision and assume a fill at the same already-observed close. Weekend/holiday gaps use a calendar, not a fixed 24-hour increment.

Release-triggered research notes MAY run immediately. Intraday execution remains disabled until quotes, timestamp precision, latency modelling, and event-driven tests pass a separate gate.

### 6.5 Immutable manifests

Every experiment MUST capture:

- Experiment ID, Git commit, spec/config schema version, dependency lock hashes, and numerical-engine version.
- Data mode, universe membership/term versions, source artifacts and checksums, curve and quote manifests, calendar/convention versions.
- Exact decision schedule, information policy, execution/cost/settlement configuration, and cash return assumption.
- Strategy IDs, model/provider identifiers, prompts/tool schema versions, retrieval mode, graph/index/embedding versions.
- Training/validation/test boundaries, fitted artifact hashes, random seeds where supported, and repetition identifiers.
- Resource limits, request budgets, realized usage, retries, failures, and exclusions.

Deterministic replay means identical saved inputs produce identical financial transitions within declared numerical tolerances. Fresh hosted-model calls are not guaranteed bit-for-bit reproducible. Recorded-response replay and fresh-inference reruns MUST be separate modes.

## 7. Market sources and data admission

### 7.1 Source plan

| Source | Initial use | Admission constraint |
|---|---|---|
| U.S. Treasury daily curves | Reference curve inputs and synthetic pricing environment | These are par curves/indicative inputs, not individual executable bond prices |
| Treasury instrument/auction information | Security terms and identifiers for observed-security mode | Validate mapping, effective dates, and supported conventions |
| Federal Reserve statements and minutes | Initial document corpus | Preserve publication dates and exact versions |
| Federal Reserve projections and selected speeches | Corpus expansion | Admit only when timestamps and parsing are validated |
| FRED/ALFRED | Macro observations and historical vintages | Select the vintage known at the information cutoff |
| BLS inflation/employment releases | Later structured release and text context | Use actual publication chronology and preserve revisions |
| Licensed or otherwise permitted security quote provider | Observed-price mode | Provider choice and rights/coverage are an unresolved implementation gate |
| Federal Reserve fitted yield-curve datasets | Optional research comparator | Treat as research products potentially subject to revision |

Treasury describes its par curve as derived from indicative bid-side quotations, rather than actual transactions. The published curve MUST NOT be represented as a security-level execution feed. [Source: Treasury curve methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology).

ALFRED supports retrieval of values known during historical periods. The adapter MUST request the correct vintage rather than defaulting to today's revised history. [Source: FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html).

Federal Reserve fitted curves can be revised or delayed and are staff research products. They are not automatically point-in-time inputs. [Source: Federal Reserve yield-curve models](https://www.federalreserve.gov/data/yield-curve-models.htm).

### 7.2 Adapter contract

Each adapter MUST emit raw artifact references, normalized observations, units, source identifiers, observation/publication/availability fields, quality flags, and ingestion results. It MUST support idempotent re-imports, bounded retries, schema validation, and explicit coverage reports.

Missing values remain missing. No zero substitution, forward filling across a publication boundary without a declared rule, fabricated OHLC bars, or invented bond volume is permitted.

Quote ingestion MUST validate non-crossed bid/ask, finite values, scale, currency, instrument status, timestamp order, stale age, and clean/dirty basis. Curve ingestion MUST validate tenor coverage, input conventions, numerical fit, and permitted interpolation/extrapolation.

### 7.3 Dataset release gate

Before a dataset is eligible for benchmark reporting, produce a coverage summary, missingness report, revision policy, timestamp-confidence report, market-mode label, and checksum manifest. A run whose data fails the gate may be retained for debugging but cannot be promoted as a valid comparison.

## 8. Bond domain, valuation, and numerical risk

### 8.1 Security master

Each instrument MUST have:

| Field group | Required content |
|---|---|
| Identity | Internal security ID, source-native identifiers, synthetic/actual classification, issuer ID |
| Economics | Currency, instrument type, coupon rate, coupon frequency, redemption per 100 face |
| Dates | Original issue, dated/accrual-start date, maturity, effective term-version dates |
| Schedule | Unadjusted coupon periods, adjusted payment dates, entitlement rules |
| Conventions | Day count, business-day/payment adjustment, calendar ID/version, settlement lag |
| Trading units | Minimum face and permitted face increment |
| Provenance | Source artifact/row, checksum, availability, validation status |

Reopenings SHOULD be issuance events linked to an existing economic security. External identifiers MUST NOT be fabricated. Inferred schedules are provisional until validated for observed-security use.

**Quantity is face amount in USD.** A price is explicitly per 100 face. Rates are stored internally as decimal annual rates; basis points and displayed percentages are boundary conversions. Every numerical field has a declared unit.

The synthetic fixture profile proposes 1,000 USD face increments and one-business-day settlement. Actual-security adapters MUST use sourced conventions instead of inheriting fixture assumptions.

### 8.2 Curves and numerical representation

A CurveSnapshot includes curve ID/version, valuation time, available_at, currency, input observation IDs, calibration-instrument definitions, interpolation/extrapolation policy, solver tolerances, build results, and a numerical-engine version.

The engine supplies discount factors D(v,t), where v is the valuation anchor and t is a payment date. Discount factors MUST be positive. Negative rates are permitted where supported; decreasing discount factors MUST NOT be imposed as a universal invariant.

The first curve builder SHOULD use a tested fixed income library and documented synthetic par-instrument schedules. Fit discount factors to admitted par inputs with a declared interpolation rule, initially piecewise linear interpolation of log discount factors between validated nodes. The short-end treatment and stub schedules MUST be explicit in CurveSpecification.

Sparse par observations do not uniquely determine all intermediate discount factors. The builder MUST publish its modelling assumptions and calibration residuals rather than claiming to reproduce Treasury's proprietary implementation exactly.

Unsupported extrapolation beyond the validated horizon is rejected initially. A curve build that lacks required nodes or fails calibration does not become READY.

### 8.3 Pricing contract

For a settlement date s and eligible remaining payments at dates t_i:

~~~text
dirty_price_per_100(s) = SUM(cash_flow_per_100[i] * D(v,t_i) / D(v,s))
clean_price_per_100(s) = dirty_price_per_100(s) - accrued_interest_per_100(s)
settlement_cash_before_fees = face_amount / 100 * dirty_price_per_100(s)
~~~

Payment eligibility uses the supported instrument's entitlement conventions, not only a naive date comparison. Principal repayment is a cash flow. Holiday adjustments, irregular first/last periods, and coupon-boundary behavior require fixtures.

The engine MUST distinguish settlement value from valuation-date present value. Both outputs identify their anchor date. A yield-to-maturity solver has a declared day count and compounding convention and is a quote-conversion tool, not a substitute for the whole discount curve.

Use floating-point arithmetic inside numerical solvers and explicit decimal conversions/rounding for ledger money. Round cash only at documented posting boundaries. Record tolerances, engine versions, and input hashes with each calculation.

QuantLib is the proposed numerical library, with an application-owned wrapper and independent fixtures for supported conventions. Library adoption does not replace validation. [Sources: QuantLib project](https://www.quantlib.org/), [maintainer's bond/cash-flow explanation](https://implementingquantlib.substack.com/p/cash-flows-and-bonds-in-quantlib).

Mutable library evaluation-date/settings state MUST be isolated across concurrent requests. Use process-isolated valuation batches or serialize access to shared settings unless a verified build provides the required isolation. Reset settings explicitly and test interleaved requests with different as-of dates; FastAPI concurrency alone does not establish numerical-library thread safety.

### 8.4 Model value, market value, and relative value

| Output | Definition |
|---|---|
| Observed price | Admitted security quote with its type and timestamp |
| Curve-consistent model price | Discounted value under a named curve and convention set |
| Relative-value estimate | Difference from an explicitly defined reference model |
| Scenario price | Repriced value under a hypothetical or forecast curve |
| Forecast value | Model-dependent future-horizon value, including the stated cash-flow treatment |

The UI MUST NOT collapse these into one unlabeled “fair value.”

Portfolio marking is a separate immutable experiment policy. Synthetic mode uses the declared curve-model marks. Observed-security mode defaults to admitted observed mid prices for reporting, with a separately reportable bid-side liquidation view; settlement-based quotes are normalized to the declared valuation anchor. A missing bid/ask or mid requires an explicitly admitted alternative mark type, not an invisible substitution.

An agent's preferred fair-value estimate MUST NOT be used as the observed portfolio mark merely because it implies a favorable valuation. Missing market marks produce stale/incomplete valuation states under policy. Add a fixture where model value exceeds the market quote and verify that reported observed-market NAV does not acquire an artificial immediate gain.

For observed-security research, the first relative-value method SHOULD fit a smooth reference curve to a declared comparison set with the target security excluded, then report the target's clean-price and yield residuals.

Each residual includes comparison-universe version, fit specification, quote age, bid/ask width where available, and sensitivity to fitting choices. No residual is treated as guaranteed profit. Issue-specific liquidity, financing, and transaction costs can explain apparent differences.

A model calibrated to a security's own quote reproducing that quote is a calibration test. It is not independent mispricing evidence. The synthetic same-curve mode MUST display relative-value output as unavailable or mechanically neutral.

### 8.5 Risk outputs

Return calculation IDs, curve and portfolio snapshot IDs, as-of times, units, and definitions for:

- Clean value, accrued interest, dirty/economic value, and settlement consideration.
- Yield-to-maturity where a supported quote convention exists.
- Yield-based modified duration and convexity, labelled separately from curve effective duration.
- Parallel-curve DV01 and key-rate DV01.
- Portfolio concentration, remaining-maturity buckets, cash availability, pending settlement obligations, and turnover.
- Full-repricing scenario values and PnL.

For face-scaled valuation PV:

~~~text
parallel_dv01_usd = (PV(curve shifted down 1 bp) - PV(curve shifted up 1 bp)) / 2
approximate_pnl_for_upward_shift = -parallel_dv01_usd * shift_in_basis_points
~~~

The sign convention is explicit: positive DV01 denotes an approximate gain for a downward one-basis-point shift. Portfolio DV01 sums economic positions; it is not multiplied again by face after scaling.

Key-rate bumps use specified zero-rate nodes and local bump functions. Initially use 2-, 5-, and 10-year nodes only if they cover the admitted universe; add short-end/end-point support as necessary. Key-rate totals SHOULD approximate parallel DV01 under compatible bump construction, with tolerance established by sensitivity tests.

### 8.6 Scenarios

Versioned initial scenarios:

| ID | Curve transformation | Purpose |
|---|---|---|
| parallel_up_25 | All supported zero-rate nodes +25 bp | Moderate upward rate shock |
| parallel_down_25 | All supported zero-rate nodes -25 bp | Moderate downward rate shock |
| parallel_up_100 | All supported zero-rate nodes +100 bp | Larger stress |
| parallel_down_100 | All supported zero-rate nodes -100 bp | Larger reverse stress |
| steepener_v1 | -25 bp at 2y, 0 at 5y, +25 bp at 10y, interpolated between nodes | Curve-shape exposure |
| flattener_v1 | Reverse of steepener_v1 | Opposite curve-shape exposure |

These are hypothetical shocks, not calibrated forecasts. Define behavior outside the scenario nodes, valuation horizon, settlement treatment, and whether holdings remain fixed. Full repricing is authoritative; approximations display their errors.

An agent MAY select an allowed scenario or provide a sourced hypothesis. It cannot submit executable pricing code, modify numerical results, or redefine the scenario library during an experiment.

## 9. Portfolio accounting, execution, and policy

### 9.1 State and ledger model

Represent orders, fills, pending settlements, economic positions, settled positions, cash, coupon payments, redemptions, fees, and valuation marks separately.

Trade-date economic exposure and settlement-date delivery MUST both be represented. An unfilled accepted order reserves cash/capacity but creates no bond exposure or contractual settlement payable. A fill creates economic exposure and a settlement obligation; committed cash is unavailable for a second purchase. Coupon entitlement follows the validated instrument and settlement rules.

The accounting implementation MUST define balanced posting templates before implementation:

- Purchase and sale recognition, including settlement receivables/payables.
- Settlement of cash and delivered face.
- Coupon accrual/payment and principal redemption.
- Transaction fees and other configured execution costs.
- Mark changes and realized versus unrealized classification.
- External capital flows.

Journal entries MUST balance and have unique event IDs. No endpoint may mutate cash or position totals outside an authorized transition.

Economic equity is:

~~~text
equity = cash + economic_bond_value + settlement_receivables - settlement_payables
~~~

If bond value includes accrued interest, do not add accrued interest again as a separate asset. Coupon payment and the corresponding inventory-value change MUST reconcile without artificial NAV jumps. Principal redemption removes the redeemed position and credits cash exactly once.

Economic bond values use valuation-date present values, not unadjusted settlement-date prices from Section 8.3. The same declared valuation policy applies to pending settlement receivables/payables; the initial model discounts their known cash amounts to valuation time using the admitted short-end curve. If that curve support is unavailable, mark the valuation incomplete rather than mixing anchors silently.

Define the lot method before reporting realized PnL; FIFO is the proposed initial method. Total period PnL is equity change adjusted for external flows. Carry, curve movement, roll-down, fees, and any residual attribution MUST reconcile to that total. Optional attribution detail MUST NOT delay a correct reconciled NAV.

### 9.2 Decision representation and sizing

LLM strategies propose target weights for eligible security IDs and cash, plus structured claims and calculation references. They do not specify arbitrary fill prices.

Weights MUST be finite, nonnegative, reference the frozen universe, and sum to one within 0.000001. A deterministic sizing function converts the proposal into face-amount orders using the decision snapshot and declared rounding/funding rules.

Small adjustments below a proposed two-percentage-point instrument-weight threshold produce HOLD unless needed to restore a breached mandatory limit. Record normalization, rounding, and any rejected target separately from the original proposal.

Initial order support is market orders only. A later limit-order extension MUST compare the limit with eligible later market observations; it MUST NOT execute at a requested limit simply because that value was supplied.

### 9.3 Proposed initial risk configuration

| Setting | Proposed default | Enforcement |
|---|---|---|
| Initial capital | 1,000,000 USD per competitor | Same experiment starting condition |
| Position direction | Long only | Reject negative target weights/face |
| Leverage | Disabled | Fund positions and pending obligations |
| Minimum available cash | 5% of NAV after committed settlements | Funding and reserve check |
| Maximum single-security exposure | 40% of NAV | Economic dirty value |
| Parallel DV01 cap | 600 USD per 1,000,000 USD NAV | Scale limit with NAV |
| Daily gross turnover cap | 20% of NAV | Sum absolute traded dirty notional |
| Minimum face increment | Instrument-specific; synthetic default 1,000 USD | Round through sizing engine |
| Maximum orders per decision | 6 | Bounded execution intent |
| Required daily curve | Current eligible session for scheduled decisions | Skip new risk-taking decision when absent |
| Maximum mark age | One supported market business day | Mark stale explicitly and block dependent actions |

These settings are reproducible starting controls, not optimized strategy choices. Tightening or changing them creates a new configuration version. Missing risk output blocks an affected order; it is never interpreted as zero risk.

Policy evaluates the entire order set and post-trade state. It MUST account for multiple simultaneous orders and pending commitments. An agent cannot make individually valid orders that jointly exceed limits.

If proposed targets fail constraints, return explicit rejection reasons. Optional deterministic projection into the feasible set is a separate policy mode, applied identically across competitors and recorded with before/after targets. It is disabled initially.

Discretionary risk limits govern proposed new orders; they do not cancel contractual obligations. Valid settlements, entitled coupons, and redemptions MUST be processed under accounting/input-validation rules even when market moves have caused a risk-limit breach. Record the breach, block risk-increasing discretionary actions, and permit only explicitly validated risk-reducing actions under the breach policy. Never suppress a due cash flow because documentary evidence is unavailable.

### 9.4 Fill model and cost accounting

The execution model is immutable per experiment and defines quote eligibility, time, spread, slippage/impact, fees, sizing, and stale-quote behavior.

- A purchase uses the eligible ask and a sale the bid when those fields exist.
- Mid-only or curve-based datasets require a declared assumed half-spread.
- The synthetic demonstration profile proposes a half-spread of 0.02 price points per 100 face per side, zero additional slippage, and zero separate commission.
- Report sensitivity at half-spreads 0.00, 0.02, and 0.05. These are illustrative assumptions and MUST NOT be presented as measured Treasury transaction costs.
- Face sizing is fixed at submission under the initial policy. At the later fill, recheck funding, instrument status, data validity, and required risk limits using eligible information.
- If a gap invalidates an order, reject it with the corresponding reason. Do not use a future favorable quote to rescue it or silently change its quantity.
- Do not infer actual market capacity from a dataset with no depth information; observed-mode reports disclose the capacity assumption.

Daily orders use next-supported-session-only time-in-force. They expire at that session's end if no valid fill observation exists; a quote appearing several days later cannot execute the stale intent. A newer target cancels/replaces still-unfilled intents through explicit cancellation events. Completed fills and pending settlements remain binding and cannot be cancelled as if they were unfilled orders.

The initial funding model uses settled cash and reserves purchase commitments. Unsettled sale receivables do not fund new purchases. Within a simultaneous execution batch, use a documented stable priority order and recompute remaining funding after each admitted fill. Any later same-settlement-date netting capability is a separate versioned policy with parity tests.

Consequently, a rotation that needs sale proceeds may require two decisions: sell to cash, wait for settlement, then submit a fresh purchase target. An unfundable simultaneous rotation is rejected rather than financed implicitly. Every strategy receives this funding rule in its policy context.

Cash accrual is explicitly configured. The initial reproducible fixture uses zero cash interest. Research comparisons SHOULD add an admitted cash-rate series, with lag/vintage and compounding rules, before interpreting excess returns.

### 9.5 Commit and concurrency protocol

1. .NET freezes the portfolio version and input snapshot references.
2. Python computes a deterministic transition or sizing/risk result against those inputs.
3. .NET verifies response schema, identity, hashes, engine version, permissions, and policy.
4. In one SQL transaction, verify the expected state version, insert the authorized journal/order events, update state, and persist the audit record.
5. A unique logical-command ID prevents a second financial effect on retries.
6. If the state version changed, discard the stale result and recompute against the new state; never merge two transitions implicitly.

Order submission, execution at a later observation, settlement, coupon payment, and redemption are distinct idempotent commands. Distributed activities may run more than once; the required guarantee is one committed financial effect.

### 9.6 Event ordering

Sort events by effective timestamp, event type priority, and stable event ID. Define and version the priority table for settlements, entitled payments, market updates, decision completion, submissions, and fills.

The clock never moves backward. A future fill cannot affect an earlier decision. Do not expose a next-session quote to an agent merely because the simulator has loaded the whole file.

Fills use the first eligible later observation under the configured session policy. A daily-only simulation MAY model next-day end-of-session execution, but MUST label that timing; it cannot claim next-open execution without open observations.

## 10. Independent strategies and internal agent delegation

### 10.1 Competitor catalogue

| Strategy ID | Behavior | Introduction |
|---|---|---|
| cash | No discretionary trades; configured cash accrual only | First replay |
| static_ladder | Fixed initial allocation with declared maturity/coupon treatment | First replay |
| quant_duration | Transparent deterministic duration-target strategy | Numerical baseline |
| llm_market | Structured market, valuation, risk, and released macro inputs; no document content | AI baseline |
| llm_rag | Same model/policy and numerical inputs plus hybrid passage retrieval | RAG milestone |
| llm_graph | Same model/policy plus bounded graph-assisted evidence retrieval | Graph milestone |
| llm_team | Lead and bounded specialists using the same evidence access as llm_graph | Delegation milestone |

A competitor is a strategy instance with its own portfolio, history, configuration, memory namespace, and budget. Specialists inside llm_team share the parent's objective and produce a single parent decision; they have no separately ranked portfolio.

The passive default is 30% initial market value in the short bucket, 34% intermediate, 30% longer, and 6% cash before transaction costs, subject to per-instrument limits. The extra cash margin supports the minimum reserve after costs and rounding.

All actively invested competitors begin from the same explicitly recorded bootstrap allocation. Bootstrap orders use eligible instruments, identical later fill timing, the same cost model, and the same funding/risk controls. They have a declared initialization-only turnover exemption so a 94% initial investment does not violate the normal 20% daily turnover cap. This exemption is available identically to all invested strategies, never to discretionary later trades. Cash is an intentionally uninvested reference rather than a duration-matched competitor.

Bootstrap costs remain in full-period returns and ledger records. If an initial fill fails, all matched invested variants receive the same valid initialized state or the experiment fails initialization. Select instruments only from the then-eligible universe. Coupon and redemption cash remain cash unless the strategy's frozen policy explicitly reinvests it.

The proposed quant_duration baseline targets four years of effective portfolio duration, subject to all shared limits. It rebalances on the first supported session of a month or when duration drifts by more than 0.25 years. Use a deterministic constrained sizing objective that minimizes squared duration error, then turnover, with a stable security-ID tie break. Freeze its specification before final evaluation. A more sophisticated curve-momentum or rich/cheap baseline is a separately registered strategy.

### 10.2 Controlled comparisons

- **Retrieval experiment:** llm_market versus llm_rag versus llm_graph; keep the base model, policy, numerical inputs, output contract, and execution configuration fixed.
- **Delegation experiment:** llm_graph versus llm_team; hold retrieval access, evidence universe, and calculation tools fixed.
- **Model experiment:** vary provider/model in a separately labelled experiment.
- **Trading-policy experiment:** change signal-to-position rules separately from retrieval or model changes.

Run a budget-matched track with equal aggregate ceilings and an optional capability track with architecture-specific declared budgets. Report actual resource use in both. Equal ceilings do not imply equal realized compute or make the information delivered identical.

Canonical source documents, immutable indexes, and deterministic calculations MAY be shared. Generated conclusions, portfolio states, conversation histories, target allocations, and pending orders MUST NOT be shared across competitors.

### 10.3 Single-agent workflow

1. Receive a frozen numerical/portfolio snapshot and eligible evidence access.
2. Inspect required valuation and risk tools.
3. Retrieve evidence if the strategy permits it.
4. Select allowed scenarios and request deterministic repricing if useful.
5. Produce structured documentary claims, calculations, hypotheses, target weights, and a concise rationale.
6. Pass schema, citation, chronology, and policy checks.

The market-only strategy MUST NOT receive graph-derived summaries or document paraphrases hidden inside its numeric feature bundle. Common instrument terms and released numerical macro values are permitted structured inputs.

### 10.4 Specialist team

The initial team has one lead and two registered specialist roles:

| Role | Task | Required output |
|---|---|---|
| Macro researcher | Compare eligible policy communications and economic releases | Supported claims, source citations, contradictory evidence, gaps |
| Critical reviewer | Challenge the proposed or candidate hypothesis using evidence and calculated exposures | Objections, alternative scenarios, unresolved assumptions |
| Lead | Choose bounded tasks and synthesize results into one proposal | Parent research note and target allocation |

The critical reviewer MAY run independently in parallel on the research question and current exposures, or sequentially on a draft proposal. The chosen workflow is a versioned architecture variant; do not mix them within one reported comparison.

A relative-value specialist MAY replace a role later when it investigates actual observed-price residuals. A simple pricing function remains a deterministic tool and does not require an LLM agent wrapper.

Default bounds:

- Maximum delegation depth: one.
- Maximum specialist invocations: two.
- Maximum model-generation attempts across the whole decision, including repairs: six.
- Maximum aggregate tool calls: twelve, of which at most three retrieve evidence.
- Overall research deadline: 90 seconds.
- Maximum unique evidence delivered across the team: the same 12 chunks / 8,000 evidence tokens as the matched single-agent run.
- Proposed aggregate model input/output ceilings: 32,000 input tokens and 12,000 output tokens per decision; provider context limits may require lower values.
- The experiment MUST also specify a monetary ceiling using a versioned provider price schedule before priced cloud runs.

Both retrieve_evidence and expand_evidence_graph consume the aggregate evidence-call allowance. All evidence text delivered through graph paths or specialist handoffs counts toward one decision-wide evidence registry. Parallel components reserve remaining budget atomically. A repeated chunk counts once against the unique-chunk budget, but every resend counts against model input-token and monetary budgets.

Every provider model call counts as a generation attempt, including task assignment, tool-selection turns, final synthesis, malformed responses, and repairs. A central budget ledger reserves worst-case remaining call/token/cost capacity before parallel work. Six attempts does not mean six final messages plus unlimited tool-loop calls.

The lead MAY decline delegation. Every subtask has a schema, input snapshot, expected output, and remaining resource budget. Retries and schema repairs consume that same budget.

No recursive teams, dynamic tool creation, specialist order submission, autonomous graph writes, or model-authorized changes to permissions or risk limits are allowed.

Store task descriptions, concise returned findings, tool calls, usage, errors, and final explanations. Do not request or expose private chain-of-thought.

Multi-agent research introduces coordination, evaluation, and resource costs; its value is an empirical question for this platform. [Source: Anthropic's multi-agent research system](https://www.anthropic.com/research/multi-agent-research-system).

### 10.5 Tool catalogue

| Tool | Input | Output and restriction |
|---|---|---|
| get_instrument_terms | Admitted security IDs and snapshot | Versioned contractual terms |
| get_market_features | Frozen snapshot ID | Eligible curve levels/changes and numerical macro features |
| get_valuation | Security IDs, curve ID, settlement anchor | Engine-verified price results |
| get_portfolio_risk | Own portfolio snapshot, curve/scenario ID | Exposure and funding outputs |
| run_scenario | Approved scenario ID, own portfolio snapshot | Deterministic full repricing |
| retrieve_evidence | Question, approved filters, cutoff/index IDs | Eligible evidence bundle |
| expand_evidence_graph | Allowed seed IDs and fixed traversal limits | Bounded source-backed paths |
| propose_targets | Structured weights and references | Proposal only; no execution permission |

Tools use typed request schemas and allowlisted query templates. Generated SQL, Cypher, Python, arbitrary URLs, and direct database access are outside the model's tool permissions.

## 11. Document ingestion and canonical evidence

### 11.1 Corpus rollout

The minimum corpus is Federal Reserve policy statements and meeting minutes. Add projections, selected speeches, press-conference transcripts, and Treasury auction documents only after their source adapters and historical timestamps pass validation.

Inflation/employment release text is a later admitted document source; numerical macro observations always enter through the structured vintage-aware data pipeline. Embedded text is never a substitute for a price feed.

Each source registry entry declares owner, allowed domains, discovery method, document types, expected cadence, parser version, timestamp rule, retry limits, and operational freshness expectations.

Prefer structured official HTML and metadata. PDF text extraction is supported through a dedicated parser adapter. OCR and unreadable/scanned documents are quarantined initially. A parser failure creates a visible coverage gap.

### 11.2 Canonical record model

| Record | Important fields |
|---|---|
| Source | ID, allowed locations, adapter/version, cadence, health |
| Document | Stable source-native ID or canonical URL, document type, publisher |
| DocumentVersion | Content hash, title, language, publication/availability/ingestion times, raw artifact URI, parser version, status |
| Chunk | Version ID, heading path, ordinal, text hash, exact normalized text, offsets/page, tokenizer/chunker version |
| Entity | Stable ID, approved type, canonical name, aliases, provenance |
| RelationshipAssertion | Subject, relation, object, support span/source row, time, extraction/version, validation status |
| ExtractionRun | Inputs, model/schema/prompt versions, output artifact hash, usage/errors |
| IndexBuild | Exact versioned members, embedding dimensions/model, graph schema, validation status |
| RetrievalRun | Query, filters, cutoff, build ID, candidates, ranking trace, delivered evidence |

Use SHA-256 hashes for artifact identity. Identical content and unchanged processing configuration reuse existing results. Corrections create new versions; they never overwrite evidence used in a completed historical decision.

Character offsets refer to stored normalized text, with a mapping to original HTML/PDF spans where needed. A citation remains resolvable after a later parser update.

### 11.3 Ingestion state machine

~~~text
discovered -> downloaded -> parsed -> chunked -> extracted -> indexed -> active
                   \-> failed_retryable / quarantined / review_required
~~~

Record each attempt independently. Download and preserve source bytes before normalization. A source outage does not mark yesterday's corpus as newly refreshed.

Chunk by section, targeting 600 tokens with 80-token overlap and a hard limit of 1,000 tokens. Preserve headings and paragraph boundaries. Never merge different releases or document versions into one chunk.

Pin embedding model, dimensions, tokenizer, extraction schema, prompts, and parser versions. Validate an index build before publishing its active manifest. A partially written graph or vector index MUST NOT become visible under a READY build ID.

A change of model, extraction schema, or parser creates a new build. Previous manifests remain available for replay and rollback.

## 12. Knowledge graph and retrieval

### 12.1 Ontology

Initial node types:

- Institution and Person.
- PolicyEvent.
- DocumentVersion and Chunk.
- MacroTopic, MacroSeries, and MacroRelease.
- Instrument.

Initial relationships:

| Relationship | Meaning and admissible source |
|---|---|
| PUBLISHED_BY | Document publisher from verified metadata |
| AUTHORED_BY | Named author/speaker from verified metadata |
| DOCUMENTS_EVENT | Statement/minutes/projections linked to a policy event |
| HAS_CHUNK | Version-to-passage structural relationship |
| MENTIONS_TOPIC | Passage explicitly discusses an approved topic |
| REFERS_TO_SERIES | Passage explicitly identifies an admitted series |
| RELEASE_OF | Structured release links to its macro series |
| REFERS_TO_INSTRUMENT | Explicit instrument reference with a validated entity match |
| ISSUED_BY | Instrument issuer from canonical terms |
| PREVIOUS_EVENT | Chronological link within an approved event series |
| SUPERSEDES | New source version corrects/replaces an older version |

Use stable entity IDs and a controlled alias table. Uncertain matches enter review; do not merge entities solely because names resemble each other.

Each projected edge has an assertion ID, availability/version fields, and source provenance. Multiple or conflicting assertions can coexist. An extraction confidence score is an aid for review, not a calibrated probability of financial truth.

Entity aliases, descriptions, merged identities, and graph-neighbor ordering are versioned and time-filtered too. Future changes to metadata or graph degree MUST NOT change a historical traversal's eligible seeds, fanout, or ranking.

### 12.2 Epistemic boundaries

Separate:

1. **Sourced facts:** source metadata, instrument terms, direct passage assertions.
2. **Calculated results:** prices, duration, DV01, and exposures from the numerical engine.
3. **Hypotheses:** possible policy paths and market effects, explicitly conditional.

The initial graph stores source facts and discovery relationships. It MUST NOT treat an inferred causal rule such as “hawkish statement causes bond prices to fall” as an established source fact.

Holdings, live cash, orders, weights, and numerical risk snapshots stay in their canonical application/calculation stores. Join them through stable IDs at research time. This avoids a second portfolio database and high-frequency graph synchronization.

### 12.3 Baseline hybrid RAG

The retrieval request includes question, decision_as_of, universe IDs, source scope, retrieval mode, and index build.

1. Resolve an eligible corpus snapshot and permitted document versions.
2. Construct a query using the research question, frozen topic vocabulary, and explicit identifiers. Initial experiments use no LLM query expansion.
3. Obtain up to 30 eligible lexical candidates and 30 eligible vector candidates.
4. Fuse ranks using reciprocal rank fusion with configurable constant 60.
5. Deduplicate overlapping passages and retain diversity across relevant documents.
6. Deliver at most 12 chunks and 8,000 evidence tokens, with deterministic truncation priorities.
7. Persist ranking components, excluded candidates, and the delivered bundle.

Historical v1 retrieval uses exact vector scoring over eligible chunks. An approximate alternative requires an index physically restricted to the eligible corpus snapshot; filtering or overfetching from a global ANN index containing future chunks is insufficient, because future members can change which historical candidates are found. Lexical statistics must likewise follow Section 6.3.

Reranking is disabled initially. Adding it creates a separately versioned retrieval experiment rather than an unrecorded improvement.

### 12.4 Graph-assisted retrieval

Use the same initial hybrid candidates and model as baseline RAG.

- Resolve at most eight seed entities/events/documents from the question and eligible candidate metadata.
- Traverse only approved relationships, to a maximum semantic depth of two.
- Limit fanout to eight and visited assertions to forty.
- Materialize supporting source chunks for reached documents/assertions without opening unbounded additional traversal.
- Combine candidates and rank by frozen seed relevance, path length, assertion status, and passage relevance.
- Apply the same final chunk and evidence-token budget as baseline RAG.

Every graph-added passage records its seed, traversed assertions, support spans, availability checks, and ranking contribution. A graph visualization without graph-dependent retrieval is not completion of this feature.

The implementation is a focused domain Graph RAG system. It combines structured relationships with source passages, consistent with the general retrieval pattern described in [Microsoft GraphRAG local search](https://microsoft.github.io/graphrag/query/local_search/). Community detection and global graph summaries are optional later experiments.

### 12.5 Representative graph queries

- Retrieve the statement and minutes for a specific meeting, plus the previous eligible meeting's documents, to compare language about inflation.
- Find earlier eligible speeches by the same speaker discussing a topic present in the current statement.
- Connect a macro-series mention to the release/vintage actually available at the decision cutoff.
- Find a cited instrument's contractual terms, then join the current portfolio and calculated exposure outside the graph.

These queries must work through explicit typed relationships and provenance. They do not assert causal links between a topic and a future price move.

## 13. Research notes, citations, and proposal validation

### 13.1 Structured output

A research note MUST contain:

- Status: supported, insufficient_evidence, or contradictory_evidence.
- Documentary claims, each with citation IDs.
- Numerical findings, each with calculation and input-snapshot IDs.
- Hypotheses/scenarios with explicit assumptions and optional supporting evidence.
- Coverage gaps and counterevidence.
- Retrieval-run IDs and concise final explanation.

A trading proposal adds target weights, the parent strategy decision ID, supporting claim/calculation IDs, and a declared action such as HOLD or REBALANCE. Natural-language certainty cannot substitute for required evidence.

### 13.2 Validation sequence

1. Validate JSON/schema, required fields, finite numeric values, IDs, units, and status.
2. Resolve all citations to the exact delivered bundle and source version.
3. Confirm temporal eligibility and permitted source/index membership.
4. Validate quoted substrings and offsets against stored normalized text.
5. Check numerical references against signed/authenticated internal calculation outputs.
6. Check that material documentary claims cite relevant passages; flag semantic support concerns.
7. Validate target weights, sizing, funding, and risk through deterministic tools.
8. Persist the original proposal and every validation result before any financial commit.

Citation membership and exact quotation checks are deterministic. A semantic claim-support classifier is only a review aid; it is not proof that a passage entails a claim. Evaluate semantic support using a reviewed benchmark.

A proposal declares supporting_claim_ids and supporting_calculation_ids. Missing citations, unresolved sources, future sources, or invalid calculation references deterministically invalidate dependent claims. A versioned semantic-support classifier can flag ambiguous entailment; the initial paper-trading policy abstains on a flagged material dependency and records review_required. Human-reviewed support labels belong to offline evaluation and must not be presented as an automatic live oracle.

Market-only agents may support numerical macro statements with eligible observation/calculation IDs. Forecasts remain hypotheses in every variant. The strategy can return an explicit abstention; do not relabel missing evidence as a confident HOLD decision.

### 13.3 Evidence failure policy

Required evidence unavailable, empty mandatory retrieval, unresolved critical citations, or a failed graph index produces an explicit outcome. A Graph RAG competitor MUST NOT silently become a RAG competitor under the same strategy label.

Existing positions still receive cash-flow processing and valuations where inputs permit. An evidence failure prevents a new discretionary evidence-dependent adjustment; it does not erase the portfolio or hide the failed cycle.

## 14. API contracts and persistence

### 14.1 Contract principles

- Public application APIs are owned by .NET; internal numerical/research APIs are owned by Python.
- Use versioned JSON/OpenAPI contracts and generated or contract-tested C# DTOs and Python models.
- IDs are stable opaque identifiers. Security IDs, source IDs, strategy IDs, and portfolio IDs are distinct types.
- Decimal money, face, prices, rates, and weights SHOULD cross the JSON boundary as decimal strings with declared units. Do not rely on locale-sensitive parsing.
- Timestamps are ISO 8601 instants with offsets; date-only contractual fields remain dates.
- Every input/reference is immutable or explicitly versioned.
- Unknown schema major versions, unsupported units, NaN/infinite numbers, stale state versions, and mismatched snapshot hashes are rejected.
- APIs never expose provider credentials or permit the model to select a different risk policy through request fields.

### 14.2 Public endpoints

| Endpoint | Purpose |
|---|---|
| GET /api/v1/instruments | Admitted securities and term versions |
| GET /api/v1/curves/{snapshotId} | Curve inputs, specification, diagnostics, and nodes |
| GET /api/v1/portfolios/{portfolioId} | Authoritative state and version |
| GET /api/v1/portfolios/{portfolioId}/valuations | Saved valuations with anchors and completeness |
| POST /api/v1/experiments | Validate and persist an immutable experiment definition |
| POST /api/v1/experiments/{id}/runs | Start a run; return 202 and a job ID |
| GET /api/v1/runs/{runId} | Manifest, progress, outcomes, and data-mode labels |
| GET /api/v1/runs/{runId}/comparison | Financial, evidence, and operational comparisons |
| GET /api/v1/decisions/{decisionId} | Proposal, claims, tools, gates, and resulting order references |
| GET /api/v1/evidence/{bundleId} | Delivered passages and graph provenance, permission-scoped |
| POST /api/v1/research-notes | Start an informational query; no order authority |
| POST /api/v1/admin/ingestions | Operator-triggered source refresh |
| POST /api/v1/admin/index-builds | Rebuild/validate an index; never mutate an old manifest |
| POST /api/v1/admin/paper-cycles | Trigger a configured forward cycle |

Long public operations return job status links rather than holding browser connections open. Pagination/filtering are required for histories and evidence lists. Read-only viewers cannot launch administrative work.

### 14.3 Internal endpoints

| Endpoint | Contract |
|---|---|
| POST /internal/v1/analytics/price | Price an admitted instrument batch against frozen curves |
| POST /internal/v1/analytics/risk | Portfolio risk/scenario outputs for exact snapshots |
| POST /internal/v1/simulation/transitions | Pure numerical transition proposal; no application DB mutation |
| POST /internal/v1/strategies/decisions | Bounded proposal generation for one strategy/cycle |
| POST /internal/v1/evidence/retrieve | Retrieve a scoped evidence bundle |
| GET /internal/v1/capabilities | Engine/model/schema/convention capabilities and readiness |

The existing Functions activity may call a bounded internal operation synchronously while the public run remains asynchronous. The internal client timeout MUST exceed the configured 90-second decision deadline plus transport margin. Large replays run through checkpointed activities/CLI batches, not a single unbounded HTTP request.

Ingestion, extraction, embedding, and rebuild work MUST NOT execute inside a decision request. A decision uses an already READY snapshot.

### 14.4 Decision request example

The following IDs and values are illustrative contract examples, not observed market data or computed recommendations. The full machine-readable schema is an implementation deliverable.

~~~json
{
  "schemaVersion": "1.0",
  "experimentId": "exp-example",
  "runId": "run-example",
  "cycleId": "cycle-2025-02-18",
  "decisionId": "decision-example-graph",
  "strategyId": "llm_graph",
  "decisionAsOf": "2025-02-19T00:00:00Z",
  "marketSessionDate": "2025-02-18",
  "availabilityPolicy": "reconstructed_publication_plus_lag_v1",
  "dataMode": "synthetic_curve",
  "portfolioSnapshot": {
    "id": "portfolio-snapshot-example",
    "version": 12,
    "contentHash": "sha256:example-portfolio"
  },
  "marketSnapshot": {
    "id": "market-snapshot-example",
    "contentHash": "sha256:example-market",
    "curveSnapshotId": "curve-example"
  },
  "instrumentUniverseVersion": "universe-example-v1",
  "evidenceSnapshotId": "evidence-example-v1",
  "indexBuildId": "index-example-v1",
  "strategyConfigId": "graph-policy-example-v1",
  "riskPolicyId": "treasury-long-only-v1",
  "budget": {
    "maxGenerationCalls": 6,
    "maxToolCalls": 12,
    "maxEvidenceCalls": 3,
    "maxUniqueEvidenceChunks": 12,
    "maxEvidenceTokens": 8000,
    "maxInputTokens": 32000,
    "maxOutputTokens": 12000,
    "deadlineSeconds": 90
  }
}
~~~

Referenced snapshots are delivered inline or through immutable authenticated artifacts whose hashes are verified. Tools cannot substitute today's mutable portfolio or market state for these references.

### 14.5 Result envelopes

Every strategy result MUST return:

| Field group | Required fields |
|---|---|
| Identity | Schema, run/cycle/decision/strategy IDs and input hashes |
| Outcome | Explicit outcome enum, completion time, error/abstention reasons |
| Proposal | Action, target weights, supporting claim/calculation IDs |
| Evidence | Claims, citations, counterevidence, hypotheses, coverage gaps, retrieval-run IDs |
| Numerics | Verified calculation references and units |
| Usage | Attempts, model calls, tokens, tools, duration, priced-cost estimate and schedule ID |
| Versions | Model/provider, prompts, tool schema, engine, evidence/index manifests |

Weights example:

~~~json
{
  "action": "REBALANCE",
  "targetWeights": [
    {"securityId": "SYN-USD-NOTE-001", "weight": "0.30"},
    {"securityId": "SYN-USD-NOTE-002", "weight": "0.34"},
    {"securityId": "SYN-USD-NOTE-003", "weight": "0.30"},
    {"securityId": "CASH-USD", "weight": "0.06"}
  ],
  "supportingClaimIds": ["claim-example"],
  "supportingCalculationIds": ["calculation-example"]
}
~~~

This example demonstrates schema shape only. It is not executable until its references and policy checks resolve.

A calculation result includes calculation type/version, input hashes, as-of and settlement anchors, per-100 versus face-scaled units, completeness, numerical diagnostics, and engine provenance. A transition result additionally includes expected/new state versions, proposed journal entries, position/cash changes, and a reconciliation report.

### 14.6 Error semantics and idempotency

- 400/422: invalid request, unsupported schema/convention, or invalid units.
- 401/403: authentication/authorization failure.
- 409: mismatched idempotency payload, stale portfolio version, or incompatible immutable configuration.
- 429: declared rate/budget concurrency limit.
- 503: required dependency or numerical capability unavailable.
- Normal domain outcomes such as insufficient evidence or HOLD are explicit result statuses, not generic HTTP failures.

An idempotency key identifies a logical command and is bound to its canonical request hash. Reusing the key with different content returns conflict. Logical decision identity includes run, cycle, strategy, repetition, and snapshot versions; it MUST NOT be only agent ID plus latest candle timestamp.

Model retries are distinct attempts under one logical decision. Select the first fully valid response within policy/deadline; retain all attempts and costs. Retried financial commits return the already committed result.

### 14.7 Canonical table groups

| Owner/schema | Records | Key constraints |
|---|---|---|
| .NET / application | ExperimentDefinition, ExperimentRun, StrategyInstance, Cycle, RunManifest | Immutable definition versions and unique logical run IDs |
| .NET / application | Portfolio, PortfolioStateVersion, OrderIntent, Fill, Settlement | Strategy isolation, expected-version checks, unique fill/settlement effects |
| .NET / application | Journal, JournalEntry, CashFlowEvent, ValuationSnapshot | Balanced journals and one effect per economic event |
| .NET / application | Decision, DecisionAttempt, PolicyEvaluation, ToolTrace, UsageRecord | Audit persists even for HOLD/failure/no graph |
| Python / research | Source, Document, DocumentVersion, Chunk, Entity, RelationshipAssertion | Stable IDs, immutable versions, support provenance |
| Python / research | MarketObservation, MacroVintage, InstrumentTerms, CurveSnapshot | Point-in-time eligibility and explicit units |
| Python / research | CalculationResult, ScenarioResult, TransitionProposal | Immutable input/output hashes, engine versions, units, anchors, and content-addressed artifacts |
| Python / research | ExtractionRun, IndexBuild, RetrievalRun, EvidenceBundle | Exact manifests and rebuildability |
| Shared references | ArtifactManifest and content-addressed object IDs | Writer ownership per record; no competing mutable masters |

Application persistence may reference research IDs but MUST NOT modify research-owned records. Python may receive application snapshot artifacts but MUST NOT write application-owned financial state.

Numerical results and uncommitted transition proposals are canonical research-owned artifacts. .NET stores their immutable references and the exact authorized transition with the committed journal. A model-produced calculation reference is resolved and verified against that store; the model cannot mint a trusted calculation by supplying a plausible ID.

Use EF migrations for application-owned tables and a documented Python migration path for research-owned tables. Reuse one SQL Server deployment initially; this does not imply independent microservice databases.

## 15. Orchestration, failure behavior, and recoverability

### 15.1 Cycle sequence

1. Discover/ingest required data outside the decision path.
2. Validate data coverage and publish READY market/evidence manifests.
3. Process previously due financial events.
4. Create one frozen common market/evidence cutoff and one own-portfolio snapshot per competitor.
5. Fan out bounded strategy proposals in parallel.
6. Validate outputs and persist every logical outcome.
7. Submit authorized order intents; schedule eligible later execution observations.
8. Apply fills, settlements, and cash flows through idempotent transition commits.
9. Value all portfolios under the common reporting convention.
10. Publish metrics and comparison views with completeness flags.

Durable orchestrators coordinate IDs and activities. Non-deterministic I/O, model calls, and mutable wall-clock reads stay inside activities or use the orchestrator's supported deterministic clock. Activity retries MUST NOT duplicate financial effects.

### 15.2 Outcomes

| Outcome | Financial behavior |
|---|---|
| completed_hold | Intentional no adjustment; continue normal financial processing |
| completed_proposal | Validate and potentially create authorized intents |
| abstained_insufficient_evidence | No new evidence-dependent risk; retain explicit abstention |
| review_required | No autonomous new trade for the flagged proposal |
| failed_invalid_output | No order; preserve attempts and diagnostics |
| failed_dependency | No affected new order; preserve dependent failure |
| failed_budget | Stop generation/tools and record consumed resources |
| skipped_stale_data | Skip matched discretionary cycle or affected execution under policy |
| cancelled | Cancel uncommitted work; committed events remain authoritative |

Job lifecycle states queued, running, completed, failed, and cancelled are separate from strategy outcomes.

### 15.3 Failure isolation

- Invalid shared market inputs skip the matched decision cycle for all competitors.
- One model failure does not stop successful competitors. The failed portfolio still receives due cash flows and eligible marks.
- Missing an optional document is a visible coverage gap. Missing a source declared mandatory by an experiment blocks its dependent decision.
- A mandatory graph failure cannot be relabelled as successful plain RAG.
- A stale or invalid execution observation produces no fill and follows time-in-force rules.
- A financial reconciliation failure blocks further commits to that portfolio and raises an operator-visible error.
- Retry transient fetch/provider failures with bounded backoff within the original deadline and usage ceiling.
- Recovery never rewrites the contents of a completed manifest or accepted decision.

### 15.4 Checkpoints and recovery

Checkpoint after each completed replay cycle, using the financial event position, portfolio versions, next pending events, and immutable manifest references.

Restarting a failed worker MUST resume from the last committed checkpoint without duplicate trades, settlements, coupons, or redemptions. SQL/object-store backups are authoritative. Neo4j can be rebuilt from canonical records; demonstrate the rebuild and compare content/version membership.

Recorded-response replay must work without provider access. Source fixtures and model outputs in public demo bundles MUST be suitable for redistribution; restricted datasets remain local or behind the appropriate access boundary.

## 16. Research methodology, metrics, and validation

### 16.1 Experiment registration

Before an evaluation run, register its hypothesis, architecture variants, primary metrics, dataset/time splits, cost assumptions, risk policy, resource ceilings, and exclusion rules.

Keep a trial registry. A configuration selected after many experiments MUST NOT be presented as an untouched held-out result. Freeze prompts, extraction/ranking settings, signal mappings, and strategy parameters before final evaluation.

Use chronological development, validation, and held-out intervals chosen after the data admission report. A proposed starter cohort spans 24–48 months of supported daily data; exact dates belong to the dataset manifest rather than this specification.

Walk-forward recalibration uses only earlier eligible data. Training labels whose return horizons cross an evaluation boundary are excluded or purged, with the gap recorded. Report overlapping holding periods and avoid treating correlated trades as independent samples.

### 16.2 LLM and retrieval comparisons

Repeat stochastic LLM configurations at least three times when affordable, using recorded repetition IDs. Pin temperature and provider seeds when supported, and record when deterministic behavior is unsupported. A seed is not a guarantee of identical hosted responses.

The budget-matched comparison uses the same aggregate ceilings. The capability comparison records architecture-specific ceilings. Both report realized usage and budget failures.

All comparisons MUST disclose:

- Synthetic versus observed quote mode.
- Retrospective versus forward information policy.
- Possible pretrained-model knowledge of later historical events.
- Model aliases versus pinned identifiers and any provider drift.
- Data gaps, failed cycles, and replay exclusions.
- Actual duration/DV01 exposure, rather than assuming equal risk because limits match.

Do not tune a prompt after inspecting a held-out outcome without declaring the resulting run a new trial.

### 16.3 Financial metrics

Use a common daily valuation convention, calendar, and reconciled total-return equity series.

Required reporting:

- Gross and net total return, elapsed period, and annualized return only when meaningful.
- Daily volatility, maximum drawdown, recovery duration, and observation count.
- Turnover, spread/slippage/fee costs, number of decisions, proposals, fills, and expiries.
- Cash proportion, average/maximum DV01, effective duration, and maturity/key-rate exposure.
- Coupon income, redemption, realized/unrealized PnL, and attribution reconciliation.
- Comparisons with cash, passive allocation, and a disclosed risk-comparable reference.
- Model/retrieval costs reported separately from financial execution costs, plus optional combined economic-cost results.

Sharpe uses a declared excess-return series and annualization convention. Display unavailable for missing risk-free inputs, zero variance, or too few valid returns. A proposed UI minimum is 60 daily returns, explicitly a reporting threshold rather than proof of statistical reliability.

Win rate, if shown, uses closed lots and the configured accounting method. The current heuristic of comparing sell prices with a contemporary average entry price is insufficient.

Where sample size permits, report paired architecture differences and uncertainty using a time-series-aware method such as a block bootstrap with the block policy declared. A short demo leaderboard MUST NOT imply statistical significance.

### 16.4 Evidence benchmark

Create a versioned initial 60-question benchmark:

- 20 direct-document questions.
- 20 questions requiring multiple documents/events.
- 20 relationship-sensitive, revision-sensitive, temporal, or insufficient-evidence questions.

Split development and held-out questions before tuning, preserving category balance. Store expected evidence IDs, support annotations, acceptable abstentions, and adjudication notes.

Metrics include evidence recall/precision at K, answer completeness, citation ID/span validity, manually reviewed factual support, temporal violations, counterevidence coverage, abstention quality, latency, and realized cost.

Graph-specific reporting MUST show:

- Additional passages retrieved because of graph traversal.
- Questions helped or harmed by those passages.
- Added latency and resource usage.
- Relationship/entity-resolution errors.
- Performance on multi-document/time/entity questions versus simple lookup questions.

Structural release gates are zero accepted future-evidence citations and 100% resolvable citation IDs/spans on the test fixtures. A proposed quality target is at least 95% manually supported factual claims on the held-out responses; report counts and reviewer disagreements, and label this as a project target rather than an achieved or statistically certain rate.

Graph RAG is a completed experiment when its implementation and evaluation pass, even if it does not outperform RAG. An operational default should be selected using the measured benefit/cost trade-off.

### 16.5 Numerical and financial fixtures

| Fixture | Acceptance condition |
|---|---|
| Regular fixed-coupon schedule | Independently checked coupon/principal dates and amounts |
| Coupon boundary and holiday | Correct accrual, entitlement, date adjustment, and settlement |
| Clean/dirty conversion | Price difference equals accrued interest under declared convention |
| Settlement/valuation anchors | Discount-factor ratio and pending cash valuations use consistent anchors |
| Curve calibration | Declared input residual tolerances pass; invalid/missing inputs rejected |
| Negative-rate environment | Supported cases do not fail an unjustified monotonic-discount constraint |
| DV01/key-rate/scenario | Agreement with independently derived fixtures and stable bump tests |
| Concurrent valuation dates | Interleaved requests cannot contaminate evaluation-date settings |
| Buy/sell/settle/coupon/mature | Correct economic and settled positions, cash, and balanced journals |
| Repeated command | No second financial effect |
| Competing state versions | Stale transition rejected |
| Pending order/cancellation | Reserved funding, expiry, and replacement behave deterministically |
| Delayed/missing quote | No stale or same-observation hindsight fill |
| Offline/application parity | Same transitions, ledger totals, and valuations from the same fixture |

Proposed price tolerance for regular reference fixtures is 0.0001 per 100 face. Ledger postings reconcile exactly at the declared cash precision, initially cents. Risk and complex-convention tolerances MUST be justified by independent fixtures and numerical sensitivity, not merely set to make tests pass.

Use independently worked examples or a separate trusted reference, not only the same library wrapper calling itself as an oracle.

### 16.6 Temporal and failure tests

Mandatory integration scenarios:

- A meeting's minutes are unavailable on its earlier statement date.
- A later correction does not alter a saved earlier decision.
- A revised macro value is excluded until that vintage is available.
- Future corpus additions do not change historical retrieval rankings or graph fanout.
- Future aliases/descriptions cannot alter past entity resolution.
- Simultaneous specialists cannot overspend the global evidence/token budget.
- Every provider call, repair, and tool-selection turn consumes the aggregate ceiling.
- A failed mandatory graph does not masquerade as baseline RAG.
- Empty/contradictory evidence produces the configured abstention/review outcome.
- A timeout, worker restart, or duplicate activity does not duplicate a trade or cash flow.
- A malformed model proposal cannot write financial state.
- A source outage remains visible and cannot falsely advance freshness.

## 17. Product interface and demonstration

### 17.1 Experiment overview

Extend the current dashboard with:

- Data mode, run type, dates, simulated clock, model/configuration versions, and manifest link.
- Equity curves and risk/cost/failure metrics beside the leaderboard.
- Explicit separation of cash references, quantitative policies, single agents, and one-portfolio specialist teams.
- Missing/stale valuation badges and exclusion reasons.
- Filters for repetition, architecture, model family, risk policy, and execution assumptions.

Do not rank runs together when their data modes, cost policies, or evaluation windows are incompatible.

### 17.2 Instrument and valuation page

Show contractual terms and source provenance; current eligible quote type/time; model versus observed clean/dirty values; accrued interest; upcoming payments; curve specification and calibration; duration/DV01/key-rate results; scenario prices; and the explicit relative-value benchmark where available.

Synthetic instruments carry a persistent synthetic label. A curve-generated price MUST NOT visually impersonate a market quote.

### 17.3 Portfolio and decision pages

Portfolio details show settled/economic face, pending orders, settlement obligations, available versus committed cash, payment calendar, reconciled NAV, and risk.

Decision details show:

- Frozen input IDs and information cutoff.
- Original target allocation, deterministic sizing, policy checks, authorized orders, and later fills.
- Concise rationale, cited claims, numerical tool outputs, scenarios, counterevidence, and coverage gaps.
- Parent/specialist task tree with structured returned findings and usage.
- Abstention/failure/expiry reasons with actual financial consequences.

The interface exposes useful explanations and audit evidence, not private chain-of-thought.

### 17.4 Evidence explorer

Selecting a citation opens its exact source version and highlighted passage, with title, source URL, publication/availability timestamps, and offsets/page.

A bounded graph view displays only relevant nodes/edges. Selecting an edge reveals supporting assertions, time/version, and extraction method. Selecting an instrument can join current valuation/risk results without pretending they are source facts stored in the graph.

### 17.5 Replay and health

Saved-data replay supports pause, step, and speed adjustment. Clearly label accelerated historical playback and show the simulation date separately from operational time.

Health shows last successful ingestion per source, current READY manifests, missing coverage, failed jobs, dependency readiness, and usage against budget.

### 17.6 Required demo script

1. Open a recorded experiment with the quantitative, market-only, RAG, and Graph RAG variants.
2. Inspect one bond's terms, cash flows, model price, and risk.
3. Advance to a policy-document event.
4. Compare the evidence delivered to RAG and Graph RAG.
5. Inspect each strategy's proposal or abstention and the deterministic policy result.
6. Advance to the next admissible execution observation and settlement.
7. Compare resulting exposure and portfolio outcomes.
8. Show one failure or rejected proposal and its audit trail.
9. Optionally repeat with the specialist-team competitor.

The demo uses recorded data/responses and can run without new model calls. A live-provider demonstration is optional.

## 18. Operations, deployment, and maintenance

### 18.1 Supported deployment profiles

| Profile | Components | Purpose |
|---|---|---|
| Fixture/research | Python CLI, local fixture artifacts, optional SQL adapter | Fast numerical/replay development |
| Local application | Existing .NET API, Functions, Python, React, SQL Server, Azurite; Neo4j for graph profile | End-to-end development |
| Cloud paper demo | Existing Azure application surfaces plus admitted graph/object storage | Bounded scheduled paper runs and dashboard |

Redis remains optional for caching; it is not the financial correctness mechanism. Do not introduce Kubernetes, Kafka, a second vector database, or separate specialist deployments as initial requirements.

Provide one documented local startup command and separate seed/fixture commands. Pin dependencies/images instead of depending indefinitely on mutable latest tags.

### 18.2 Configuration

Versioned configuration covers data mode, source registry, convention/calendar sets, curve builder, risk limits, execution costs, strategy/model/prompt IDs, retrieval/index settings, schedules, and resource ceilings.

Environment variables and secret storage provide credentials, not hidden strategy behavior. A run manifest records resolved non-secret settings. A developer must be able to explain a result without reconstructing undocumented environment state.

### 18.3 Observability

Propagate experiment, run, cycle, strategy, decision, attempt, calculation, retrieval, command, and journal IDs.

Required metrics:

- Source freshness and coverage, parser/extraction errors, quarantine counts.
- Curve calibration failures, stale marks, incomplete valuations, reconciliation failures.
- Decision latency, model/tool calls, tokens, actual costs, retries, abstentions, and budget exhaustion.
- Retrieval/citation failures and graph traversal limits.
- Pending/expired orders, duplicate-command detections, concurrency conflicts, and checkpoint age.

Errors must identify whether they affect a single source, a strategy, a cycle, or the financial state. Avoid logging credentials or unrestricted full provider payloads. Store authorized audit artifacts with a retention/access policy.

For future scheduling, cost limits and ingestion freshness alerts are configurable. This document does not create an automation or deploy any monitoring service.

### 18.4 Security boundaries

- Reuse application authentication and roles for public endpoints.
- Authenticate internal service calls; isolate databases and graph ports from public access.
- Allowlist fetch hosts and validate redirects; agent tools cannot fetch arbitrary URLs.
- Treat retrieved instructions as untrusted document content.
- Execute only typed allowlisted tools, with parameterized database/graph queries.
- Separate model credentials from execution/state-write authority.
- Permit only application services to commit financial transitions.
- Scope generated-result caches and evidence access by experiment/strategy/permission.
- Preserve provider/data usage restrictions in exports and public demo artifacts.

These boundaries are part of making the proposed agent tools reliable; they do not introduce a user approval step for simulated decisions.

### 18.5 Maintenance model

The recurring work is data-source health, parser/schema drift, model/embedding changes, evidence quality, dependency updates, and replay validation.

Keep maintenance bounded through:

- One supported deployment path and a small source registry.
- Stable typed graph relationships and reviewed entity aliases.
- Deterministic metadata relationships wherever possible; constrained extraction for text assertions.
- Rebuildable graph/vector indexes and immutable canonical inputs.
- Batched numerical calls and isolated valuation settings.
- A small fixed regression suite run after dependency, prompt, model, parser, or convention changes.
- Saved-data/recorded-response operation when live integrations are unavailable.

No periodic full-corpus re-embedding is required merely because a trading cycle runs. Index only changed sources or changed processing versions. Ingestion/extraction costs have a separate budget and usage record from per-decision inference.

## 19. Delivery plan and milestone acceptance

Each milestone should be independently runnable and reviewable. Complete the smallest working vertical slice before expanding the universe or source registry.

| Milestone | Deliverable | Exit criteria |
|---|---|---|
| M0: foundation | Architecture decisions, runtime compatibility, contracts, source feasibility | Supported runtime plan; ownership settled; sample data legally/technically usable; legacy behavior preserved |
| M1: numerical slice | One synthetic fixed-rate instrument, curve, cash flows, price, risk | Independent price/accrual/curve fixtures; explicit units and anchors; no model calls required |
| M2: financial replay | Shared transition engine, ledger, settlement, costs, passive/quant policies | Coupon/maturity/expiry/concurrency tests; offline/application parity; saved replay report |
| M3: first AI competitor | Market-only tool-using agent, strict proposal schema, policy/audit path | Bounded calls; all outcomes logged; no direct model writes; comparison with numerical baselines |
| M4: document RAG | Source versions, chunks, hybrid retrieval, citations | Temporal fixtures; citation resolvability; benchmark annotations; explicit insufficient evidence |
| M5: Graph RAG | Typed projection, bounded traversal, graph evidence trace | Rebuild/rollback; graph-dependent evidence; matched RAG comparison |
| M6: specialist team | One lead and bounded researcher/reviewer roles | Shared budgets; no recursive authority; matched delegation experiment |
| M7: product/report | Extended dashboard, experiment exports, demo bundle, methodology card | Reproduce saved run; inspect evidence-to-trade chain; report risk, cost, and failures |
| M8: observed quotes | Validated real securities and independent quote adapter | Terms/coverage/rights/timestamps validated; observed pricing/fills labelled; relative-value method tested |
| M9: forward/intraday extension | Scheduled forward runs; optional release-driven intraday | Feed freshness/latency/capacity gates and execution chronology pass before intraday claims |

M8 is not required to demonstrate genuine RAG/Graph RAG or the synthetic research platform. It is required for claims about actual individual-security relative value and observed-price execution. M9 does not require live brokerage.

### 19.1 Initial implementation backlog

1. Add versioned contracts and an immutable experiment/market/portfolio snapshot model.
2. Extract an importable Python package and build one pricing fixture.
3. Add security/curve schemas and canonical artifact storage.
4. Implement pure event transitions and a transactional .NET adapter.
5. Replace the new-path candle/spot assumptions in context, sizing, risk, and valuation.
6. Add daily replay and common initialization, cash/passive/quant references.
7. Introduce llm_market and its audit/usage records.
8. Implement Fed statement/minutes ingestion and historical source versions.
9. Implement baseline hybrid retrieval and citation validation.
10. Add graph projection/traversal and the evidence comparison benchmark.
11. Add specialist orchestration only after single-agent behavior is measurable.
12. Extend UI, export a reproducible report, and document limitations.
13. Resolve quote-provider access before activating observed-security relative-value work.

### 19.2 Planning scale

For one developer already familiar with the repository, M1–M3 are a plausible first substantial prototype over several focused weeks. Completing the broader daily platform through M7 is an order-of-magnitude 6–12+ focused-week effort, subject to numerical/data issues and desired polish. This is a planning assumption, not a delivery commitment. Revise after the first end-to-end replay. Observed quote acquisition and intraday operation have separate data-dependent estimates.

## 20. Requirement traceability and release gates

| ID | Requirement | Primary acceptance evidence |
|---|---|---|
| FI-01 | Price supported individual instruments with explicit conventions/anchors | Independent numerical fixtures and valuation API outputs |
| FI-02 | Distinguish market/model/scenario/relative value | API types, UI labels, synthetic-mode restrictions |
| FI-03 | One numerical and simulation implementation | Offline/application parity replay |
| FI-04 | Balanced, idempotent ledger and correct cash flows | Reconciliation, duplicate, settlement, coupon/maturity tests |
| FI-05 | Temporal integrity across all inputs and indexes | Future-document/quote/vintage/metadata/ranking fixtures |
| FI-06 | Independent portfolios and matched experiment inputs | Snapshot manifests and isolation tests |
| FI-07 | Genuine source-document RAG | Versioned corpus, delivered passages, citation checks, benchmark report |
| FI-08 | Graph relationships influence evidence retrieval | Traversal traces and graph-added-evidence comparison |
| FI-09 | Bounded specialist architecture is one competitor | Task tree, budget-reservation tests, authority isolation |
| FI-10 | Discretionary trading gates plus mandatory-event accounting validation | Recorded policy decisions, rejected orders, and due-event processing during limit breaches |
| FI-11 | Honest execution and expiry | Later-observation fills, spread assumptions, time-in-force tests |
| FI-12 | Every outcome is auditable | HOLD/failure/abstention records without graph dependencies |
| FI-13 | Reproducible research and replay | Immutable manifests, recorded-response demo, exports |
| FI-14 | Financial and AI evaluation remain distinct | Net/risk/cost metrics plus retrieval/support results |
| FI-15 | Synthetic and observed modes cannot be confused | Separate result groups, metadata, and data admission gates |
| FI-16 | Recoverable, bounded operations | Checkpoint restart, index rebuild, source-failure and cost-cap tests |

A release is complete for its declared milestone when its corresponding requirements and fixtures pass. No positive return or superiority claim substitutes for correctness, and an honest negative research result does not invalidate a technically complete experiment.

## 21. Open implementation decisions and known limitations

| Item | Current position | Resolution point |
|---|---|---|
| Actual-security quote source | Unselected; no assumption of free executable historical quotes | Before M8 |
| Real-security conventions | Must be sourced and tested per adapter | Before observed-security admission |
| Neo4j edition/image/hosting | One proposed graph/search backend; choose supported pinned deployment | M0/M5 |
| Embedding and generation models | Provider-neutral versioned configuration | Before first measured AI run |
| Model monetary ceilings | Required configuration based on current provider price schedule | Before priced cloud runs |
| Dataset years and splits | Choose after coverage/availability audit | Before experiment registration |
| Numerical tolerance extensions | Set per supported convention and conditioning | M1/M2 |
| Cash interest series | Fixture defaults to zero; admitted lagged series preferred for research | Before excess-return interpretation |
| Intraday feed and execution | Disabled initially | M9 gate |
| Expanded credit universe | Deferred | Separate future specification |

Known research limitations include pretrained-model hindsight, indicative-versus-executable prices, revised datasets, imperfect source timestamps, entity/extraction errors, model drift, limited sample size, and unmodelled market capacity. Each run reports the limitations that apply to its mode; the system does not hide them behind a single aggregate score.

## 22. Required repository artifacts

Implementation should leave:

- This specification and architecture decision records for material departures.
- Versioned OpenAPI/JSON schemas, migration instructions, and fixture manifests.
- Canonical Python package with CLI examples and tested numerical/accounting behavior.
- Source-adapter fixtures and a provenance/time-policy guide.
- RAG/Graph RAG benchmark questions, annotations, and evaluation scripts.
- Registered experiment definitions, methodology cards, and reproducible reports.
- A recorded demo bundle and dashboard walkthrough.
- A short operations guide covering startup, freshness failures, budget limits, checkpoints, backups, and index rebuild.
- Updated README and project description reflecting implemented scope only.

The resulting project can be described as a fixed income research and paper-trading platform with evaluated retrieval and agent architectures once the corresponding milestones are implemented. Claims about real bond valuation, observed-market performance, or specialist benefits must match the delivered evidence.
