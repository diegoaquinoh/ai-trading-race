# Full Deployment Plan

End-to-end plan to go from code to running in Azure. Covers first-time setup, application deployment, database migration, CI/CD automation, and verification.

## Prerequisites (one-time, manual)

1. **Azure CLI** installed and logged in (`az login`)
2. **GitHub PAT** with scopes: `read:packages`, `write:packages`, `repo`
3. **Secrets generated** via `./scripts/rotate-credentials.sh --generate-only`
4. **.NET 8 SDK** and `dotnet-ef` tool installed (for migration script generation)
5. **Azure subscription** (free tier is sufficient for all resources)

## GitHub Secrets to Configure

Run these after infrastructure is provisioned:

```
gh secret set AZURE_WEBAPP_PUBLISH_PROFILE     # from: az webapp deployment list-publishing-profiles
gh secret set AZURE_FUNCTIONAPP_PUBLISH_PROFILE # from: az functionapp deployment list-publishing-profiles
gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN   # from: az staticwebapp secrets list
gh secret set GHCR_TOKEN                        # GitHub PAT with write:packages
gh secret set AZURE_CREDENTIALS                 # service principal JSON (for container apps deploy)
```

## Files to Create

| File | Purpose |
|------|---------|
| `scripts/deploy-app.sh` | One-shot manual deployment of all application code |
| `scripts/migrate-azure-db.sh` | Run EF Core migrations against Azure SQL |
| `.github/workflows/deploy.yml` | Unified CD workflow triggered on push to main |

## Files to Modify

| File | Change |
|------|--------|
| `.github/workflows/backend.yml` | Uncomment deploy job, fix resource names |
| `.github/workflows/functions.yml` | Uncomment deploy job, fix resource names |
| `.github/workflows/ml-service.yml` | Uncomment deploy job, target GHCR + Container Apps |
| `.github/workflows/frontend.yml` | Uncomment deploy job, target Static Web App |
| `.github/workflows/ci.yml` | Add deployment status to integration readiness |

---

## New File: `scripts/deploy-app.sh`

Manual first-deploy script. Runs after `deploy-infra.sh` has provisioned Azure resources.

Steps:
1. Pre-flight: check `az`, `dotnet`, `docker` available and logged in
2. **Build & push ML image** to `ghcr.io/diegoaquinoh/ai-trading-race-ml:latest`
   - `docker build -t ghcr.io/diegoaquinoh/ai-trading-race-ml:latest ./ai-trading-race-ml`
   - `docker push ghcr.io/diegoaquinoh/ai-trading-race-ml:latest`
3. **Run database migrations** (calls `migrate-azure-db.sh`)
4. **Deploy Web API** to App Service
   - `dotnet publish AiTradingRace.Web -c Release -o ./publish/web`
   - `az webapp deploy --name ai-trading-race-api --resource-group ai-trading-rg --src-path publish/web.zip --type zip`
5. **Deploy Functions** to Function App
   - `dotnet publish AiTradingRace.Functions -c Release -o ./publish/functions`
   - `cd publish/functions && func azure functionapp publish ai-trading-race-func`
6. **Retrieve Function keys** and inject into Web App settings
   - `az functionapp keys list --name ai-trading-race-func --resource-group ai-trading-rg`
   - `az webapp config appsettings set` to store function key in Web API
7. **Update Container App** to pull latest ML image
   - `az containerapp update --name ai-trading-ml --resource-group ai-trading-rg --image ghcr.io/diegoaquinoh/ai-trading-race-ml:latest`
8. Print status summary with all URLs

## New File: `scripts/migrate-azure-db.sh`

Runs idempotent EF Core migration SQL against Azure SQL.

Steps:
1. Generate idempotent SQL script via `dotnet ef migrations script --idempotent`
2. Open temporary SQL firewall rule for current machine IP
3. Run SQL script via `sqlcmd` against Azure SQL endpoint
4. Remove temporary firewall rule
5. Verify migration applied (query `__EFMigrationsHistory`)

Params from env: `AZURE_SQL_SERVER`, `AZURE_SQL_DB`, `SQL_ADMIN_PASSWORD`, `RESOURCE_GROUP`

## New File: `.github/workflows/deploy.yml`

Unified CD workflow. Triggers on push to `main` after CI passes.

