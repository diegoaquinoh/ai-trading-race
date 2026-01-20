#!/bin/bash

#################################################
# AI Trading Race - Database Seeding Script
#################################################
# Purpose: Populate database with initial data:
# - Tradeable assets (BTC, ETH)
# - Test agents with different providers
# - Initial portfolios with starting balance
#################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AI Trading Race - Database Seeding${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Configuration from environment variables with defaults
DB_SERVER="${SQL_SERVER:-localhost}"
DB_PORT="${SQL_PORT:-1433}"
DB_NAME="${SQL_DATABASE_NAME:-AiTradingRace}"
DB_USER="${SQL_USER:-sa}"
DB_PASSWORD="${SA_PASSWORD:-YourStrong!Passw0rd}"
STARTING_BALANCE="${STARTING_BALANCE:-100000.00}"

# Validate required variables
if [ -z "$DB_PASSWORD" ]; then
    echo -e "${RED}❌ Error: SA_PASSWORD environment variable is required${NC}"
    echo "   Set it with: export SA_PASSWORD='YourPassword'"
    exit 1
fi

# Check if running inside Docker
if [ -f /.dockerenv ]; then
    DB_SERVER="sqlserver"
    echo -e "${YELLOW}Running inside Docker container${NC}"
fi

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --server)
            DB_SERVER="$2"
            shift 2
            ;;
        --port)
            DB_PORT="$2"
            shift 2
            ;;
        --database)
            DB_NAME="$2"
            shift 2
            ;;
        --user)
            DB_USER="$2"
            shift 2
            ;;
        --password)
            DB_PASSWORD="$2"
            shift 2
            ;;
        --balance)
            STARTING_BALANCE="$2"
            shift 2
            ;;
        --docker)
            DB_SERVER="sqlserver"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--server SERVER] [--port PORT] [--database DB] [--user USER] [--password PASS] [--balance AMOUNT] [--docker]"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}Configuration:${NC}"
echo "  Server: $DB_SERVER:$DB_PORT"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Starting Balance: \$$STARTING_BALANCE"
echo ""

# Function to execute SQL
execute_sql() {
    local sql="$1"
    
    if command -v docker &> /dev/null && docker ps | grep -q ai-trading-sqlserver; then
        echo -e "${BLUE}Executing SQL via Docker...${NC}"
        docker exec -i ai-trading-sqlserver /opt/mssql-tools18/bin/sqlcmd \
            -S localhost -U "$DB_USER" -P "$DB_PASSWORD" -d "$DB_NAME" \
            -C -Q "$sql" -b
    elif command -v sqlcmd &> /dev/null; then
        echo -e "${BLUE}Executing SQL via sqlcmd...${NC}"
        sqlcmd -S "$DB_SERVER,$DB_PORT" -U "$DB_USER" -P "$DB_PASSWORD" -d "$DB_NAME" \
            -C -Q "$sql" -b
    else
        echo -e "${RED}Error: Neither Docker container nor sqlcmd found${NC}"
        echo "Please ensure SQL Server is running and accessible"
        exit 1
    fi
}

# Step 1: Seed Assets
echo -e "${YELLOW}Step 1: Seeding Assets...${NC}"

ASSET_SQL="
SET NOCOUNT ON;

-- Insert Bitcoin (BTC)
IF NOT EXISTS (SELECT 1 FROM Assets WHERE Symbol = 'BTC')
BEGIN
    INSERT INTO Assets (Symbol, Name, AssetType, IsActive, CreatedAt, UpdatedAt)
    VALUES ('BTC', 'Bitcoin', 0, 1, GETUTCDATE(), GETUTCDATE());
    PRINT 'Inserted BTC';
END
ELSE
    PRINT 'BTC already exists';

-- Insert Ethereum (ETH)
IF NOT EXISTS (SELECT 1 FROM Assets WHERE Symbol = 'ETH')
BEGIN
    INSERT INTO Assets (Symbol, Name, AssetType, IsActive, CreatedAt, UpdatedAt)
    VALUES ('ETH', 'Ethereum', 0, 1, GETUTCDATE(), GETUTCDATE());
    PRINT 'Inserted ETH';
