#!/bin/bash

# Azure Infrastructure Security Script (Phase 4)
# Configures IP restrictions, SQL firewall, and internal ingress
# for the AI Trading Race platform.

set -e

echo "Azure Infrastructure Security - Phase 4"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration from environment variables with defaults
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-ai-trading-rg}"
FUNC_APP_NAME="${AZURE_FUNC_APP_NAME:-ai-trading-race-func}"
SQL_SERVER_NAME="${AZURE_SQL_SERVER_NAME:-ai-trading-sql}"
ML_CONTAINER_APP_NAME="${AZURE_ML_APP_NAME:-ai-trading-ml}"
WEB_APP_NAME="${AZURE_WEB_APP_NAME:-ai-trading-race-web}"

# -------------------------------------------------------------------
# Pre-flight checks
# -------------------------------------------------------------------

echo -e "${CYAN}Validating prerequisites...${NC}"

# Check Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI (az) is not installed${NC}"
    echo "   Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Check user is logged in
if ! az account show > /dev/null 2>&1; then
    echo -e "${RED}Error: Not logged in to Azure${NC}"
    echo "   Run: az login"
    exit 1
fi

# Check resource group exists
if ! az group show --name "$RESOURCE_GROUP" > /dev/null 2>&1; then
    echo -e "${RED}Error: Resource group '$RESOURCE_GROUP' not found${NC}"
    echo "   Set AZURE_RESOURCE_GROUP to the correct resource group name"
    exit 1
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "${GREEN}Logged in to subscription: $SUBSCRIPTION${NC}"
echo -e "Resource group: ${CYAN}$RESOURCE_GROUP${NC}"
echo ""

# Prompt for confirmation
echo -e "${YELLOW}This script will:${NC}"
echo "  1. Configure Function App IP restrictions"
echo "  2. Configure SQL Server firewall rules"
echo "  3. Set ML Container App to internal ingress"
echo "  4. Retrieve and display Function keys"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi
echo ""

# Track overall success
ERRORS=0

# -------------------------------------------------------------------
# Task 4.1: Configure Function App IP Restrictions
# -------------------------------------------------------------------

echo "============================================="
echo -e "${CYAN}Task 4.1: Function App IP Restrictions${NC}"
echo "============================================="
echo ""

# Verify Function App exists
if ! az functionapp show --name "$FUNC_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    echo -e "${YELLOW}Function App '$FUNC_APP_NAME' not found, skipping...${NC}"
    echo "   Set AZURE_FUNC_APP_NAME if the name differs"
    ERRORS=$((ERRORS+1))
