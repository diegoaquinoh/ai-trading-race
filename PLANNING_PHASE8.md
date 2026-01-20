# Phase 8 — Azure Deployment & Production Configuration

**Objective:** Deploy the AI Trading Race application to Azure with production-grade reliability, security, and CI/CD automation.

## 📋 Current State — 🚧 IN PROGRESS

> **Prerequisites:** Phase 7 completed ✅ (React Dashboard with live data integration)

> **LLM Provider:** Llama API (free tier) via Meta's Llama Cloud or compatible services (Groq, Together.ai, Replicate)

> **Date:** 19/01/2026

> ⚠️ **IMPORTANT NOTE**: Azure deployment (Sprints 8.2, 8.3, 8.5, 8.6) is **temporarily skipped** due to cost constraints. We've completed Sprint 8.1 (Llama Integration) and Sprint 8.4 (GitHub Actions CI/CD). Azure provisioning and deployment will be addressed in a future phase when budget allows.

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           AZURE CLOUD                                                  │
├───────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                        │
│   ┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐       │
│   │    Azure App Service    │      │    Azure Functions      │      │  Azure Static Web Apps  │       │
│   │    (AiTradingRace.Web)  │      │    (Consumption Plan)   │      │    (React Frontend)     │       │
│   │                         │      │                         │      │                         │       │
│   │  • REST API             │      │  • MarketDataFunction   │      │  • Dashboard            │       │
│   │  • Health endpoints     │      │  • RunAgentsFunction    │      │  • Leaderboard          │       │
│   │  • CORS configured      │      │  • EquitySnapshotFunc   │      │  • Agent Detail         │       │
│   │  • Managed Identity     │      │  • HealthCheckFunction  │      │  • Live updates         │       │
│   └───────────┬─────────────┘      └───────────┬─────────────┘      └───────────┬─────────────┘       │
│               │                                │                                │                      │
│               └────────────────────────────────┼────────────────────────────────┘                      │
│                                                │                                                       │
│                                                ▼                                                       │
│                            ┌─────────────────────────────────────┐                                     │
│                            │        Azure SQL Database           │                                     │
│                            │   • MarketCandles, Agents, Trades   │                                     │
│                            │   • EquitySnapshots, Portfolios     │                                     │
│                            │   • Connection pooling enabled      │                                     │
│                            │   • Geo-redundant backups           │                                     │
│                            └─────────────────────────────────────┘                                     │
│                                                │                                                       │
│   ┌─────────────────────────┐                  │                  ┌─────────────────────────┐          │
│   │    Azure Key Vault      │◄─────────────────┼─────────────────►│   Azure Cache for Redis │          │
│   │                         │                  │                  │                         │          │
│   │  • ConnectionStrings    │                  │                  │  • ML Idempotency cache │          │
│   │  • Llama API Key        │                  │                  │  • Response dedup (1h)  │          │
│   │  • CoinGecko API Key    │                  │                  │  • Session cache        │          │
│   │  • ML Service secrets   │                  │                  │                         │          │
│   └─────────────────────────┘                  │                  └─────────────────────────┘          │
│                                                │                                                       │
│   ┌─────────────────────────┐      ┌───────────┴───────────┐      ┌─────────────────────────┐          │
│   │  Azure Container Apps   │      │   Application         │      │   Azure Monitor         │          │
│   │  (Python ML Service)    │      │   Insights            │      │   (Alerts & Dashboards) │          │
│   │                         │      │                       │      │                         │          │
│   │  • FastAPI + PyTorch    │      │  • Request tracing    │      │  • Error rate alerts    │          │
│   │  • Custom ML models     │      │  • Exception logging  │      │  • Latency alerts       │          │
│   │  • Health probes        │      │  • Dependency tracking│      │  • Resource metrics     │          │
│   └─────────────────────────┘      └───────────────────────┘      └─────────────────────────┘          │
│                                                                                                        │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────┐          │
│   │                              EXTERNAL SERVICES                                           │          │
│   │                                                                                          │          │
│   │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐                     │          │
│   │   │   Llama API     │    │   CoinGecko     │    │   GitHub        │                     │          │
│   │   │   (Free Tier)   │    │   (Market Data) │    │   Actions       │                     │          │
│   │   │                 │    │                 │    │   (CI/CD)       │                     │          │
│   │   │ • Llama 3.3 70B │    │ • OHLC candles  │    │ • Build & test  │                     │          │
│   │   │ • Rate limited  │    │ • Price feeds   │    │ • Deploy        │                     │          │
│   │   └─────────────────┘    └─────────────────┘    └─────────────────┘                     │          │
│   └─────────────────────────────────────────────────────────────────────────────────────────┘          │
│                                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🦙 Llama API Integration

