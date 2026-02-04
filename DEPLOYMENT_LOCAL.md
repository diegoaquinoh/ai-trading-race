# Local Deployment Guide

Complete guide to running the AI Trading Race application locally without Azure.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Detailed Setup](#detailed-setup)
4. [Architecture](#architecture)
5. [Troubleshooting](#troubleshooting)
6. [Development Workflow](#development-workflow)

---

## Prerequisites

### Required Software

- **Docker Desktop** (20.10+)
  - [Mac](https://docs.docker.com/desktop/install/mac-install/)
  - [Windows](https://docs.docker.com/desktop/install/windows-install/)
  - [Linux](https://docs.docker.com/desktop/install/linux-install/)

- **.NET SDK** (8.0)
  - Download: https://dotnet.microsoft.com/download/dotnet/8.0

- **Node.js** (20+) with npm
  - Download: https://nodejs.org/

- **Python** (3.11+) with pip
  - Download: https://www.python.org/downloads/

### Optional Tools

- **sqlcmd** - SQL Server command-line tool
- **Azure Functions Core Tools** (v4) - For running Functions locally

---

## Quick Start

### 1. Clone and Setup

```bash
# Clone repository
cd .

# Start infrastructure (SQL Server, Redis, ML Service)
docker-compose up -d
```

### 2. Initialize Database

```bash
# Create database and apply migrations
./scripts/setup-database.sh

# Seed test data (BTC, ETH, test agents)
./scripts/seed-database.sh
```

### 3. Configure API Keys

```bash
# Copy environment templates
cp AiTradingRace.Web/.env.example AiTradingRace.Web/.env
cp AiTradingRace.Functions/local.settings.json.example AiTradingRace.Functions/local.settings.json
cp ai-trading-race-web/.env.example ai-trading-race-web/.env

# Edit and add your API keys
nano AiTradingRace.Web/.env
# Set LLAMA_API_KEY=your_groq_api_key_here
# Set COINGECKO_API_KEY=your_coingecko_key_here (optional)
```

### 4. Start Services

```bash
# Terminal 1: Start Functions (market data collection, agent execution)
cd AiTradingRace.Functions
func start

# Terminal 2: Start Web API
cd AiTradingRace.Web
dotnet run

# Terminal 3: Start Frontend
cd ai-trading-race-web
npm install
npm run dev
```

### 5. Access Applications

- **Frontend Dashboard:** http://localhost:5173
- **Web API:** http://localhost:5172
- **API Documentation:** http://localhost:5172/swagger
- **Azure Functions:** http://localhost:7071
- **ML Service:** http://localhost:8000
- **ML API Docs:** http://localhost:8000/docs

---

## Detailed Setup

### Step 1: Start Infrastructure Services

Docker Compose orchestrates all backend services:

```bash
docker-compose up -d
```

**Services Started:**
- `sqlserver` - SQL Server 2022 (port 1433)
- `redis` - Redis 7 (port 6379)
- `ml-service` - Python FastAPI ML service (port 8000)

**Verify Services:**

```bash
# Check running containers
docker ps

# Expected output:
# ai-trading-sqlserver   (healthy)
# ai-trading-redis       (healthy)
# ai-trading-ml-service  (healthy)

# View logs
docker-compose logs -f
```

### Step 2: Database Initialization

#### 2.1 Setup Schema

The `setup-database.sh` script:
- Creates the `AiTradingRaceDb` database
- Applies EF Core migrations
- Verifies connection

```bash
./scripts/setup-database.sh
```

**Manual Alternative:**

```bash
cd AiTradingRace.Web
dotnet ef database update --project ../AiTradingRace.Infrastructure
```

#### 2.2 Seed Test Data

The `seed-database.sh` script inserts:
- **Assets:** BTC (Bitcoin), ETH (Ethereum), USD
- **Agents:** 5 test agents with different strategies
- **Portfolios:** $100,000 starting balance per agent

```bash
./scripts/seed-database.sh
```

**What's Created:**

| Agent Name | Provider | Strategy |
|------------|----------|----------|
| Llama Momentum Trader | Llama | Follows price trends |
| Llama Value Investor | Llama | Long-term holding |
| CustomML Technical Analyst | CustomML | ML predictions |
| Llama Contrarian Trader | Llama | Goes against crowd |
| Llama Balanced Trader | Llama | Risk-managed |

### Step 3: Configure Environment Variables

#### 3.1 Web API Configuration

**File:** `AiTradingRace.Web/.env`

```bash
# Copy template
cp AiTradingRace.Web/.env.example AiTradingRace.Web/.env

# Edit configuration
nano AiTradingRace.Web/.env
```

**Required Settings:**

```bash
# Database (use localhost for local dev)
ConnectionStrings__DefaultConnection="Server=localhost,1433;Database=AiTradingRaceDb;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True;"

# Llama API (get free key from Groq)
LlamaApiSettings__Provider="Groq"
LlamaApiSettings__BaseUrl="https://api.groq.com/openai/v1"
LlamaApiSettings__ApiKey="YOUR_GROQ_API_KEY_HERE"
LlamaApiSettings__Model="llama-3.3-70b-versatile"

# Custom ML Service
CustomMlAgent__BaseUrl="http://localhost:8000"

# CoinGecko (optional, has free tier)
CoinGeckoApiSettings__ApiKey="YOUR_COINGECKO_KEY"

# CORS (frontend URL)
AllowedOrigins="http://localhost:5173,http://localhost:5174"
```

**Get API Keys:**
- **Groq (Llama):** https://console.groq.com/keys (free, 14,400 req/day)
- **CoinGecko:** https://www.coingecko.com/api/pricing (free tier available)

#### 3.2 Azure Functions Configuration

**File:** `AiTradingRace.Functions/local.settings.json`

```bash
# Copy template
cp AiTradingRace.Functions/local.settings.json.example AiTradingRace.Functions/local.settings.json

# Edit configuration
nano AiTradingRace.Functions/local.settings.json
```

**Required Settings:**

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "dotnet-isolated",
    
    "SqlConnectionString": "Server=localhost,1433;Database=AiTradingRaceDb;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True;",
    
    "CoinGeckoApiSettings__ApiKey": "YOUR_COINGECKO_KEY",
    
    "LlamaApiSettings__Provider": "Groq",
    "LlamaApiSettings__BaseUrl": "https://api.groq.com/openai/v1",
    "LlamaApiSettings__ApiKey": "YOUR_GROQ_API_KEY_HERE",
    "LlamaApiSettings__Model": "llama-3.3-70b-versatile",
    
    "CustomMlAgent__BaseUrl": "http://localhost:8000",
    
    "MarketDataCron": "0 */15 * * * *",
    "RunAgentsCron": "0 */5 * * * *",
    "EquitySnapshotCron": "0 0 0 * * *"
  }
}
```

#### 3.3 Frontend Configuration

**File:** `ai-trading-race-web/.env`

```bash
# Copy template
cp ai-trading-race-web/.env.example ai-trading-race-web/.env

# Edit configuration
nano ai-trading-race-web/.env
```

**Required Settings:**

```bash
# Web API endpoint
VITE_API_URL=http://localhost:5172

# Feature flags
VITE_ENABLE_POLLING=true
VITE_POLLING_INTERVAL=30000

# Debug mode
VITE_DEBUG_MODE=true
```

### Step 4: Start Application Services

#### 4.1 Azure Functions (Background Jobs)

Functions handle:
- **MarketDataFunction** - Collects BTC/ETH prices every 15 minutes
- **RunAgentsFunction** - AI agents make trading decisions every 5 minutes
- **EquitySnapshotFunction** - Daily portfolio snapshots at midnight
- **HealthCheckFunction** - Service health monitoring

```bash
cd AiTradingRace.Functions
func start
```

**Expected Output:**
```
Functions:
    EquitySnapshotFunction: [TimerTrigger]
    HealthCheckFunction: [HttpTrigger]
    MarketDataFunction: [TimerTrigger]
    RunAgentsFunction: [TimerTrigger]

For detailed output, run func with --verbose flag.
[2026-01-19T10:00:00.000] Host started
```

**Trigger Manually (Testing):**

```bash
# Collect market data immediately
curl http://localhost:7071/admin/functions/MarketDataFunction

# Run agents immediately
curl http://localhost:7071/admin/functions/RunAgentsFunction

# Check health
curl http://localhost:7071/api/health
```

#### 4.2 Web API (Backend)

API provides:
- REST endpoints for agents, portfolios, trades, market data
- WebSocket support for real-time updates
- Swagger documentation at `/swagger`

```bash
cd AiTradingRace.Web
dotnet run
```

**Expected Output:**
```
info: Microsoft.Hosting.Lifetime[14]
      Now listening on: http://localhost:5172
info: Microsoft.Hosting.Lifetime[0]
      Application started. Press Ctrl+C to shut down.
```

**Test Endpoints:**

```bash
# Health check
curl http://localhost:5172/api/health

# Get all agents
curl http://localhost:5172/api/agents

# Get market data
curl http://localhost:5172/api/marketdata/latest?symbol=BTC

# API documentation
open http://localhost:5172/swagger
```

#### 4.3 Frontend (React Dashboard)

Dashboard features:
- Real-time leaderboard with portfolio rankings
- Agent performance charts
- Recent trades feed
- Market data visualization

```bash
cd ai-trading-race-web
npm install
npm run dev
```

**Expected Output:**
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

**Access Dashboard:**
```bash
open http://localhost:5173
```

---

## Architecture

### Service Communication

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER BROWSER                              │
│                     http://localhost:5173                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ HTTP/WebSocket
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      REACT FRONTEND                              │
│                    (Vite Dev Server)                             │
│                     Port: 5173                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ REST API calls
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      .NET WEB API                                │
│                  (AiTradingRace.Web)                             │
│                     Port: 5172                                   │
│                                                                  │
│  • /api/agents, /api/portfolios, /api/trades                    │
│  • /api/marketdata, /api/equity-snapshots                       │
│  • /swagger for API docs                                        │
└─────────┬─────────────────────────────┬────────────────────────┘
          │                             │
          │                             │ HTTP POST
          │                             ▼
          │               ┌──────────────────────────────┐
          │               │   PYTHON ML SERVICE          │
          │               │   (FastAPI)                  │
          │               │   Port: 8000                 │
          │               │                              │
          │               │  • /predict endpoint         │
          │               │  • Redis caching (1h TTL)    │
          │               │  • 20-50x faster with cache  │
          │               └──────────────┬───────────────┘
          │                              │
          │                              │ Cache lookup
          │                              ▼
          │               ┌──────────────────────────────┐
          │               │   REDIS                      │
          │               │   Port: 6379                 │
          │               │                              │
          │               │  • Idempotency keys          │
          │               │  • Prediction cache          │
          │               └──────────────────────────────┘
          │
          │ SQL queries
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQL SERVER 2022                             │
│                     Port: 1433                                   │
│                                                                  │
│  • AiTradingRaceDb database                                     │
│  • Tables: Agents, Portfolios, Trades, Candles, etc.           │
│  • Persistent volume: sqlserver-data                            │
└────────────────────────────┬────────────────────────────────────┘
                             ▲
                             │
                             │ Timer triggers
┌────────────────────────────┴────────────────────────────────────┐
│                  AZURE FUNCTIONS (Local)                         │
│                     Port: 7071                                   │
│                                                                  │
│  • MarketDataFunction:    Every 15 min → Fetch BTC/ETH prices   │
│  • RunAgentsFunction:     Every 5 min  → AI trading decisions   │
│  • EquitySnapshotFunction: Daily 00:00 → Portfolio snapshots    │
│  • HealthCheckFunction:   HTTP trigger → Service health         │
└─────────────────────────────────────────────────────────────────┘
          │
          │ External API calls
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                             │
│                                                                  │
│  • Groq (Llama API):  https://api.groq.com/openai/v1           │
│  • CoinGecko:         https://api.coingecko.com/api/v3         │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Market Data Collection** (Every 15 minutes)
   ```
   CoinGecko API → MarketDataFunction → SQL Server (Candles table)
   ```

2. **Agent Decision Making** (Every 5 minutes)
   ```
   SQL Server (Candles) → RunAgentsFunction → Llama API / ML Service
   → Agent Decision → Execute Trade → SQL Server (Trades, Portfolios)
   ```

3. **ML Predictions** (Cached)
   ```
   RunAgentsFunction → CustomMlAgentModelClient
   → Check Redis cache (Idempotency-Key)
   → If miss: ML Service → Cache response → Return
   → If hit: Return cached (5-10ms vs 300ms)
   ```

4. **Frontend Updates** (Real-time)
   ```
   React Dashboard → Poll /api/agents, /api/portfolios
   → Display leaderboard, charts, trades
   ```

---

## Troubleshooting

### Services Not Starting

#### Docker Containers

**Problem:** Containers fail to start or are unhealthy

```bash
# Check status
docker ps -a

# View logs
docker-compose logs sqlserver
docker-compose logs redis
docker-compose logs ml-service

# Restart services
docker-compose down
docker-compose up -d

# Remove volumes (⚠️ deletes data)
docker-compose down -v
docker-compose up -d
```

#### Database Connection Failed

**Problem:** Cannot connect to SQL Server

```bash
# Wait for SQL Server to be ready (can take 30-60 seconds)
docker logs ai-trading-sqlserver | grep "ready for client connections"

# Test connection
docker exec -it ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P '$SA_PASSWORD' -Q "SELECT @@VERSION"

# If still failing, check connection string in .env files
```

See [DATABASE.md](./DATABASE.md) for detailed troubleshooting.

#### ML Service Not Responding

**Problem:** ML service returns errors or timeouts

```bash
# Check ML service logs
docker logs ai-trading-ml-service

# Restart ML service
docker-compose restart ml-service

# Test ML service
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

### API Key Issues

#### Groq API Key Invalid

**Problem:** "401 Unauthorized" from Llama API

```bash
# Verify API key is set
grep LLAMA_API_KEY AiTradingRace.Web/.env
grep LlamaApiSettings__ApiKey AiTradingRace.Functions/local.settings.json

# Test API key
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://api.groq.com/openai/v1/models
```

**Solution:**
1. Get new API key from https://console.groq.com/keys
2. Update both `.env` and `local.settings.json`
3. Restart Web API and Functions

#### CoinGecko Rate Limit

**Problem:** "429 Too Many Requests" from CoinGecko

```bash
# Check current usage
curl "https://api.coingecko.com/api/v3/ping"

# Free tier limit: 30 calls/minute
# MarketDataFunction calls every 15 min, so should be fine
```

**Solution:**
- Wait 1 minute and retry
- Get API key for higher limits: https://www.coingecko.com/api/pricing
- Reduce MarketDataCron frequency in `local.settings.json`

### Frontend Build Errors

#### npm install fails

```bash
cd ai-trading-race-web

# Clear cache
rm -rf node_modules package-lock.json
npm cache clean --force

# Reinstall
npm install
```

#### Vite build errors

```bash
# Check Node version (requires 20+)
node --version

# Update Node if needed (using nvm)
nvm install 20
nvm use 20

# Rebuild
npm run dev
```

### .NET Build Errors

#### Missing dependencies

```bash
# Restore packages
dotnet restore

# Clean and rebuild
dotnet clean
dotnet build
```

#### EF Core tools not found

```bash
# Install EF Core tools globally
dotnet tool install --global dotnet-ef

# Update existing installation
dotnet tool update --global dotnet-ef

# Verify installation
dotnet ef --version
```

---

## Development Workflow

### Daily Development

```bash
# 1. Start infrastructure (if not running)
docker-compose up -d

# 2. Check services are healthy
docker ps

# 3. Start Functions (Terminal 1)
cd AiTradingRace.Functions && func start

# 4. Start Web API (Terminal 2)
cd AiTradingRace.Web && dotnet run

# 5. Start Frontend (Terminal 3)
cd ai-trading-race-web && npm run dev

# 6. Open dashboard
open http://localhost:5173
```

### Making Changes

#### Backend (.NET)

```bash
# Make changes to C# files
# Hot reload enabled by default

# If adding new packages
cd AiTradingRace.Application
dotnet add package PackageName

# If changing models/entities
cd AiTradingRace.Infrastructure
dotnet ef migrations add YourMigrationName --startup-project ../AiTradingRace.Web
dotnet ef database update --startup-project ../AiTradingRace.Web
```

#### Frontend (React)

```bash
# Make changes to .tsx/.ts files
# Vite hot-reloads automatically

# If adding new packages
cd ai-trading-race-web
npm install package-name

# If changing environment variables
# Edit .env file, then restart dev server (Ctrl+C, npm run dev)
```

#### ML Service (Python)

```bash
# Stop ml-service container
docker-compose stop ml-service

# Make changes to Python files

# Rebuild and restart
docker-compose build ml-service
docker-compose up -d ml-service

# View logs
docker-compose logs -f ml-service
```

### Running Tests

```bash
# .NET tests
cd AiTradingRace.Tests
dotnet test

# Python tests
cd ai-trading-race-ml
docker-compose exec ml-service pytest

# Or locally (if Python env configured)
cd ai-trading-race-ml
pytest
```

### Viewing Logs

```bash
# Docker services
docker-compose logs -f sqlserver
docker-compose logs -f redis
docker-compose logs -f ml-service

# .NET applications
# Logs printed to console (stdout)

# Azure Functions
# Logs printed to console, saved to %temp%\LogFiles
```

### Database Operations

```bash
# Apply new migrations
cd AiTradingRace.Web
dotnet ef database update --project ../AiTradingRace.Infrastructure

# Reset database (⚠️ deletes all data)
dotnet ef database drop --project ../AiTradingRace.Infrastructure --force
./scripts/setup-database.sh
./scripts/seed-database.sh

# Generate SQL script from migrations
./scripts/generate-migration-script.sh
cat database-scripts/migrations.sql

# SQL shell
docker exec -it ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P '$SA_PASSWORD' -d AiTradingRaceDb
```

### Cleaning Up

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ deletes database data)
docker-compose down -v

# Remove all containers, networks, images
docker-compose down --rmi all --volumes --remove-orphans
```

---

## Performance Tips

### 1. Docker Resource Limits

Docker Desktop → Settings → Resources:
- **CPUs:** 4+ cores
- **Memory:** 8+ GB
- **Swap:** 2+ GB

### 2. Database Connection Pooling

Already configured in `appsettings.json`:
```json
"ConnectionStrings": {
  "DefaultConnection": "...;Min Pool Size=5;Max Pool Size=100;"
}
```

### 3. Redis Caching

ML predictions cached for 1 hour (configurable):
- **Without cache:** 300ms per prediction
- **With cache:** 5-10ms per prediction
- **Improvement:** 20-50x faster

To adjust TTL, edit `ai-trading-race-ml/app/middleware/idempotency.py`:
```python
CACHE_TTL = 3600  # seconds (1 hour)
```

### 4. Frontend Polling Interval

Adjust refresh rate in `ai-trading-race-web/.env`:
```bash
# Refresh every 30 seconds (default)
VITE_POLLING_INTERVAL=30000

# More frequent (every 10 seconds)
VITE_POLLING_INTERVAL=10000

# Less frequent (every 60 seconds)
VITE_POLLING_INTERVAL=60000
```

---

## Security Checklist

### Development

- ✅ `.env` and `local.settings.json` in `.gitignore`
- ✅ `.env.example` templates committed (no secrets)
- ✅ Strong SQL Server password (`$SA_PASSWORD`)
- ✅ CORS restricted to `localhost:5173`
- ✅ API keys stored in environment variables

### Production (Future)

When deploying to production:
- [ ] Use Azure Key Vault for secrets
- [ ] Enable Managed Identity
- [ ] Use Azure SQL with firewall rules
- [ ] Enable HTTPS/TLS everywhere
- [ ] Rotate API keys regularly
- [ ] Enable Application Insights
- [ ] Configure CORS to production domain only
- [ ] Use production-grade database passwords

---

## Next Steps

1. **Let it Run** - Wait 30-60 minutes for:
   - Market data to accumulate (15-min candles)
   - Agents to make trading decisions (every 5 min)
   - Portfolio values to update

2. **Monitor the Race**
   - Dashboard: http://localhost:5173
   - Check leaderboard rankings
   - View recent trades
   - Analyze agent strategies

3. **Experiment**
   - Create new agents with different strategies
   - Adjust agent system prompts
   - Compare Llama vs CustomML providers
   - Tune ML model hyperparameters

4. **Deploy to Production** (when ready)
   - Follow Azure deployment guide (Phase 8)
   - Use GitHub Actions CI/CD workflows
   - Configure production secrets
   - Monitor with Application Insights

---

## Useful Commands Reference

| Task | Command |
|------|---------|
| **Docker** |
| Start all services | `docker-compose up -d` |
| Stop all services | `docker-compose down` |
| View logs | `docker-compose logs -f <service>` |
| Restart service | `docker-compose restart <service>` |
| Rebuild service | `docker-compose build <service>` |
| **Database** |
| Initialize | `./scripts/setup-database.sh` |
| Seed data | `./scripts/seed-database.sh` |
| SQL shell | `docker exec -it ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P '$SA_PASSWORD' -d AiTradingRaceDb` |
| **Application** |
| Run Functions | `cd AiTradingRace.Functions && func start` |
| Run Web API | `cd AiTradingRace.Web && dotnet run` |
| Run Frontend | `cd ai-trading-race-web && npm run dev` |
| **Development** |
| Add migration | `dotnet ef migrations add <Name> --startup-project ../AiTradingRace.Web` |
| Apply migrations | `dotnet ef database update --project ../AiTradingRace.Infrastructure` |
| Run tests | `cd AiTradingRace.Tests && dotnet test` |
| **Health Checks** |
| Web API | `curl http://localhost:5172/api/health` |
| Functions | `curl http://localhost:7071/api/health` |
| ML Service | `curl http://localhost:8000/health` |
| SQL Server | `docker exec ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P '$SA_PASSWORD' -Q "SELECT @@VERSION"` |

---

## Support

- **Documentation:** [README.md](./README.md), [DATABASE.md](./DATABASE.md)
- **CI/CD:** [.github/workflows/README.md](./.github/workflows/README.md)
- **ML Service:** [ai-trading-race-ml/README.md](./ai-trading-race-ml/README.md)
- **Architecture:** [PLANNING_PHASE8.md](./PLANNING_PHASE8.md)

