# Operations guide — Fixed Income Research Lab

Short operator guide (spec §18, §22). Two supported profiles: **fixture/research** (Python only,
offline) and **local application** (.NET API + Functions + Python + React + SQL Server + Azurite,
optional Neo4j). No cloud profile is documented for the fixed income path yet.

## 1. Fixture/research profile (offline, no services, no credentials)

```bash
cd ai-trading-race-ml
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt   # once
.venv/bin/python -m research_engine demo verify      # replay the recorded demo bundle (~20 s)
.venv/bin/python -m research_engine --help           # all commands (also installed as fi-research)
```

Seed/fixture commands (all offline unless marked NETWORK):

| Purpose | Command |
|---|---|
| Ingest FOMC fixtures into the evidence home | `fi-research ingest fed [--include-synthetic]` (NETWORK only with `--online` / `--refresh-fixtures`) |
| Build, validate and activate an evidence index | `fi-research index build --activate [--graph memory\|neo4j]` |
| Re-validate an index (reload + independent rebuild compare) | `fi-research index validate [--build-id ID]` |
| Evidence benchmark | `fi-research benchmark run --split dev\|heldout\|all --output FILE` |
| Curve / price / risk / scenario / universe / data admission | `fi-research curve build`, `price`, `risk`, `scenario`, `instruments list`, `market admission` (see `--help`) |
| Offline replay from a config | `FI_TRANSITION_SIGNING_KEY=… fi-research replay run --config C.json --run-dir D` |
| Resume an interrupted replay | `fi-research replay resume --run-dir D` |
| Report for a run directory | `fi-research replay report --run-dir D` |
| Parity fixtures for .NET | `fi-research parity export` (writes `contracts/fixtures/parity/`) |
| Contract schemas for .NET | `python -m research_engine.contracts.export` (writes `contracts/schemas/v1/`) |
| Agent sample capture + verify | `fi-research record --experiment demo-sample-2023-06 --from 2023-06-13 --to 2023-06-16 --overwrite` |
| Demo bundle | `fi-research demo build --overwrite` / `fi-research demo verify` |

The evidence home is `--home`, else `$FI_RESEARCH_HOME`, else `~/.cache/fi-research`
(`research.sqlite` plus a content-addressed artifact store). `FI_RESEARCH_DB_URL` points the research
store at SQL Server (schema `research`). Index build ids are content-addressed, so a fresh home
reproduces the same index (the demo uses a temporary home).

## 2. Local application profile

One startup command (from the repository root, after configuring `.env`):

```bash
cp .env.example .env            # fill in secrets (section 3)
overmind start -f Procfile.dev  # docker compose up (SQL Server, Redis, Azurite, ml-service) + Functions + API + React
```

`Procfile.dev` runs `docker compose up`, `func start` (Functions), `dotnet watch run` (API) and
`npm run dev` (React). Equivalent manual steps:

```bash
docker compose up -d sqlserver redis azurite ml-service    # ml-service = FastAPI + research_engine on :8000
docker compose --profile graph up -d neo4j                  # optional graph backend (127.0.0.1:7474/7687)
source .env && ./scripts/setup-database.sh                  # database + EF migrations (section 4)
cd AiTradingRace.Web && dotnet run                          # API (Swagger at /swagger)
cd AiTradingRace.Functions && func start                    # only if FixedIncome__Execution__RunExecutionHost=functions
cd ai-trading-race-web && npm install && npm run dev        # dashboard; fixed income pages under /fi
```

Compose publishes every port on `127.0.0.1` only, Redis requires `REDIS_PASSWORD`, and the ML
container runs with `ENVIRONMENT=production` (no `/docs`, no public development signing keys) unless
`ML_SERVICE_ENVIRONMENT=development` is set.

Without Docker for Python: `cd ai-trading-race-ml && .venv/bin/uvicorn app.main:app --port 8000`
with the same `ML_SERVICE_*` variables. `ML_SERVICE_EVIDENCE_AUTOLOAD=fixtures` (compose default)
ingests the offline FOMC fixtures and activates the default index at startup, never inside a request.

Exactly one host executes queued runs: `FixedIncome:Execution:RunExecutionHost` = `web` (hosted queue
in the API, default) or `functions` (durable `FixedIncomeReplayOrchestrator`). Forward paper cycles
(19:00 America/New_York on supported sessions) are disabled unless `FixedIncome:PaperTrading:Enabled`
and an experiment id are configured.

## 3. Environment variables and secrets

Credentials come from the environment or a secret store, never from strategy configuration. Run
manifests record resolved non-secret settings only.