### Provider Options (Free Tier)

| Provider         | Model                   | Rate Limit (Free) | Endpoint                               |
| ---------------- | ----------------------- | ----------------- | -------------------------------------- |
| **Groq**         | Llama 3.3 70B Versatile | 14,400 req/day    | `https://api.groq.com/openai/v1`       |
| **Together.ai**  | Llama 3.1 70B Instruct  | 60 req/min        | `https://api.together.xyz/v1`          |
| **Replicate**    | Meta Llama 3.1          | Pay per use       | `https://api.replicate.com/v1`         |
| **Hugging Face** | Llama models            | Rate limited      | `https://api-inference.huggingface.co` |

> [!TIP]
> **Recommended:** Use **Groq** for the free tier — fastest inference, generous limits, OpenAI-compatible API.

### Code Changes Required

#### 1. Add new `ModelProvider` enum value

```csharp
// AiTradingRace.Domain/Entities/ModelProvider.cs
public enum ModelProvider
{
    AzureOpenAI,  // Legacy, will be deprecated
    OpenAI,
    Llama,        // NEW — Llama API via Groq/Together.ai
    CustomML,
    Mock
}
```

#### 2. Create `LlamaAgentModelClient`

```csharp
// AiTradingRace.Infrastructure/Agents/LlamaAgentModelClient.cs
public sealed class LlamaAgentModelClient : IAgentModelClient
{
    private readonly HttpClient _httpClient;
    private readonly LlamaOptions _options;
    private readonly ILogger<LlamaAgentModelClient> _logger;

    public async Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context, CancellationToken ct)
    {
        var request = new
        {
            model = _options.Model, // e.g., "llama-3.3-70b-versatile"
            messages = new[]
            {
                new { role = "system", content = BuildSystemPrompt() },
                new { role = "user", content = BuildUserPrompt(context) }
            },
            response_format = new { type = "json_object" },
            temperature = 0.3,
            max_tokens = 500
        };

        var response = await _httpClient.PostAsJsonAsync(
            "/chat/completions", request, ct);

        // Parse JSON response to AgentDecision
        return ParseDecision(await response.Content.ReadAsStringAsync(ct));
    }
}
```

#### 3. Update `AgentModelClientFactory`

```csharp
// AiTradingRace.Infrastructure/Agents/AgentModelClientFactory.cs
public IAgentModelClient GetClient(ModelProvider provider)
{
    return provider switch
    {
        ModelProvider.Llama => _serviceProvider.GetRequiredService<LlamaAgentModelClient>(),
        ModelProvider.AzureOpenAI => _serviceProvider.GetRequiredService<AzureOpenAiAgentModelClient>(),
        ModelProvider.CustomML => _serviceProvider.GetRequiredService<CustomMlAgentModelClient>(),
        ModelProvider.Mock => _serviceProvider.GetRequiredService<TestAgentModelClient>(),
        _ => throw new NotSupportedException($"Provider {provider} not supported")
    };
}
```

#### 4. Configuration

