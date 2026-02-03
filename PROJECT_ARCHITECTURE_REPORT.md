# AI Trading Race - Architecture & Pipeline Report
**Project Documentation**  
*Generated: January 20, 2026*

---

## 📋 Executive Summary

**AI Trading Race** is a sophisticated multi-agent AI trading competition platform that simulates cryptocurrency trading using different AI strategies. The system combines LLM-based agents (GPT-4) with custom machine learning models (RandomForest) to execute automated trading decisions in a controlled simulation environment.

### Key Metrics
- **Technology Stack**: .NET 8, React 18, Python 3.11, FastAPI, Docker Compose, RabbitMQ 3.12
- **Architecture**: Clean/Hexagonal Architecture with DDD principles + Distributed Message Queue
- **Infrastructure**: SQL Server 2022, Redis 7, RabbitMQ 3.12, Docker Compose orchestration
- **Test Coverage**: 33/33 tests passed (23 static + 10 integration)
- **Supported Assets**: BTC, ETH (expandable)
- **AI Providers**: Groq (Llama 3.3 70B), Azure OpenAI, Custom ML (RandomForest)
- **Current Status**: Phase 8 complete - Phase 9 (RabbitMQ) planned
- **Deployment**: Azure deployment deferred (cost optimization)
- **Scalability**: Sequential (Phase 8) → Parallel with RabbitMQ (Phase 9)

---

## 🏗️ System Architecture Overview

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                            │
├─────────────────────────────┬───────────────────────────────────────────┤
│   React Dashboard (Port 5173)        ASP.NET Core Web API (Port 5000)  │
│   • TypeScript + Vite                • REST API Endpoints               │
│   • React Query + Axios              • Swagger/OpenAPI                  │
│   • Recharts Visualization           • CORS + Authentication            │
└─────────────────────────────┴───────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          APPLICATION LAYER                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Use Cases & Business Logic Orchestration                               │
│  • IAgentRunner - Agent execution pipeline                              │
│  • IPortfolioService - Portfolio & trade management                     │
│  • IEquityService - Performance tracking                                │
│  • IMarketDataService - Market data retrieval                           │
│                                                                          │
│  DTOs: AgentContext, AgentDecision, PerformanceMetrics                  │
└─────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        INFRASTRUCTURE LAYER                             │
├───────────────────┬─────────────────────────┬───────────────────────────┤
│  EF Core Repos    │    Agent Clients        │   Market Data Client      │
│  • SQL Server     │    • Groq (Llama 3.3)   │   • CoinGecko API         │
│  • Migrations     │    • Azure OpenAI       │   • Rate Limiting         │
│  • DbContext      │    • Custom ML (HTTP)   │   • Retry Logic           │
│                   │    • Factory Pattern    │                           │
└───────────────────┴─────────────────────────┴───────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            DOMAIN LAYER                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  Pure Business Entities & Rules                                         │
│  • Agent, Portfolio, Position, Trade                                    │
│  • MarketAsset, MarketCandle                                            │
│  • EquitySnapshot                                                       │
│  • Enums: ModelProvider, OrderSide, Strategy                            │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL SERVICES                              │
├─────────────────────────────┬───────────────────────────────────────────┤
│  Docker Compose Services    │    Python ML Service (Port 8000)          │
│  • SQL Server 2022          │    • FastAPI Framework                    │
│  • Redis 7 (Cache)          │    • Feature Engineering                  │
│  • RabbitMQ 3.12 (Phase 9+) │    • RandomForest Predictor               │
│  • ML Service Container     │    • API Key Authentication               │
│                             │    • Idempotency Middleware               │
│  Azure Functions            │    • Health Checks                        │
│  • Timer Triggers           │                                           │
│  • Message Consumers (P9+)  │    RabbitMQ (Phase 9+)                    │
│  • Market Data Ingestion    │    • Message Queue (AMQP)                 │
│  • Agent Scheduler          │    • Worker orchestration                 │
│                             │    • Dead Letter Queue                    │
└─────────────────────────────┴───────────────────────────────────────────┘
```

---

## 🚀 Phase 9: Distributed Architecture Transformation (Planned)

### Evolution: Sequential → Parallel Processing

**Phase 9 Goal**: Transform the sequential agent execution model into a distributed, horizontally scalable system using RabbitMQ message queues and Redis-based idempotency.

### Current Architecture (Phase 8) - Sequential Bottleneck

```
Timer Trigger (Every 30 min)
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│ RunAgentsFunction                                                   │
│ ├─ Query active agents from database                                │
│ └─ foreach agent in activeAgents (SEQUENTIAL):                      │
│      ├─ Agent 1: Build context → AI decision → Execute (10s)        │
│      ├─ Agent 2: Build context → AI decision → Execute (10s)        │
│      ├─ Agent 3: Build context → AI decision → Execute (10s)        │
│      ├─ Agent 4: Build context → AI decision → Execute (10s)        │
│      └─ Agent 5: Build context → AI decision → Execute (10s)        │
│                                                                     │
│ Total Time: 50+ seconds for 5 agents                                │
│                                                                     │
│ Limitations:                                                        │
│   ❌ Sequential bottleneck (agents wait for each other)             │
│   ❌ Single point of failure (one crash stops all)                  │
│   ❌ Cannot scale horizontally (fixed to 1 instance)                │
│   ❌ One slow agent blocks others (Groq timeout = all wait)         │
│   ❌ Scales linearly: 100 agents = 1000+ seconds (16+ minutes)      │
└─────────────────────────────────────────────────────────────────────┘
```

### Future Architecture (Phase 9) - Parallel with RabbitMQ

```
Timer Trigger (Every 30 min)
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PublishAgentsFunction [Singleton]                                   │
│ ├─ Query active agents from database                                │
│ ├─ Generate execution cycle ID: "20260122-1430"                     │
│ └─ Publish one message per agent (< 1 second total)                 │
│      Message: {                                                     │
│        agentId: "guid",                                             │
│        executionCycleId: "20260122-1430",                           │
│        timestamp: "2026-01-22T14:30:00Z",                           │
│        idempotencyKey: "agent-run:guid:20260122-1430"               │
│      }                                                              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RabbitMQ Message Queue                            │
│                    (agent-execution queue)                           │
│                                                                     │
│  Messages: [Agent1] [Agent2] [Agent3] [Agent4] [Agent5]             │
│                                                                     │
│  Features:                                                          │
│  • Durable: Messages survive broker restart                         │
│  • Priority support: Aggressive traders first (optional)            │
│  • Dead Letter Exchange: Failed messages → agent-execution-dlq      │
│  • TTL: Message expires after 1 hour (prevent stale execution)      │
│                                                                     │
│  Management UI: http://localhost:15672 (guest/guest)                │
└─────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┬─────────────────┐
          │                   │                   │                 │
          ▼                   ▼                   ▼                 ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌────┐
│ Worker 1         │  │ Worker 2         │  │ Worker 3         │  │ ...│
│ (AgentWorker     │  │ (AgentWorker     │  │ (AgentWorker     │  │    │
│  Service)        │  │  Service)        │  │  Service)        │  │    │
├──────────────────┤  ├──────────────────┤  ├──────────────────┤  └────┘
│ Flow:            │  │ Flow:            │  │ Flow:            │
│ 1. Consume msg   │  │ 1. Consume msg   │  │ 1. Consume msg   │
│ 2. Check Redis   │  │ 2. Check Redis   │  │ 2. Check Redis   │
│    idempotency   │  │    idempotency   │  │    idempotency   │
│ 3. Acquire lock  │  │ 3. Acquire lock  │  │ 3. Acquire lock  │
│    (atomic)      │  │    (atomic)      │  │    (atomic)      │
│ 4. Run agent:    │  │ 4. Run agent:    │  │ 4. Run agent:    │
│    • Context     │  │    • Context     │  │    • Context     │
│    • AI decision │  │    • AI decision │  │    • AI decision │
│    • Validate    │  │    • Validate    │  │    • Validate    │
│    • Execute     │  │    • Execute     │  │    • Execute     │
│    • Snapshot    │  │    • Snapshot    │  │    • Snapshot    │
│ 5. Mark complete │  │ 5. Mark complete │  │ 5. Mark complete │
│    in Redis      │  │    in Redis      │  │    in Redis      │
│ 6. ACK message   │  │ 6. ACK message   │  │ 6. ACK message   │
│    to RabbitMQ   │  │    to RabbitMQ   │  │    to RabbitMQ   │
│                  │  │                  │  │                  │
│ If error:        │  │ If error:        │  │ If error:        │
│ • Log details    │  │ • Log details    │  │ • Log details    │
│ • NACK message   │  │ • NACK message   │  │ • NACK message   │
│ • Requeue (3x)   │  │ • Requeue (3x)   │  │ • Requeue (3x)   │
│ • → DLQ if fail  │  │ • → DLQ if fail  │  │ • → DLQ if fail  │
│                  │  │                  │  │                  │
│ Processing:      │  │ Processing:      │  │ Processing:      │
│ Agent 1 (10s)    │  │ Agent 2 (10s)    │  │ Agent 3 (10s)    │
└──────────────────┘  └──────────────────┘  └──────────────────┘

Total Time: ~10-15 seconds (3-5x faster!)
Scalability: Add more workers → process more agents concurrently

Benefits:
✅ 3-5x performance improvement (parallel execution)
✅ Horizontal scalability (scale workers independently)
✅ Fault tolerance (isolated failures, auto-retry)
✅ Idempotency (no duplicate executions via Redis locks)
✅ Dead Letter Queue (persistent failure handling)
✅ Observable (RabbitMQ Management UI with real-time metrics)
✅ Cost: $0/month (open source)
```

### Phase 9 Architecture Components

```
┌──────────────────────────────────────────────────────────────────────┐
│                   PHASE 9 NEW COMPONENTS                             │
└──────────────────────────────────────────────────────────────────────┘

1. RabbitMQ Infrastructure (Docker Compose)
   ├─ Image: rabbitmq:3.12-management
   ├─ Port 5672: AMQP protocol
   ├─ Port 15672: Management UI (guest/guest)
   ├─ Queues:
   │   ├─ agent-execution (main queue)
   │   └─ agent-execution-dlq (dead letter queue)
   ├─ Features:
   │   ├─ Durable queues (survive restart)
   │   ├─ Message persistence
   │   ├─ Automatic retry with exponential backoff
   │   └─ Dead letter exchange for failed messages
   └─ Health check: rabbitmq-diagnostics ping

2. Redis Idempotency Service (Extended)
   ├─ Interface: IIdempotencyService (Application layer)
   ├─ Implementation: RedisIdempotencyService (Infrastructure layer)
   ├─ Methods:
   │   ├─ TryAcquireLockAsync(key, workerId, ttl)
   │   │   └─ Atomic SETNX with expiry (prevents race conditions)
   │   ├─ IsAlreadyProcessedAsync(key)
   │   │   └─ Check if agent already executed in this cycle
   │   ├─ MarkAsCompletedAsync(key, result)
   │   │   └─ Store execution result for audit/debugging
   │   └─ GetCachedResultAsync<T>(key)
   │       └─ Retrieve cached execution result
   ├─ Key Structure:
   │   ├─ Lock: "agent-lock:{agentId}:{cycleId}"
   │   └─ Result: "agent-result:{agentId}:{cycleId}"
   └─ TTL: 1 hour (prevents stale locks, allows retry in next cycle)

