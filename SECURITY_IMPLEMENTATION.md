# Security Implementation Plan

## Document Information

| Field | Value |
|-------|-------|
| **Version** | 1.0 |
| **Created** | February 3, 2026 |
| **Status** | Ready for Implementation |
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
| V1 | Azure Functions | `AuthorizationLevel.Anonymous` on sensitive endpoints | `RunAgentsFunction.cs:40`, `MarketCycleOrchestrator.cs:170` | ⏳ Open |
| V2 | ASP.NET API | Missing `[Authorize]` on POST `/api/agents/{id}/portfolio/trades` | `PortfolioController.cs:51` | ⏳ Open |
| V3 | ASP.NET API | Missing `[Authorize]` on POST `/api/agents/{id}/equity/snapshot` | `EquityController.cs:72` | ⏳ Open |
| V4 | ML Service | API key bypass when not configured | `middleware/auth.py:21-23` | ⏳ Open |
| V5 | ML Service | CORS allows all origins (`*`) | `config.py:21` | ⏳ Open |
| V6 | Configuration | Hardcoded credentials in config files | `appsettings.Development.json:10` | ⏳ Open |

### 2.2 Medium Issues

| ID | Component | Vulnerability | Location | Status |
|----|-----------|--------------|----------|--------|
| V7 | ML Service | Timing-vulnerable API key comparison | `middleware/auth.py:25` | ⏳ Open |
| V8 | Configuration | Test API key in example files | `.env.example:42` | ⏳ Open |
| V9 | Git | `.env` file may be tracked | Root directory | ⏳ Open |

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

#### Task 4.1: Configure Function App IP Restrictions

```bash
# Allow only Azure services and your Web API
az functionapp config access-restriction add \
  --name ai-trading-race-func \
  --resource-group ai-trading-rg \
  --rule-name "AllowAzureServices" \
  --action Allow \
  --service-tag AzureCloud \
  --priority 100

# Allow your Web API's outbound IPs (get from App Service)
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

```bash
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

```bash
# Set ML service to internal only
az containerapp ingress update \
  --name ai-trading-ml \
  --resource-group ai-trading-rg \
  --type internal
```

---

### Phase 5: Credential Rotation (Day 3)

#### Task 5.1: Generate New Secrets

```bash
# Generate secure secrets
echo "New JWT Secret: $(openssl rand -base64 32)"
echo "New ML API Key: $(openssl rand -base64 32)"
echo "New DB Password: $(openssl rand -base64 24)"
```

#### Task 5.2: Update All Environments

1. Update Azure App Service configuration
2. Update Azure Functions configuration
3. Update Container App secrets
4. Update local development secrets (user-secrets)
5. Update any CI/CD pipeline secrets

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

### Phase 1: Immediate Fixes ⏳
- [ ] Update `RunAgentsFunction.cs` to `AuthorizationLevel.Function`
- [ ] Update `MarketCycleOrchestrator.cs` to `AuthorizationLevel.Function`
- [ ] Add `[Authorize]` to `PortfolioController.ExecuteTrades`
- [ ] Add `[Authorize]` to `EquityController.CaptureSnapshot`
- [ ] Fix ML service API key bypass vulnerability
- [ ] Fix ML service CORS configuration
- [ ] Deploy changes

### Phase 2: Configuration Security ⏳
- [ ] Remove hardcoded credentials from `appsettings.Development.json`
- [ ] Set up dotnet user-secrets for local development
- [ ] Verify `.env` is in `.gitignore`
- [ ] Remove `.env` from git tracking if present
- [ ] Update `.env.example` with safe placeholders

### Phase 3: ASP.NET Hardening ⏳
- [ ] Verify JWT configuration is correct
- [ ] Verify rate limiting is active
- [ ] Update CORS for production origins

### Phase 4: Azure Infrastructure ⏳
- [ ] Configure Function App IP restrictions
- [ ] Configure SQL firewall rules
- [ ] Set ML Container App to internal ingress
- [ ] Retrieve and store function keys securely

### Phase 5: Credential Rotation ⏳
- [ ] Generate new JWT secret
- [ ] Generate new ML API key
- [ ] Generate new database password
- [ ] Update all environments
- [ ] Verify all services work with new credentials

### Final Verification ⏳
- [ ] Run all security tests
- [ ] Verify public endpoints accessible
- [ ] Verify protected endpoints require auth
- [ ] Verify rate limiting works
- [ ] Verify CORS blocks unauthorized origins

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
