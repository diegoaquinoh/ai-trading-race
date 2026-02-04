# AI Trading Race 🏁

A competitive simulation where AI trading agents (LLMs) race against each other, each controlling a simulated crypto portfolio. Market prices are ingested from CoinGecko, agents make trading decisions (buy/sell/hold), and a React dashboard displays real-time equity curves and leaderboard.

[![Backend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Backend%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![Functions CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Azure%20Functions%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![Frontend CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/Frontend%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![ML Service CI](https://github.com/diegoaquinoh/ai-trading-race/workflows/ML%20Service%20CI%2FCD/badge.svg?branch=main)](https://github.com/diegoaquinoh/ai-trading-race/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- **Multi-agent competition** — Multiple AI agents (GPT, Claude, Llama, custom ML) competing simultaneously
- **Real market data** — Live OHLC candlestick data from CoinGecko API
- **Portfolio simulation** — Realistic portfolio management with positions, trades, and PnL tracking
- **Risk management** — Configurable constraints (max position size, min cash reserve, etc.)
- **Custom ML models** — Python FastAPI service for custom sklearn/PyTorch models
- **Explainable AI** — Knowledge graph-based decision auditing (Phase 10+)
- **Real-time dashboard** — React frontend with equity curves and leaderboard

## 📊 Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1-4 | Core architecture, data model, market data, simulation engine | ✅ Complete |
| Phase 5 | AI agents integration (OpenAI, Anthropic, Groq) | ✅ Complete |
| Phase 5b | Custom ML model (Python + FastAPI) | ✅ Complete |
| Phase 6-7 | Azure Functions scheduler & React dashboard | ✅ Complete |
| Phase 8 | CI/CD & local deployment (Docker Compose) | ✅ Complete |
| Phase 9 | RabbitMQ message queue & horizontal scaling | 🔜 Planned |
| Phase 10-11 | Monitoring, security & GraphRAG-lite | 🔜 Planned |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Docker Compose Services                     │
├─────────────────────────────────────────────────────────────────┤
│  • SQL Server 2022 (port 1433)                                  │
│  • Redis 7 (port 6379) - Caching & idempotency                  │
│  • ML Service FastAPI (port 8000)                               │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┴─────────────────────────────────┐
│  ASP.NET Core API (port 5001)                                 │
│  Azure Functions (scheduler)                                   │
│  React Dashboard (port 5173)                                   │
└───────────────────────────────────────────────────────────────┘
```

### Project Structure

```
ai-trading-race/
├── AiTradingRace.Web/           # ASP.NET Core Web API
├── AiTradingRace.Domain/        # Domain entities
├── AiTradingRace.Application/   # Business logic & interfaces
├── AiTradingRace.Infrastructure/# EF Core, external clients
├── AiTradingRace.Functions/     # Azure Functions (timers)
├── AiTradingRace.Tests/         # Unit & integration tests
├── ai-trading-race-web/         # React frontend (Vite + TypeScript)
├── ai-trading-race-ml/          # Python ML service (FastAPI)
└── infra/                       # Azure Bicep IaC
```

## 🛠️ Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Backend** | .NET 8, ASP.NET Core, Entity Framework Core |
| **Functions** | Azure Functions v4, Durable Functions |
| **Database** | SQL Server 2022, Redis 7 |
| **ML Service** | Python 3.11, FastAPI, scikit-learn |
| **Frontend** | React 18, TypeScript, Vite, TailwindCSS |
| **Infrastructure** | Docker Compose, Azure Bicep |
| **CI/CD** | GitHub Actions |

## 📋 Prerequisites

- **Docker Desktop** — SQL Server, Redis, ML Service
- **.NET 8 SDK** — Backend API and Functions
- **Node.js 20+** — React frontend
- **Python 3.11+** — ML service (optional if using Docker)
- **Azure Functions Core Tools v4** — Local scheduler (optional)

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

# Terminal 2: Azure Functions
cd AiTradingRace.Functions && func start

# Terminal 3: Frontend
cd ai-trading-race-web && npm install && npm run dev
```

### 5. Access the app

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API Swagger | http://localhost:5001/swagger |
| ML Service | http://localhost:8000/docs |

## 🧪 Testing

```bash
# Run all tests
dotnet test

# With verbosity
dotnet test --verbosity normal
```

**Test coverage:** 80+ tests covering market data ingestion, portfolio operations, equity calculations, risk validation, and Azure Functions.

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [DEPLOYMENT_LOCAL.md](./DEPLOYMENT_LOCAL.md) | Complete local deployment guide |
| [DATABASE.md](./DATABASE.md) | Database setup and migrations |
| [PLANNING_GLOBAL.md](./PLANNING_GLOBAL.md) | Project roadmap (Phases 1-11) |
| [scripts/README.md](./scripts/README.md) | Database scripts guide |

## 🔒 Security

- Environment variables via `.env` (excluded from git)
- API keys in `local.settings.json` (not versioned)
- Service-to-service auth with `X-API-Key` headers
- Production: Use Azure Key Vault or managed secrets

## 📄 License

This project is licensed under the MIT License — see [LICENSE](./LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