3. Message Publisher (Azure Function)
   ├─ Function: PublishAgentsFunction
   ├─ Trigger: Timer (0 */30 * * * *) with [Singleton] attribute
   ├─ Responsibilities:
   │   ├─ Query active agents from database
   │   ├─ Generate execution cycle ID (timestamp-based)
   │   ├─ Create message per agent with idempotency key
   │   └─ Publish to RabbitMQ agent-execution queue
   ├─ Message Format:
   │   {
   │     "agentId": "guid",
   │     "executionCycleId": "20260122-1430",
   │     "timestamp": "2026-01-22T14:30:00Z",
   │     "idempotencyKey": "agent-run:guid:20260122-1430"
   │   }
   └─ Execution Time: < 1 second (publish only, no execution)

4. Worker Service (Background Service)
   ├─ Service: AgentWorkerService
   ├─ Type: IHostedService (long-running background service)
   ├─ Consumes from: agent-execution queue
   ├─ Concurrency: Configurable via appsettings (default: 3 workers)
   ├─ Processing Logic:
   │   ├─ Receive message from RabbitMQ
   │   ├─ Extract idempotency key
   │   ├─ Check Redis: Already processed?
   │   ├─ Acquire Redis lock (atomic SETNX)
   │   ├─ Execute agent via IAgentRunner
   │   ├─ Store result in Redis
   │   ├─ Acknowledge message to RabbitMQ
   │   └─ Release lock (implicit via TTL)
   ├─ Error Handling:
   │   ├─ Transient errors: NACK message → requeue
   │   ├─ Retry policy: 3 attempts with exponential backoff
   │   ├─ Permanent errors: Route to DLQ after max retries
   │   └─ Structured logging with correlation IDs
   └─ Deployment:
       ├─ Local: func start (AiTradingRace.Functions)
       ├─ Docker: Separate worker containers (scalable)
       └─ Azure: Azure Container Instances or App Service

5. Observability & Monitoring
   ├─ RabbitMQ Management UI
   │   ├─ URL: http://localhost:15672
   │   ├─ Credentials: guest/guest
   │   ├─ Metrics:
   │   │   ├─ Queue depth (messages waiting)
   │   │   ├─ Message publish/consume rate
   │   │   ├─ Consumer count (active workers)
   │   │   ├─ Unacknowledged messages
   │   │   └─ DLQ message count
   │   └─ Features:
   │       ├─ Real-time queue visualization
   │       ├─ Manual message inspection
   │       └─ Queue purging (for testing)
   ├─ Structured Logging
   │   ├─ Correlation IDs: Track request across publisher/worker
   │   ├─ Log enrichment: workerId, agentId, executionCycleId
   │   ├─ Timestamps: High-precision for latency tracking
   │   └─ Log levels: DEBUG (detailed), INFO (execution flow), ERROR (failures)
   ├─ Custom Metrics (Future)
   │   ├─ Agent execution time (P50, P95, P99)
   │   ├─ Messages published/consumed per minute
   │   ├─ Failed agent count per cycle
   │   ├─ Redis lock acquisition time
   │   └─ Queue backlog size
   └─ Health Checks
       ├─ RabbitMQ connection health
       ├─ Redis connection health
       ├─ Worker liveness (heartbeat)
       └─ Database connection health
```

### Performance Comparison

| Metric | Phase 8 (Sequential) | Phase 9 (RabbitMQ) | Improvement |
|--------|---------------------|-------------------|-------------|
| **5 agents** | 50s | 10-15s | **3-5x faster** |
| **20 agents** | 200s (3.3 min) | 40-60s (1 min) | **3-4x faster** |
| **100 agents** | 1000s (16.7 min) | 100-150s (2.5 min) | **6-10x faster** |
| **Scalability** | 1 instance (fixed) | N workers (elastic) | **Horizontal** |
| **Fault tolerance** | All fail if one fails | Isolated failures | **Resilient** |
| **Cost** | $0/month | $0/month | **No change** |

### Migration Strategy (Phase 9 Execution Plan)

```
Sprint 9.1 (1 day) - Infrastructure Setup
├─ Add RabbitMQ to docker-compose.yml
├─ Add RabbitMQ.Client NuGet package
├─ Configure RabbitMQ connection in appsettings.json
├─ Verify RabbitMQ Management UI access
└─ Create health check endpoints

Sprint 9.2 (1 day) - Message Publishing
├─ Create PublishAgentsFunction (replace RunAgentsFunction)
├─ Add [Singleton] attribute (prevent duplicate publishes)
├─ Implement IRabbitMqPublisher interface
├─ Add retry policy with Polly
└─ Test: Publish messages appear in RabbitMQ UI

Sprint 9.3 (1 day) - Idempotency Layer
├─ Create IIdempotencyService interface
├─ Implement RedisIdempotencyService
├─ Test lock acquisition (simulate concurrent workers)
├─ Test idempotency (same key → no duplicate execution)
└─ Verify TTL expiration (old locks auto-release)

Sprint 9.4 (2 days) - Worker Service
├─ Create AgentWorkerService (IHostedService)
├─ Implement message consumption logic
├─ Integrate with IAgentRunner (reuse existing code)
├─ Add error handling and retry logic
├─ Test: Workers consume and process agents
└─ Test: Failed agents route to DLQ after 3 retries

Sprint 9.5 (1 day) - Testing & Validation
├─ Unit tests: IdempotencyService, RabbitMqPublisher
├─ Integration tests: End-to-end message flow
├─ Load tests: 5 workers × 20 agents
├─ Failure tests: Worker crash → message requeue
└─ DLQ test: Persistent failure → routed correctly

Sprint 9.6 (0.5 day) - Documentation
├─ Update DEPLOYMENT_LOCAL.md with RabbitMQ setup
├─ Create ARCHITECTURE_DISTRIBUTED.md
├─ Update PROJECT_ARCHITECTURE_REPORT.md
└─ Add troubleshooting guide

Sprint 9.7 (0.5 day) - Migration & Rollback
├─ Rename RunAgentsFunction → RunAgentsFunction.OLD
├─ Add feature flag: UseMessageQueue (default: true)
├─ Test rollback: Switch to sequential mode
└─ Deploy to production (when ready)

Total Effort: 7 days (1 week sprint)
```

---

## 🐳 Docker Infrastructure

### Docker Compose Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    DOCKER COMPOSE SERVICES                           │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ SQL Server 2022 (ai-trading-sqlserver)                              │
├─────────────────────────────────────────────────────────────────────┤
│ Image: mcr.microsoft.com/mssql/server:2022-latest                   │
│ Platform: linux/amd64 (Rosetta on ARM Mac)                          │
│ Port: 1433 → localhost:1433                                         │
│ Environment:                                                        │
│   • ACCEPT_EULA=Y                                                   │
│   • SA_PASSWORD=YourStrong!Passw0rd                                 │
│   • MSSQL_PID=Developer                                             │
│ Volumes:                                                            │
│   • sqlserver_data:/var/opt/mssql (persistent)                     │
│ Health Check:                                                       │
│   • /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa             │
│   • Interval: 10s, Timeout: 3s, Retries: 5                          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Redis 7 (ai-trading-redis)                                          │
├─────────────────────────────────────────────────────────────────────┤
│ Image: redis:7-alpine                                               │
│ Port: 6379 → localhost:6379                                         │
│ Volumes:                                                            │
│   • redis_data:/data (persistent)                                   │
│ Health Check:                                                       │
│   • redis-cli ping (expects PONG)                                   │
│   • Interval: 10s, Timeout: 3s, Retries: 5                          │
│ Purpose:                                                            │
│   • ML prediction caching (idempotency)                             │
│   • 20-50x performance improvement                                  │
│   • Request deduplication                                           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ ML Service (ai-trading-ml-service)                                  │
├─────────────────────────────────────────────────────────────────────┤
│ Build Context: ./ai-trading-race-ml                                 │
│ Dockerfile: Multi-stage build (builder + runtime)                   │
│ Port: 8000 → localhost:8000                                         │
│ Environment:                                                        │
│   • ML_SERVICE_API_KEY=test-api-key-12345                           │
│   • REDIS_HOST=redis                                                │
│   • REDIS_PORT=6379                                                 │
│ Dependencies:                                                       │
│   • redis (waits for healthy status)                                │
│ User: appuser (non-root)                                            │
│ Health Check:                                                       │
│   • curl -f http://localhost:8000/health                            │
│   • Interval: 30s, Timeout: 10s, Retries: 3                         │
│ Security:                                                           │
│   • API key authentication                                          │
│   • Non-root container execution                                    │
│   • Proper file ownership (appuser:appuser)                         │
└─────────────────────────────────────────────────────────────────────┘

Commands:
• Start all services: docker compose up -d
• View logs: docker compose logs -f [service]
• Stop all: docker compose down
• Rebuild: docker compose build [service]
```

---

## 🗄️ Database Management

### Automated Database Setup

```
┌──────────────────────────────────────────────────────────────────────┐
│                    DATABASE AUTOMATION SCRIPTS                       │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ scripts/setup-database.sh                                           │
├─────────────────────────────────────────────────────────────────────┤
│ Purpose: Initialize database and apply EF Core migrations           │
│                                                                     │
│ Steps:                                                              │
│ 1. Wait for SQL Server health (30 retries, 10s intervals)           │
│ 2. Create AiTradingRace database if not exists                      │
│ 3. Apply EF Core migrations from AiTradingRace.Infrastructure       │
│ 4. Verify schema creation (8 tables)                                │
│                                                                     │
│ Output:                                                             │
│ • Connection string for application                                 │
│ • Migration status                                                  │
│                                                                     │
│ Usage: ./scripts/setup-database.sh                                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ scripts/seed-database.sh                                            │
├─────────────────────────────────────────────────────────────────────┤
│ Purpose: Populate database with test data                           │
│                                                                     │
│ Seeded Data:                                                        │
│ • 3 Assets: BTC, ETH, USD                                           │
│ • 5 Agents:                                                         │
│   - Llama Momentum Trader (Groq, Aggressive)                        │
│   - Llama Value Investor (Groq, Conservative)                       │
│   - CustomML Technical Analyst (ML Service, Balanced)               │
│   - Llama Contrarian (Groq, Aggressive)                             │
│   - Llama Balanced Trader (Groq, Balanced)                          │
│ • 5 Portfolios: $100,000 starting capital each                      │
│                                                                     │
│ Usage: ./scripts/seed-database.sh                                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ scripts/generate-migration-script.sh                                │
├─────────────────────────────────────────────────────────────────────┤
│ Purpose: Export SQL migration script for manual review              │
│                                                                     │
│ Output: migrations/InitialCreate.sql                                │
│ • CREATE TABLE statements                                           │
│ • Indexes and constraints                                           │
│ • Foreign key relationships                                         │
│                                                                     │
│ Usage: ./scripts/generate-migration-script.sh                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Complete Data Flow Pipeline

### 1️⃣ Market Data Ingestion Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                    MARKET DATA INGESTION FLOW                        │
└──────────────────────────────────────────────────────────────────────┘

Step 1: Trigger
┌─────────────────┐          ┌────────────────────────────────────┐
│ Azure Function  │ (CRON)   │ MarketDataIngestionService         │
│ Timer: */15min  │─────────▶│ IngestAllAssetsAsync()             │
│ (func start)    │          │                                    │
└─────────────────┘          └────────────────────────────────────┘
      OR (Testing Only)                      │
┌─────────────────┐                          │
│ POST /api/      │                          │
│ admin/ingest    │─────────────────────────▶│
└─────────────────┘          
                                             ▼
Step 2: External API Call
                             ┌────────────────────────────────────┐
                             │ CoinGeckoMarketDataClient          │
                             │ GET /coins/{id}/ohlc?days=30       │
                             └────────────────────────────────────┘
                                             │
                                             ▼
                             ┌────────────────────────────────────┐
                             │ Response: [[timestamp, O,H,L,C],   │
                             │            [1640995200, 42000, ... │
                             └────────────────────────────────────┘
                                             │
                                             ▼
Step 3: Data Transformation
                             ┌────────────────────────────────────┐
                             │ Map to ExternalCandleDto           │
                             │ • Convert Unix → DateTime          │
                             │ • Validate OHLC logic              │
                             │ • Set MarketAssetId                │
                             └────────────────────────────────────┘
                                             │
                                             ▼
Step 4: Deduplication Check
                             ┌────────────────────────────────────┐
                             │ Query Existing Timestamps          │
                             │ WHERE MarketAssetId = @id          │
                             │ AND TimestampUtc IN (@timestamps)  │
                             └────────────────────────────────────┘
                                             │
                                             ▼
Step 5: Bulk Insert
                             ┌────────────────────────────────────┐
                             │ DbContext.MarketCandles.AddRange() │
                             │ SaveChangesAsync()                 │
                             └────────────────────────────────────┘
                                             │
                                             ▼
                             ┌────────────────────────────────────┐
                             │ SQL Server 2022 (Docker local)     │
                             │ ✓ MarketCandles Table Updated      │
                             └────────────────────────────────────┘

Frequency: Every 15 minutes (Azure Functions timer trigger)
Development: Run locally with `func start` in AiTradingRace.Functions
Production: Deployed to Azure (when ready)
Testing: Manual trigger via POST /api/admin/ingest (AdminController)
Error Handling: Retry policy (3 attempts), structured logging
```