| Variable | Used by | Purpose |
|---|---|---|
| `ML_SERVICE_API_KEY` = `ResearchEngine__ApiKey` | Python / .NET | `X-API-Key` for `/internal/v1/*` |
| `ML_SERVICE_SIGNING_KEY` = `ResearchEngine__SigningKey` | Python / .NET | HMAC key: Python signs `TransitionProposal`s and `StrategyResult`s, .NET verifies. Required outside `ENVIRONMENT=development`; the two values must be identical |
| `RESEARCH_SIGNING_KEY` | Python only | Signs the content-addressed calculation store. When unset: a fixed public key with a warning in development; a random per-process key in any other environment (signatures then do not survive a restart) |
| `FI_TRANSITION_SIGNING_KEY` | CLI `replay` | Signs offline replay transitions (never stored in run artifacts) |
| `FI_RESULT_SIGNING_KEY` | Python agents | Signs StrategyResults outside the service (development key when unset) |
| `ML_SERVICE_STRATEGY_PROVIDER` | Python | `reference` (default) \| `recorded` \| `anthropic` \| `openai`; chosen by configuration, never by request fields |
| `ML_SERVICE_STRATEGY_MODEL`, `ML_SERVICE_STRATEGY_BASE_URL`, `ML_SERVICE_RECORDED_RESPONSES_DIR` | Python | pinned model id, OpenAI-compatible/Azure/local base URL, recordings directory |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Python | hosted provider keys (none are configured for this project) |
| `ResearchEngine__BaseUrl` | .NET | Python service URL (`http://localhost:8000`) |
| `ConnectionStrings__TradingDb`, `SA_PASSWORD` | .NET / compose | SQL Server |
| `REDIS_PASSWORD` | compose | Redis `requirepass`; passed to the ML service as `ML_SERVICE_REDIS_PASSWORD` |
| `ML_SERVICE_ENVIRONMENT` | compose | `ENVIRONMENT` of the ML container (default `production`) |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | Python `--graph neo4j` | Neo4j backend (loopback-only development default) |
| `FI_RESEARCH_HOME`, `FI_RESEARCH_DB_URL` | Python | evidence home; SQL Server research store |

Fixture keys published in `research_engine.agents.recording` and `experiments.parity` exist only to
make fixtures reproducible. They are never valid in application mode.

## 4. Migrations

**.NET (schema `fi`):** `AddFixedIncomeSchema` (2026-11-05) and `AddFixedIncomeRunCheckpoints`
(2026-11-08), additive, with no change to legacy tables.

```bash
dotnet ef database update --project AiTradingRace.Infrastructure --startup-project AiTradingRace.Web
dotnet ef migrations list  --project AiTradingRace.Infrastructure --startup-project AiTradingRace.Web
# rollback to before the fixed income schema (drops fi.* tables and data):
dotnet ef database update <migration-before-AddFixedIncomeSchema> --project AiTradingRace.Infrastructure --startup-project AiTradingRace.Web
```

`FixedIncomeMigrationTests` checks that the migration touches only `fi` and that the model snapshot
is current.

**Python research store (schema `research`):** `ResearchStore.create()` creates the schema if needed
and applies each numbered migration in `research_engine/evidence/store.py::MIGRATIONS` above the
recorded `schema_version`, in one transaction. To evolve it, append a new numbered function; never
edit an applied one. The SQL Server path uses the same SQLAlchemy definitions and has not been run
against a live SQL Server.

## 5. Freshness failures and source outages

- Curves: a session without a READY curve available by 19:00 New York is skipped for every
  competitor (`skipped_stale_data`, listed in manifest exclusions). Gaps are never forward-filled.
  Missing marks make valuations incomplete; they are never substituted.
- FOMC ingestion: an outage is recorded as a fetch run with outcome `outage`. Source health is
  updated, but freshness does **not** advance; `fi-research ingest fed` exits 3. Partial download
  failures are visible per item. Online fetches use the allowlisted host only
  (`www.federalreserve.gov`), with redirects re-validated.
- Agents: a missing mandatory index or graph is `failed_dependency` (graph mode never falls back to
  plain RAG); an empty bundle is the configured abstention.
- Health: `GET /api/v1/health/fixed-income` (API) and `GET /health` (Python). The dashboard Health
  page shows ingestion, manifests, failed jobs and usage.

## 6. Budget limits

Per decision (`DecisionBudget`, shared by a lead and its specialists): 6 generation calls including
repairs, 12 tool calls of which 3 retrieve evidence, 12 unique chunks / 8,000 evidence tokens, 32,000
input / 12,000 output tokens, 90 s deadline, delegation depth 1, 2 specialist invocations. A central
ledger reserves worst-case capacity before each call; exhaustion is `failed_budget` with usage
recorded. **Priced hosted runs are refused** unless a versioned price schedule and `maxCostUsd` are
configured. The Python service bounds concurrency (`ML_SERVICE_MAX_CONCURRENT_DECISIONS`, 429 +
`Retry-After` when saturated). Ingestion and index builds have no per-decision budget; they run
outside the decision path.