else
    # Get Web API outbound IPs (if the web app exists)
    WEB_OUTBOUND_IPS=""
    if az webapp show --name "$WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
        WEB_OUTBOUND_IPS=$(az webapp show \
            --name "$WEB_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --query "possibleOutboundIpAddresses" -o tsv)
        echo -e "Web API outbound IPs: ${CYAN}$WEB_OUTBOUND_IPS${NC}"
    else
        echo -e "${YELLOW}Web App '$WEB_APP_NAME' not found, skipping Web API IP rule${NC}"
    fi

    # Clear existing restrictions (except SCM)
    echo "Clearing existing access restrictions..."
    EXISTING_RULES=$(az functionapp config access-restriction show \
        --name "$FUNC_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "ipSecurityRestrictions[?name!='Allow all access'].name" -o tsv 2>/dev/null || true)

    for rule in $EXISTING_RULES; do
        if [ "$rule" != "Allow all access" ] && [ "$rule" != "Deny all access" ]; then
            az functionapp config access-restriction remove \
                --name "$FUNC_APP_NAME" \
                --resource-group "$RESOURCE_GROUP" \
                --rule-name "$rule" > /dev/null 2>&1 || true
        fi
    done

    # Rule 1: Allow Azure services
    echo "Adding rule: Allow Azure services..."
    az functionapp config access-restriction add \
        --name "$FUNC_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --rule-name "AllowAzureServices" \
        --action Allow \
        --service-tag AzureCloud \
        --priority 100 > /dev/null 2>&1 && \
        echo -e "  ${GREEN}AllowAzureServices (priority 100)${NC}" || \
        { echo -e "  ${YELLOW}AllowAzureServices rule may already exist${NC}"; }

    # Rule 2: Allow Web API outbound IPs
    if [ -n "$WEB_OUTBOUND_IPS" ]; then
        PRIORITY=110
        IFS=',' read -ra IPS <<< "$WEB_OUTBOUND_IPS"
        for IP in "${IPS[@]}"; do
            IP=$(echo "$IP" | xargs)  # trim whitespace
            echo "Adding rule: Allow Web API IP $IP..."
            az functionapp config access-restriction add \
                --name "$FUNC_APP_NAME" \
                --resource-group "$RESOURCE_GROUP" \
                --rule-name "AllowWebAPI-${IP//./-}" \
                --action Allow \
                --ip-address "${IP}/32" \
                --priority $PRIORITY > /dev/null 2>&1 && \
                echo -e "  ${GREEN}AllowWebAPI ${IP}/32 (priority $PRIORITY)${NC}" || \
                echo -e "  ${YELLOW}Rule for $IP may already exist${NC}"
            PRIORITY=$((PRIORITY+1))
        done
    fi

    # Rule 3: Deny all other traffic
    echo "Adding rule: Deny all other traffic..."
    az functionapp config access-restriction add \
        --name "$FUNC_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --rule-name "DenyAll" \
        --action Deny \
        --ip-address "0.0.0.0/0" \
        --priority 500 > /dev/null 2>&1 && \
        echo -e "  ${GREEN}DenyAll (priority 500)${NC}" || \
        echo -e "  ${YELLOW}DenyAll rule may already exist${NC}"

    # Show final rules
    echo ""
    echo "Current access restrictions:"
    az functionapp config access-restriction show \
        --name "$FUNC_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "ipSecurityRestrictions[].{Name:name, Action:action, Priority:priority, IP:ipAddress, Tag:tag}" \
        -o table 2>/dev/null || true

    echo ""
    echo -e "${GREEN}Function App IP restrictions configured${NC}"
fi

echo ""

# -------------------------------------------------------------------
# Task 4.2: Configure SQL Server Firewall
# -------------------------------------------------------------------

echo "============================================="
echo -e "${CYAN}Task 4.2: SQL Server Firewall Rules${NC}"
echo "============================================="
echo ""

# Verify SQL Server exists
if ! az sql server show --name "$SQL_SERVER_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    echo -e "${YELLOW}SQL Server '$SQL_SERVER_NAME' not found, skipping...${NC}"
    echo "   Set AZURE_SQL_SERVER_NAME if the name differs"
    ERRORS=$((ERRORS+1))
else
    # Allow Azure services (0.0.0.0 - 0.0.0.0 is a special range)
    echo "Adding rule: Allow Azure services..."
    az sql server firewall-rule create \
        --resource-group "$RESOURCE_GROUP" \
        --server "$SQL_SERVER_NAME" \
        --name "AllowAzureServices" \
        --start-ip-address 0.0.0.0 \
        --end-ip-address 0.0.0.0 > /dev/null 2>&1 && \
        echo -e "  ${GREEN}AllowAzureServices (0.0.0.0 - 0.0.0.0)${NC}" || \
        echo -e "  ${YELLOW}AllowAzureServices rule may already exist${NC}"

    # Remove overly permissive rules
    echo "Removing overly permissive rules..."
    FIREWALL_RULES=$(az sql server firewall-rule list \
        --resource-group "$RESOURCE_GROUP" \
        --server "$SQL_SERVER_NAME" \
        --query "[].{Name:name, Start:startIpAddress, End:endIpAddress}" -o json 2>/dev/null)

    # Check for and remove any "allow all" style rules
    PERMISSIVE_RULES=$(echo "$FIREWALL_RULES" | python3 -c "
import sys, json
rules = json.load(sys.stdin)
for r in rules:
    if r['Name'] == 'AllowAzureServices':
        continue
    if r['Start'] == '0.0.0.0' and r['End'] == '255.255.255.255':
        print(r['Name'])
    elif r['Name'] in ['AllowAllWindowsAzureIps', 'AllowAll']:
        if r['Start'] != '0.0.0.0' or r['End'] != '0.0.0.0':
            print(r['Name'])
" 2>/dev/null || true)

    if [ -n "$PERMISSIVE_RULES" ]; then
        while IFS= read -r rule; do
            echo "  Removing permissive rule: $rule"
            az sql server firewall-rule delete \
                --resource-group "$RESOURCE_GROUP" \
                --server "$SQL_SERVER_NAME" \
                --name "$rule" > /dev/null 2>&1 || true
        done <<< "$PERMISSIVE_RULES"
    else
        echo -e "  ${GREEN}No overly permissive rules found${NC}"
    fi

    # Show final firewall rules
    echo ""
    echo "Current firewall rules:"
    az sql server firewall-rule list \
        --resource-group "$RESOURCE_GROUP" \
        --server "$SQL_SERVER_NAME" \
        --query "[].{Name:name, StartIP:startIpAddress, EndIP:endIpAddress}" \
        -o table 2>/dev/null || true

    echo ""
    echo -e "${GREEN}SQL Server firewall configured${NC}"
fi

echo ""

# -------------------------------------------------------------------
# Task 4.3: Configure ML Container App Internal Ingress
# -------------------------------------------------------------------

echo "============================================="
echo -e "${CYAN}Task 4.3: ML Container App Internal Ingress${NC}"
echo "============================================="
echo ""

# Verify Container App exists
if ! az containerapp show --name "$ML_CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    echo -e "${YELLOW}Container App '$ML_CONTAINER_APP_NAME' not found, skipping...${NC}"
    echo "   Set AZURE_ML_APP_NAME if the name differs"
    ERRORS=$((ERRORS+1))
else
    # Get current ingress type
    CURRENT_INGRESS=$(az containerapp ingress show \
        --name "$ML_CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "type" -o tsv 2>/dev/null || echo "unknown")

    if [ "$CURRENT_INGRESS" = "internal" ]; then
        echo -e "${GREEN}ML service ingress is already set to internal${NC}"
    else
        echo "Current ingress type: $CURRENT_INGRESS"
        echo "Updating to internal ingress..."
        az containerapp ingress update \
            --name "$ML_CONTAINER_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --type internal > /dev/null 2>&1 && \
            echo -e "${GREEN}ML service ingress set to internal${NC}" || \
            { echo -e "${RED}Failed to update ML service ingress${NC}"; ERRORS=$((ERRORS+1)); }
    fi

    # Show current ingress configuration
    echo ""
    echo "Current ingress configuration:"
    az containerapp ingress show \
        --name "$ML_CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "{Type:type, TargetPort:targetPort, External:external, FQDN:fqdn}" \
        -o table 2>/dev/null || true
fi

echo ""

# -------------------------------------------------------------------
# Task 4.4: Retrieve Function Keys
# -------------------------------------------------------------------

echo "============================================="
echo -e "${CYAN}Task 4.4: Retrieve Function Keys${NC}"
echo "============================================="
echo ""

if ! az functionapp show --name "$FUNC_APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    echo -e "${YELLOW}Function App '$FUNC_APP_NAME' not found, skipping...${NC}"
else
    echo "Retrieving function keys..."
    echo ""

    # Get host keys (master + default)
    echo "Host keys:"
    az functionapp keys list \
        --name "$FUNC_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "{DefaultKey:functionKeys.default, MasterKey:masterKey}" \
        -o table 2>/dev/null || echo -e "  ${YELLOW}Could not retrieve host keys${NC}"
    echo ""

    # Get function-specific keys
    FUNCTIONS=("RunAgentsManual" "TriggerMarketCycle")
    for func in "${FUNCTIONS[@]}"; do
        echo "Function key for $func:"
        az functionapp function keys list \
            --name "$FUNC_APP_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --function-name "$func" \
            --query "default" -o tsv 2>/dev/null || \
            echo -e "  ${YELLOW}Could not retrieve key (function may not be deployed)${NC}"
        echo ""
    done

    echo -e "${YELLOW}Store these keys securely in your Web API configuration:${NC}"
    echo "  az webapp config appsettings set \\"
    echo "    --name $WEB_APP_NAME \\"
    echo "    --resource-group $RESOURCE_GROUP \\"
    echo "    --settings AzureFunctions__Key=<function-key>"
fi

echo ""

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------

echo "============================================="
echo "Summary"
echo "============================================="
echo ""

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}All tasks completed successfully${NC}"
else
    echo -e "${YELLOW}Completed with $ERRORS skipped resource(s)${NC}"
    echo "   Skipped resources may not be deployed yet."
    echo "   Re-run this script after deploying all Azure resources."
fi

echo ""
echo "Configured resources:"
echo "  - Function App:    $FUNC_APP_NAME"
echo "  - SQL Server:      $SQL_SERVER_NAME"
echo "  - ML Container:    $ML_CONTAINER_APP_NAME"
echo "  - Web App:         $WEB_APP_NAME"
echo "  - Resource Group:  $RESOURCE_GROUP"
echo ""
echo "Environment variables for customization:"
echo "  AZURE_RESOURCE_GROUP    (default: ai-trading-rg)"
echo "  AZURE_FUNC_APP_NAME    (default: ai-trading-race-func)"
echo "  AZURE_SQL_SERVER_NAME  (default: ai-trading-sql)"
echo "  AZURE_ML_APP_NAME      (default: ai-trading-ml)"
echo "  AZURE_WEB_APP_NAME     (default: ai-trading-race-web)"
echo ""
echo "Next steps:"
echo "  1. Store function keys in Web API app settings"
echo "  2. Run Phase 5: Credential rotation"
echo "  3. Run security verification tests"
echo ""