**Key Features:**
- ✅ Duplicate prevention via unique index `(MarketAssetId, TimestampUtc)`
- ✅ Rate limiting compliance with CoinGecko API (50 calls/min)
- ✅ Automatic retry with exponential backoff
- ✅ Structured logging with correlation IDs

---

### 2️⃣ Agent Execution Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                    AGENT EXECUTION PIPELINE                          │
└──────────────────────────────────────────────────────────────────────┘

Trigger: Azure Function Timer (*/30 min via func start)
Testing: POST /api/agents/{id}/run (manual override for debugging)

┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 1: CONTEXT BUILDING                                           │
├─────────────────────────────────────────────────────────────────────┤
│ AgentContextBuilder.BuildAsync(agentId)                             │
│                                                                     │
│ 1. Load Agent Configuration                                         │
│    ├─ Agent.Instructions (custom prompt)                            │
│    ├─ Agent.ModelProvider (Groq/Llama | AzureOpenAI | CustomML)     │
│    └─ Agent.Strategy (Aggressive, Conservative, Balanced)           │
│                                                                     │
│ 2. Fetch Current Portfolio State (SQL Server)                       │
│    ├─ Portfolio.Cash                                                │
│    ├─ Positions[] (Asset, Quantity, AvgEntryPrice)                  │
│    └─ TotalValue (Cash + PositionsValue)                            │
│                                                                     │
│ 3. Get Recent Market Data (Last 50 Candles per Asset)               │
│    ├─ BTC: [{timestamp, open, high, low, close, volume}, ...]       │
│    └─ ETH: [{timestamp, open, high, low, close, volume}, ...]       │
│                                                                     │
│ 4. Calculate Current Prices                                         │
│    └─ Latest candle close price for each asset                      │
│                                                                     │
│ Output: AgentContext {                                              │
│   agentId, portfolio, recentCandles, instructions, strategy         │
│ }                                                                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 2: AI DECISION GENERATION                                     │
├─────────────────────────────────────────────────────────────────────┤
│ IAgentModelClient.GenerateDecisionAsync(context)                    │
│                                                                     │
│ ┌──────────────────────────┐    ┌────────────────────────────────┐ │
│ │ LLM Path                 │    │ Custom ML Path                 │ │
│ │ (Groq/Llama or Azure AI) │    │ (Python FastAPI Service)       │ │
│ ├──────────────────────────┤    ├────────────────────────────────┤ │
│ │ 1. Format prompt         │    │ 1. Check Redis cache           │ │
│ │    - System role         │    │    • Key: hash(context)        │ │
│ │    - Market analysis     │    │    • TTL: 1 hour               │ │
│ │    - Portfolio state     │    │    • Cache HIT: return cached  │ │
│ │    - Risk rules          │    │                                │ │
│ │    - JSON schema         │    │ 2. Cache MISS: continue        │ │
│ │                          │    │                                │ │
│ │ 2. Call LLM API          │    │ 3. HTTP POST /predict          │ │
│ │    • Groq (default)      │    │ 4. API key authentication      │ │
│ │    • Azure OpenAI        │    │ 5. Feature engineering         │ │
│ │                          │    │    • RSI, MACD, Bollinger      │ │
│ │ 3. Parse JSON response   │    │    • SMA crossovers            │ │
│ │                          │    │ 6. RandomForest prediction     │ │
│ │                          │    │ 7. Generate signals            │ │
│ │                          │    │ 8. Create orders               │ │
│ │                          │    │                                │ │
│ │                          │    │ 9. Cache result in Redis       │ │
│ │                          │    │ 10. Return structured response │ │
│ └──────────────────────────┘    └────────────────────────────────┘ │
│                │                              │                     │
│                └──────────────┬───────────────┘                     │
│                               ▼                                     │
│ AgentDecision {                                                     │
│   orders: [                                                         │
│     { side: "BUY", symbol: "BTC", quantity: 0.05, limitPrice: null }│
│   ],                                                                │
│   reasoning: "BTC oversold (RSI=28), bullish MACD crossover",      │
│   signals: [                                                        │
│     { feature: "rsi_14", value: 28.3, rule: "<30", fired: true }   │
│   ],                                                                │
│   modelVersion: "llama-3.3-70b" | "gpt-4-turbo" | "1.0.0"          │
│ }                                                                   │
│                                                                     │
│ Performance:                                                        │
│ • Cache HIT: <10ms response time (20-50x faster)                    │
│ • Cache MISS: 50-200ms (ML service) or 500-2000ms (LLM)            │
│ • Idempotency: Same context = Same decision (within TTL)            │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 3: RISK VALIDATION                                            │
├─────────────────────────────────────────────────────────────────────┤
│ RiskValidator.ValidateDecision(decision, portfolio)                 │
│                                                                     │
│ Constraints Checked:                                                │
│ ✓ Max position size: 50% of portfolio value per asset               │
│ ✓ Max single order: 20% of available cash                           │
│ ✓ Max orders per run: 3 orders                                      │
│ ✓ No short selling (quantity > 0)                                   │
│ ✓ Sufficient cash for BUY orders                                    │
│ ✓ Sufficient position for SELL orders                               │
│                                                                     │
│ Actions Taken:                                                      │
│ • Reject invalid orders (logged)                                    │
│ • Adjust quantities to comply with limits                           │
│ • Generate warnings for user review                                 │
│                                                                     │
│ Output: ValidatedDecision {                                         │
│   validOrders: [Order[]],                                           │
│   rejectedOrders: [{ order, reason }],                              │
│   warnings: [string[]]                                              │
│ }                                                                   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 4: TRADE EXECUTION                                            │
├─────────────────────────────────────────────────────────────────────┤
│ PortfolioService.ApplyTradesAsync(agentId, validOrders)            │
│                                                                     │
│ For each valid order:                                               │
│                                                                     │
│ 1. Resolve Execution Price                                          │
│    price = order.limitPrice ?? currentMarketPrice                   │
│                                                                     │
│ 2. Calculate Notional Value                                         │
│    notional = quantity × price                                      │
│                                                                     │
│ 3. Update Cash Balance                                              │
│    IF BUY:  portfolio.Cash -= notional                              │
│    IF SELL: portfolio.Cash += notional                              │
│                                                                     │
│ 4. Update Positions                                                 │
│    IF BUY:                                                          │
│      • Add new position OR                                          │
│      • Update existing: newAvgPrice = (oldQty*oldPrice +            │
│                          newQty*newPrice) / totalQty                │
│    IF SELL:                                                         │
│      • Reduce position quantity                                     │
│      • Calculate realized PnL: (sellPrice - avgEntryPrice) × qty    │
│      • Close position if quantity = 0                               │
│                                                                     │
│ 5. Create Trade Record                                              │
│    Trade {                                                          │
│      agentId, marketAssetId, side, quantity, price,                 │
│      totalValue, realizedPnL, timestamp                             │
│    }                                                                │
│                                                                     │
│ 6. Persist to Database                                              │
│    • UPDATE Portfolios                                              │
│    • INSERT/UPDATE Positions                                        │
│    • INSERT Trades                                                  │
│    • SaveChangesAsync() [Transaction]                               │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 5: EQUITY SNAPSHOT                                            │
├─────────────────────────────────────────────────────────────────────┤
│ EquityService.CaptureSnapshotAsync(agentId)                         │
│                                                                     │
│ 1. Calculate Total Portfolio Value                                  │
│    totalValue = cash + Σ(position.quantity × currentPrice)          │
│                                                                     │
│ 2. Calculate Unrealized PnL per Position                            │
│    unrealizedPnL = (currentPrice - avgEntryPrice) × quantity        │
│                                                                     │
│ 3. Aggregate Realized PnL (from closed trades)                      │
│    realizedPnL = Σ(trade.realizedPnL) WHERE timestamp = today       │
│                                                                     │
│ 4. Create Snapshot                                                  │
│    EquitySnapshot {                                                 │
│      agentId, timestampUtc, totalValue,                             │
│      cash, positionsValue, unrealizedPnL, realizedPnL               │
│    }                                                                │
│                                                                     │
│ 5. Save to Database                                                 │
│    INSERT INTO EquitySnapshots                                      │
│                                                                     │
│ 6. Calculate Performance Metrics (if requested)                     │
│    • Return %: (current - initial) / initial                        │
│    • Sharpe Ratio: avgReturn / stdDevReturn                         │
│    • Max Drawdown: max((peak - trough) / peak)                      │
│    • Win Rate: winningTrades / totalTrades                          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    ✅ Execution Complete
                    Dashboard Auto-Refreshes via WebSocket/Polling
