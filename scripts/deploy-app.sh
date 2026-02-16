#!/usr/bin/env bash
set -euo pipefail

# Deploy Application Code to Azure
# Runs after deploy-infra.sh has provisioned Azure resources.
# Builds & pushes ML image, migrates DB, deploys API + Functions + Container App.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

RESOURCE_GROUP="${RESOURCE_GROUP:-ai-trading-rg}"
ML_IMAGE="ghcr.io/${GHCR_USERNAME:-diegoaquinoh}/ai-trading-race-ml"
ML_IMAGE_TAG="${ML_IMAGE_TAG:-latest}"

# Azure resource names (must match infra/modules/*.bicep)
APP_SERVICE_NAME="ai-trading-race-api"
FUNCTION_APP_NAME="ai-trading-race-func"
CONTAINER_APP_NAME="ai-trading-ml"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Pre-flight checks ───────────────────────────────────────────────────────
info "Running pre-flight checks..."

for cmd in az dotnet docker; do
  if ! command -v "$cmd" &>/dev/null; then
    error "$cmd is not installed"
    exit 1
  fi
done

if ! az account show &>/dev/null; then
  error "Not logged in to Azure. Run: az login"
  exit 1
fi

if ! docker info &>/dev/null 2>&1; then
  error "Docker is not running"
  exit 1
fi

info "Logged in as: $(az account show --query user.name -o tsv)"

# ── Resolve secrets from env ─────────────────────────────────────────────────
if [[ -z "${GHCR_USERNAME:-}" ]]; then
  read -rp "GitHub username (GHCR_USERNAME): " GHCR_USERNAME
  ML_IMAGE="ghcr.io/${GHCR_USERNAME}/ai-trading-race-ml"
fi

if [[ -z "${GHCR_PASSWORD:-}" ]]; then
  read -rsp "GitHub PAT (GHCR_PASSWORD): " GHCR_PASSWORD
  echo
fi

# ── Step 1: Build & push ML image ───────────────────────────────────────────
info "Step 1/6: Building ML service Docker image..."
docker build \
  --platform linux/amd64 \
  -t "$ML_IMAGE:$ML_IMAGE_TAG" \
  -t "$ML_IMAGE:$(git -C "$PROJECT_ROOT" rev-parse --short HEAD)" \
  "$PROJECT_ROOT/ai-trading-race-ml"

info "Logging in to ghcr.io..."
echo "$GHCR_PASSWORD" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin

info "Pushing ML image..."
docker push "$ML_IMAGE:$ML_IMAGE_TAG"
docker push "$ML_IMAGE:$(git -C "$PROJECT_ROOT" rev-parse --short HEAD)"

# ── Step 2: Run database migrations ─────────────────────────────────────────
info "Step 2/6: Running database migrations..."
"$SCRIPT_DIR/migrate-azure-db.sh"

# ── Step 3: Deploy Web API ──────────────────────────────────────────────────
info "Step 3/6: Publishing and deploying Web API..."
PUBLISH_DIR=$(mktemp -d)

dotnet publish "$PROJECT_ROOT/AiTradingRace.Web/AiTradingRace.Web.csproj" \
  --configuration Release \
  --output "$PUBLISH_DIR/web"

# Create zip for deployment
(cd "$PUBLISH_DIR/web" && zip -r "$PUBLISH_DIR/web.zip" .)

az webapp deploy \
  --name "$APP_SERVICE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --src-path "$PUBLISH_DIR/web.zip" \
  --type zip \
  --output none

info "Web API deployed to $APP_SERVICE_NAME"

# ── Step 4: Deploy Functions ────────────────────────────────────────────────
info "Step 4/6: Publishing and deploying Azure Functions..."

dotnet publish "$PROJECT_ROOT/AiTradingRace.Functions/AiTradingRace.Functions.csproj" \
  --configuration Release \
  --output "$PUBLISH_DIR/functions"

(cd "$PUBLISH_DIR/functions" && zip -r "$PUBLISH_DIR/functions.zip" .)

az functionapp deployment source config-zip \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --src "$PUBLISH_DIR/functions.zip" \
  --output none

info "Functions deployed to $FUNCTION_APP_NAME"

# ── Step 5: Update Container App ────────────────────────────────────────────
info "Step 5/6: Updating Container App with latest ML image..."
az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --container-name ml-service \
  --image "$ML_IMAGE:$ML_IMAGE_TAG" \
  --output none

info "Container App updated to $ML_IMAGE:$ML_IMAGE_TAG"

# ── Step 6: Retrieve Function keys & inject into Web API ────────────────────
info "Step 6/6: Configuring Function keys in Web API..."
FUNC_DEFAULT_KEY=$(az functionapp keys list \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "functionKeys.default // masterKey" \
  --output tsv 2>/dev/null || true)

if [[ -n "$FUNC_DEFAULT_KEY" ]]; then
  az webapp config appsettings set \
    --name "$APP_SERVICE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings "Functions__ApiKey=$FUNC_DEFAULT_KEY" \
    --output none
  info "Function key injected into Web API settings"
else
  warn "Could not retrieve Function key — configure manually if needed"
fi

# ── Cleanup ──────────────────────────────────────────────────────────────────
rm -rf "$PUBLISH_DIR"

# ── Summary ──────────────────────────────────────────────────────────────────
echo
info "Deployment complete!"
echo "────────────────────────────────────────────────────"

API_URL=$(az webapp show --name "$APP_SERVICE_NAME" --resource-group "$RESOURCE_GROUP" --query defaultHostName -o tsv 2>/dev/null || echo "N/A")
FUNC_URL=$(az functionapp show --name "$FUNCTION_APP_NAME" --resource-group "$RESOURCE_GROUP" --query defaultHostName -o tsv 2>/dev/null || echo "N/A")

echo -e "API:       https://$API_URL"
echo -e "Functions: https://$FUNC_URL"
echo -e "ML Image:  $ML_IMAGE:$ML_IMAGE_TAG"
echo "────────────────────────────────────────────────────"
echo
echo "Next steps:"
echo "  1. Verify: curl https://$API_URL/api/health"
echo "  2. Verify: curl https://$FUNC_URL/api/health"
echo "  3. Configure GitHub Secrets for CI/CD (see docs/DEPLOYMENT_PLAN.md)"