```json
// appsettings.json
{
  "Llama": {
    "Provider": "Groq",
    "BaseUrl": "https://api.groq.com/openai/v1",
    "Model": "llama-3.3-70b-versatile",
    "ApiKey": "<from-keyvault>",
    "TimeoutSeconds": 60,
    "MaxRetries": 3
  }
}
```

---

## Current State Audit

### What Already Exists ✅

| Component                   | Location                  | Status                            |
| --------------------------- | ------------------------- | --------------------------------- |
| .NET Web API                | `AiTradingRace.Web`       | ✅ Ready for deployment           |
| Azure Functions             | `AiTradingRace.Functions` | ✅ Timer triggers implemented     |
| React Frontend              | `ai-trading-race-web`     | ✅ Production build ready         |
| Python ML Service           | `ai-trading-race-ml`      | ✅ FastAPI with Docker support    |
| EF Core Migrations          | Infrastructure            | ✅ Initial migration ready        |
| IAgentModelClient interface | Application               | ✅ Ready for Llama implementation |
| AgentModelClientFactory     | Infrastructure            | ✅ Supports multiple providers    |

### What's Missing ❌

| Component                 | Description                          | Priority |
| ------------------------- | ------------------------------------ | -------- |
| **LlamaAgentModelClient** | New client for Llama API integration | P0       |
| Azure Resource Group      | Container for all resources          | P0       |
| Azure SQL Database        | Production database                  | P0       |
| Azure App Service         | Host for .NET Web API                | P0       |
| Azure Functions App       | Host for timer functions             | P0       |
| Azure Static Web Apps     | Host for React frontend              | P0       |
| Azure Key Vault           | Secure secrets storage               | P0       |
| Azure Container Apps      | Host for Python ML service           | P1       |
| Azure Cache for Redis     | Idempotency for ML service           | P1       |
| GitHub Actions workflows  | CI/CD pipelines                      | P0       |
| Retry policies (Polly)    | Resilient HTTP calls                 | P0       |
| Health check endpoints    | Readiness/liveness probes            | P0       |

---

## 🎯 Phase 8 Deliverables

### 1. Llama API Integration (Pre-deployment) ✅ COMPLETE

- [x] **1.1** Add `Llama` to `ModelProvider` enum
- [x] **1.2** Create `LlamaOptions` configuration class
- [x] **1.3** Implement `LlamaAgentModelClient` with OpenAI-compatible API
- [x] **1.4** Update `AgentModelClientFactory` to support Llama provider
- [x] **1.5** Register Llama services in DI (`AddInfrastructureServices()`)
- [x] **1.6** Add retry policy with Polly (exponential backoff)
- [x] **1.7** Add rate limiting handler for free tier compliance
- [x] **1.8** Write unit tests for `LlamaAgentModelClient`
- [x] **1.9** Update seed data to use `ModelProvider.Llama` as default

### 2. Azure Resource Provisioning

- [ ] **2.1** Create Azure Resource Group `rg-ai-trading-race-prod`
- [ ] **2.2** Create Azure SQL Database (Basic/S0 tier)
- [ ] **2.3** Create Azure App Service Plan (B1 Linux)
- [ ] **2.4** Create Azure App Service for `AiTradingRace.Web`
- [ ] **2.5** Create Azure Functions App (Consumption plan)
- [ ] **2.6** Create Azure Static Web Apps for React frontend
- [ ] **2.7** Create Azure Key Vault for secrets management
- [ ] **2.8** Create Azure Container Apps environment for Python ML service
- [ ] **2.9** Create Azure Cache for Redis (Basic C0)
- [ ] **2.10** Create Application Insights resource

### 3. Security & Secrets Configuration

- [ ] **3.1** Store SQL connection string in Key Vault
- [ ] **3.2** Store Llama API key in Key Vault (`Llama-ApiKey`)
- [ ] **3.3** Store CoinGecko API key in Key Vault
- [ ] **3.4** Store Python ML service API key in Key Vault
- [ ] **3.5** Configure App Service Managed Identity
- [ ] **3.6** Grant Managed Identity access to Key Vault (Get, List secrets)
- [ ] **3.7** Configure Functions App Managed Identity
- [ ] **3.8** Enable HTTPS-only on all endpoints
- [ ] **3.9** Configure CORS with explicit allowed origins