```

**Execution Frequency:**
- **Automated (Primary)**: Every 30 minutes via Azure Function timer trigger
  - Development: `func start` in AiTradingRace.Functions
  - Production: Deployed to Azure (pending)
- **Manual (Testing Only)**: POST /api/agents/{id}/run for debugging specific agents
- **Retry Policy**: 3 attempts with exponential backoff on transient failures
- **CRON Schedule**: `0 */30 * * * *` (runs at minute 0 and 30 of every hour)

---

### 3️⃣ Python ML Service - Detailed Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                  PYTHON ML SERVICE ARCHITECTURE                      │
│                  (ai-trading-race-ml/)                               │
└──────────────────────────────────────────────────────────────────────┘

HTTP Request from .NET Backend:
POST http://localhost:8000/predict
Headers: 
  - Content-Type: application/json
  - X-API-Key: <secret-key>
  - Idempotency-Key: <uuid> (optional, for retry safety)
Body: AgentContextRequest

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 0: IDEMPOTENCY MIDDLEWARE (Redis Cache)                        │
├─────────────────────────────────────────────────────────────────────┤
│ IdempotencyMiddleware.dispatch(request)                             │
│                                                                     │
│ 1. Extract Idempotency-Key header (or generate from request hash)   │
│ 2. Check Redis cache: GET idempotency:{key}                         │
│ 3. If CACHE HIT:                                                    │
│    • Return cached response immediately (<10ms)                     │
│    • Add header X-Cache-Status: HIT                                 │
│    • Skip all downstream processing                                 │
│ 4. If CACHE MISS:                                                   │
│    • Continue to next middleware                                    │
│    • After response generated, cache for 1 hour                     │
│    • Add header X-Cache-Status: MISS                                │
│                                                                     │
│ Performance: 20-50x faster on cache hits                            │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: MIDDLEWARE AUTHENTICATION                                   │
├─────────────────────────────────────────────────────────────────────┤
│ APIKeyMiddleware.dispatch(request)                                  │
│                                                                     │
│ 1. Extract X-API-Key header                                         │
│ 2. Compare with env var ML_SERVICE_API_KEY                          │
│ 3. Return 403 Forbidden if invalid/missing                          │
│ 4. Continue to endpoint if valid                                    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: REQUEST VALIDATION (Pydantic)                               │
├─────────────────────────────────────────────────────────────────────┤
│ Parse JSON → AgentContextRequest model                              │
│                                                                     │
│ Validate Fields:                                                    │
│ • schemaVersion (must be "1.0")                                     │
│ • agentId (UUID format)                                             │
│ • portfolio { cash, totalValue, positions[] }                       │
│ • recentCandles { BTC: [CandleData[]], ETH: [CandleData[]] }        │
│ • instructions (string, optional)                                   │
│                                                                     │
│ Reject with 422 if validation fails                                 │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: DECISION SERVICE ORCHESTRATION                              │
├─────────────────────────────────────────────────────────────────────┤
│ decision_service.generate_decision(context)                         │
│                                                                     │
│ For each asset (BTC, ETH):                                          │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │ 3.1 DATA PREPARATION                                        │  │
│   ├─────────────────────────────────────────────────────────────┤  │
│   │ Convert CandleData[] → pandas DataFrame                     │  │
│   │                                                             │  │
│   │ DataFrame columns:                                          │  │
│   │ • timestamp (datetime64)                                    │  │
│   │ • open, high, low, close (float64)                          │  │
│   │ • volume (float64)                                          │  │
│   │                                                             │  │
│   │ Validate:                                                   │  │
│   │ • Minimum 50 candles required                               │  │
│   │ • No missing values                                         │  │
│   │ • OHLC logic (high ≥ max(O,C), low ≤ min(O,C))              │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                │                                    │
│                                ▼                                    │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │ 3.2 FEATURE ENGINEERING (features.py)                      │  │
│   ├─────────────────────────────────────────────────────────────┤  │
│   │ engineer_features(df) → DataFrame with 11 features          │  │
│   │                                                             │  │
│   │ Technical Indicators:                                       │  │
│   │ ┌─────────────────────────────────────────────────────────┐ │  │
│   │ │ Trend Indicators:                                       │ │  │
│   │ │ • sma_7: Simple Moving Average (7 periods)              │ │  │
│   │ │ • sma_21: Simple Moving Average (21 periods)            │ │  │
│   │ │ • macd: MACD Line (12-26 EMA difference)                │ │  │
│   │ │ • macd_signal: Signal Line (9 EMA of MACD)              │ │  │
│   │ │ • macd_diff: Histogram (MACD - Signal)                  │ │  │
│   │ └─────────────────────────────────────────────────────────┘ │  │
│   │ ┌─────────────────────────────────────────────────────────┐ │  │
│   │ │ Momentum Indicators:                                    │ │  │
│   │ │ • rsi_14: Relative Strength Index (14 periods)          │ │  │
│   │ │          [0-100 scale, <30=oversold, >70=overbought]    │ │  │
│   │ └─────────────────────────────────────────────────────────┘ │  │
│   │ ┌─────────────────────────────────────────────────────────┐ │  │
│   │ │ Volatility Indicators:                                  │ │  │
│   │ │ • bb_width: Bollinger Bands Width                       │ │  │
│   │ │            (upper - lower) / middle                     │ │  │
│   │ │ • volatility_7: Rolling 7-period standard deviation     │ │  │
│   │ └─────────────────────────────────────────────────────────┘ │  │
│   │ ┌─────────────────────────────────────────────────────────┐ │  │
│   │ │ Price Action:                                           │ │  │
│   │ │ • returns_1: 1-period price change (%)                  │ │  │
│   │ │ • returns_7: 7-period price change (%)                  │ │  │
│   │ └─────────────────────────────────────────────────────────┘ │  │
│   │ ┌─────────────────────────────────────────────────────────┐ │  │
│   │ │ Volume Indicators:                                      │ │  │
│   │ │ • volume_ratio: volume / volume_sma_7                   │ │  │
│   │ │                [>1 = above average volume]              │ │  │
│   │ └─────────────────────────────────────────────────────────┘ │  │
│   │                                                             │  │
│   │ Output: numpy array shape (11,) - last row only             │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                │                                    │
│                                ▼                                    │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │ 3.3 MODEL PREDICTION (predictor.py)                        │  │
│   ├─────────────────────────────────────────────────────────────┤  │
│   │ TradingPredictor.predict(features, feature_values)          │  │
│   │                                                             │  │
│   │ IF model loaded (trading_model.pkl exists):                 │  │
│   │   ┌───────────────────────────────────────────────────────┐ │  │
│   │   │ ML Path (sklearn RandomForestClassifier)            │ │  │
│   │   ├───────────────────────────────────────────────────────┤ │  │
│   │   │ 1. model.predict(features) → class [0,1,2]          │ │  │
│   │   │    0 = HOLD, 1 = BUY, 2 = SELL                      │ │  │
│   │   │                                                      │ │  │
│   │   │ 2. model.predict_proba(features) → probabilities    │ │  │
│   │   │    [0.15, 0.75, 0.10] → confidence = 75%            │ │  │
│   │   │                                                      │ │  │
│   │   │ 3. Get feature importances from model               │ │  │
│   │   └───────────────────────────────────────────────────────┘ │  │
│   │ ELSE:                                                       │  │
│   │   ┌───────────────────────────────────────────────────────┐ │  │
│   │   │ Rule-Based Fallback                                 │ │  │
│   │   ├───────────────────────────────────────────────────────┤ │  │
│   │   │ BUY signals:                                        │ │  │
│   │   │ • RSI < 30 (oversold)                               │ │  │
│   │   │ • MACD_diff > 0 (bullish crossover)                 │ │  │
│   │   │ • SMA_7 > SMA_21 (uptrend)                          │ │  │
│   │   │                                                      │ │  │
│   │   │ SELL signals:                                       │ │  │
│   │   │ • RSI > 70 (overbought)                             │ │  │
│   │   │ • MACD_diff < 0 (bearish crossover)                 │ │  │
│   │   │ • SMA_7 < SMA_21 (downtrend)                        │ │  │
│   │   │                                                      │ │  │
│   │   │ Threshold: ≥2 signals → Action, else HOLD           │ │  │
│   │   └───────────────────────────────────────────────────────┘ │  │
│   │                                                             │  │
│   │ Output: PredictedAction (BUY/SELL/HOLD), confidence (0-1)   │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                │                                    │
│                                ▼                                    │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │ 3.4 GENERATE EXPLANATION SIGNALS                            │  │
│   ├─────────────────────────────────────────────────────────────┤  │
│   │ For each feature, create ExplanationSignal:                 │  │
│   │                                                             │  │
│   │ Example:                                                    │  │
│   │ {                                                           │  │
│   │   "feature": "rsi_14",                                      │  │
│   │   "value": 27.3,                                            │  │
│   │   "rule": "<30 indicates oversold condition",               │  │
│   │   "fired": true,                                            │  │
│   │   "contribution": "Bullish"  // Bullish | Bearish | Neutral │  │
│   │ }                                                           │  │
│   │                                                             │  │
│   │ Purpose:                                                    │  │
│   │ • Transparency: Show why model made decision                │  │
│   │ • Debugging: Identify misfiring rules                       │  │
│   │ • Compliance: Audit trail for regulatory review             │  │
│   │ • Learning: User education on technical analysis            │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                │                                    │
│                                ▼                                    │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │ 3.5 CREATE TRADE ORDERS                                     │  │
│   ├─────────────────────────────────────────────────────────────┤  │
│   │ Based on predicted action:                                  │  │
│   │                                                             │  │
│   │ IF action == BUY:                                           │  │
│   │   • Check available cash                                    │  │
│   │   • Calculate allocation (e.g., 10% of cash)                │  │
│   │   • quantity = (cash × 0.10) / current_price                │  │
│   │   • Create TradeOrderResponse:                              │  │
│   │     { side: "BUY", symbol: "BTC", quantity: 0.05 }          │  │
│   │                                                             │  │
│   │ IF action == SELL:                                          │  │
│   │   • Get current position quantity                           │  │
│   │   • Sell percentage (e.g., 50% of position)                 │  │
│   │   • quantity = position_qty × 0.50                          │  │
│   │   • Create TradeOrderResponse:                              │  │
│   │     { side: "SELL", symbol: "BTC", quantity: 0.03 }         │  │
│   │                                                             │  │
│   │ IF action == HOLD:                                          │  │
│   │   • No order created                                        │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ Aggregate orders from all assets                                    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: RESPONSE ASSEMBLY                                           │
├─────────────────────────────────────────────────────────────────────┤
│ Create AgentDecisionResponse (Pydantic model)                       │
│                                                                     │
│ {                                                                   │
│   "schemaVersion": "1.0",                                           │
│   "modelVersion": "1.0.0",  // Or RandomForest version              │
│   "requestId": "550e8400-e29b-41d4-a716-446655440000",              │
│   "agentId": "agent-123",                                           │
│   "createdAt": "2026-01-20T14:30:00Z",                              │
│   "orders": [                                                       │
│     {                                                               │
│       "side": "BUY",                                                │
│       "symbol": "BTC",                                              │
│       "quantity": 0.05,                                             │
│       "limitPrice": null  // Market order                           │
│     }                                                               │
│   ],                                                                │
│   "reasoning": "BTC: BUY (conf: 85%) - RSI oversold, MACD bullish; │
│                 ETH: HOLD (conf: 60%)",                             │
│   "signals": [                                                      │
│     {                                                               │
│       "feature": "rsi_14",                                          │
│       "value": 27.3,                                                │
│       "rule": "<30 indicates oversold condition",                   │
│       "fired": true,                                                │
│       "contribution": "Bullish"                                     │
│     },                                                              │
│     {                                                               │
│       "feature": "macd_diff",                                       │
│       "value": 120.5,                                               │
│       "rule": ">0 indicates bullish momentum",                      │
│       "fired": true,                                                │
│       "contribution": "Bullish"                                     │
│     }                                                               │
│     // ... more signals                                             │
│   ]                                                                 │
│ }                                                                   │
│                                                                     │
│ Response Headers:                                                   │
│ • X-Cache-Status: HIT | MISS                                        │
│ • X-Request-Id: <uuid>                                              │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    Return HTTP 200 + JSON Response
                    Cache in Redis (if not cached)
                    Back to .NET Backend for Risk Validation
```

