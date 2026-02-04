#!/bin/bash

# Credential Rotation Script (Phase 5)
# Generates new secrets and updates all Azure environments.
# Run after deploying Azure resources and completing Phase 4.

set -e

echo "Credential Rotation - Phase 5"
echo "=============================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-ai-trading-rg}"
WEB_APP_NAME="${AZURE_WEB_APP_NAME:-ai-trading-race-web}"
FUNC_APP_NAME="${AZURE_FUNC_APP_NAME:-ai-trading-race-func}"
ML_CONTAINER_APP_NAME="${AZURE_ML_APP_NAME:-ai-trading-ml}"
SQL_SERVER_NAME="${AZURE_SQL_SERVER_NAME:-ai-trading-sql}"
SQL_DATABASE_NAME="${AZURE_SQL_DB_NAME:-AiTradingRace}"
PRODUCTION_DOMAIN="${PRODUCTION_DOMAIN:-https://ai-trading-race.com}"

# Script directory for relative paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Output file for generated secrets (temporary)
SECRETS_FILE=$(mktemp)
trap "rm -f $SECRETS_FILE" EXIT

# -------------------------------------------------------------------
# Mode selection
# -------------------------------------------------------------------

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --generate-only    Generate secrets and print them (no deployment)"
    echo "  --azure            Generate secrets and deploy to Azure resources"
    echo "  --local            Update local development secrets (dotnet user-secrets)"
    echo "  --verify           Verify deployed services are healthy"
    echo "  --help             Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  AZURE_RESOURCE_GROUP     (default: ai-trading-rg)"
    echo "  AZURE_WEB_APP_NAME      (default: ai-trading-race-web)"
    echo "  AZURE_FUNC_APP_NAME     (default: ai-trading-race-func)"
    echo "  AZURE_ML_APP_NAME       (default: ai-trading-ml)"
    echo "  AZURE_SQL_SERVER_NAME   (default: ai-trading-sql)"
    echo "  AZURE_SQL_DB_NAME       (default: AiTradingRace)"
    echo "  PRODUCTION_DOMAIN       (default: https://ai-trading-race.com)"
    echo ""
}

MODE="${1:---generate-only}"

case "$MODE" in
    --generate-only|--azure|--local|--verify)
        ;;
    --help|-h)
        usage
        exit 0
        ;;
    *)
        echo -e "${RED}Unknown option: $MODE${NC}"
        usage
        exit 1
        ;;
esac

# -------------------------------------------------------------------
# Pre-flight checks
# -------------------------------------------------------------------

echo -e "${CYAN}Pre-flight checks...${NC}"

# openssl is required for secret generation
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}Error: openssl is not installed${NC}"
    exit 1
fi

if [ "$MODE" = "--azure" ]; then
    if ! command -v az &> /dev/null; then
        echo -e "${RED}Error: Azure CLI (az) is not installed${NC}"
        exit 1
    fi
    if ! az account show > /dev/null 2>&1; then
        echo -e "${RED}Error: Not logged in to Azure. Run: az login${NC}"
        exit 1
    fi
    SUBSCRIPTION=$(az account show --query name -o tsv)
    echo -e "Azure subscription: ${CYAN}$SUBSCRIPTION${NC}"
fi

if [ "$MODE" = "--local" ]; then
    if ! command -v dotnet &> /dev/null; then
        echo -e "${RED}Error: .NET SDK is not installed${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}Pre-flight checks passed${NC}"
echo ""

# -------------------------------------------------------------------
# Task 5.1: Generate New Secrets
# -------------------------------------------------------------------

echo "============================================="
echo -e "${CYAN}Task 5.1: Generate New Secrets${NC}"
echo "============================================="
echo ""

# Generate cryptographically secure secrets
JWT_SECRET=$(openssl rand -base64 48)
ML_API_KEY=$(openssl rand -base64 32)
DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)@Pwd$(openssl rand -hex 2)"

# Store secrets in temp file for later use
cat > "$SECRETS_FILE" <<EOF
JWT_SECRET=$JWT_SECRET
ML_API_KEY=$ML_API_KEY
DB_PASSWORD=$DB_PASSWORD
EOF