### 4. Database Migration Strategy

- [ ] **4.1** Generate SQL migration script (`dotnet ef migrations script`)
- [ ] **4.2** Review migration script for production safety
- [ ] **4.3** Apply initial migration to Azure SQL Database
- [ ] **4.4** Seed initial data (BTC, ETH assets; Llama-powered agents)
- [ ] **4.5** Verify database connectivity from all services
- [ ] **4.6** Configure connection resilience (retry on transient failures)

### 5. Resilience & Error Handling

- [ ] **5.1** Add Polly retry policies for HTTP clients (Llama, CoinGecko, ML service)
- [ ] **5.2** Configure circuit breaker for external API calls
- [ ] **5.3** Implement graceful degradation (fallback to HOLD if LLM fails)
- [ ] **5.4** Add structured logging with correlation IDs
- [ ] **5.5** Configure health checks for all dependencies
- [ ] **5.6** Set up Azure Monitor alerts for error rates > 5%
- [ ] **5.7** Document rollback procedures

### 6. GitHub Actions CI/CD

- [ ] **6.1** Create `.github/workflows/backend.yml` — Build, test, deploy .NET
- [ ] **6.2** Create `.github/workflows/functions.yml` — Deploy Azure Functions
- [ ] **6.3** Create `.github/workflows/frontend.yml` — Deploy to Static Web Apps
- [ ] **6.4** Create `.github/workflows/ml-service.yml` — Deploy to Container Apps
- [ ] **6.5** Configure GitHub secrets for Azure credentials
- [ ] **6.6** Add branch protection rules (require PR, passing tests)
- [ ] **6.7** Configure deployment slots for zero-downtime deploys
- [ ] **6.8** Add manual approval gate for production deployments

### 7. Python ML Service Deployment

- [ ] **7.1** Create production Dockerfile with multi-stage build
- [ ] **7.2** Create Azure Container Registry or use GitHub Container Registry
- [ ] **7.3** Push Docker image to registry
- [ ] **7.4** Deploy container to Azure Container Apps
- [ ] **7.5** Configure health probes (liveness, readiness)
- [ ] **7.6** Configure environment variables from Key Vault
- [ ] **7.7** Set up auto-scaling rules (min: 0, max: 3)

### 8. Redis Idempotency Implementation

- [ ] **8.1** Add `redis` dependency to Python ML service
- [ ] **8.2** Implement `Idempotency-Key` header handling
- [ ] **8.3** Cache `(idempotency_key -> response)` with 1h TTL
- [ ] **8.4** Update .NET `CustomMlAgentModelClient` to send idempotency keys
- [ ] **8.5** Test retry scenarios to verify deduplication
- [ ] **8.6** Add cache miss/hit metrics

### 9. Frontend Deployment

- [ ] **9.1** Configure `VITE_API_URL` for production backend
- [ ] **9.2** Update CORS settings in backend for production domain
- [ ] **9.3** Deploy to Azure Static Web Apps
- [ ] **9.4** Configure custom domain (optional)
- [ ] **9.5** Verify SPA routing and fallback to index.html
- [ ] **9.6** Test all pages load correctly

### 10. Post-Deployment Validation

- [ ] **10.1** Verify `/api/health` endpoint returns 200
- [ ] **10.2** Verify `/api/agents` returns agents with Llama provider
- [ ] **10.3** Trigger manual run of `MarketDataFunction`
- [ ] **10.4** Trigger manual run of `RunAgentsFunction`
- [ ] **10.5** Verify Llama API responds and generates valid decisions
- [ ] **10.6** Verify frontend displays live data
- [ ] **10.7** Run end-to-end flow: ingestion → Llama decision → trade → snapshot
- [ ] **10.8** Check Application Insights for telemetry
- [ ] **10.9** Verify all alerts are configured and functional
- [ ] **10.10** Document production URLs and access procedures

