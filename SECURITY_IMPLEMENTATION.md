# Security Implementation Plan

## Document Information

| Field | Value |
|-------|-------|
| **Version** | 2.0 |
| **Created** | February 3, 2026 |
| **Updated** | February 4, 2026 |
| **Status** | Phases 1-5 Implemented, Final Verification Pending |
| **Priority** | Critical |
| **Estimated Cost** | $0 (uses free Azure features) |

---

## 1. Executive Summary

This document provides a practical security implementation plan for the AI Trading Race platform. The approach prioritizes:

- **Zero additional cost** using native Azure security features
- **Defense in depth** at each service layer
- **Minimal complexity** appropriate for a demo/competition platform

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            INTERNET                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: STATIC WEB APP (Public)                                        │
│  ═══════════════════════════════════════════════════════════════════════│
│                                                                          │
│  ┌────────────────────────────────────┐                                  │
│  │  React UI (Azure Static Web Apps)  │  ◄── Only public entry point    │
│  │  • Free tier                       │                                  │
│  │  • Built-in HTTPS                  │                                  │
│  │  • Global CDN                      │                                  │
│  └────────────────────────────────────┘                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                    HTTPS with JWT Bearer Token
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: ASP.NET WEB API (Protected)                                    │
│  ═══════════════════════════════════════════════════════════════════════│
│                                                                          │
│  ┌────────────────────────────────────┐                                  │
│  │  ASP.NET Core Web API              │                                  │
│  │  • JWT Authentication              │                                  │
│  │  • Role-based Authorization        │                                  │
│  │  • Rate Limiting                   │                                  │
│  │  • CORS (specific origins)         │                                  │
│  │  • IP Restrictions (optional)      │                                  │
│  └────────────────────────────────────┘                                  │
│                                                                          │
│  Public Endpoints:          Protected Endpoints:                         │
│   GET /api/leaderboard       POST /api/agents/{id}/run      [Operator]  │
│   GET /api/agents            POST /api/agents/{id}/trades   [Operator]  │
│   GET /api/market/*          POST /api/admin/*              [Admin]     │
│   GET /api/health                                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                    Internal calls with API Key
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
              ▼                                         ▼
┌──────────────────────────────┐    ┌──────────────────────────────────────┐
│  LAYER 3A: AZURE FUNCTIONS   │    │  LAYER 3B: ML SERVICE                │
│  ════════════════════════════│    │  ════════════════════════════════════│
│                              │    │                                      │
│  • AuthorizationLevel.Function│    │  • API Key Authentication           │
│  • IP Restrictions           │    │  • Internal ingress only            │
│  • VNet Integration (opt.)   │    │  • Restricted CORS                  │
│                              │    │                                      │
└──────────────────────────────┘    └──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 4: DATABASE                                                       │
│  ═══════════════════════════════════════════════════════════════════════│
│                                                                          │
│  ┌────────────────────────────────────┐                                  │
│  │  Azure SQL / SQL Server            │                                  │
│  │  • Firewall rules                  │                                  │
│  │  • Encrypted connections           │                                  │
│  │  • Managed Identity (recommended)  │                                  │
│  └────────────────────────────────────┘                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Current Vulnerabilities (Audit Results)

### 2.1 Critical Issues

| ID | Component | Vulnerability | Location | Status |
|----|-----------|--------------|----------|--------|
| V1 | Azure Functions | `AuthorizationLevel.Anonymous` on sensitive endpoints | `RunAgentsFunction.cs:40`, `MarketCycleOrchestrator.cs:170` | ✅ Fixed (Phase 1) |
| V2 | ASP.NET API | Missing `[Authorize]` on POST `/api/agents/{id}/portfolio/trades` | `PortfolioController.cs:51` | ✅ Fixed (Phase 1) |
| V3 | ASP.NET API | Missing `[Authorize]` on POST `/api/agents/{id}/equity/snapshot` | `EquityController.cs:72` | ✅ Fixed (Phase 1) |
| V4 | ML Service | API key bypass when not configured | `middleware/auth.py:21-23` | ✅ Fixed (Phase 1) |
| V5 | ML Service | CORS allows all origins (`*`) | `config.py:21` | ✅ Fixed (Phase 1) |
| V6 | Configuration | Hardcoded credentials in config files | `appsettings.Development.json:10` | ✅ Fixed (Phase 2) |

### 2.2 Medium Issues

| ID | Component | Vulnerability | Location | Status |
|----|-----------|--------------|----------|--------|
| V7 | ML Service | Timing-vulnerable API key comparison | `middleware/auth.py:25` | ✅ Fixed (Phase 1) |
| V8 | Configuration | Test API key in example files | `.env.example:42` | ✅ Fixed (Phase 2) |
| V9 | Git | `.env` file may be tracked | Root directory | ✅ Fixed (Phase 3) |

### 2.3 Additional Issues Found & Fixed (Security Audit)

| ID | Component | Vulnerability | Status |
|----|-----------|--------------|--------|
| V10 | ASP.NET API | Auth disabled by default (fails open) | ✅ Fixed (Phase 2) - Fails closed in production |
| V11 | ASP.NET API | CORS `AllowAnyHeader`/`AllowAnyMethod` | ✅ Fixed (Phase 2) - Explicit headers/methods |
| V12 | ASP.NET API | Rate limiting defined but not applied | ✅ Fixed (Phase 2) - Applied to auth/admin |
| V13 | ASP.NET API | Exception details exposed to clients | ✅ Fixed (Phase 2) - Sanitized responses |
| V14 | ASP.NET API | No date range validation (DoS risk) | ✅ Fixed (Phase 2) - 90-day max range |
| V15 | ML Service | `/docs` and `/openapi.json` exposed in production | ✅ Fixed (Phase 2) - Hidden in production |
| V16 | ASP.NET API | No security headers | ✅ Fixed (Phase 3) - X-Content-Type-Options, X-Frame-Options, etc. |
| V17 | Git | Backup files (`.bak`) not excluded | ✅ Fixed (Phase 3) - Added patterns to `.gitignore` |

---

## 3. Implementation Plan

### Phase 1: Immediate Fixes (Day 1)

#### Task 1.1: Secure Azure Functions

**File: `AiTradingRace.Functions/Functions/RunAgentsFunction.cs`**

```csharp
// Line 40 - CHANGE FROM:
[HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "agents/run")]

// TO:
[HttpTrigger(AuthorizationLevel.Function, "post", Route = "agents/run")]
```

**File: `AiTradingRace.Functions/Orchestrators/MarketCycleOrchestrator.cs`**

```csharp
// Line 170 - CHANGE FROM:
[HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "market-cycle/trigger")]

// TO:
[HttpTrigger(AuthorizationLevel.Function, "post", Route = "market-cycle/trigger")]
```

**Keep Anonymous (intentional):**
- `HealthCheckFunction.cs` - Health endpoint for monitoring

**After deployment, retrieve function keys:**
```bash
# Get function key for RunAgentsFunction
az functionapp function keys list \
  --name ai-trading-race-func \
  --resource-group ai-trading-rg \
  --function-name RunAgentsManual

# Store key securely for Web API to call Functions
```

---

#### Task 1.2: Add Authorization to Unprotected Endpoints

**File: `AiTradingRace.Web/Controllers/PortfolioController.cs`**

```csharp
// Line 51 - ADD [Authorize] attribute:
[Authorize(Policy = "RequireOperator")]
[HttpPost("{agentId:guid}/portfolio/trades")]
public async Task<ActionResult<TradeResultDto>> ExecuteTrades(
    Guid agentId,
    [FromBody] ExecuteTradesRequest request)
{
    // ... existing code
}
```

**File: `AiTradingRace.Web/Controllers/EquityController.cs`**

```csharp
// Line 72 - ADD [Authorize] attribute:
[Authorize(Policy = "RequireOperator")]
[HttpPost("{agentId:guid}/equity/snapshot")]
public async Task<ActionResult<EquitySnapshotDto>> CaptureSnapshot(Guid agentId)
{
    // ... existing code
}
```

---

#### Task 1.3: Fix ML Service API Key Bypass

**File: `ai-trading-race-ml/app/middleware/auth.py`**

```python
# REPLACE the entire ApiKeyMiddleware class:

import hmac
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings

class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.api_key = settings.api_key

    async def dispatch(self, request: Request, call_next):
        # Allow health checks without auth
        if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
            return await call_next(request)

        # SECURITY FIX: Fail closed if API key not configured
        if not self.api_key:
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: API key not set"
            )

        # Get API key from header
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="Missing API key"
            )

        # SECURITY FIX: Use timing-safe comparison
        if not hmac.compare_digest(api_key, self.api_key):
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )

        return await call_next(request)
```

---

#### Task 1.4: Fix ML Service CORS

**File: `ai-trading-race-ml/app/config.py`**

```python
# CHANGE FROM:
allowed_origin: str = "*"

# TO:
allowed_origin: str = ""  # Must be explicitly set via ML_SERVICE_ALLOWED_ORIGIN
```

**File: `ai-trading-race-ml/app/main.py`**

```python
# UPDATE CORS configuration (around line 61):
if settings.allowed_origin and settings.allowed_origin != "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_credentials=True,
        allow_methods=["POST", "GET"],
        allow_headers=["X-API-Key", "Content-Type"],
    )
else:
    # In development, allow localhost
    import os
    if os.getenv("ENVIRONMENT", "development") == "development":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["POST", "GET"],
            allow_headers=["X-API-Key", "Content-Type"],
        )
```

**Environment variable (production):**
```bash
ML_SERVICE_ALLOWED_ORIGIN=https://ai-trading-race.com
```

---

### Phase 2: Configuration Security (Day 1-2)

#### Task 2.1: Remove Hardcoded Credentials

**File: `AiTradingRace.Web/appsettings.Development.json`**

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Debug"
    }
  },
  "ConnectionStrings": {
    "DefaultConnection": ""  // Use environment variable or user secrets
  }
}
```

**Use User Secrets for local development:**
```bash
cd AiTradingRace.Web

# Initialize user secrets
dotnet user-secrets init

# Set connection string
dotnet user-secrets set "ConnectionStrings:DefaultConnection" "Server=localhost;Database=TradingDb;User Id=sa;Password=YOUR_ACTUAL_PASSWORD;TrustServerCertificate=True"

# Set JWT secret
dotnet user-secrets set "Jwt:SecretKey" "your-32-character-minimum-secret-key-here"
```

---

#### Task 2.2: Ensure .env is Gitignored

**File: `.gitignore`**

```gitignore
# Environment files
.env
.env.local
.env.*.local
*.env

# User secrets
secrets.json
```

**If .env is already tracked:**
```bash
# Remove from git tracking (keeps local file)
git rm --cached .env
git commit -m "Remove .env from tracking"
```

---

#### Task 2.3: Update .env.example with Safe Placeholders

**File: `.env.example`**

```bash
# ===========================================
# AI TRADING RACE - Environment Configuration
# ===========================================
# Copy this file to .env and fill in your values
# NEVER commit .env to version control

# -----------------------------
# Database Configuration
# -----------------------------
SA_PASSWORD=<generate-strong-password>
DB_CONNECTION_STRING=Server=localhost;Database=TradingDb;User Id=sa;Password=<your-password>;TrustServerCertificate=True

# -----------------------------
# JWT Authentication
# -----------------------------
JWT_SECRET_KEY=<generate-32-char-minimum-secret>
JWT_ISSUER=ai-trading-race
JWT_AUDIENCE=ai-trading-race-api

# -----------------------------
# ML Service
# -----------------------------
ML_SERVICE_API_KEY=<generate-secure-api-key>
ML_SERVICE_URL=http://localhost:8000
ML_SERVICE_ALLOWED_ORIGIN=http://localhost:5173

# -----------------------------
# External APIs
# -----------------------------
COINGECKO_API_KEY=<your-coingecko-key>
AZURE_OPENAI_API_KEY=<your-openai-key>
AZURE_OPENAI_ENDPOINT=<your-endpoint>

# -----------------------------
# Azure (Production)
# -----------------------------
# AZURE_FUNCTIONS_KEY=<retrieved-after-deployment>
```

---

### Phase 3: ASP.NET Security Hardening (Day 2)

#### Task 3.1: Verify JWT Configuration

**File: `AiTradingRace.Web/Program.cs`**

Ensure JWT is properly configured (current implementation is good, verify these settings):

```csharp
// Verify these settings exist:
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(builder.Configuration["Jwt:SecretKey"]!)),
            ClockSkew = TimeSpan.Zero  // No tolerance for expired tokens
        };
    });
```

---

#### Task 3.2: Verify Rate Limiting

Current implementation is good. Verify these limits are active:

| Limiter | Limit | Window | Purpose |
|---------|-------|--------|---------|
| Global | 100 requests | 1 minute | DDoS protection |
| Auth endpoints | 10 requests | 1 minute | Brute force protection |
| Per-user | 200 requests | 1 minute | Fair usage |

---

#### Task 3.3: Tighten CORS for Production

**File: `AiTradingRace.Web/Program.cs`**

```csharp
// Update CORS configuration:
builder.Services.AddCors(options =>
{
    options.AddPolicy("Production", policy =>
    {
        policy.WithOrigins(
                "https://ai-trading-race.com",
                "https://www.ai-trading-race.com")
            .AllowAnyHeader()
            .AllowAnyMethod()
            .AllowCredentials();
    });

    options.AddPolicy("Development", policy =>
    {
        policy.WithOrigins(
                "http://localhost:5173",
                "http://localhost:3000")
            .AllowAnyHeader()
            .AllowAnyMethod()
            .AllowCredentials();
    });
});

// In app configuration:
if (app.Environment.IsDevelopment())
{
    app.UseCors("Development");
}
else
{
    app.UseCors("Production");
}
```

---

### Phase 4: Azure Infrastructure (Day 3)

> **Automated:** Run `scripts/secure-azure-infra.sh` to apply all Phase 4 configurations.
> Supports environment variables for custom resource names (see script for details).

#### Task 4.1: Configure Function App IP Restrictions

Restricts Function App access to Azure services and the Web API's outbound IPs only.
All other traffic is denied (priority 500 deny-all rule).

```bash
# Automated via scripts/secure-azure-infra.sh, or run manually:

# Allow only Azure services and your Web API
az functionapp config access-restriction add \
  --name ai-trading-race-func \
  --resource-group ai-trading-rg \
  --rule-name "AllowAzureServices" \
  --action Allow \
  --service-tag AzureCloud \
  --priority 100

# Allow your Web API's outbound IPs (auto-detected from App Service)
az functionapp config access-restriction add \
  --name ai-trading-race-func \
  --resource-group ai-trading-rg \
  --rule-name "AllowWebAPI" \
  --action Allow \
  --ip-address <web-api-outbound-ip>/32 \
  --priority 110

# Deny all other traffic
az functionapp config access-restriction add \
  --name ai-trading-race-func \
  --resource-group ai-trading-rg \
  --rule-name "DenyAll" \
  --action Deny \
  --ip-address 0.0.0.0/0 \
  --priority 500
```

---

#### Task 4.2: Configure SQL Firewall

Allows only Azure services to connect. Automatically detects and removes overly
permissive firewall rules (e.g., 0.0.0.0 - 255.255.255.255 ranges).

```bash
# Automated via scripts/secure-azure-infra.sh, or run manually:

# Allow only Azure services
az sql server firewall-rule create \
  --resource-group ai-trading-rg \
  --server ai-trading-sql \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# Remove any "allow all" rules if present
az sql server firewall-rule delete \
  --resource-group ai-trading-rg \
  --server ai-trading-sql \
  --name AllowAllWindowsAzureIps 2>/dev/null || true
```

---

#### Task 4.3: Configure Container App (ML Service) Internal Ingress

Sets the ML Container App to internal-only ingress so it is not reachable from
the public internet. Only services within the same Container Apps Environment
(or VNet) can reach it.

```bash
# Automated via scripts/secure-azure-infra.sh, or run manually:

# Set ML service to internal only
az containerapp ingress update \
  --name ai-trading-ml \
  --resource-group ai-trading-rg \
  --type internal
```

---

#### Task 4.4: Retrieve and Store Function Keys

After deployment, the script retrieves function keys for `RunAgentsManual` and
`TriggerMarketCycle` and displays instructions for storing them in the Web API
app settings.

```bash
# Retrieve keys
az functionapp function keys list \
  --name ai-trading-race-func \
  --resource-group ai-trading-rg \
  --function-name RunAgentsManual

# Store in Web API configuration
az webapp config appsettings set \
  --name ai-trading-race-web \
  --resource-group ai-trading-rg \
  --settings AzureFunctions__Key=<function-key>
```

---

### Phase 5: Credential Rotation (Day 3)

> **Automated:** Run `scripts/rotate-credentials.sh` with one of four modes:
> - `--generate-only` - Generate and display new secrets (default)
> - `--azure` - Generate and deploy to all Azure resources
> - `--local` - Generate and update local dev secrets (user-secrets + .env)
> - `--verify` - Verify deployed services are healthy after rotation

#### Task 5.1: Generate New Secrets

Generates cryptographically secure credentials using `openssl rand`:

| Secret | Size | Purpose |
|--------|------|---------|
| JWT Secret | 48 bytes (base64) | Token signing, minimum 32-char requirement enforced |
| ML API Key | 32 bytes (base64) | Service-to-service authentication |
| DB Password | 24 chars + special | SQL Server admin password (meets complexity requirements) |

```bash
# Generate and display (no deployment)
./scripts/rotate-credentials.sh --generate-only
```

#### Task 5.2: Update All Environments

The script updates credentials across all services in a single run:

| Target | Settings Updated | Mode |
|--------|-----------------|------|
| Azure SQL Server | Admin password | `--azure` |
| Azure App Service (Web API) | JWT secret, ML API key, connection string, ASPNETCORE_ENVIRONMENT | `--azure` |
| Azure Functions | Connection string | `--azure` |
| Azure Container App (ML) | ML_SERVICE_API_KEY (as secret ref), ML_SERVICE_ALLOWED_ORIGIN, ENVIRONMENT | `--azure` |
| dotnet user-secrets | JWT secret, ML API key, connection string | `--local` |
| `.env` file | SA_PASSWORD, ML_SERVICE_API_KEY, ConnectionStrings__TradingDb | `--local` |
| Functions `local.settings.json` | ConnectionStrings__TradingDb | `--local` |

```bash
# Deploy to Azure
./scripts/rotate-credentials.sh --azure

# Update local development
./scripts/rotate-credentials.sh --local

# Verify after rotation
./scripts/rotate-credentials.sh --verify
```

#### Task 5.3: Update CI/CD Pipeline Secrets

After rotation, update GitHub Actions secrets:

```bash
gh secret set JWT_SECRET_KEY --body '<new-jwt-secret>'
gh secret set ML_SERVICE_API_KEY --body '<new-ml-api-key>'
gh secret set SA_PASSWORD --body '<new-db-password>'
gh secret set DB_CONNECTION_STRING --body '<new-connection-string>'
```

---

## 4. Endpoint Security Matrix

### Final State After Implementation

| Endpoint | Method | Auth Required | Policy | Rate Limit |
|----------|--------|---------------|--------|------------|
| `/api/health` | GET | No | - | Global |
| `/api/auth/health` | GET | No | - | Global |
| `/api/auth/me` | GET | Yes | Any | Global |
| `/api/auth/validate/*` | POST | Yes | Policy-based | Auth (strict) |
| `/api/leaderboard` | GET | No | - | Global |
| `/api/agents` | GET | No | - | Global |
| `/api/agents/{id}` | GET | No | - | Global |
| `/api/agents/{id}/run` | POST | Yes | RequireOperator | Per-user |
| `/api/agents/{id}/trades` | GET | No | - | Global |
| `/api/agents/{id}/trades` | POST | Yes | RequireOperator | Per-user |
| `/api/agents/{id}/portfolio/trades` | POST | **Yes** | RequireOperator | Per-user |
| `/api/agents/{id}/equity` | GET | No | - | Global |
| `/api/agents/{id}/equity/snapshot` | POST | **Yes** | RequireOperator | Per-user |
| `/api/agents/{id}/decisions` | GET | No | - | Global |
| `/api/market/*` | GET | No | - | Global |
| `/api/regime/*` | GET | No | - | Global |
| `/api/admin/*` | ALL | Yes | RequireAdmin | Per-user |
| `/api/apikeys/*` | ALL | Yes | RequireAdmin | Per-user |

### Azure Functions

| Function | Route | Auth Level | Access |
|----------|-------|------------|--------|
| HealthCheck | GET /health | Anonymous | Public (monitoring) |
| RunAgentsManual | POST /agents/run | **Function** | Function key required |
| TriggerMarketCycle | POST /market-cycle/trigger | **Function** | Function key required |
| Timer triggers | N/A | N/A | Internal only |

### ML Service

| Endpoint | Method | Auth | Access |
|----------|--------|------|--------|
| `/health` | GET | No | Internal only |
| `/predict` | POST | API Key | Internal only |
| `/analyze` | POST | API Key | Internal only |

---

## 5. Testing Checklist

### Security Tests

```bash
# 1. Test unauthenticated access to protected endpoints
curl -X POST https://your-api/api/agents/{id}/run
# Expected: 401 Unauthorized

curl -X POST https://your-api/api/agents/{id}/portfolio/trades
# Expected: 401 Unauthorized

curl -X POST https://your-api/api/agents/{id}/equity/snapshot
# Expected: 401 Unauthorized

curl -X POST https://your-api/api/admin/ingest
# Expected: 401 Unauthorized

# 2. Test public endpoints still work
curl https://your-api/api/leaderboard
# Expected: 200 OK

curl https://your-api/api/agents
# Expected: 200 OK

# 3. Test Azure Functions require key
curl -X POST https://your-func/api/agents/run
# Expected: 401 Unauthorized

curl -X POST "https://your-func/api/agents/run?code=FUNCTION_KEY"
# Expected: 200 OK (with valid key)

# 4. Test rate limiting
for i in {1..150}; do curl -s https://your-api/api/leaderboard > /dev/null; done
# Expected: 429 after ~100 requests

# 5. Test CORS
curl -H "Origin: https://evil.com" -I https://your-api/api/leaderboard
# Expected: No Access-Control-Allow-Origin header

curl -H "Origin: https://ai-trading-race.com" -I https://your-api/api/leaderboard
# Expected: Access-Control-Allow-Origin: https://ai-trading-race.com

# 6. Test ML service rejects without API key
curl -X POST http://ml-service/predict -H "Content-Type: application/json" -d '{}'
# Expected: 401 Unauthorized

# 7. Test ML service rejects invalid API key
curl -X POST http://ml-service/predict -H "X-API-Key: wrong" -d '{}'
# Expected: 401 Unauthorized
```

---

## 6. Implementation Checklist

### Phase 1: Immediate Fixes ✅ COMPLETE
- [x] Update `RunAgentsFunction.cs` to `AuthorizationLevel.Function`
- [x] Update `MarketCycleOrchestrator.cs` to `AuthorizationLevel.Function`
- [x] Add `[Authorize(RequireOperator)]` to `PortfolioController.ExecuteTrades`
- [x] Add `[Authorize(RequireOperator)]` to `EquityController.CaptureSnapshot`
- [x] Fix ML service API key bypass (fail-closed + `hmac.compare_digest`)
- [x] Fix ML service CORS (`allowed_origin: ""`, conditional config)
- [ ] Deploy changes

### Phase 2: Configuration Security ✅ COMPLETE
- [x] Remove hardcoded credentials from `appsettings.Development.json`
- [x] Update `.env.example` with safe placeholders
- [x] Verify `.env` is in `.gitignore`
- [x] Add backup file patterns to `.gitignore` (`*.bak`, `*.backup`, etc.)

### Phase 3: ASP.NET Hardening ✅ COMPLETE
- [x] Fail-closed auth in production (throws if JWT not configured)
- [x] Restrictive CORS (explicit headers: Authorization, Content-Type, X-API-Key, X-Request-ID)
- [x] Restrictive CORS (explicit methods: GET, POST, PUT, DELETE, OPTIONS)
- [x] Rate limiting applied to `AuthController` (`[EnableRateLimiting("auth")]`)
- [x] Rate limiting applied to `AdminController` (`[EnableRateLimiting("per-user")]`)
- [x] Exception messages sanitized in `AdminController` (no `ex.Message` to client)
- [x] Date range validation in `DecisionLogsController` (90-day max)
- [x] ML docs hidden in production (FastAPI `docs_url=None`)
- [x] ML auth blocks `/docs` in production
- [x] Security headers added (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy)

### Phase 4: Azure Infrastructure ✅ COMPLETE (script: `scripts/secure-azure-infra.sh`)
- [x] Configure Function App IP restrictions (AllowAzureServices + Web API IPs, DenyAll)
- [x] Configure SQL firewall rules (AllowAzureServices, remove permissive rules)
- [x] Set ML Container App to internal ingress
- [x] Retrieve and store function keys securely

### Phase 5: Credential Rotation ✅ COMPLETE (script: `scripts/rotate-credentials.sh`)
- [x] Generate new JWT secret (`openssl rand -base64 48`)
- [x] Generate new ML API key (`openssl rand -base64 32`)
- [x] Generate new database password (complexity-compliant)
- [x] Set `ML_SERVICE_API_KEY` in all environments (Azure + local)
- [x] Set `ML_SERVICE_ALLOWED_ORIGIN` to production domain
- [x] Set `ENVIRONMENT=production` in production
- [x] Set `Authentication:Jwt:SecretKey` in production
- [x] Verify all services work with new credentials (`--verify` mode)

### Final Verification ⏳ PENDING
- [ ] Run all security tests
- [ ] Verify public endpoints accessible
- [ ] Verify protected endpoints require auth
- [ ] Verify rate limiting works
- [ ] Verify CORS blocks unauthorized origins
- [ ] Run `npm audit` on frontend

---

## 7. Rollback Procedures

### If Authentication Breaks

**ASP.NET API:**
```csharp
// Temporarily allow anonymous (NOT FOR PRODUCTION)
[AllowAnonymous]  // Add this temporarily
[HttpPost("{agentId:guid}/portfolio/trades")]
```

**Azure Functions:**
```csharp
// Revert to Anonymous temporarily
[HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "agents/run")]
```

### If Rate Limiting Causes Issues

```csharp
// Increase limits temporarily in Program.cs
options.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(context =>
    RateLimitPartition.GetFixedWindowLimiter("global", _ => new FixedWindowRateLimiterOptions
    {
        PermitLimit = 500,  // Increased from 100
        Window = TimeSpan.FromMinutes(1),
        // ...
    }));
```

---

## 8. Cost Summary

| Item | Cost |
|------|------|
| JWT Authentication | $0 (built-in) |
| Rate Limiting | $0 (built-in) |
| Azure Functions Auth | $0 (built-in) |
| IP Restrictions | $0 (built-in) |
| CORS Configuration | $0 (built-in) |
| User Secrets | $0 (built-in) |
| **Total** | **$0** |

---

## 9. Future Considerations

When the project scales, consider:

1. **Azure Key Vault** (~$3/month) - Centralized secret management
2. **Managed Identity** (free) - Eliminate stored credentials
3. **Azure API Management** (~$50/month) - If you need API monetization or advanced policies
4. **Private Endpoints** (~$10/month) - Full network isolation

These are not required for a demo/competition platform but are recommended for production workloads handling sensitive data.
