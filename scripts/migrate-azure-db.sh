#!/usr/bin/env bash
set -euo pipefail

# Migrate Azure SQL Database
# Generates an idempotent EF Core migration script and applies it to Azure SQL.
# Requires: dotnet-ef, sqlcmd (or go-sqlcmd), az CLI logged in.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

RESOURCE_GROUP="${RESOURCE_GROUP:-ai-trading-rg}"
SQL_SERVER_NAME="${SQL_SERVER_NAME:-ai-trading-sql}"
DB_NAME="${SQL_DATABASE_NAME:-AiTradingRace}"
SQL_ADMIN_USER="${SQL_ADMIN_USER:-sqladmin}"

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

if ! command -v dotnet &>/dev/null; then
  error ".NET SDK is not installed. https://dotnet.microsoft.com/download"
  exit 1
fi

if ! dotnet ef --version &>/dev/null 2>&1; then
  error "dotnet-ef tool is not installed. Run: dotnet tool install --global dotnet-ef"
  exit 1
fi

# ── Resolve password from env ───────────────────────────────────────────────
if [[ -z "${SA_PASSWORD:-}" ]]; then
  read -rsp "SQL admin password (SA_PASSWORD): " SA_PASSWORD
  echo
fi

# ── Resolve Azure SQL FQDN ──────────────────────────────────────────────────
info "Resolving SQL Server FQDN..."
SQL_FQDN=$(az sql server show \
  --name "$SQL_SERVER_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query fullyQualifiedDomainName \
  --output tsv)

if [[ -z "$SQL_FQDN" ]]; then
  error "Could not resolve SQL Server FQDN. Check server name and resource group."
  exit 1
fi

info "SQL Server: $SQL_FQDN"

# ── Generate idempotent migration SQL ────────────────────────────────────────
MIGRATION_SQL="/tmp/ai-trading-race-migration-$(date +%Y%m%d%H%M%S).sql"

info "Generating idempotent migration script..."
dotnet ef migrations script \
  --project "$PROJECT_ROOT/AiTradingRace.Infrastructure/AiTradingRace.Infrastructure.csproj" \
  --startup-project "$PROJECT_ROOT/AiTradingRace.Web/AiTradingRace.Web.csproj" \
  --context TradingDbContext \
  --idempotent \
  --output "$MIGRATION_SQL"

info "Migration script generated: $MIGRATION_SQL"

# ── Open temporary firewall rule ─────────────────────────────────────────────
MY_IP=$(curl -s https://api.ipify.org)
RULE_NAME="migrate-temp-$(date +%s)"

info "Opening temporary firewall rule for $MY_IP..."
az sql server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --server "$SQL_SERVER_NAME" \
  --name "$RULE_NAME" \
  --start-ip-address "$MY_IP" \
  --end-ip-address "$MY_IP" \
  --output none

# Ensure firewall rule is removed on exit (success or failure)
cleanup() {
  info "Removing temporary firewall rule '$RULE_NAME'..."
  az sql server firewall-rule delete \
    --resource-group "$RESOURCE_GROUP" \
    --server "$SQL_SERVER_NAME" \
    --name "$RULE_NAME" \
    --yes \
    --output none 2>/dev/null || true
}
trap cleanup EXIT

# Wait for firewall propagation
sleep 5

# ── Apply migration ─────────────────────────────────────────────────────────
info "Applying migration to $SQL_FQDN / $DB_NAME..."

if command -v sqlcmd &>/dev/null; then
  sqlcmd -S "$SQL_FQDN" -U "$SQL_ADMIN_USER" -P "$SA_PASSWORD" -d "$DB_NAME" -i "$MIGRATION_SQL" -C
else
  error "sqlcmd not found. Install via: brew install sqlcmd (macOS) or https://learn.microsoft.com/sql/tools/sqlcmd"
  exit 1
fi

# ── Verify migration ────────────────────────────────────────────────────────
info "Verifying migrations..."
sqlcmd -S "$SQL_FQDN" -U "$SQL_ADMIN_USER" -P "$SA_PASSWORD" -d "$DB_NAME" -C \
  -Q "SELECT MigrationId, ProductVersion FROM __EFMigrationsHistory ORDER BY MigrationId;"

echo
info "Migration complete!"