---

## 🛡️ Resilience Patterns

### Retry Policy with Polly

```csharp
// Configure in DI
services.AddHttpClient<LlamaAgentModelClient>()
    .AddPolicyHandler(GetRetryPolicy())
    .AddPolicyHandler(GetCircuitBreakerPolicy());

static IAsyncPolicy<HttpResponseMessage> GetRetryPolicy()
{
    return HttpPolicyExtensions
        .HandleTransientHttpError()
        .OrResult(r => r.StatusCode == HttpStatusCode.TooManyRequests)
        .WaitAndRetryAsync(
            retryCount: 3,
            sleepDurationProvider: attempt =>
                TimeSpan.FromSeconds(Math.Pow(2, attempt)), // 2s, 4s, 8s
            onRetry: (outcome, delay, attempt, context) =>
            {
                Log.Warning("Retry {Attempt} after {Delay}s: {Error}",
                    attempt, delay.TotalSeconds, outcome.Exception?.Message);
            });
}

static IAsyncPolicy<HttpResponseMessage> GetCircuitBreakerPolicy()
{
    return HttpPolicyExtensions
        .HandleTransientHttpError()
        .CircuitBreakerAsync(
            handledEventsAllowedBeforeBreaking: 5,
            durationOfBreak: TimeSpan.FromMinutes(1));
}
```

### Graceful Degradation

```csharp
// In AgentRunner.cs
public async Task<AgentRunResult> RunAgentOnceAsync(Guid agentId, CancellationToken ct)
{
    try
    {
        var decision = await _llmClient.GenerateDecisionAsync(context, ct);
        return ProcessDecision(decision);
    }
    catch (CircuitBreakerException ex)
    {
        _logger.LogWarning("LLM circuit breaker open, defaulting to HOLD");
        return AgentRunResult.Success("LLM unavailable - holding position");
    }
    catch (HttpRequestException ex) when (ex.StatusCode == HttpStatusCode.TooManyRequests)
    {
        _logger.LogWarning("Rate limited by LLM provider, skipping cycle");
        return AgentRunResult.RateLimited("Llama API rate limit reached");
    }
}
```

### Rate Limiting for Free Tier

```csharp
// RateLimitingHandler.cs
public class RateLimitingHandler : DelegatingHandler
{
    private static readonly SemaphoreSlim _semaphore = new(1, 1);
    private static DateTime _lastRequest = DateTime.MinValue;
    private readonly TimeSpan _minInterval = TimeSpan.FromSeconds(1); // 60 req/min

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken ct)
    {
        await _semaphore.WaitAsync(ct);
        try
        {
            var elapsed = DateTime.UtcNow - _lastRequest;
            if (elapsed < _minInterval)
            {
                await Task.Delay(_minInterval - elapsed, ct);
            }
            _lastRequest = DateTime.UtcNow;
            return await base.SendAsync(request, ct);
        }
        finally
        {
            _semaphore.Release();
        }
    }
}
```

---

## 📅 Execution Plan

### Sprint 8.1 — Llama Integration (0.5 day) ✅ COMPLETE

| #   | Task                              | Status |
| --- | --------------------------------- | ------ |
| 1.1 | Add `Llama` to ModelProvider enum | [x]    |
| 1.2 | Create `LlamaOptions` config      | [x]    |
| 1.3 | Implement `LlamaAgentModelClient` | [x]    |
| 1.4 | Update AgentModelClientFactory    | [x]    |
| 1.5 | Register in DI                    | [x]    |
| 1.6 | Add Polly retry policies          | [x]    |
| 1.7 | Add rate limiting handler         | [x]    |
| 1.8 | Write unit tests                  | [x]    |

### Sprint 8.2 — Azure Resource Provisioning (1 day)

