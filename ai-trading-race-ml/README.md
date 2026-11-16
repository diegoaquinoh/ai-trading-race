# AI Trading Race - ML Service

Custom ML model for trading decisions, exposed via FastAPI.

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

| Method | Path       | Description                    |
| ------ | ---------- | ------------------------------ |
| GET    | `/health`  | Health check with model status |
| POST   | `/predict` | Generate trading decision      |

## Environment Variables

| Variable                    | Description                | Default                    |
| --------------------------- | -------------------------- | -------------------------- |
| `ML_SERVICE_MODEL_PATH`     | Path to trained model      | `models/trading_model.pkl` |
| `ML_SERVICE_MODEL_VERSION`  | Model version string       | `1.0.0`                    |
| `ML_SERVICE_API_KEY`        | API key for authentication | (required)                 |
| `ML_SERVICE_ALLOWED_ORIGIN` | CORS allowed origin        | `*`                        |

## Internal API v1 (fixed income research engine)

`app/v1/` exposes `research_engine` to the .NET application under `/internal/v1/*`
(spec §14.3). The OpenAPI document is committed at
`contracts/openapi/research-engine.v1.json`; regenerate it with
`.venv/bin/python -m app.v1.openapi_models` after an API change (a test fails when it is stale).

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/internal/v1/capabilities` | Engine/QuantLib versions, conventions, curve coverage/admission, READY index builds, evidence snapshots, source health, providers, strategies, signing |
| POST | `/internal/v1/simulation/transitions` | Signed `TransitionProposal` (pure; no DB writes) |
| POST | `/internal/v1/simulation/bootstrap-allocation` | Common bootstrap targets for invested strategies |
| POST | `/internal/v1/strategies/decisions` | Signed `StrategyResult` for one strategy/cycle |
| POST | `/internal/v1/analytics/price`, `/analytics/risk` | Curve-model prices; portfolio risk/scenarios |
| GET  | `/internal/v1/market/sessions?start&end` | Sessions, snapshot ids, gap flags (19:00 New York decision time) |
| GET  | `/internal/v1/curves/{id}`, `/instruments`, `/instruments/{id}/valuation?date` | Curve detail; point-in-time instruments; valuation |
| POST | `/internal/v1/evidence/retrieve`, `/research-notes` | Evidence bundle at a cutoff; cited note (no order authority) |
| GET  | `/internal/v1/evidence/bundles/{id}`, `/evidence/chunks/{id}`, `/evidence/graph?bundleId` | Bundle pages, chunk text/provenance, bounded graph provenance |
| POST | `/internal/v1/admin/ingestions`, `/admin/index-builds`; GET `/admin/jobs/{id}` | Background jobs (never inside a decision) |

- **Auth:** every `/internal/*` path requires `X-API-Key` (fails closed when
  `ML_SERVICE_API_KEY` is unset). `/health` stays public.
- **Errors:** `application/problem+json` with a `code`: 400/422 invalid input, unknown schema
  major, floats in decimal fields or NaN; 422 also for deterministic engine rejections
  (`ledger_invariant_violation`, `withdrawal_exceeds_available_cash` - both with
  `portfolioId` - and numerical `calculation_rejected`); 404 unknown resource; 409
  hash/snapshot mismatch, stale version or `requestId` reuse with other content; 429 +
  `Retry-After` when the decision pool is full; 503 dependency/capability unavailable. HOLD and
  abstention are 200 results; only unexpected exceptions are 500.
- **Request binding:** on `POST /simulation/transitions` and `POST /strategies/decisions`,
  `requestHash` = `content_hash` of the JSON request body exactly as received: the body is
  parsed and re-serialized as canonical JSON (sorted keys, compact separators, ASCII escaping,
  no floats) without filling defaults, so a caller that omits null fields reproduces the value
  from the body it sent (`content_hash(json.loads(body))`). Any field change, including an
  explicit default or the optional `riskPolicy`/`executionModel` objects, changes the hash.
  Offline replay has no HTTP body and keeps hashing the parsed model;
  `inputHashes.decisionRequest` is always the parsed `DecisionRequest` model hash.
- **Signing:** `proposalHash`/`resultHash` = sha256 over canonical JSON of the body without the
  hash and signature; `signature` = HMAC-SHA256 with `ML_SERVICE_SIGNING_KEY` (same value as
  .NET `ResearchEngine:SigningKey`). Outside `ENVIRONMENT=development` internal endpoints
  answer 503 without it; development uses a public key and logs a warning. Calculation
  results keep their own `RESEARCH_SIGNING_KEY`.
- **Providers/policy:** the strategy model provider comes from configuration only; requests
  name `riskPolicyId` (an optional `riskPolicy` object must carry the same id) and can never
  select a provider, model or policy.

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `ML_SERVICE_SIGNING_KEY` | Shared HMAC key for proposals/results | required outside development |
| `ML_SERVICE_STRATEGY_PROVIDER` | `reference` \| `recorded` \| `anthropic` \| `openai` | `reference` |
| `ML_SERVICE_STRATEGY_MODEL` / `ML_SERVICE_STRATEGY_BASE_URL` | Pinned model id / API base URL | provider default |
| `ML_SERVICE_RECORDED_RESPONSES_DIR` | Recordings for `recorded` | - |
| `ML_SERVICE_MAX_CONCURRENT_DECISIONS` / `ML_SERVICE_DECISION_RETRY_AFTER_SECONDS` | Decision pool size / 429 `Retry-After` | `4` / `5` |
| `ML_SERVICE_EVIDENCE_AUTOLOAD` | `active` (load active READY index from `FI_RESEARCH_HOME`), `fixtures` (offline Fed fixtures at startup), `off` | `active` |
| `ML_SERVICE_INGESTION_ONLINE` | Admin ingestion fetches federalreserve.gov instead of fixtures | `false` |
| `ML_SERVICE_ACTIVATE_INDEX_BUILDS` | Activate READY builds produced by admin jobs | `true` |
| `ML_SERVICE_WARM_CURVES` | Build all curves + admission report in the background | `true` |

Credentials for live providers come from `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` and are never
reported. Tests: `.venv/bin/python -m pytest tests/api_v1 tests/test_api.py -q`.

## Project Structure

```
ai-trading-race-ml/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── v1/                  # Internal research API v1 (/internal/v1/*)
│   ├── models/schemas.py    # Pydantic models
│   ├── ml/                  # ML predictor & features
│   ├── services/            # Business logic
│   └── middleware/          # Authentication
├── models/                  # Saved ML models
├── data/                    # Training data
├── tests/                   # Unit tests
└── requirements.txt
```