## 7. Checkpoints and resume

- Offline: the runner checkpoints after every cycle (`checkpoint.json`: cycle index, event position,
  portfolio versions and hashes, pending orders/settlements, config hash, manifest reference).
  `fi-research replay resume --run-dir D` skips committed command ids
  (`cmd:<run>:<strategy>:<session>:<step>`) and reuses persisted outcomes. A finalized manifest is
  never rewritten.
- Application: `AddFixedIncomeRunCheckpoints` stores the last completed cycle. Interrupted runs are
  re-queued at worker start; a transient engine outage fails the run as resumable and the next
  execution continues after the checkpoint. Unique logical command ids and SQL constraints guarantee
  one financial effect (`FixedIncomeRunExecutorTests`, `FixedIncomeOrchestrationTests`).
- A reconciliation failure blocks further commits to that portfolio until an admin calls
  `POST /api/v1/admin/portfolios/{id}/unblock`.

## 8. Backups and authority

SQL Server (`fi`, `research` schemas) and the artifact store (raw source bytes, normalized
artifacts, replay bundles) are **authoritative**; back them up together (for example SQL Server
`BACKUP DATABASE` plus a copy of the artifact directory or Azurite/Blob container). Neo4j, in-memory
graphs, embeddings and retrieval caches are **derived** and need no backup: rebuild them.

## 9. Index rebuild and rollback

```bash
fi-research index build --activate            # new build; READY only after validation
fi-research index validate --build-id <id>    # reload + independent in-memory rebuild; membership must match
```

Builds are immutable and content-addressed. Activation is a recorded pointer, so rolling back means
re-activating the previous READY build id from Python
(`research_engine.retrieval.activate_index(store, build_id)`). `POST /api/v1/admin/index-builds`
starts a build or validation (activation follows `ML_SERVICE_ACTIVATE_INDEX_BUILDS`); it cannot
select an older build. Runs record the `indexBuildId` they used; a completed run never changes
index. For Neo4j: `docker compose --profile graph up -d neo4j`,
then `index build --graph neo4j`. That path is covered only by `integration` tests and has not been
run against a live server here.

## 10. Regression suite (after dependency, prompt, model, parser or convention changes)

```bash
cd ai-trading-race-ml
.venv/bin/python -m pytest -q                         # all Python suites (includes demo verify, marked slow)
.venv/bin/python -m research_engine demo verify       # recorded demo: identical results, transitions, metrics
.venv/bin/python -m research_engine benchmark run --split dev   # structural gates: 0 temporal violations, 100% citations
python -m research_engine.contracts.export && git diff --exit-code ../contracts   # schema drift
cd .. && make test-backend                            # .NET: contracts, parity, commit protocol, orchestration
```

Expected effects: a prompt, tool-schema or model change alters recorded-response fingerprints, so
`demo verify` and `tests/agents/test_recorded_replay.py` fail with `RecordingMissing` or result
differences. Re-record (`demo build --overwrite`, `record --overwrite`) and register a new trial. A
numerical or convention change alters transitions: re-export parity fixtures and rebuild the demo.
A parser or chunker change alters chunk ids: rebuild the index, re-run the benchmark, re-record.

## 11. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `demo verify`: `strategy_configs` mismatch | Strategy config drift (prompt/tool/index version changed). Rebuild the bundle as a new trial |
| `demo verify`: `strategy_results_identical` fails with `recording_missing` reasons | Prompt, tool output or evidence changed. Recordings no longer match; see section 10 |
| `demo verify`: only notes about git commit or dependency hashes | Informational; the bundle still reproduces |
| `ResponseModeError` from the runner | A replay-only provider in `fresh_inference`, or a live provider with `replay_source=recorded_responses` |
| `/internal/v1/*` returns 401/503 | Missing `X-API-Key`, or `ML_SERVICE_SIGNING_KEY` unset outside development |
| .NET rejects a proposal (hash/signature mismatch) | `ML_SERVICE_SIGNING_KEY` ≠ `ResearchEngine__SigningKey`, or engine version not allowlisted |
| Evidence strategies return 503 / `failed_dependency` | No READY active index: set `ML_SERVICE_EVIDENCE_AUTOLOAD=fixtures` or run `index build --activate` |
| `RESEARCH_SIGNING_KEY is not set` warning | Expected in development. Outside development the store falls back to a random per-process key; set the variable so signatures survive restarts |
| Priced run refused | Provide a versioned price schedule and `maxCostUsd` |
| Portfolio blocked | Reconciliation failure; investigate the journal, then admin unblock |