**ML Service Endpoints:**
- `POST /predict` - Generate trading decision (with Redis caching)
- `GET /health` - Health check (includes Redis connectivity)
- `GET /version` - Model version info

**Performance Metrics:**
- Cache HIT: <10ms response time (20-50x improvement)
- Cache MISS: 50-150ms total
  - Feature engineering: 20-30ms
  - Model inference: 10-20ms
  - Network overhead: 20-30ms
- Redis operations: <5ms per call
- Cache TTL: 1 hour (configurable)

---

### 4️⃣ Frontend Dashboard Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                    REACT DASHBOARD ARCHITECTURE                      │
│                    (ai-trading-race-web/)                            │
└──────────────────────────────────────────────────────────────────────┘

User Browser → http://localhost:5173

┌─────────────────────────────────────────────────────────────────────┐
│ ROUTE: / (Dashboard)                                                │
├─────────────────────────────────────────────────────────────────────┤
│ Components Hierarchy:                                               │
│                                                                     │
│ <Dashboard>                                                         │
│   ├─ <PageHeader title="AI Trading Race" />                         │
│   │                                                                 │
│   ├─ <LeaderboardSection>                                           │
│   │    ├─ useLeaderboard() hook                                     │
│   │    │   └─ GET /api/leaderboard                                  │
│   │    │      Response: [                                           │
│   │    │        { agentId, name, totalValue, roi, rank },           │
│   │    │        ...                                                 │
│   │    │      ]                                                     │
│   │    │                                                            │
│   │    └─ <LeaderboardTable>                                        │
│   │         ├─ Sortable columns (Name, Value, ROI%, Rank)           │
│   │         ├─ Click row → navigate to /agents/{id}                 │
│   │         └─ Auto-refresh every 30s (React Query polling)         │
│   │                                                                 │
│   ├─ <MarketStatsSection>                                           │
│   │    ├─ useMarketPrices() hook                                    │
│   │    │   └─ GET /api/market/prices                                │
│   │    │      Response: [                                           │
│   │    │        { symbol: "BTC", price: 42000, change24h: 2.5 },    │
│   │    │        { symbol: "ETH", price: 2200, change24h: -1.2 }     │
│   │    │      ]                                                     │
│   │    │                                                            │
│   │    └─ <MarketCard> (for each asset)                             │
│   │         ├─ Symbol + Logo                                        │
│   │         ├─ Current Price ($42,000)                              │
│   │         ├─ 24h Change (+2.5% ↑) [color: green/red]              │
│   │         └─ Mini sparkline chart                                 │
│   │                                                                 │
│   └─ <EquityChartSection>                                           │
│        ├─ useEquity(selectedAgentId) hook                            │
│        │   └─ GET /api/equity/{id}/history                           │
│        │      Response: [                                           │
│        │        { timestamp: "2024-01-01T00:00:00Z", value: 10000 },│
│        │        ...                                                 │
│        │      ]                                                     │
│        │                                                            │
│        └─ <EquityLineChart> (Recharts)                              │
│             ├─ X-axis: Time                                         │
│             ├─ Y-axis: Portfolio Value ($)                          │
│             ├─ Tooltip: Timestamp + Value                           │
│             └─ Responsive container                                 │
└─────────────────────────────────────────────────────────────────────┘

User clicks agent row → Navigate to /agents/:id

┌─────────────────────────────────────────────────────────────────────┐
│ ROUTE: /agents/:id (Agent Detail)                                  │
├─────────────────────────────────────────────────────────────────────┤
│ <AgentDetailPage>                                                   │
│   │                                                                 │
│   ├─ <AgentInfoCard>                                                │
│   │    ├─ useAgent(id) hook → GET /api/agents/{id}                  │
│   │    └─ Display:                                                  │
│   │         • Agent Name                                            │
│   │         • Strategy (Aggressive, Conservative, etc.)             │
│   │         • Model Provider (Azure OpenAI / Custom ML)             │
│   │         • Status Badge (Active/Inactive)                        │
│   │         • [Run Agent Now] Button                                │
│   │                                                                 │
│   ├─ <PerformanceMetrics>                                           │
│   │    ├─ usePerformance(id) → GET /api/equity/{id}/performance     │
│   │    └─ Display Grid:                                             │
│   │         ┌─────────────┬─────────────┬─────────────┐             │
│   │         │ Total ROI   │ Sharpe      │ Win Rate    │             │
│   │         │ +15.2% ↑    │ 1.8         │ 65%         │             │
│   │         ├─────────────┼─────────────┼─────────────┤             │
│   │         │ Max Drawdn  │ Total Trad. │ Avg Hold    │             │
│   │         │ -8.3%       │ 47          │ 18h         │             │
│   │         └─────────────┴─────────────┴─────────────┘             │
│   │                                                                 │
│   ├─ <PortfolioBreakdown>                                           │
│   │    ├─ usePortfolio(id) → GET /api/portfolios/{id}               │
│   │    └─ Display:                                                  │
│   │         • Cash Balance: $5,234.50                               │
│   │         • Positions Value: $4,765.50                            │
│   │         • Total Value: $10,000.00                               │
│   │         • Pie Chart (Cash vs Positions)                         │
│   │         • Allocation per asset (BTC 30%, ETH 20%, Cash 50%)     │
│   │                                                                 │
│   ├─ <PositionsTable>                                               │
│   │    └─ Table Columns:                                            │
│   │         | Asset | Quantity | Entry $ | Current $ | PnL    | %  │ │
│   │         |-------|----------|---------|-----------|--------|----│ │
│   │         | BTC   | 0.05     | $40,000 | $42,000   | +$100  | +5%│ │
│   │         | ETH   | 1.2      | $2,100  | $2,200    | +$120  | +4%│ │
│   │         Color coding: Green (profit), Red (loss)                │
│   │                                                                 │
│   ├─ <RecentTradesTable>                                            │
│   │    ├─ useTrades(id, limit=20) → GET /api/trades?agentId={id}   │
│   │    └─ Table Columns:                                            │
│   │         | Time     | Side | Symbol | Qty  | Price  | Total   │  │
│   │         |----------|------|--------|------|--------|---------|  │
│   │         | 14:30:00 | BUY  | BTC    | 0.05 | 42,000 | 2,100   │  │
│   │         | 14:25:00 | SELL | ETH    | 0.5  | 2,200  | 1,100   │  │
│   │         Badges: BUY (green), SELL (red)                         │
│   │                                                                 │
│   └─ <EquityHistoryChart>                                           │
│        ├─ useEquity(id) → GET /api/equity/{id}/history              │
│        └─ <ResponsiveContainer>                                     │
│             <LineChart data={equityHistory}>                        │
│               <XAxis dataKey="timestamp" tickFormatter={formatDate}/>│
│               <YAxis tickFormatter={formatCurrency} />              │
│               <Tooltip />                                           │
│               <Line type="monotone" dataKey="value" stroke="#8884d8"│
│                     strokeWidth={2} />                              │
│             </LineChart>                                            │
└─────────────────────────────────────────────────────────────────────┘

User clicks "Run Agent Now" button

┌─────────────────────────────────────────────────────────────────────┐
│ ACTION: Manual Agent Execution                                      │
├─────────────────────────────────────────────────────────────────────┤
│ 1. onClick → runAgentMutation.mutate(agentId)                       │
│                                                                     │
│ 2. React Query Mutation:                                            │
│    POST /api/agents/{id}/run                                        │
│    - Show loading spinner                                           │
│    - Disable button during execution                                │
│                                                                     │
│ 3. Backend executes full agent pipeline (see Phase 2)               │
│                                                                     │
│ 4. On success (HTTP 200):                                           │
│    - Show toast notification: "Agent executed successfully"         │
│    - Invalidate React Query cache for:                              │
│      • usePortfolio(id)                                             │
│      • useTrades(id)                                                │
│      • useEquity(id)                                                │
│      • usePerformance(id)                                           │
│    - Components auto-refetch with fresh data                        │
│    - Charts animate with new data points                            │
│                                                                     │
│ 5. On error (HTTP 4xx/5xx):                                         │
│    - Show error toast: "Execution failed: {reason}"                 │
│    - Enable button for retry                                        │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Frontend Technologies:**
- **React Query**: Automatic caching, refetching, optimistic updates
- **Recharts**: Declarative chart library
- **Axios**: HTTP client with interceptors
- **React Router**: SPA navigation
- **Tailwind CSS**: Utility-first styling

---

## 🗄️ Database Schema