| #    | Task                         | Status |
| ---- | ---------------------------- | ------ |
| 2.1  | Create Resource Group        | [ ]    |
| 2.2  | Create Azure SQL Database    | [ ]    |
| 2.3  | Create App Service Plan      | [ ]    |
| 2.4  | Create App Service (Web API) | [ ]    |
| 2.5  | Create Azure Functions App   | [ ]    |
| 2.7  | Create Key Vault             | [ ]    |
| 2.10 | Create Application Insights  | [ ]    |

### Sprint 8.3 — Security & Database (0.5 day)

| #   | Task                          | Status |
| --- | ----------------------------- | ------ |
| 3.1 | Store connection string in KV | [ ]    |
| 3.2 | Store Llama API key in KV     | [ ]    |
| 3.5 | Configure Managed Identities  | [ ]    |
| 4.1 | Generate SQL migration script | [ ]    |
| 4.3 | Apply migrations to Azure SQL | [ ]    |
| 4.4 | Seed initial data             | [ ]    |

### Sprint 8.4 — GitHub Actions CI/CD (1 day) ✅ COMPLETE

| #   | Task                             | Status |
| --- | -------------------------------- | ------ |
| 6.1 | Create backend workflow          | [x]    |
| 6.2 | Create functions workflow        | [x]    |
| 6.3 | Create frontend workflow         | [x]    |
| 6.4 | Create ml-service workflow       | [x]    |
| 6.5 | Create pr-checks workflow        | [x]    |
| 6.6 | Create ci.yml (full pipeline)    | [x]    |
| 6.7 | Create CODEOWNERS file           | [x]    |
| 6.8 | Create PR template               | [x]    |
| 6.9 | Create issue templates           | [x]    |
| 6.10| Document CI/CD setup             | [x]    |

### Sprint 8.5 — ML Service & Redis (1 day) ✅ COMPLETE (Local/Docker)

| #   | Task                                          | Status |
| --- | --------------------------------------------- | ------ |
| 7.1 | Create production Dockerfile (multi-stage)    | [x]    |
| 7.2 | Create docker-compose.yml with Redis         | [x]    |
| 7.3 | Configure ML service environment variables    | [x]    |
| 7.4 | Create .env.example template                  | [x]    |
| 8.1 | Add redis dependency to requirements.txt      | [x]    |
| 8.2 | Create CacheService for Redis integration     | [x]    |
| 8.3 | Implement IdempotencyMiddleware               | [x]    |
| 8.4 | Update main.py to use idempotency middleware  | [x]    |
| 8.5 | Update .NET client to send Idempotency-Key    | [x]    |
| 8.6 | Write cache service tests                     | [x]    |
| 8.7 | Create comprehensive deployment documentation | [x]    |

> **Note**: Azure Container Apps and Azure Cache for Redis deployment deferred until Azure budget available. Local Docker Compose deployment fully functional.

### Sprint 8.6 — Frontend & Validation (0.5 day)

| #    | Task                         | Status |
| ---- | ---------------------------- | ------ |
| 2.6  | Create Static Web Apps       | [ ]    |
| 9.1  | Configure production API URL | [ ]    |
| 9.2  | Update CORS settings         | [ ]    |
| 9.3  | Deploy frontend              | [ ]    |
| 10.x | Run all validation checks    | [ ]    |

---

## 🔐 Key Configuration

### Azure App Settings