END
ELSE
    PRINT 'ETH already exists';

-- Insert USD (for portfolio cash balance)
IF NOT EXISTS (SELECT 1 FROM Assets WHERE Symbol = 'USD')
BEGIN
    INSERT INTO Assets (Symbol, Name, AssetType, IsActive, CreatedAt, UpdatedAt)
    VALUES ('USD', 'US Dollar', 1, 1, GETUTCDATE(), GETUTCDATE());
    PRINT 'Inserted USD';
END
ELSE
    PRINT 'USD already exists';

SELECT Id, Symbol, Name, AssetType, IsActive FROM Assets;
"

execute_sql "$ASSET_SQL" || {
    echo -e "${RED}Failed to seed assets${NC}"
    exit 1
}

echo -e "${GREEN}✓ Assets seeded successfully${NC}"
echo ""

# Step 2: Seed Test Agents
echo -e "${YELLOW}Step 2: Seeding Test Agents...${NC}"

AGENT_SQL="
SET NOCOUNT ON;

-- Agent 1: Llama Momentum Trader
IF NOT EXISTS (SELECT 1 FROM Agents WHERE Name = 'Llama Momentum Trader')
BEGIN
    INSERT INTO Agents (Name, ModelProvider, ModelConfiguration, SystemPrompt, IsActive, CreatedAt, UpdatedAt)
    VALUES (
        'Llama Momentum Trader',
        'Llama',
        '{\"Model\":\"llama-3.3-70b-versatile\",\"Temperature\":0.7,\"MaxTokens\":500}',
        'You are a momentum trading AI. Analyze price trends and volume to identify strong upward or downward momentum. Buy assets showing strong upward momentum and sell when momentum weakens. Focus on short to medium-term trends.',
        1,
        GETUTCDATE(),
        GETUTCDATE()
    );
    PRINT 'Inserted Llama Momentum Trader';
END
ELSE
    PRINT 'Llama Momentum Trader already exists';

-- Agent 2: Llama Value Investor
IF NOT EXISTS (SELECT 1 FROM Agents WHERE Name = 'Llama Value Investor')
BEGIN
    INSERT INTO Agents (Name, ModelProvider, ModelConfiguration, SystemPrompt, IsActive, CreatedAt, UpdatedAt)
    VALUES (
        'Llama Value Investor',
        'Llama',
        '{\"Model\":\"llama-3.3-70b-versatile\",\"Temperature\":0.5,\"MaxTokens\":500}',
        'You are a value investing AI. Look for undervalued assets by analyzing long-term trends, support/resistance levels, and market cycles. Buy when prices are below historical averages and hold for long-term gains. Be patient and disciplined.',
        1,
        GETUTCDATE(),
        GETUTCDATE()
    );
    PRINT 'Inserted Llama Value Investor';
END
ELSE
    PRINT 'Llama Value Investor already exists';

-- Agent 3: CustomML Technical Analyst
IF NOT EXISTS (SELECT 1 FROM Agents WHERE Name = 'CustomML Technical Analyst')
BEGIN
    INSERT INTO Agents (Name, ModelProvider, ModelConfiguration, SystemPrompt, IsActive, CreatedAt, UpdatedAt)
    VALUES (
        'CustomML Technical Analyst',
        'CustomMl',
        '{\"ApiUrl\":\"http://ml-service:8000\"}',
        'You are a technical analysis AI using machine learning models. Analyze candlestick patterns, technical indicators, and historical data to predict future price movements. Make data-driven decisions based on statistical patterns.',
        1,
        GETUTCDATE(),
        GETUTCDATE()
    );
    PRINT 'Inserted CustomML Technical Analyst';
END
ELSE
    PRINT 'CustomML Technical Analyst already exists';