```sql
┌──────────────────────────────────────────────────────────────────────┐
│                    DATABASE ENTITY MODEL                             │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ MarketAssets                                                        │
├──────────────────┬──────────────────────────────────────────────────┤
│ Id               │ GUID (PK)                                        │
│ Symbol           │ VARCHAR(10) [BTC, ETH, SOL, etc.]                │
│ Name             │ VARCHAR(100) [Bitcoin, Ethereum]                 │
│ ExternalId       │ VARCHAR(50) [bitcoin, ethereum] (CoinGecko ID)   │
│ IsActive         │ BIT [TRUE for tracked assets]                    │
│ CreatedAt        │ DATETIME2                                        │
└──────────────────┴──────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ MarketCandles                                                       │
├──────────────────┬──────────────────────────────────────────────────┤
│ Id               │ GUID (PK)                                        │
│ MarketAssetId    │ GUID (FK → MarketAssets)                         │
│ TimestampUtc     │ DATETIME2 (Indexed)                              │
│ Open             │ DECIMAL(18,8)                                    │
│ High             │ DECIMAL(18,8)                                    │
│ Low              │ DECIMAL(18,8)                                    │
│ Close            │ DECIMAL(18,8)                                    │
│ Volume           │ DECIMAL(18,8)                                    │
├──────────────────┴──────────────────────────────────────────────────┤
│ Unique Index: IX_MarketCandles_AssetId_Timestamp                    │
│   (MarketAssetId, TimestampUtc) - Prevents duplicates               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Agents                                                              │
├──────────────────┬──────────────────────────────────────────────────┤
│ Id               │ GUID (PK)                                        │
│ Name             │ VARCHAR(200) [Aggressive Trader, Conservative]   │
│ Instructions     │ NVARCHAR(MAX) [Custom LLM prompt]                │
│ ModelProvider    │ INT [0=AzureOpenAI, 1=CustomML, 2=Anthropic]     │
│ Strategy         │ INT [0=Aggressive, 1=Conservative, 2=Balanced]   │
│ IsActive         │ BIT [TRUE = eligible for auto-execution]         │
│ CreatedAt        │ DATETIME2                                        │
│ UpdatedAt        │ DATETIME2                                        │
└──────────────────┴──────────────────────────────────────────────────┘
         │
         │ 1:1
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Portfolios                                                          │
├──────────────────┬──────────────────────────────────────────────────┤
│ Id               │ GUID (PK)                                        │
│ AgentId          │ GUID (FK → Agents, UNIQUE)                       │
│ Cash             │ DECIMAL(18,8) [Available USD]                    │
│ TotalValue       │ DECIMAL(18,8) [Cash + PositionsValue - computed] │
│ LastUpdatedUtc   │ DATETIME2                                        │
└──────────────────┴──────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Positions                                                           │
├──────────────────┬──────────────────────────────────────────────────┤
│ Id               │ GUID (PK)                                        │
│ PortfolioId      │ GUID (FK → Portfolios)                           │
│ MarketAssetId    │ GUID (FK → MarketAssets)                         │
│ Quantity         │ DECIMAL(18,8) [Amount of asset held]             │
│ AverageEntryPrice│ DECIMAL(18,8) [Weighted avg purchase price]      │
│ UnrealizedPnL    │ DECIMAL(18,8) [Computed: (current - entry) × qty]│
│ LastUpdatedUtc   │ DATETIME2                                        │
├──────────────────┴──────────────────────────────────────────────────┤
│ Unique Index: IX_Positions_Portfolio_Asset                          │
│   (PortfolioId, MarketAssetId) - One position per asset             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Trades                                                              │
├──────────────────┬──────────────────────────────────────────────────┤
│ Id               │ GUID (PK)                                        │
│ AgentId          │ GUID (FK → Agents)                               │
│ MarketAssetId    │ GUID (FK → MarketAssets)                         │
│ Side             │ INT [0=Buy, 1=Sell]                              │
│ Quantity         │ DECIMAL(18,8)                                    │
│ Price            │ DECIMAL(18,8) [Execution price per unit]         │
│ TotalValue       │ DECIMAL(18,8) [quantity × price]                 │
│ RealizedPnL      │ DECIMAL(18,8)? [Only for SELL trades]            │
│ Timestamp        │ DATETIME2 (Indexed)                              │
│ Reasoning        │ NVARCHAR(MAX)? [Agent's explanation]             │
├──────────────────┴──────────────────────────────────────────────────┤
│ Index: IX_Trades_AgentId_Timestamp                                  │
│   For efficient querying of agent trade history                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ EquitySnapshots                                                     │
├──────────────────┬──────────────────────────────────────────────────┤
│ Id               │ GUID (PK)                                        │
│ AgentId          │ GUID (FK → Agents)                               │
│ TimestampUtc     │ DATETIME2 (Indexed)                              │
│ TotalValue       │ DECIMAL(18,8) [Portfolio total value]            │
│ Cash             │ DECIMAL(18,8)                                    │
│ PositionsValue   │ DECIMAL(18,8) [Sum of all position values]       │
│ UnrealizedPnL    │ DECIMAL(18,8) [Total unrealized P&L]             │
│ RealizedPnL      │ DECIMAL(18,8) [Cumulative realized P&L]          │
├──────────────────┴──────────────────────────────────────────────────┤
│ Index: IX_EquitySnapshots_AgentId_Timestamp                         │
│   For efficient chart queries (time-series data)                    │
└─────────────────────────────────────────────────────────────────────┘
```

**Relationships:**
- `MarketAssets` → `MarketCandles` (1:N)
- `MarketAssets` → `Positions` (1:N)
- `MarketAssets` → `Trades` (1:N)
- `Agents` → `Portfolios` (1:1)
- `Agents` → `Trades` (1:N)
- `Agents` → `EquitySnapshots` (1:N)
- `Portfolios` → `Positions` (1:N)

**Key Constraints:**
- Unique constraint on `(MarketAssetId, TimestampUtc)` prevents duplicate candles
- Unique constraint on `AgentId` in Portfolios ensures 1:1 relationship
- Foreign keys with `ON DELETE CASCADE` for data integrity

---

## 🔐 Security & Production Features

### Authentication & Authorization

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SECURITY ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 1. ML Service API Key Authentication                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Request Header:                                                     │
│   X-API-Key: sk_ml_prod_a8d9f7b6e5c4d3e2f1                          │
│                                                                     │
│ Middleware Validation:                                              │
│   • Extract header value                                            │
│   • Compare with environment variable ML_SERVICE_API_KEY            │
│   • Return 403 if invalid/missing                                   │
│   • Log failed attempts                                             │
│                                                                     │
│ Stored in:                                                          │
│   • .NET Backend: appsettings.json (dev), Azure Key Vault (prod)    │
│   • Python Service: .env file (dev), Container env vars (prod)      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 2. Contract Versioning                                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Request/Response Schema:                                            │
│   {                                                                 │
│     "schemaVersion": "1.0",  ← Protocol version                     │
│     "modelVersion": "1.0.0", ← ML model version                     │
│     "requestId": "uuid",     ← Idempotency key                      │
│     ...                                                             │
│   }                                                                 │
│                                                                     │
│ Benefits:                                                           │
│   • Breaking changes detection (reject mismatched versions)         │
│   • A/B testing support (route to different models)                 │
│   • Backward compatibility enforcement                              │
│   • Audit trail (track which model version made decision)           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 3. Risk Constraints (Server-Side Enforcement)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Hard Limits (Cannot be bypassed):                                   │
│   ✓ Max position size: 50% of portfolio per asset                   │
│   ✓ Max single order: 20% of available cash                         │
│   ✓ Max orders per run: 3 orders                                    │
│   ✓ No short selling (quantity must be > 0)                         │
│   ✓ Sufficient balance checks for buys                              │
│   ✓ Sufficient position checks for sells                            │
│                                                                     │
│ Rejection Handling:                                                 │
│   • Log rejected order with reason                                  │
│   • Return warning in API response                                  │
│   • Continue with valid orders (partial execution)                  │
│   • Notify user via UI toast/alert                                  │
│                                                                     │
│ Purpose:                                                            │
│   • Prevent rogue AI decisions                                      │
│   • Protect against prompt injection attacks                        │
│   • Ensure fair competition (level playing field)                   │
│   • Compliance with simulated trading rules                         │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 4. Structured Explainability (Transparency)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Signal Schema:                                                      │
│   {                                                                 │
│     "feature": "rsi_14",              ← Feature name                │
│     "value": 27.3,                    ← Current value               │
│     "rule": "<30 = oversold",         ← Human-readable rule         │
│     "fired": true,                    ← Rule triggered?             │
│     "contribution": "Bullish"         ← Impact on decision          │
│   }                                                                 │
│                                                                     │
│ Use Cases:                                                          │
│   • Debugging: "Why did agent buy at peak?"                         │
│   • Compliance: "Show regulator why decision was made"              │
│   • Learning: "Teach users about technical indicators"              │
│   • Optimization: "Which features have highest impact?"             │
│                                                                     │
│ Storage:                                                            │
│   • Embedded in Trade.Reasoning field (JSON)                        │
│   • Queryable for analysis                                          │
│   • Displayed in UI detail modals                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Future Security Enhancements

```
┌─────────────────────────────────────────────────────────────────────┐
│ PLANNED (Phase 10+)                                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ • Idempotency with Redis:                                           │
│   - Cache requestId → response (24h TTL)                            │
│   - Prevent duplicate executions on retry                           │
│   - Return cached response immediately                              │
│                                                                     │
│ • Rate Limiting:                                                    │
│   - Limit agent runs per hour (e.g., max 5/hour)                    │
│   - Prevent abuse of compute resources                              │
│   - Implement sliding window algorithm                              │
│                                                                     │
│ • Audit Logging:                                                    │
│   - All decisions logged to append-only store                       │
│   - Immutable trail for regulatory compliance                       │
│   - Queryable with Elasticsearch                                    │
│                                                                     │
│ • OpenTelemetry Tracing:                                            │
│   - Distributed tracing across .NET ↔ Python                        │
│   - Propagate traceparent headers                                   │
│   - Export to Azure Monitor / Jaeger                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Performance Metrics & Analytics

### Equity Calculation Algorithm

```python
┌─────────────────────────────────────────────────────────────────────┐
│              PERFORMANCE METRICS CALCULATION                        │
└─────────────────────────────────────────────────────────────────────┘

Input: EquitySnapshot[] (time-series)

┌─────────────────────────────────────────────────────────────────────┐
│ 1. Total Return (ROI)                                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   initial_value = snapshots[0].TotalValue  (e.g., $10,000)          │
│   current_value = snapshots[-1].TotalValue (e.g., $11,500)          │
│                                                                     │
│   total_return = (current_value - initial_value) / initial_value    │
│                = (11,500 - 10,000) / 10,000                         │
│                = 0.15 (15% return)                                  │
│                                                                     │
│   Annualized ROI (if > 1 year):                                     │
│   days_elapsed = (current_time - start_time).days                   │
│   annualized_roi = ((1 + total_return) ^ (365 / days_elapsed)) - 1 │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 2. Sharpe Ratio (Risk-Adjusted Return)                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Calculate daily returns:                                          │
│   returns[i] = (value[i] - value[i-1]) / value[i-1]                 │
│                                                                     │
│   mean_return = average(returns)                                    │
│   std_return = standard_deviation(returns)                          │
│   risk_free_rate = 0.02 / 252  (2% annual, daily)                   │
│                                                                     │
│   sharpe_ratio = (mean_return - risk_free_rate) / std_return        │
│                                                                     │
│   Interpretation:                                                   │
│   • > 1.0 = Good (return exceeds risk)                              │
│   • > 2.0 = Excellent                                               │
│   • < 1.0 = Poor risk-adjusted returns                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 3. Maximum Drawdown (Largest Peak-to-Trough Decline)                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   For each point i in time:                                         │
│     peak[i] = max(values[0:i])                                      │
│     drawdown[i] = (peak[i] - value[i]) / peak[i]                    │
│                                                                     │
│   max_drawdown = max(drawdown)                                      │
│                                                                     │
│   Example:                                                          │
│   Peak = $12,000                                                    │
│   Trough = $10,500                                                  │
│   Drawdown = (12,000 - 10,500) / 12,000 = 12.5%                     │
│                                                                     │
│   Interpretation:                                                   │
│   • Measures worst-case loss from peak                              │
│   • Lower is better (< 10% is excellent)                            │
│   • Critical for risk management                                    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 4. Win Rate (Trading Accuracy)                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   winning_trades = COUNT(trades WHERE RealizedPnL > 0)              │
│   total_trades = COUNT(trades WHERE Side = SELL)                    │
│                                                                     │
│   win_rate = winning_trades / total_trades                          │
│            = 32 / 50 = 0.64 (64%)                                   │
│                                                                     │
│   Interpretation:                                                   │
│   • > 60% = Strong performance                                      │
│   • 50% = Breakeven (random)                                        │
│   • Must combine with profit factor for full picture                │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ 5. Profit Factor (Gross Profit / Gross Loss)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   gross_profit = SUM(RealizedPnL WHERE RealizedPnL > 0)             │
│   gross_loss = ABS(SUM(RealizedPnL WHERE RealizedPnL < 0))          │
│                                                                     │
│   profit_factor = gross_profit / gross_loss                         │
│                 = $2,500 / $1,200 = 2.08                            │
│                                                                     │
│   Interpretation:                                                   │
│   • > 2.0 = Excellent (wins 2x losses)                              │
│   • > 1.5 = Good                                                    │
│   • < 1.0 = Losing strategy                                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Leaderboard Ranking Query

