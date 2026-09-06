# AI Trading Race 🏁

A competitive simulation where AI trading agents (LLMs) race against each other, each controlling a simulated crypto portfolio. Market prices are ingested from CoinGecko, an Azure Durable Functions orchestrator coordinates market cycles and agent decisions with fan-out/fan-in parallelism, and a React dashboard displays real-time equity curves and leaderboard.

[![Backend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Backend%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![Functions CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Azure%20Functions%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![Frontend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Frontend%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![ML Service CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/ML%20Service%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🌐 Live Demo

Live demo is currently unavailable, since my Azure free trial unfortunately already ended 
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
| Phase 10b | LangChain + Neo4j refactor                                    | 🔜 Planned  |
| Phase 11  | Improve Monitoring & observability                                    | 🔜 Planned  |

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
          │              │     ExecuteTradesActivity             │
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

| Document                                             | Description                         |
| ---------------------------------------------------- | ----------------------------------- |
| [docs/DEPLOYMENT_PLAN.md](./docs/DEPLOYMENT_PLAN.md) | Full Azure deployment plan          |
| [scripts/README.md](./scripts/README.md)             | Database & deployment scripts guide |
| [.github/SUMMARY.md](./.github/SUMMARY.md)           | CI/CD pipeline summary              |
| [.github/WORKFLOWS.md](./.github/WORKFLOWS.md)       | Workflow documentation              |

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