# Build the new connection string
DB_CONNECTION_STRING="Server=tcp:${SQL_SERVER_NAME}.database.windows.net,1433;Initial Catalog=${SQL_DATABASE_NAME};User ID=sqladmin;Password=${DB_PASSWORD};Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"

echo "Generated secrets:"
echo ""
echo -e "  JWT Secret (48 bytes):  ${CYAN}${JWT_SECRET:0:8}...${JWT_SECRET: -4}${NC}  (${#JWT_SECRET} chars)"
echo -e "  ML API Key (32 bytes):  ${CYAN}${ML_API_KEY:0:8}...${ML_API_KEY: -4}${NC}  (${#ML_API_KEY} chars)"
echo -e "  DB Password:            ${CYAN}${DB_PASSWORD:0:4}...${DB_PASSWORD: -4}${NC}  (${#DB_PASSWORD} chars)"
echo ""

# Validate key lengths
if [ ${#JWT_SECRET} -lt 32 ]; then
    echo -e "${RED}Error: JWT secret is shorter than 32 characters${NC}"
    exit 1
fi

echo -e "${GREEN}All secrets generated and validated${NC}"
echo ""

# -------------------------------------------------------------------
# Generate-only mode: print and exit
# -------------------------------------------------------------------

if [ "$MODE" = "--generate-only" ]; then
    echo "============================================="
    echo -e "${CYAN}Generated Credentials (copy securely)${NC}"
    echo "============================================="
    echo ""
    echo -e "${YELLOW}WARNING: These secrets are shown once. Store them securely.${NC}"
    echo ""
    echo "--- ASP.NET Web API / Azure App Service ---"
    echo "  Authentication__Jwt__SecretKey = $JWT_SECRET"
    echo "  CustomMlAgent__ApiKey          = $ML_API_KEY"
    echo "  ConnectionStrings__TradingDb   = $DB_CONNECTION_STRING"
    echo ""
    echo "--- Azure Functions ---"
    echo "  ConnectionStrings__TradingDb   = $DB_CONNECTION_STRING"
    echo ""
    echo "--- ML Container App (Python) ---"
    echo "  ML_SERVICE_API_KEY             = $ML_API_KEY"
    echo "  ML_SERVICE_ALLOWED_ORIGIN      = $PRODUCTION_DOMAIN"
    echo "  ENVIRONMENT                    = production"
    echo ""
    echo "--- SQL Server ---"
    echo "  Admin Password                 = $DB_PASSWORD"
    echo ""
    echo "--- CI/CD Secrets (GitHub Actions) ---"
    echo "  JWT_SECRET_KEY                 = $JWT_SECRET"
    echo "  ML_SERVICE_API_KEY             = $ML_API_KEY"
    echo "  SA_PASSWORD                    = $DB_PASSWORD"
    echo "  DB_CONNECTION_STRING           = $DB_CONNECTION_STRING"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  - Run with --azure to deploy to Azure resources"
    echo "  - Run with --local to update local development secrets"
    echo "  - Set GitHub Actions secrets via: gh secret set <NAME>"
    echo ""
    exit 0
fi

# -------------------------------------------------------------------
# Azure deployment mode
# -------------------------------------------------------------------

if [ "$MODE" = "--azure" ]; then
    echo "============================================="
    echo -e "${CYAN}Task 5.2: Update Azure Resources${NC}"
    echo "============================================="
    echo ""

    echo -e "${YELLOW}This will update credentials for:${NC}"
    echo "  - Web App:       $WEB_APP_NAME"
    echo "  - Function App:  $FUNC_APP_NAME"
    echo "  - ML Container:  $ML_CONTAINER_APP_NAME"
    echo "  - SQL Server:    $SQL_SERVER_NAME"
    echo "  - Resource Group: $RESOURCE_GROUP"
    echo ""
    read -p "Continue? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    echo ""

    ERRORS=0

    # ---------------------------------------------------------------
    # 5.2.1: Update SQL Server admin password
    # ---------------------------------------------------------------
    echo -e "${CYAN}[1/4] Updating SQL Server admin password...${NC}"

    if az sql server show --name "$SQL_SERVER_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        az sql server update \
            --name "$SQL_SERVER_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --admin-password "$DB_PASSWORD" > /dev/null 2>&1 && \
            echo -e "  ${GREEN}SQL Server password updated${NC}" || \
            { echo -e "  ${RED}Failed to update SQL Server password${NC}"; ERRORS=$((ERRORS+1)); }
    else
        echo -e "  ${YELLOW}SQL Server '$SQL_SERVER_NAME' not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # 5.2.2: Update Web App (ASP.NET API) settings
    # ---------------------------------------------------------------
    echo -e "${CYAN}[2/4] Updating Web App settings...${NC}"

    if az webapp show --name "$WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        az webapp config appsettings set \
            --name "$WEB_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --settings \
                "Authentication__Jwt__SecretKey=$JWT_SECRET" \
                "CustomMlAgent__ApiKey=$ML_API_KEY" \
                "ConnectionStrings__TradingDb=$DB_CONNECTION_STRING" \
                "ASPNETCORE_ENVIRONMENT=Production" \
            > /dev/null 2>&1 && \
            echo -e "  ${GREEN}Web App settings updated (4 settings)${NC}" || \
            { echo -e "  ${RED}Failed to update Web App settings${NC}"; ERRORS=$((ERRORS+1)); }
    else
        echo -e "  ${YELLOW}Web App '$WEB_APP_NAME' not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # 5.2.3: Update Function App settings
    # ---------------------------------------------------------------
    echo -e "${CYAN}[3/4] Updating Function App settings...${NC}"

    if az functionapp show --name "$FUNC_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        az functionapp config appsettings set \
            --name "$FUNC_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --settings \
                "ConnectionStrings__TradingDb=$DB_CONNECTION_STRING" \
            > /dev/null 2>&1 && \
            echo -e "  ${GREEN}Function App settings updated${NC}" || \
            { echo -e "  ${RED}Failed to update Function App settings${NC}"; ERRORS=$((ERRORS+1)); }
    else
        echo -e "  ${YELLOW}Function App '$FUNC_APP_NAME' not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # 5.2.4: Update ML Container App secrets and env vars
    # ---------------------------------------------------------------
    echo -e "${CYAN}[4/4] Updating ML Container App secrets...${NC}"

    if az containerapp show --name "$ML_CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        # Set secrets
        az containerapp secret set \
            --name "$ML_CONTAINER_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --secrets "ml-api-key=$ML_API_KEY" > /dev/null 2>&1 && \
            echo -e "  ${GREEN}Container App secret 'ml-api-key' set${NC}" || \
            echo -e "  ${YELLOW}Could not set secret (may need manual update)${NC}"

        # Update environment variables
        az containerapp update \
            --name "$ML_CONTAINER_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --set-env-vars \
                "ML_SERVICE_API_KEY=secretref:ml-api-key" \
                "ML_SERVICE_ALLOWED_ORIGIN=$PRODUCTION_DOMAIN" \
                "ENVIRONMENT=production" \
            > /dev/null 2>&1 && \
            echo -e "  ${GREEN}Container App env vars updated${NC}" || \
            { echo -e "  ${RED}Failed to update Container App env vars${NC}"; ERRORS=$((ERRORS+1)); }
    else
        echo -e "  ${YELLOW}Container App '$ML_CONTAINER_APP_NAME' not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    echo "============================================="
    echo "Azure Deployment Summary"
    echo "============================================="
    echo ""

    if [ $ERRORS -eq 0 ]; then
        echo -e "${GREEN}All Azure resources updated successfully${NC}"
    else
        echo -e "${YELLOW}Completed with $ERRORS skipped/failed resource(s)${NC}"
    fi

    echo ""
    echo -e "${YELLOW}Post-deployment steps:${NC}"
    echo "  1. Run: $0 --verify"
    echo "  2. Update GitHub Actions secrets:"
    echo "     gh secret set JWT_SECRET_KEY --body '$JWT_SECRET'"
    echo "     gh secret set ML_SERVICE_API_KEY --body '$ML_API_KEY'"
    echo "     gh secret set SA_PASSWORD --body '$DB_PASSWORD'"
    echo "  3. Test all endpoints (see SECURITY_IMPLEMENTATION.md section 5)"
    echo ""
    exit 0
fi

# -------------------------------------------------------------------
# Local development mode
# -------------------------------------------------------------------

if [ "$MODE" = "--local" ]; then
    echo "============================================="
    echo -e "${CYAN}Task 5.2: Update Local Development Secrets${NC}"
    echo "============================================="
    echo ""

    LOCAL_DB_PASSWORD="$DB_PASSWORD"
    LOCAL_CONNECTION_STRING="Server=localhost,1433;Database=${SQL_DATABASE_NAME};User Id=sa;Password=${LOCAL_DB_PASSWORD};TrustServerCertificate=True"

    # ---------------------------------------------------------------
    # Update dotnet user-secrets for Web API
    # ---------------------------------------------------------------
    WEB_PROJECT="$PROJECT_ROOT/AiTradingRace.Web/AiTradingRace.Web.csproj"

    if [ -f "$WEB_PROJECT" ]; then
        echo -e "${CYAN}Updating Web API user-secrets...${NC}"

        # Initialize user-secrets if not already
        dotnet user-secrets init --project "$WEB_PROJECT" 2>/dev/null || true

        dotnet user-secrets set "Authentication:Jwt:SecretKey" "$JWT_SECRET" --project "$WEB_PROJECT" > /dev/null 2>&1 && \
            echo -e "  ${GREEN}Authentication:Jwt:SecretKey${NC}" || \
            echo -e "  ${RED}Failed to set JWT secret${NC}"

        dotnet user-secrets set "CustomMlAgent:ApiKey" "$ML_API_KEY" --project "$WEB_PROJECT" > /dev/null 2>&1 && \
            echo -e "  ${GREEN}CustomMlAgent:ApiKey${NC}" || \
            echo -e "  ${RED}Failed to set ML API key${NC}"

        dotnet user-secrets set "ConnectionStrings:TradingDb" "$LOCAL_CONNECTION_STRING" --project "$WEB_PROJECT" > /dev/null 2>&1 && \
            echo -e "  ${GREEN}ConnectionStrings:TradingDb${NC}" || \
            echo -e "  ${RED}Failed to set connection string${NC}"

        echo ""
    else
        echo -e "${YELLOW}Web API project not found at $WEB_PROJECT${NC}"
    fi

    # ---------------------------------------------------------------
    # Update .env file (for docker-compose and scripts)
    # ---------------------------------------------------------------
    ENV_FILE="$PROJECT_ROOT/.env"

    if [ -f "$ENV_FILE" ]; then
        echo -e "${CYAN}Updating .env file...${NC}"

        # Create backup
        cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%s)"
        echo -e "  ${GREEN}Backup created${NC}"

        # Update SA_PASSWORD
        if grep -q "^export SA_PASSWORD=" "$ENV_FILE" 2>/dev/null; then
            sed -i.tmp "s|^export SA_PASSWORD=.*|export SA_PASSWORD=${LOCAL_DB_PASSWORD}|" "$ENV_FILE"
            echo -e "  ${GREEN}SA_PASSWORD updated${NC}"
        elif grep -q "^SA_PASSWORD=" "$ENV_FILE" 2>/dev/null; then
            sed -i.tmp "s|^SA_PASSWORD=.*|SA_PASSWORD=${LOCAL_DB_PASSWORD}|" "$ENV_FILE"
            echo -e "  ${GREEN}SA_PASSWORD updated${NC}"
        fi

        # Update ML_SERVICE_API_KEY
        if grep -q "^export ML_SERVICE_API_KEY=" "$ENV_FILE" 2>/dev/null; then
            sed -i.tmp "s|^export ML_SERVICE_API_KEY=.*|export ML_SERVICE_API_KEY=${ML_API_KEY}|" "$ENV_FILE"
            echo -e "  ${GREEN}ML_SERVICE_API_KEY updated${NC}"
        elif grep -q "^ML_SERVICE_API_KEY=" "$ENV_FILE" 2>/dev/null; then
            sed -i.tmp "s|^ML_SERVICE_API_KEY=.*|ML_SERVICE_API_KEY=${ML_API_KEY}|" "$ENV_FILE"
            echo -e "  ${GREEN}ML_SERVICE_API_KEY updated${NC}"
        fi

        # Update ConnectionStrings__TradingDb
        if grep -q "^export ConnectionStrings__TradingDb=" "$ENV_FILE" 2>/dev/null; then
            sed -i.tmp "s|^export ConnectionStrings__TradingDb=.*|export ConnectionStrings__TradingDb=\"${LOCAL_CONNECTION_STRING}\"|" "$ENV_FILE"
            echo -e "  ${GREEN}ConnectionStrings__TradingDb updated${NC}"
        elif grep -q "^ConnectionStrings__TradingDb=" "$ENV_FILE" 2>/dev/null; then
            sed -i.tmp "s|^ConnectionStrings__TradingDb=.*|ConnectionStrings__TradingDb=\"${LOCAL_CONNECTION_STRING}\"|" "$ENV_FILE"
            echo -e "  ${GREEN}ConnectionStrings__TradingDb updated${NC}"
        fi

        # Clean up sed temp files
        rm -f "${ENV_FILE}.tmp"
        echo ""
    else
        echo -e "${YELLOW}.env file not found at $ENV_FILE${NC}"
        echo "  Copy .env.example to .env first: cp .env.example .env"
    fi

    # ---------------------------------------------------------------
    # Update Functions local.settings.json
    # ---------------------------------------------------------------
    FUNC_SETTINGS="$PROJECT_ROOT/AiTradingRace.Functions/local.settings.json"

    if [ -f "$FUNC_SETTINGS" ]; then
        echo -e "${CYAN}Updating Functions local.settings.json...${NC}"

        if command -v python3 &> /dev/null; then
            python3 -c "
import json, sys

with open('$FUNC_SETTINGS', 'r') as f:
    settings = json.load(f)

values = settings.get('Values', {})
values['ConnectionStrings__TradingDb'] = '$LOCAL_CONNECTION_STRING'
settings['Values'] = values

with open('$FUNC_SETTINGS', 'w') as f:
    json.dump(settings, f, indent=2)

print('  Updated ConnectionStrings__TradingDb')
" && echo -e "  ${GREEN}local.settings.json updated${NC}" || \
            echo -e "  ${YELLOW}Could not update local.settings.json automatically${NC}"
        else
            echo -e "  ${YELLOW}Python3 not found, skipping automatic update${NC}"
            echo "  Manually set ConnectionStrings__TradingDb in $FUNC_SETTINGS"
        fi
        echo ""
    fi

    echo "============================================="
    echo "Local Development Summary"
    echo "============================================="
    echo ""
    echo -e "${GREEN}Local secrets updated${NC}"
    echo ""
    echo -e "${YELLOW}Remember:${NC}"
    echo "  - Restart all services after rotating credentials"
    echo "  - If using Docker, recreate SQL container with new password:"
    echo "    docker compose down sqlserver && docker compose up -d sqlserver"
    echo "  - Re-run database setup: source .env && ./scripts/setup-database.sh"
    echo ""
    exit 0
fi

# -------------------------------------------------------------------
# Verify mode
# -------------------------------------------------------------------

if [ "$MODE" = "--verify" ]; then
    echo "============================================="
    echo -e "${CYAN}Verify Deployed Services${NC}"
    echo "============================================="
    echo ""

    ERRORS=0

    # ---------------------------------------------------------------
    # Check Web API health
    # ---------------------------------------------------------------
    echo -e "${CYAN}[1/4] Checking Web API...${NC}"

    if az webapp show --name "$WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        WEB_URL=$(az webapp show \
            --name "$WEB_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "defaultHostName" -o tsv)

        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${WEB_URL}/api/health" 2>/dev/null || echo "000")

        if [ "$HTTP_STATUS" = "200" ]; then
            echo -e "  ${GREEN}Web API healthy (HTTP $HTTP_STATUS)${NC}"
        else
            echo -e "  ${RED}Web API unhealthy (HTTP $HTTP_STATUS)${NC}"
            ERRORS=$((ERRORS+1))
        fi

        # Test auth is enforced
        AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "https://${WEB_URL}/api/agents/00000000-0000-0000-0000-000000000000/run" 2>/dev/null || echo "000")
        if [ "$AUTH_STATUS" = "401" ]; then
            echo -e "  ${GREEN}Auth enforcement working (POST /run returns 401)${NC}"
        else
            echo -e "  ${YELLOW}Auth check returned HTTP $AUTH_STATUS (expected 401)${NC}"
        fi
    else
        echo -e "  ${YELLOW}Web App not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # Check Function App health
    # ---------------------------------------------------------------
    echo -e "${CYAN}[2/4] Checking Function App...${NC}"

    if az functionapp show --name "$FUNC_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        FUNC_URL=$(az functionapp show \
            --name "$FUNC_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "defaultHostName" -o tsv)

        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${FUNC_URL}/api/health" 2>/dev/null || echo "000")

        if [ "$HTTP_STATUS" = "200" ]; then
            echo -e "  ${GREEN}Function App healthy (HTTP $HTTP_STATUS)${NC}"
        else
            echo -e "  ${YELLOW}Function App health returned HTTP $HTTP_STATUS${NC}"
        fi

        # Test function auth is enforced
        AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "https://${FUNC_URL}/api/agents/run" 2>/dev/null || echo "000")
        if [ "$AUTH_STATUS" = "401" ]; then
            echo -e "  ${GREEN}Function key enforcement working (returns 401 without key)${NC}"
        else
            echo -e "  ${YELLOW}Function auth check returned HTTP $AUTH_STATUS (expected 401)${NC}"
        fi
    else
        echo -e "  ${YELLOW}Function App not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # Check ML Container App
    # ---------------------------------------------------------------
    echo -e "${CYAN}[3/4] Checking ML Container App...${NC}"

    if az containerapp show --name "$ML_CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        INGRESS_TYPE=$(az containerapp ingress show \
            --name "$ML_CONTAINER_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "type" -o tsv 2>/dev/null || echo "unknown")

        if [ "$INGRESS_TYPE" = "internal" ]; then
            echo -e "  ${GREEN}ML service ingress is internal${NC}"
        else
            echo -e "  ${YELLOW}ML service ingress is '$INGRESS_TYPE' (expected internal)${NC}"
        fi

        # Check environment variable is set
        ENV_VAL=$(az containerapp show \
            --name "$ML_CONTAINER_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "properties.template.containers[0].env[?name=='ENVIRONMENT'].value" -o tsv 2>/dev/null || echo "")

        if [ "$ENV_VAL" = "production" ]; then
            echo -e "  ${GREEN}ENVIRONMENT=production is set${NC}"
        else
            echo -e "  ${YELLOW}ENVIRONMENT='$ENV_VAL' (expected 'production')${NC}"
        fi
    else
        echo -e "  ${YELLOW}Container App not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # Check SQL Server connectivity
    # ---------------------------------------------------------------
    echo -e "${CYAN}[4/4] Checking SQL Server...${NC}"

    if az sql server show --name "$SQL_SERVER_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        SQL_STATE=$(az sql server show \
            --name "$SQL_SERVER_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "state" -o tsv)

        if [ "$SQL_STATE" = "Ready" ]; then
            echo -e "  ${GREEN}SQL Server state: Ready${NC}"
        else
            echo -e "  ${YELLOW}SQL Server state: $SQL_STATE${NC}"
        fi

        # Check firewall rules
        RULE_COUNT=$(az sql server firewall-rule list \
            --resource-group "$RESOURCE_GROUP" \
            --server "$SQL_SERVER_NAME" \
            --query "length(@)" -o tsv 2>/dev/null || echo "0")
        echo -e "  Firewall rules configured: ${CYAN}$RULE_COUNT${NC}"
    else
        echo -e "  ${YELLOW}SQL Server not found, skipping${NC}"
        ERRORS=$((ERRORS+1))
    fi
    echo ""

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    echo "============================================="
    echo "Verification Summary"
    echo "============================================="
    echo ""

    if [ $ERRORS -eq 0 ]; then
        echo -e "${GREEN}All services verified successfully${NC}"
    else
        echo -e "${YELLOW}$ERRORS service(s) could not be verified${NC}"
    fi

    echo ""
    echo "Manual checks still recommended:"
    echo "  - Test CORS: curl -H 'Origin: https://evil.com' -I https://<api>/api/leaderboard"
    echo "  - Test rate limiting: Send 150 requests in rapid succession"
    echo "  - Run: npm audit (in frontend directory)"
    echo ""
    exit 0
fi