```json
{
  "ConnectionStrings__TradingDb": "@Microsoft.KeyVault(VaultName=kv-ai-trading;SecretName=ConnectionString-TradingDb)",

  "Llama__Provider": "Groq",
  "Llama__BaseUrl": "https://api.groq.com/openai/v1",
  "Llama__Model": "llama-3.3-70b-versatile",
  "Llama__ApiKey": "@Microsoft.KeyVault(VaultName=kv-ai-trading;SecretName=Llama-ApiKey)",
  "Llama__TimeoutSeconds": "60",
  "Llama__MaxRetries": "3",

  "CoinGecko__ApiKey": "@Microsoft.KeyVault(VaultName=kv-ai-trading;SecretName=CoinGecko-ApiKey)",

  "CustomMlAgent__BaseUrl": "https://ml-service.azurecontainerapps.io",
  "CustomMlAgent__ApiKey": "@Microsoft.KeyVault(VaultName=kv-ai-trading;SecretName=MlService-ApiKey)",

  "Redis__ConnectionString": "@Microsoft.KeyVault(VaultName=kv-ai-trading;SecretName=Redis-ConnectionString)"
}
```

### GitHub Secrets Required

| Secret Name                         | Description                     |
| ----------------------------------- | ------------------------------- |
| `AZURE_CREDENTIALS`                 | Service principal JSON          |
| `AZURE_SUBSCRIPTION_ID`             | Azure subscription              |
| `AZURE_WEBAPP_PUBLISH_PROFILE`      | Publish profile for App Service |
| `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` | Publish profile for Functions   |
| `AZURE_STATIC_WEB_APPS_TOKEN`       | Deployment token for SWA        |
| `REGISTRY_USERNAME`                 | Container registry username     |
| `REGISTRY_PASSWORD`                 | Container registry password     |
| `LLAMA_API_KEY`                     | Llama API key (for CI tests)    |

---

## 🚀 Deployment Commands

```bash
# ============================================
# 1. Login & Setup
# ============================================
az login
az account set --subscription "<subscription-id>"

RESOURCE_GROUP="rg-ai-trading-race-prod"
LOCATION="westeurope"

# ============================================
# 2. Create Resource Group
# ============================================
az group create --name $RESOURCE_GROUP --location $LOCATION

# ============================================
# 3. Create SQL Server & Database
# ============================================
az sql server create \
  --name sql-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --admin-user sqladmin \
  --admin-password "$(openssl rand -base64 24)"

az sql db create \
  --name AiTradingRace \
  --resource-group $RESOURCE_GROUP \
  --server sql-ai-trading-race \
  --service-objective Basic

# Allow Azure services
az sql server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --server sql-ai-trading-race \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# ============================================
# 4. Create Key Vault
# ============================================
az keyvault create \
  --name kv-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --enable-rbac-authorization true

# Store Llama API key
az keyvault secret set \
  --vault-name kv-ai-trading-race \
  --name "Llama-ApiKey" \
  --value "<your-groq-api-key>"

# ============================================
# 5. Create App Service
# ============================================
az appservice plan create \
  --name plan-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --sku B1 \
  --is-linux

az webapp create \
  --name app-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --plan plan-ai-trading-race \
  --runtime "DOTNETCORE:8.0"

# Enable Managed Identity
az webapp identity assign \
  --name app-ai-trading-race \
  --resource-group $RESOURCE_GROUP

# ============================================
# 6. Create Function App
# ============================================
az storage account create \
  --name staitradingrace \
  --resource-group $RESOURCE_GROUP \
  --sku Standard_LRS

az functionapp create \
  --name func-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --storage-account staitradingrace \
  --consumption-plan-location $LOCATION \
  --runtime dotnet-isolated \
  --runtime-version 8 \
  --functions-version 4

# ============================================
# 7. Create Static Web App (React)
# ============================================
az staticwebapp create \
  --name swa-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# ============================================
# 8. Create Redis Cache
# ============================================
az redis create \
  --name redis-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Basic \
  --vm-size C0

# ============================================
# 9. Create Application Insights
# ============================================
az monitor app-insights component create \
  --app ai-trading-race-insights \
  --location $LOCATION \
  --resource-group $RESOURCE_GROUP \
  --application-type web
```

---

## ✅ Exit Criteria

