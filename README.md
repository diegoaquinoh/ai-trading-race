# Fixed Income Research Lab (AI Trading Race) 🏁

A reproducible fixed income research and paper-trading lab. Independent strategies (cash, passive,
quantitative and AI decision architectures) each manage an isolated portfolio of **synthetic**
U.S. Treasury-style notes priced from observed Treasury par curves. The lab measures what document
retrieval (RAG), graph-assisted retrieval and a bounded specialist team change, with an auditable
trail from evidence to trade.

The original **crypto AI Trading Race** (CoinGecko prices, LLM agents, five-minute Durable Functions
cycle) still works and is documented below as **legacy**.

[![Backend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Backend%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![Functions CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Azure%20Functions%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![Frontend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Frontend%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![ML Service CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/ML%20Service%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 📈 Fixed Income Research Lab

Specification: [docs/FIXED_INCOME_PLATFORM_SPEC.md](./docs/FIXED_INCOME_PLATFORM_SPEC.md) ·
plan: [docs/fixed-income/IMPLEMENTATION_PLAN.md](./docs/fixed-income/IMPLEMENTATION_PLAN.md) ·
requirement status: [docs/fixed-income/traceability.md](./docs/fixed-income/traceability.md)

### What is implemented

- **Canonical Python engine** (`ai-trading-race-ml/research_engine`, QuantLib 1.44): synthetic
  fixed-rate notes, U.S. government-bond calendar, Treasury par-curve bootstrap, settlement- and
  valuation-anchored pricing, accrued interest, DV01/key-rate/duration, versioned scenarios, fills
  at the next session's observation with declared half-spreads, balanced ledger postings, FIFO lots,
  settlement, coupons and redemptions, risk policy, and a daily replay runner with checkpoints.
- **.NET transactional authority** (schema `fi`, `/api/v1`): verifies HMAC-signed transition
  proposals, re-checks policy and commits atomically with idempotent command ids. Durable
  orchestration for replay and (disabled by default) forward paper cycles.
- **Evidence:** Federal Reserve FOMC statements and minutes 2023–2024 (offline fixtures, provenance
  and reconstructed availability), chunking, hybrid retrieval (BM25 + deterministic local
  embedding), a typed knowledge graph (in-memory default, Neo4j optional), graph-assisted
  retrieval, citation validation, and a 60-question benchmark.
- **Strategies:** `cash`, `static_ladder`, `quant_duration`, and `llm_market`, `llm_rag`,
  `llm_graph`, `llm_team` (lead + macro researcher + critical reviewer) under shared decision
  budgets, typed tools, validation and audit.
- **Reproducibility:** immutable hashed manifests, separate fresh-inference and recorded-replay
  modes, recorded demo bundle, reports and methodology card. Dashboard pages under `/fi`.

### What it is not (yet)

- **No hosted LLM has been run.** No LLM credentials exist for this project. AI strategies run on
  provider `reference` (`reference-heuristic-v1`), a deterministic rule-based policy model, not an
  LLM. Anthropic/OpenAI-compatible clients exist and are tested only with mocked transports.
- **No real bonds or market quotes.** Instruments are synthetic; prices are curve-model observations.
  Observed-security mode (M8) and intraday execution (M9) are gated, not delivered.
- The Neo4j path is untested against a live server. The repository targets .NET 8, whose support
  ends 10 Nov 2026; the upgrade is a pending migration
  ([ADR 0007](./docs/fixed-income/adr/0007-dotnet-10-upgrade-deferred.md)).

### Run the recorded demo offline (no services, no credentials)

```bash
cd ai-trading-race-ml
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m research_engine demo verify     # replays the bundle with every provider disabled (~20 s)
.venv/bin/python -m research_engine demo build --overwrite   # optional: rebuild the bundle (~70 s)
```

The bundle `ai-trading-race-ml/fixtures/demo/fi-demo-2024q1/` replays 2024-01-02 → 2024-03-28
(61 sessions, covering the 31 Jan and 20 Mar 2024 FOMC statements and two minutes releases) for
seven competitors. Headline from that recorded run: synthetic instruments, reference model (not an
LLM), one repetition, **not statistically significant**. In a quarter in which the 2Y, 5Y and 10Y
Treasury par yields rose 25–28 bp, net returns ranged from 0.00% (`cash`) and −0.35% (`llm_rag`/`llm_graph`/
`llm_team`, which made identical decisions) to −0.72% (`llm_market`), mostly following each
portfolio's rate exposure (average DV01 305–438 USD/bp). See the
[demo report](./docs/fixed-income/reports/demo-experiment.md).

### Fixed income documentation

| Document | Content |
|---|---|
| [docs/fixed-income/reports/demo-experiment.md](./docs/fixed-income/reports/demo-experiment.md) | Demo experiment report (results, risk, costs, failures, evidence, limitations) |
| [docs/fixed-income/reports/cost-sensitivity.md](./docs/fixed-income/reports/cost-sensitivity.md) | Half-spread 0.00 / 0.02 / 0.05 reruns |
| [docs/fixed-income/reports/evidence-benchmark.md](./docs/fixed-income/reports/evidence-benchmark.md) | Hybrid vs graph retrieval benchmark |
| [docs/fixed-income/reports/methodology-card.md](./docs/fixed-income/reports/methodology-card.md) | Hypotheses, variants, metrics, splits, trial registry |
| [docs/fixed-income/operations.md](./docs/fixed-income/operations.md) | Local startup, secrets, migrations, checkpoints, backups, index rebuild, troubleshooting |
| [docs/fixed-income/traceability.md](./docs/fixed-income/traceability.md) | FI-01…FI-16 and milestone status |
| [docs/fixed-income/adr/](./docs/fixed-income/adr/) | Architecture decision records 0001–0008 |
| [numerical-methods](./docs/fixed-income/numerical-methods.md) · [accounting](./docs/fixed-income/accounting.md) · [execution-and-policy](./docs/fixed-income/execution-and-policy.md) | Engine design |
| [evidence-and-retrieval](./docs/fixed-income/evidence-and-retrieval.md) · [provenance-and-time-policy](./docs/fixed-income/provenance-and-time-policy.md) · [agents-and-validation](./docs/fixed-income/agents-and-validation.md) | Evidence, time policy, agents |

Local application startup (SQL Server, Azurite, Python engine, .NET API, React, optional
`docker compose --profile graph` Neo4j) is in the
[operations guide](./docs/fixed-income/operations.md). The quick start below starts the same
infrastructure.

---

# Legacy: crypto AI Trading Race

The sections below document the original crypto race. It remains functional and separate from the
fixed income path (its tables, `/predict` endpoint and five-minute cycle are unchanged).

## 🌐 Live Demo

| Service  | URL                                                           |
| -------- | ------------------------------------------------------------- |
| Frontend | https://gentle-water-079ee5803.1.azurestaticapps.net          |
| API      | https://ai-trading-race-api.azurewebsites.net/api/auth/health |

## ✨ Features

- **Multi-agent competition** — Multiple AI agents (GPT, Claude, Llama, custom ML) competing simultaneously
- **Durable orchestration** — Azure Durable Functions `MarketCycleOrchestrator` coordinates the full market cycle with deterministic replays and idempotency
- **Fan-out/fan-in parallelism** — All agent decisions run in parallel via Durable Functions activities
- **Real market data** — Live OHLC candlestick data from CoinGecko API
- **Portfolio simulation** — Realistic portfolio management with positions, trades, and PnL tracking
- **Risk management** — Configurable constraints (max position size, min cash reserve, etc.)
- **Custom ML models** — Python FastAPI service for custom sklearn/PyTorch models
- **Real-time dashboard** — React frontend with equity curves and leaderboard

## 📊 Project Status

| Phase     | Description                                                   | Status      |
| --------- | ------------------------------------------------------------- | ----------- |
| Phase 1-4 | Core architecture, data model, market data, simulation engine | ✅ Complete |
| Phase 5   | AI agents integration (OpenAI, Anthropic, Groq, Llama)        | ✅ Complete |
| Phase 5b  | Custom ML model (Python + FastAPI)                            | ✅ Complete |
| Phase 6-7 | Durable Functions orchestrator & React dashboard              | ✅ Complete |
| Phase 8   | CI/CD & local deployment (Docker Compose)                     | ✅ Complete |
| Phase 9   | Cloud deployment (Azure)                                      | ✅ Complete |
| Phase 10  | Knowledge graph (GraphRAG-lite)                               | ✅ Complete |
| Phase 11  | Improve monitoring & observability                            | 🔜 Planned  |

## 🏗️ Architecture

The system uses an **Azure Durable Functions orchestrator** (`MarketCycleOrchestrator`) as the central coordination engine. A timer trigger fires every 5 minutes, and the orchestrator sequences activities with built-in retry, idempotency, and replay safety.

```
                    ┌───────────────────────────┐
                    │  Timer Trigger (*/5 min)   │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   MarketCycleOrchestrator  │
                    │    (Durable Functions)     │
                    └─────────────┬─────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
  ┌───────▼────────┐   ┌─────────▼──────────┐   ┌───────▼────────┐
  │ IngestMarket   │   │ CaptureSnapshots   │   │  GetActive     │
  │ DataActivity   │   │ Activity           │   │  AgentsActivity│
  │                │   │ (pre & post trade)  │   │                │
  └───────┬────────┘   └────────────────────┘   └───────┬────────┘
          │                                             │
          │ prices                           agent IDs  │
          │                                             │
          │              ┌──────────────────────────────▼──────┐
          │              │   Fan-out: RunAgentDecisionActivity  │
          │              │   (one per agent, in parallel)       │
          │              └──────────────────┬───────────────────┘
          │                                 │ decisions
          │              ┌──────────────────▼───────────────────┐
          │              │   ReportExecutedTradesActivity       │
          │              └──────────────────────────────────────┘
          │
          └──► Decision cycles run every 15 minutes (:00, :15, :30, :45)
               Market data ingestion runs every 5 minutes
```

### Local Services (Docker Compose)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Docker Compose Services                     │
├─────────────────────────────────────────────────────────────────┤
│  • SQL Server 2022 (port 1433)                                  │
│  • Redis 7 (port 6379) — Caching & idempotency                  │
│  • ML Service FastAPI (port 8000)                               │
│  • Azurite (ports 10000-10002) — Durable Functions storage      │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┴─────────────────────────────────┐
│  ASP.NET Core API (port 5001)                                 │
│  Azure Functions + Durable Orchestrator (port 7071)           │
│  React Dashboard (port 5173)                                  │
└───────────────────────────────────────────────────────────────┘
```

### Cloud Services (Azure)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Azure (francecentral)                        │
├─────────────────────────────────────────────────────────────────┤
│  App Service (F1)      — ASP.NET Core API                       │
│  Azure SQL (Free tier) — Database                               │
│  Container App         — Python ML service (ghcr.io image)      │
├─────────────────────────────────────────────────────────────────┤
│                    Azure (westeurope)                           │
├─────────────────────────────────────────────────────────────────┤
│  Functions (Consumption) — Durable orchestrator                 │
│  Static Web App (Free)   — React frontend                       │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
ai-trading-race/
├── AiTradingRace.Web/              # ASP.NET Core Web API
├── AiTradingRace.Domain/           # Domain entities
├── AiTradingRace.Application/      # Business logic & interfaces
├── AiTradingRace.Infrastructure/   # EF Core, external API clients
├── AiTradingRace.Functions/        # Azure Functions
│   ├── Orchestrators/              #   └─ MarketCycleOrchestrator
│   ├── Activities/                 #   └─ Ingest, Snapshot, Decision, Trade
│   ├── Functions/                  #   └─ Health check, manual triggers
│   └── Models/                     #   └─ Orchestration request/result DTOs
├── AiTradingRace.Tests/            # Unit & integration tests
├── ai-trading-race-web/            # React frontend (Vite + TypeScript)
├── ai-trading-race-ml/             # Python ML service (FastAPI + scikit-learn)
├── infra/                          # Azure Bicep IaC
├── scripts/                        # Database setup, deploy & credential scripts
└── .github/workflows/              # CI/CD pipelines (7 workflows)
```

## 🛠️ Tech Stack

| Layer              | Technologies                                                            |
| ------------------ | ----------------------------------------------------------------------- |
| **Backend**        | .NET 8, ASP.NET Core, Entity Framework Core                             |
| **Orchestration**  | Azure Functions v4 (isolated worker), Durable Functions                 |
| **Database**       | SQL Server 2022, Redis 7                                                |
| **ML Service**     | Python 3.11, FastAPI, scikit-learn                                      |
| **Frontend**       | React 18, TypeScript, Vite, TailwindCSS                                 |
| **Infrastructure** | Docker Compose (local), Azure Bicep (cloud)                             |
| **Cloud**          | Azure App Service, Functions, Container Apps, Static Web App, Azure SQL |
| **CI/CD**          | GitHub Actions (7 workflows)                                            |

## 📋 Prerequisites

- **Docker Desktop** — SQL Server, Redis, Azurite, ML Service
- **.NET 8 SDK** — Backend API, Functions, and Tests
- **Node.js 20+** — React frontend
- **Python 3.11+** — ML service (optional if using Docker)
- **Azure Functions Core Tools v4** — Local orchestrator

<details>
<summary><b>macOS Installation (Apple Silicon)</b></summary>

```bash
# .NET 8 SDK
brew install dotnet@8
brew link dotnet@8 --force
export PATH="/opt/homebrew/opt/dotnet@8/bin:$PATH"

# EF Core tools
dotnet tool install --global dotnet-ef
export PATH="$HOME/.dotnet/tools:$PATH"

# Azure Functions Core Tools
brew tap azure/functions
brew install azure-functions-core-tools@4

# Process manager (optional, recommended)
brew install overmind
```

</details>

## 🚀 Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and passwords
```

> ⚠️ **SQL Server password requirements:** Min 8 chars, uppercase, lowercase, digit, special char (`@#$` — avoid `!` on macOS/zsh)

### 2. Start infrastructure

```bash
docker compose up -d
```

This starts SQL Server, Redis, Azurite (Durable Functions storage), and the ML service.

### 3. Initialize database

```bash
source .env
./scripts/setup-database.sh
./scripts/seed-database.sh
```

### 4. Start services

**Option A: One command (recommended)**

```bash
overmind start -f Procfile.dev
```

**Option B: Manual (3 terminals)**

```bash
# Terminal 1: Backend API
source .env && cd AiTradingRace.Web && dotnet run

# Terminal 2: Azure Functions (orchestrator + activities)
cd AiTradingRace.Functions && func start

# Terminal 3: Frontend
cd ai-trading-race-web && npm install && npm run dev
```

### 5. Access the app

| Service     | URL                              |
| ----------- | -------------------------------- |
| Dashboard   | http://localhost:5173            |
| API Swagger | http://localhost:5001/swagger    |
| Functions   | http://localhost:7071/api/health |
| ML Service  | http://localhost:8000/docs       |

### 6. Trigger a market cycle manually

```bash
curl -X POST http://localhost:7071/api/market-cycle/trigger
```

## 🧪 Testing

```bash
# Run all tests
dotnet test

# With verbosity
dotnet test --verbosity normal
```

**Test coverage:** 166 tests covering market data ingestion, portfolio operations, equity calculations, risk validation, agent decisions, and Azure Functions orchestration.

Fixed income Python engine (numerical, simulation, evidence, agents, API, contracts, demo bundle):

```bash
cd ai-trading-race-ml && .venv/bin/python -m pytest -q   # 398 passed on 2026-11-10 (2 integration tests deselected)
```

## ☁️ Cloud Deployment (Azure)

### First-time setup

```bash
# 1. Copy and fill in all values (API keys, passwords, domain)
cp .env.example .env

# 2. Log in to Azure
az login

# 3. Provision all Azure resources (Bicep IaC)
source .env
./scripts/deploy-infra.sh

# 4. Deploy all application code
./scripts/deploy-app.sh
```

`deploy-infra.sh` creates: resource group, App Service, Azure SQL, Azure Functions, Container App, Static Web App.
`deploy-app.sh` builds & pushes the ML Docker image, runs DB migrations, deploys the API + Functions + Container App, and injects Function keys.

### CI/CD (GitHub Actions)

On every push to `main`, the `deploy.yml` workflow runs automatically. Some deploy steps use publish profiles (automated), others require `AZURE_CREDENTIALS` service principal which isn't available when Entra ID is org-controlled (manual).

**Automated deploys (on push to `main`):**

| Workflow Job       | Target         | Secret                              |
| ------------------ | -------------- | ----------------------------------- |
| `deploy-api`       | App Service    | `AZURE_WEBAPP_PUBLISH_PROFILE`      |
| `deploy-functions` | Function App   | `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` |
| `deploy-frontend`  | Static Web App | `AZURE_STATIC_WEB_APPS_API_TOKEN`   |

**Manual operations (require `az login`):**

| Task               | Command                                                         |
| ------------------ | --------------------------------------------------------------- |
| DB Migration       | `./scripts/migrate-azure-db.sh`                                 |
| ML Service Deploy  | `./scripts/deploy-app.sh` (or see below)                        |
| Post-deploy checks | `curl https://ai-trading-race-api.azurewebsites.net/api/health` |

<details>
<summary><b>Manual ML Service Deploy</b></summary>

```bash
# Build and push Docker image
docker build -t ghcr.io/diegoaquinoh/ai-trading-race-ml:latest ./ai-trading-race-ml
docker push ghcr.io/diegoaquinoh/ai-trading-race-ml:latest

# Update Container App
az containerapp update \
  --name ai-trading-ml \
  --resource-group ai-trading-rg \
  --image ghcr.io/diegoaquinoh/ai-trading-race-ml:latest
```

</details>

<details>
<summary><b>Manual DB Migration</b></summary>

```bash
# Option A: Use the existing script
./scripts/migrate-azure-db.sh

# Option B: Direct EF Core update (requires connection string)
dotnet ef database update \
  --project AiTradingRace.Infrastructure \
  --startup-project AiTradingRace.Web
```

</details>

#### Required GitHub Secrets

| Secret                              | How to get it                                          |
| ----------------------------------- | ------------------------------------------------------ |
| `AZURE_WEBAPP_PUBLISH_PROFILE`      | Azure Portal → App Service → Download publish profile  |
| `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` | Azure Portal → Function App → Download publish profile |
| `AZURE_STATIC_WEB_APPS_API_TOKEN`   | Auto-created when SWA linked to GitHub                 |

### Required tools

```bash
brew install azure-cli jq sqlcmd
dotnet tool install --global dotnet-ef
```

## 📚 Documentation

| Document                                                                   | Description                          |
| -------------------------------------------------------------------------- | ------------------------------------ |
| [scripts/README.md](./scripts/README.md)                                   | Database & deployment scripts guide  |
| [ai-trading-race-ml/README.md](./ai-trading-race-ml/README.md)             | ML service setup                     |
| [ai-trading-race-ml/FASTAPI_SCHEMA.md](./ai-trading-race-ml/FASTAPI_SCHEMA.md) | ML service API & architecture    |
| [ai-trading-race-ml/DEPLOYMENT.md](./ai-trading-race-ml/DEPLOYMENT.md)     | ML service & Redis deployment guide  |
| [docs/fixed-income/](./docs/fixed-income/)                                 | Fixed income lab: reports, ADRs, operations, traceability |

## 🔒 Security

- Environment variables via `.env` (excluded from git)
- API keys in `local.settings.json` (not versioned)
- JWT authentication with API key fallback
- Rate limiting (global, per-user, auth-endpoint)
- Service-to-service auth with `X-API-Key` headers
- Production: Azure Key Vault for managed secrets

## 📄 License

This project is licensed under the MIT License — see [LICENSE](./LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