```sql
-- Efficient leaderboard calculation
WITH LatestEquity AS (
  SELECT 
    AgentId,
    TotalValue,
    UnrealizedPnL,
    RealizedPnL,
    ROW_NUMBER() OVER (
      PARTITION BY AgentId 
      ORDER BY TimestampUtc DESC
    ) AS rn
  FROM EquitySnapshots
),
InitialEquity AS (
  SELECT 
    AgentId,
    TotalValue AS InitialValue,
    ROW_NUMBER() OVER (
      PARTITION BY AgentId 
      ORDER BY TimestampUtc ASC
    ) AS rn
  FROM EquitySnapshots
)
SELECT 
  a.Name,
  a.ModelProvider,
  a.Strategy,
  le.TotalValue,
  ((le.TotalValue - ie.InitialValue) / ie.InitialValue * 100) AS ReturnPct,
  le.UnrealizedPnL,
  le.RealizedPnL,
  COUNT(t.Id) AS TotalTrades,
  ROW_NUMBER() OVER (ORDER BY le.TotalValue DESC) AS Rank
FROM Agents a
JOIN LatestEquity le ON a.Id = le.AgentId AND le.rn = 1
JOIN InitialEquity ie ON a.Id = ie.AgentId AND ie.rn = 1
LEFT JOIN Trades t ON a.Id = t.AgentId
WHERE a.IsActive = 1
GROUP BY 
  a.Name, a.ModelProvider, a.Strategy, 
  le.TotalValue, le.UnrealizedPnL, le.RealizedPnL,
  ie.InitialValue
ORDER BY Rank;
```

---

## ⚙️ Automation & Scheduling

### Azure Functions Configuration

```csharp
┌─────────────────────────────────────────────────────────────────────┐
│                    AZURE FUNCTIONS ARCHITECTURE                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Function 1: MarketDataIngestionFunction                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Trigger: Timer (CRON)                                               │
│   Schedule: "0 */15 * * * *"  (Every 15 minutes)                    │
│                                                                     │
│ Execution:                                                          │
│   [Function("MarketDataIngestion")]                                 │
│   public async Task Run(                                            │
│       [TimerTrigger("0 */15 * * * *")] TimerInfo timer,             │
│       ILogger log)                                                  │
│   {                                                                 │
│       log.LogInformation("Starting market data ingestion...");      │
│                                                                     │
│       var assets = await _dbContext.MarketAssets                    │
│           .Where(a => a.IsActive)                                   │
│           .ToListAsync();                                           │
│                                                                     │
│       foreach (var asset in assets)                                 │
│       {                                                             │
│           var candles = await _coinGeckoClient                      │
│               .GetHistoricalOhlcAsync(asset.ExternalId, days: 30);  │
│                                                                     │
│           await _ingestionService                                   │
│               .IngestCandlesAsync(asset.Id, candles);               │
│       }                                                             │
│                                                                     │
│       log.LogInformation("Ingestion complete.");                    │
│   }                                                                 │
│                                                                     │
│ Error Handling:                                                     │
│   • Retry policy: 3 attempts with exponential backoff               │
│   • Log failures to Application Insights                            │
│   • Send alert if consecutive failures > 3                          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Function 2: AgentSchedulerFunction                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Trigger: Timer (CRON)                                               │
│   Schedule: "0 0 * * * *"  (Every hour, on the hour)                │
│                                                                     │
│ Execution:                                                          │
│   [Function("AgentScheduler")]                                      │
│   public async Task Run(                                            │
│       [TimerTrigger("0 0 * * * *")] TimerInfo timer,                │
│       ILogger log)                                                  │
│   {                                                                 │
│       log.LogInformation("Starting agent execution cycle...");      │
│                                                                     │
│       var agents = await _dbContext.Agents                          │
│           .Where(a => a.IsActive)                                   │
│           .ToListAsync();                                           │
│                                                                     │
│       foreach (var agent in agents)                                 │
│       {                                                             │
│           try                                                       │
│           {                                                         │
│               await _agentRunner.RunAsync(agent.Id);                │
│               log.LogInformation($"Agent {agent.Name} executed.");  │
│           }                                                         │
│           catch (Exception ex)                                      │
│           {                                                         │
│               log.LogError(ex, $"Failed to run agent {agent.Id}");  │
│               // Continue with next agent                           │
│           }                                                         │
│       }                                                             │
│                                                                     │
│       log.LogInformation("Execution cycle complete.");              │
│   }                                                                 │
│                                                                     │
│ Concurrency:                                                        │
│   • Sequential execution (no parallel agent runs)                   │
│   • Prevents race conditions on portfolio state                     │
│   • Average execution time: 2-5 seconds per agent                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Deployment Configuration                                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Local Development:                                                  │
│   func start --csharp                                               │
│   Listens on: http://localhost:7071                                 │
│                                                                     │
│ Azure Production:                                                   │
│   • Consumption Plan (pay-per-execution)                            │
│   • Auto-scaling based on load                                      │
│   • Integrated with Application Insights                            │
│   • Environment variables from Azure Key Vault                      │
│                                                                     │
│ Cost Estimate (Monthly):                                            │
│   • Market ingestion: 2,976 executions × $0.20/million = $0.60      │
│   • Agent scheduler: 744 executions × $0.20/million = $0.15         │
│   • Total: < $1/month (within free tier)                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🧪 Testing Strategy

### Test Pyramid

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TEST PYRAMID                                │
└─────────────────────────────────────────────────────────────────────┘

                         ╱╲
                        ╱  ╲
                       ╱ E2E╲                5 tests
                      ╱──────╲              ~5% coverage
                     ╱        ╲
                    ╱Integration╲            25 tests
                   ╱────────────╲          ~30% coverage
                  ╱              ╲
                 ╱      Unit      ╱         65 tests
                ╱────────────────╱         ~65% coverage
```

### .NET Backend Tests

```
AiTradingRace.Tests/
├── Unit/
│   ├── PortfolioServiceTests.cs (18 tests)
│   │   ✓ ApplyBuyTrade_UpdatesCashAndPosition
│   │   ✓ ApplySellTrade_CalculatesRealizedPnL
│   │   ✓ ApplySellTrade_ClosesPositionWhenFullySold
│   │   ✓ GetAvailableMargin_ReturnsCorrectValue
│   │   ✓ InsufficientCash_ThrowsException
│   │
│   ├── EquityServiceTests.cs (12 tests)
│   │   ✓ CaptureSnapshot_CalculatesTotalValueCorrectly
│   │   ✓ CalculatePerformanceMetrics_ReturnsValidSharpeRatio
│   │   ✓ CalculateMaxDrawdown_FindsLargestDecline
│   │   ✓ CalculateWinRate_IncludesOnlySellTrades
│   │
│   ├── RiskValidatorTests.cs (15 tests)
│   │   ✓ ValidateDecision_RejectsOrderExceedingMaxPositionSize
│   │   ✓ ValidateDecision_RejectsOrderExceedingMaxOrderSize
│   │   ✓ ValidateDecision_RejectsMoreThanMaxOrdersPerRun
│   │   ✓ ValidateDecision_AdjustsQuantityToComplyWithLimits
│   │   ✓ ValidateDecision_RejectsShortSelling
│   │
│   ├── AgentRunnerTests.cs (10 tests)
│   │   ✓ RunAsync_BuildsContextCorrectly
│   │   ✓ RunAsync_CallsCorrectModelClient
│   │   ✓ RunAsync_ValidatesRiskConstraints
│   │   ✓ RunAsync_ExecutesTradesInOrder
│   │   ✓ RunAsync_CapturesEquitySnapshot
│   │
│   └── CoinGeckoClientTests.cs (10 tests)
│       ✓ GetHistoricalOhlc_ReturnsParsedCandles
│       ✓ GetHistoricalOhlc_HandlesRateLimiting
│       ✓ GetHistoricalOhlc_RetriesOnTransientFailure
│
├── Integration/
│   ├── MarketDataIntegrationTests.cs (8 tests)
│   │   ✓ IngestCandles_PreventseDuplicates
│   │   ✓ IngestCandles_UpdatesDatabase
│   │   ✓ GetRecentCandles_ReturnsCorrectTimeRange
│   │
│   ├── PortfolioIntegrationTests.cs (10 tests)
│   │   ✓ FullTradeFlow_BuyThenSell_CalculatesPnL
│   │   ✓ ConcurrentTrades_MaintainDataIntegrity
│   │   ✓ PositionUpdate_TriggersEquityRecalculation
│   │
│   └── DatabaseTests.cs (7 tests)
│       ✓ Migrations_ApplySuccessfully
│       ✓ UniqueConstraints_PreventDuplicates
│       ✓ ForeignKeys_CascadeDeletes
│
└── E2E/
    ├── AgentExecutionE2ETests.cs (3 tests)
    │   ✓ FullPipeline_MarketDataToTrade_Succeeds
    │   ✓ MultipleAgents_ExecuteConcurrently
    │
    └── ApiE2ETests.cs (2 tests)
        ✓ DashboardFlow_LoadsLeaderboard
        ✓ AgentDetailFlow_RunsAgentAndRefreshes

Total: 65 tests
Execution Time: ~15 seconds
```

### Python ML Service Tests

```
ai-trading-race-ml/tests/
├── test_features.py (4 tests)
│   ✓ test_engineer_features_returns_dataframe
│   ✓ test_engineer_features_has_all_columns
│   ✓ test_engineer_features_drops_na
│   ✓ test_get_feature_values_returns_dict
│
├── test_predictor.py (5 tests)
│   ✓ test_predictor_without_model
│   ✓ test_predict_returns_result
│   ✓ test_predict_generates_signals
│   ✓ test_predict_with_model_loaded
│   ✓ test_fallback_rule_based_logic
│
├── test_decision_service.py (2 tests)
│   ✓ test_generate_decision_creates_orders
│   ✓ test_generate_decision_respects_portfolio_state
│
└── test_api.py (1 test)
    ✓ test_predict_endpoint_requires_api_key
    ✓ test_predict_endpoint_validates_schema
    ✓ test_predict_endpoint_returns_valid_response

Total: 12 tests
Execution Time: ~3 seconds
```

**Run Commands:**
```bash
# .NET tests
dotnet test AiTradingRace.Tests --logger "console;verbosity=detailed"

# Python tests
cd ai-trading-race-ml
pytest -v --cov=app --cov-report=html

# Coverage report
dotnet test /p:CollectCoverage=true /p:CoverageReportFormat=cobertura
```

---

## 🚀 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AZURE PRODUCTION DEPLOYMENT                      │
└─────────────────────────────────────────────────────────────────────┘

                          ┌─────────────────┐
                          │  Azure Front    │
                          │  Door (CDN)     │
                          └────────┬────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │                             │
         ┌──────────▼─────────┐        ┌─────────▼──────────┐
         │  Static Web Apps   │        │  App Service       │
         │  (React Frontend)  │        │  (.NET Backend)    │
         │  • Auto-deploy     │        │  • Linux B1        │
         │  • GitHub Actions  │        │  • Auto-scale      │
         └────────────────────┘        └─────────┬──────────┘
                                                  │
                                                  │
                          ┌───────────────────────┼───────────────────┐
                          │                       │                   │
               ┌──────────▼─────────┐  ┌─────────▼──────────┐  ┌─────▼──────┐
               │  Azure Functions   │  │  Container Instance│  │  Azure SQL │
               │  • Market Ingestion│  │  (Python ML)       │  │  Database  │
               │  • Agent Scheduler │  │  • FastAPI         │  │  • S1      │
               │  • Consumption Plan│  │  • 1 vCPU, 2GB     │  │  • 50GB    │
               └────────────────────┘  └────────────────────┘  └────────────┘
                          │                       │
                          └───────────┬───────────┘
                                      │
                          ┌───────────▼────────────┐
                          │  Azure Key Vault       │
                          │  • OpenAI API keys     │
                          │  • SQL conn strings    │
                          │  • ML service API key  │
                          └────────────────────────┘
                                      │
                          ┌───────────▼────────────┐
                          │  Application Insights  │
                          │  • Distributed tracing │
                          │  • Log aggregation     │
                          │  • Performance metrics │
                          └────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ CI/CD Pipeline (GitHub Actions)                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ On Push to main:                                                    │