| Criterion                                          | Validated |
| -------------------------------------------------- | --------- |
| `LlamaAgentModelClient` implemented and tested     | [x]       |
| All Azure resources created and accessible         | [ ]       |
| Secrets stored in Key Vault                        | [ ]       |
| Managed Identities configured for Key Vault access | [ ]       |
| Database migrations applied successfully           | [ ]       |
| GitHub Actions deploy on push to main              | [ ]       |
| React frontend accessible via public URL           | [ ]       |
| Python ML service deployed with idempotency        | [ ]       |
| Llama API generates valid trading decisions        | [ ]       |
| Health check endpoint returns 200                  | [ ]       |
| End-to-end flow works in production                | [ ]       |
| Error alerts configured in Azure Monitor           | [ ]       |

---

## 💰 Estimated Azure Costs (Monthly)

| Resource             | SKU / Tier    | Estimated Cost  |
| -------------------- | ------------- | --------------- |
| Azure SQL Database   | Basic (5 DTU) | ~$5             |
| App Service          | B1 (Basic)    | ~$13            |
| Azure Functions      | Consumption   | ~$0 (free tier) |
| Static Web Apps      | Free          | $0              |
| Key Vault            | Standard      | ~$0.03/secret   |
| Container Apps       | Consumption   | ~$5-10          |
| Redis Cache          | Basic C0      | ~$16            |
| Application Insights | Pay-as-you-go | ~$2-5           |
| **Llama API (Groq)** | **Free tier** | **$0**          |
| **Total**            |               | **~$45-55/mo**  |

> [!TIP]
> The Llama API via Groq is **completely free** with generous rate limits (14,400 requests/day). This significantly reduces costs compared to Azure OpenAI or OpenAI.

---

## 🔄 Rollback Procedures

### Application Rollback

```bash
# List recent deployments
az webapp deployment list --name app-ai-trading-race --resource-group $RESOURCE_GROUP

# Rollback to previous deployment
az webapp deployment slot swap \
  --name app-ai-trading-race \
  --resource-group $RESOURCE_GROUP \
  --slot staging \
  --target-slot production
```

### Database Rollback

```bash
# Point-in-time restore (up to 7 days for Basic tier)
az sql db restore \
  --dest-name AiTradingRace-Restored \
  --resource-group $RESOURCE_GROUP \
  --server sql-ai-trading-race \
  --name AiTradingRace \
  --time "2026-01-19T12:00:00Z"
```

---

## 📊 Monitoring & Alerts

### Recommended Alerts

| Alert Name           | Condition                         | Severity |
| -------------------- | --------------------------------- | -------- |
| High Error Rate      | Exceptions > 10 in 5 minutes      | Critical |
| LLM Response Failure | Llama API errors > 5 in 5 minutes | High     |
| Database Connection  | SQL connection failures > 3       | Critical |
| Function Failures    | Function execution failures > 3   | High     |
| High Latency         | P95 response time > 5s            | Warning  |

---

## 🔗 Dependencies

- **Phase 7** (React Dashboard): ✅ Completed
- **Phase 6** (Azure Functions): ✅ Completed
- **Phase 5/5b** (Agents): ✅ Completed

---

## 📚 Related Documents

- [PLANNING_GLOBAL.md](file:///Users/diegoaquino/Projets/ai-trading-race/PLANNING_GLOBAL.md) — Overall project phases
- [PLANNING_PHASE7.md](file:///Users/diegoaquino/Projets/ai-trading-race/PLANNING_PHASE7.md) — React Dashboard
- [PLANNING_PHASE6.md](file:///Users/diegoaquino/Projets/ai-trading-race/PLANNING_PHASE6.md) — Azure Functions
- [RECAP.md](file:///Users/diegoaquino/Projets/ai-trading-race/RECAP.md) — Completed milestones

---

## Notes

- **Llama API via Groq is OpenAI-compatible** — minimal code changes required
- Frontend uses `VITE_API_URL` environment variable for API endpoint
- Consider Azure Front Door for CDN + WAF in future phases
- Application Insights deep integration deferred to Phase 9
- Start with free/basic tiers, scale based on usage patterns