-- Agent 4: Llama Contrarian Trader
IF NOT EXISTS (SELECT 1 FROM Agents WHERE Name = 'Llama Contrarian Trader')
BEGIN
    INSERT INTO Agents (Name, ModelProvider, ModelConfiguration, SystemPrompt, IsActive, CreatedAt, UpdatedAt)
    VALUES (
        'Llama Contrarian Trader',
        'Llama',
        '{\"Model\":\"llama-3.3-70b-versatile\",\"Temperature\":0.8,\"MaxTokens\":500}',
        'You are a contrarian trading AI. Go against the crowd - buy when others are selling (fear) and sell when others are buying (greed). Look for overreactions and market extremes. Be bold but calculated in your trades.',
        1,
        GETUTCDATE(),
        GETUTCDATE()
    );
    PRINT 'Inserted Llama Contrarian Trader';
END
ELSE
    PRINT 'Llama Contrarian Trader already exists';

-- Agent 5: Llama Balanced Trader
IF NOT EXISTS (SELECT 1 FROM Agents WHERE Name = 'Llama Balanced Trader')
BEGIN
    INSERT INTO Agents (Name, ModelProvider, ModelConfiguration, SystemPrompt, IsActive, CreatedAt, UpdatedAt)
    VALUES (
        'Llama Balanced Trader',
        'Llama',
        '{\"Model\":\"llama-3.3-70b-versatile\",\"Temperature\":0.6,\"MaxTokens\":500}',
        'You are a balanced trading AI. Combine fundamental and technical analysis for well-rounded decisions. Manage risk carefully with diversification and position sizing. Aim for steady, consistent returns rather than high-risk plays.',
        1,
        GETUTCDATE(),
        GETUTCDATE()
    );
    PRINT 'Inserted Llama Balanced Trader';
END
ELSE
    PRINT 'Llama Balanced Trader already exists';

SELECT Id, Name, ModelProvider, IsActive FROM Agents;
"

execute_sql "$AGENT_SQL" || {
    echo -e "${RED}Failed to seed agents${NC}"
    exit 1
}

echo -e "${GREEN}✓ Agents seeded successfully${NC}"
echo ""

# Step 3: Create Portfolios for Each Agent
echo -e "${YELLOW}Step 3: Creating Portfolios for Agents...${NC}"

PORTFOLIO_SQL="
SET NOCOUNT ON;

DECLARE @UsdAssetId INT;
SELECT @UsdAssetId = Id FROM Assets WHERE Symbol = 'USD';

-- Create portfolios for all agents that don't have one
INSERT INTO Portfolios (AgentId, Name, CashBalance, TotalValue, CreatedAt, UpdatedAt)
SELECT 
    a.Id,
    a.Name + ' Portfolio',
    $STARTING_BALANCE,
    $STARTING_BALANCE,
    GETUTCDATE(),
    GETUTCDATE()
FROM Agents a
WHERE NOT EXISTS (
    SELECT 1 FROM Portfolios p WHERE p.AgentId = a.Id
);

PRINT 'Created ' + CAST(@@ROWCOUNT AS VARCHAR) + ' new portfolio(s)';

-- Show all portfolios
SELECT 
    p.Id as PortfolioId,
    a.Name as AgentName,
    p.Name as PortfolioName,
    p.CashBalance,
    p.TotalValue
FROM Portfolios p
JOIN Agents a ON p.AgentId = a.Id;
"

execute_sql "$PORTFOLIO_SQL" || {
    echo -e "${RED}Failed to create portfolios${NC}"
    exit 1
}

echo -e "${GREEN}✓ Portfolios created successfully${NC}"
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Database Seeding Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo "  ✓ Assets: BTC, ETH, USD"
echo "  ✓ Agents: 5 test agents with different strategies"
echo "  ✓ Portfolios: Initial balance of \$$STARTING_BALANCE per agent"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Start the Functions to collect market data: cd AiTradingRace.Functions && func start"
echo "  2. Wait 15-30 minutes for market data to accumulate"
echo "  3. Start the Web API: cd AiTradingRace.Web && dotnet run"
echo "  4. Agents will begin making trading decisions automatically"
echo ""
echo -e "${BLUE}Monitor the race:${NC}"
echo "  • Check logs for agent decisions and trades"
echo "  • View portfolio performance over time"
echo "  • Compare different trading strategies"
echo ""