│   1. Run tests (.NET + Python)                                      │
│   2. Build Docker images                                            │
│   3. Push to Azure Container Registry                               │
│   4. Deploy to staging environment                                  │
│   5. Run smoke tests                                                │
│   6. Deploy to production (manual approval)                         │
│   7. Post-deployment health checks                                  │
└─────────────────────────────────────────────────────────────────────┘

Estimated Monthly Cost: ~$150-200
  - App Service B1: $55
  - Azure SQL S1: $30
  - Container Instance: $30
  - Static Web Apps: $9
  - Functions: <$1 (free tier)
  - Application Insights: ~$25 (5GB ingestion)
  - Key Vault: <$1
  - Front Door: ~$40
```

---

### Current Development Environment

```
┌──────────────────────────────────────────────────────────────────────┐
│                    LOCAL DEVELOPMENT STACK                           │
└──────────────────────────────────────────────────────────────────────┘

Running Services:
├─ SQL Server 2022
│  └─ Status: Healthy
│  └─ Port: 1433
│  └─ Database: AiTradingRace (initialized with schema and test data)
│
├─ Redis 7
│  └─ Status: Healthy
│  └─ Port: 6379
│  └─ Purpose: ML prediction caching (idempotency)
│
└─ ML Service (FastAPI)
   └─ Status: Healthy
   └─ Port: 8000
   └─ API Key: Configured
   └─ Model: Rule-based (RandomForest training pending)

Quick Start:
1. docker compose up -d              # Start all services
2. ./scripts/setup-database.sh       # Initialize database
3. ./scripts/seed-database.sh        # Populate test data
4. dotnet run --project AiTradingRace.Web  # Start backend API
5. cd ai-trading-race-web && npm run dev   # Start frontend

Documentation:
• DATABASE.md: Database schema and migrations
• DEPLOYMENT_LOCAL.md: Complete setup guide
• TEST_RESULTS.md: Testing validation details
• README.md: Project overview and quick start
```

---

## 🔮 Future Enhancements

### Phase 10: GraphRAG-lite (Explainable AI)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GRAPHRAG-LITE ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Knowledge Graph Structure                                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Nodes:                                                              │
│   • Rule Nodes: {id: "R001", name: "RSI_Oversold", threshold: 30}   │
│   • Regime Nodes: {id: "M001", name: "Bull_Market", indicators: []}│
│   • Indicator Nodes: {id: "I001", name: "RSI_14", formula: "..."}   │
│                                                                     │
│ Edges:                                                              │
│   • APPLIES_IN: Rule → Regime (when rule is valid)                  │
│   • USES: Rule → Indicator (which data rule consumes)               │
│   • CONFLICTS_WITH: Rule ↔ Rule (mutually exclusive)                │
│                                                                     │
│ Storage: Neo4j or Azure Cosmos DB (Gremlin API)                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Decision Flow with Citations                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ 1. Agent receives market context                                    │
│ 2. Query graph for applicable rules in current regime               │
│ 3. LLM prompt includes rule IDs and descriptions                    │
│ 4. LLM response MUST cite rule IDs: "Applied [R001, R042]"          │
│ 5. Validate citations (rules exist and are applicable)              │
│ 6. Store decision with rule graph snapshot                          │
│                                                                     │
│ Benefits:                                                           │
│   • Full traceability: decision → rules → indicators → data         │
│   • Conflict detection: identify contradictory rules                │
│   • Rule evolution: track rule performance over time                │
│   • Regulatory compliance: explain any historical decision          │
└─────────────────────────────────────────────────────────────────────┘
```

### Phase 11: Advanced Observability

```
┌─────────────────────────────────────────────────────────────────────┐
│              OPENTELEMETRY DISTRIBUTED TRACING                      │
└─────────────────────────────────────────────────────────────────────┘

Trace Example:

Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Span Hierarchy:

├─ AgentRunner.RunAsync (120ms)
│  ├─ AgentContextBuilder.BuildAsync (25ms)
│  │  ├─ DbContext.Agents.FindAsync (5ms)
│  │  ├─ DbContext.Portfolios.FindAsync (4ms)
│  │  └─ DbContext.MarketCandles.GetRecent (16ms)
│  │
│  ├─ AzureOpenAiClient.GenerateDecision (850ms)  ← Bottleneck!
│  │  └─ HTTP POST https://api.openai.azure.com (845ms)
│  │
│  ├─ RiskValidator.Validate (8ms)
│  │
│  ├─ PortfolioService.ApplyTrades (45ms)
│  │  ├─ DbContext.Positions.Update (12ms)
│  │  ├─ DbContext.Trades.Add (8ms)
│  │  └─ DbContext.SaveChangesAsync (25ms)
│  │
│  └─ EquityService.CaptureSnapshot (12ms)

Total Duration: 970ms
Status: Success

Metrics Exported:
  • agent.execution.duration (histogram)
  • agent.trades.count (counter)
  • llm.response.time (histogram)
  • db.query.duration (histogram)
```

---

## 📋 Quick Reference

### API Endpoints

```
Backend API (localhost:5000)
├─ GET  /api/agents                    - List all agents
├─ GET  /api/agents/{id}               - Get agent details
├─ POST /api/agents/{id}/run           - [TESTING ONLY] Execute single agent
├─ GET  /api/portfolios/{id}           - Get portfolio state
├─ GET  /api/trades?agentId={id}       - Get trade history
├─ GET  /api/equity/{id}/history       - Get equity curve
├─ GET  /api/equity/{id}/performance   - Get performance metrics
├─ GET  /api/leaderboard               - Get rankings
├─ GET  /api/market/prices             - Get current prices
└─ POST /api/admin/ingest              - [TESTING ONLY] Manual data ingestion

ML Service (localhost:8000)
├─ POST /predict                       - Generate trading decision
├─ GET  /health                        - Health check
└─ GET  /version                       - Model version info

Azure Functions (Primary Automation)
├─ MarketDataFunction                  - CRON: 0 */15 * * * * (every 15 min)
└─ RunAgentsFunction                   - CRON: 0 */30 * * * * (every 30 min)
```

### Environment Variables

```bash
# .NET Backend
ConnectionStrings__DefaultConnection=Server=...;Database=AiTradingRace;...
AzureOpenAI__Endpoint=https://your-resource.openai.azure.com/
AzureOpenAI__ApiKey=sk_...
CustomML__BaseUrl=http://localhost:8000
CustomML__ApiKey=sk_ml_...

# Python ML Service
ML_SERVICE_API_KEY=sk_ml_prod_...
MODEL_PATH=models/trading_model.pkl
LOG_LEVEL=INFO
```

### Development Commands

```bash
# Docker Infrastructure
docker compose up -d                    # Start all services
docker compose logs -f [service]        # View logs
docker compose down                     # Stop all services
./scripts/setup-database.sh             # Initialize database
./scripts/seed-database.sh              # Populate test data

# Azure Functions (Primary Method)
cd AiTradingRace.Functions
func start                              # Start timer triggers locally
# This automatically runs:
# - Market data ingestion every 15 minutes
# - Agent execution every 30 minutes

# Backend API (runs alongside Functions)
cd AiTradingRace.Web
dotnet run

# Frontend
cd ai-trading-race-web
npm run dev

# ML Service (if running outside Docker)
cd ai-trading-race-ml
uvicorn app.main:app --reload

# Testing/Debugging Only (manual triggers)
curl -X POST http://localhost:5000/api/admin/ingest      # Manual data ingest
curl -X POST http://localhost:5000/api/agents/{id}/run   # Manual agent run

# Run all tests
dotnet test && cd ai-trading-race-ml && pytest
```

---

## 📚 Key Takeaways

1. **Clean Architecture**: Separation of concerns enables independent testing and deployment of each layer
2. **Polyglot Microservices**: .NET for business logic, Python for ML, React for UI - best tool for each job
3. **Docker-First Development**: Containerized infrastructure ensures consistency across environments
4. **AI Flexibility**: Support multiple AI providers (Groq/Llama, Azure OpenAI, Custom ML) through factory pattern
5. **Production-Ready Infrastructure**: Docker Compose, health checks, idempotency, automated scripts
6. **Risk Management**: Server-side constraints prevent rogue AI decisions
7. **Explainability**: Transparent signal generation for debugging and compliance
8. **Cost Optimization**: Local development with Docker, Azure deployment deferred until production
9. **Comprehensive Testing**: 33/33 integration tests validate complete pipeline
10. **Documentation Excellence**: 574-line database guide, 926-line deployment guide, architecture report
11. **Horizontal Scalability (Phase 9)**: RabbitMQ message queue enables 3-5x performance improvement and unlimited agent scaling

### Phase 8 Achievements

```
✅ Local Development Infrastructure Complete
   • Docker Compose orchestration (SQL Server, Redis, ML Service)
   • Automated database initialization and seeding
   • 5 pre-configured test agents with diverse strategies
   • Health monitoring for all services
   
✅ CI/CD Pipeline Established
   • 7 GitHub Actions workflows
   • Automated testing on every commit
   • Cross-service integration validation
   
✅ Integration Testing Validated
   • 33/33 tests passed
   • Infrastructure, database, and service layers verified
   • 4 critical issues identified and resolved
   
✅ Comprehensive Documentation
   • DATABASE.md (574 lines)
   • DEPLOYMENT_LOCAL.md (926 lines)
   • PROJECT_ARCHITECTURE_REPORT.md (2000+ lines)
   • TEST_RESULTS.md with integration evidence

⏸️ Azure Deployment Ready
   • Workflows configured, pending activation
   • Cost-optimized approach: local development first
   • Production deployment deferred to final phase
```

### Phase 9 Roadmap (Planned)

```
📋 Distributed Architecture with RabbitMQ
   • Transform sequential → parallel agent execution
   • 3-5x performance improvement (50s → 10-15s for 5 agents)
   • Horizontal scalability (add workers to scale)
   • Fault tolerance (isolated failures, auto-retry)
   • Idempotency with Redis (no duplicate executions)
   • Dead Letter Queue (capture persistent failures)
   • RabbitMQ Management UI (real-time observability)
   
🎯 Benefits:
   ✅ Cost: $0/month (RabbitMQ is open source)
   ✅ Resume value: Industry-standard message queue technology
   ✅ Engineering maturity: Right tool for the job (task distribution)
   ✅ Interview talking point: Distributed systems knowledge
   
⏱️ Timeline: 1 week sprint (7 days)
   • Sprint 9.1-9.7 (see detailed plan above)
   • Low risk: Feature flag allows rollback to sequential mode
```

---

**Document Version**: 2.1  
**Last Updated**: January 22, 2026  
**Status**: Phase 8 Complete - Phase 9 Planned (RabbitMQ Distributed Architecture)  
**Author**: AI Trading Race Team  
**License**: MIT

