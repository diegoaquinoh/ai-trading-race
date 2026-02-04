#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-ai-trading-rg}"
LOCATION="${LOCATION:-westeurope}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="$SCRIPT_DIR/../infra/main.bicep"
PARAMS_FILE="$SCRIPT_DIR/../infra/main.bicepparam"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Pre-flight checks ───────────────────────────────────────────────────────
if ! command -v az &>/dev/null; then
  error "Azure CLI (az) is not installed. https://aka.ms/install-azure-cli"
  exit 1
fi

if ! az account show &>/dev/null; then
  error "Not logged in to Azure. Run: az login"
  exit 1
fi

info "Logged in as: $(az account show --query user.name -o tsv)"
info "Subscription: $(az account show --query name -o tsv)"

# ── Prompt for secrets if not set ────────────────────────────────────────────
prompt_secret() {
  local var_name="$1" prompt_text="$2"
  if [[ -z "${!var_name:-}" ]]; then
    read -rsp "$prompt_text: " "$var_name"
    echo
  fi
}

prompt_value() {
  local var_name="$1" prompt_text="$2"
  if [[ -z "${!var_name:-}" ]]; then
    read -rp "$prompt_text: " "$var_name"
  fi
}

prompt_secret SQL_ADMIN_PASSWORD "SQL admin password"
prompt_secret JWT_SECRET_KEY     "JWT secret key"
prompt_secret ML_API_KEY         "ML service API key"
prompt_value  GHCR_USERNAME      "GitHub username (ghcr.io)"
prompt_secret GHCR_PASSWORD      "GitHub PAT (read:packages)"
prompt_value  GITHUB_REPO_URL    "GitHub repo URL"
prompt_secret GITHUB_TOKEN       "GitHub token for Static Web App"
prompt_value  PRODUCTION_DOMAIN  "Production domain (CORS origin)"

ML_IMAGE_TAG="${ML_IMAGE_TAG:-latest}"

# ── Create resource group ────────────────────────────────────────────────────
info "Ensuring resource group '$RESOURCE_GROUP' exists in '$LOCATION'..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# ── Deploy Bicep ─────────────────────────────────────────────────────────────
info "Deploying Bicep templates..."
DEPLOYMENT_OUTPUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$TEMPLATE_FILE" \
  --parameters "$PARAMS_FILE" \
  --parameters \
    sqlAdminPassword="$SQL_ADMIN_PASSWORD" \
    jwtSecretKey="$JWT_SECRET_KEY" \
    mlApiKey="$ML_API_KEY" \
    ghcrUsername="$GHCR_USERNAME" \
    ghcrPassword="$GHCR_PASSWORD" \
    mlImageTag="$ML_IMAGE_TAG" \
    githubRepoUrl="$GITHUB_REPO_URL" \
    githubToken="$GITHUB_TOKEN" \
    productionDomain="$PRODUCTION_DOMAIN" \
  --query properties.outputs \
  --output json)

# ── Print outputs ────────────────────────────────────────────────────────────
echo
info "Deployment complete!"
echo "────────────────────────────────────────────────────"
echo -e "SQL Server:       $(echo "$DEPLOYMENT_OUTPUT" | jq -r '.sqlServerFqdn.value')"
echo -e "SQL Database:     $(echo "$DEPLOYMENT_OUTPUT" | jq -r '.sqlDatabaseName.value')"
echo -e "API URL:          $(echo "$DEPLOYMENT_OUTPUT" | jq -r '.apiUrl.value')"
echo -e "Functions URL:    $(echo "$DEPLOYMENT_OUTPUT" | jq -r '.functionsUrl.value')"
echo -e "ML Internal FQDN: $(echo "$DEPLOYMENT_OUTPUT" | jq -r '.mlInternalFqdn.value')"
echo -e "Static Web App:   $(echo "$DEPLOYMENT_OUTPUT" | jq -r '.staticWebAppUrl.value')"
echo "────────────────────────────────────────────────────"