```yaml
name: Deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  ci:
    uses: ./.github/workflows/ci.yml

  deploy-ml:
    needs: ci
    # Login to GHCR, build+push ML image, update Container App
    # Uses: docker/login-action, docker/build-push-action, azure/login, az containerapp update

  deploy-db:
    needs: ci
    # Generate migration script, apply to Azure SQL
    # Uses: dotnet ef migrations script, sqlcmd

  deploy-api:
    needs: [ci, deploy-db, deploy-ml]
    # Download web-api artifact, zip deploy to App Service
    # Uses: azure/webapps-deploy@v3, publish profile

  deploy-functions:
    needs: [ci, deploy-db]
    # Download functions artifact, deploy to Function App
    # Uses: Azure/functions-action@v1, publish profile

  deploy-frontend:
    needs: ci
    # Auto-handled by Static Web App GitHub integration
    # But explicit deploy with Azure/static-web-apps-deploy@v1 for VITE_API_URL injection

  post-deploy:
    needs: [deploy-api, deploy-functions, deploy-ml, deploy-frontend]
    # Retrieve function keys, inject into Web API
    # Run smoke tests against all endpoints
```

**Dependency graph:**
```
ci ──→ deploy-ml ──────────→ deploy-api ──→ post-deploy
  ├──→ deploy-db ──→ deploy-api           ↗
  │              └──→ deploy-functions ──→
  └──→ deploy-frontend ─────────────────→
```

## Modifications to Existing Workflows

### `.github/workflows/backend.yml`
Uncomment the deploy job (lines 97-115). Update:
- `app-name`: `ai-trading-race-api` (matches Bicep)
- `publish-profile`: `${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}`
- Add condition: `if: github.ref == 'refs/heads/main' && github.event_name == 'push'`

### `.github/workflows/functions.yml`
Uncomment the deploy job (lines 83-101). Update:
- `app-name`: `ai-trading-race-func` (matches Bicep)
- `publish-profile`: `${{ secrets.AZURE_FUNCTIONAPP_PUBLISH_PROFILE }}`
- Same condition as above

### `.github/workflows/ml-service.yml`
Uncomment the deploy job (lines 115-145). Update:
- Registry: `ghcr.io` (not a generic `REGISTRY_URL` secret)
- Login: `docker/login-action@v3` with `registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GHCR_TOKEN }}`
- Push tag: `ghcr.io/diegoaquinoh/ai-trading-race-ml:latest` and `:${{ github.sha }}`
- Container Apps deploy: `az containerapp update --name ai-trading-ml --resource-group ai-trading-rg --image ghcr.io/diegoaquinoh/ai-trading-race-ml:${{ github.sha }}`
- Needs `AZURE_CREDENTIALS` secret (service principal) for `azure/login@v2`

### `.github/workflows/frontend.yml`
Uncomment the deploy job (lines 94-118). Update:
- Use `Azure/static-web-apps-deploy@v1`
- `azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}`
- Set `VITE_API_URL` env var pointing to `https://ai-trading-race-api.azurewebsites.net`
- `app_location: ai-trading-race-web`, `output_location: dist`

### `.github/workflows/ci.yml`
Add deployment status output to the integration-readiness summary step.

---

## First-Time Deployment Sequence

```
1. Generate secrets       →  ./scripts/rotate-credentials.sh --generate-only
2. Provision infra        →  ./scripts/deploy-infra.sh
3. Push ML image          →  docker build + docker push to ghcr.io
4. Migrate database       →  ./scripts/migrate-azure-db.sh
5. Deploy application     →  ./scripts/deploy-app.sh
6. Set GitHub Secrets     →  gh secret set ...
7. Verify                 →  ./scripts/rotate-credentials.sh --verify
```

## Verification

```bash
# Smoke test all endpoints
curl https://ai-trading-race-api.azurewebsites.net/api/health
curl https://ai-trading-race-func.azurewebsites.net/api/health
curl https://<swa-hostname>/

# Check ML is internal only (should fail from outside Azure)
az containerapp ingress show --name ai-trading-ml --resource-group ai-trading-rg -o table

# Check Function IP restrictions
az functionapp config access-restriction show --name ai-trading-race-func --resource-group ai-trading-rg -o table

# Auth enforcement
curl -s -o /dev/null -w "%{http_code}" -X POST https://ai-trading-race-api.azurewebsites.net/api/agents/00000000-0000-0000-0000-000000000000/run
# Expected: 401
```

## Implementation Order

1. `scripts/migrate-azure-db.sh` (standalone utility)
2. `scripts/deploy-app.sh` (manual first-deploy, calls migrate-azure-db.sh)
3. `.github/workflows/deploy.yml` (unified CD)
4. Modify `.github/workflows/backend.yml` (uncomment deploy)
5. Modify `.github/workflows/functions.yml` (uncomment deploy)
6. Modify `.github/workflows/ml-service.yml` (uncomment deploy, fix registry)
7. Modify `.github/workflows/frontend.yml` (uncomment deploy, fix SWA config)
