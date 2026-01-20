#!/bin/bash

# Database Setup Script
# Sets up the SQL Server database in Docker and applies migrations

set -e

echo "🗄️  AI Trading Race - Database Setup"
echo "====================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="ai-trading-sqlserver"
SA_PASSWORD="YourStrong!Passw0rd"
DB_NAME="AiTradingRace"

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker is not running${NC}"
    echo "   Please start Docker and try again"
    exit 1
fi

# Check if SQL Server container exists
if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}📦 SQL Server container not found${NC}"
    echo "   Starting docker-compose services..."
    docker-compose up -d sqlserver
    echo ""
    echo "⏳ Waiting for SQL Server to be ready (30 seconds)..."
    sleep 30
fi

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}🔄 SQL Server container is stopped, starting...${NC}"
    docker start $CONTAINER_NAME
    sleep 15
fi

# Wait for SQL Server to be healthy
echo "🏥 Checking SQL Server health..."
MAX_RETRIES=30
RETRY=0

while [ $RETRY -lt $MAX_RETRIES ]; do
    if docker exec $CONTAINER_NAME /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -C -Q "SELECT 1" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ SQL Server is healthy${NC}"
        break
    fi
    
    RETRY=$((RETRY+1))
    if [ $RETRY -eq $MAX_RETRIES ]; then
        echo -e "${RED}❌ SQL Server failed to become healthy after $MAX_RETRIES attempts${NC}"
        echo "   Check logs: docker logs $CONTAINER_NAME"
        exit 1
    fi
    
    echo "   Waiting... ($RETRY/$MAX_RETRIES)"
    sleep 2
done

echo ""

# Create database if it doesn't exist
echo "📊 Creating database '$DB_NAME' if not exists..."
docker exec $CONTAINER_NAME /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -C -Q "
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = '$DB_NAME')
BEGIN
    CREATE DATABASE [$DB_NAME];
    SELECT 'Database created' AS Status;
END
ELSE
BEGIN
    SELECT 'Database already exists' AS Status;
END
" 2>&1 | grep -v "Changed database context"

echo ""

# Check if dotnet is available for migrations
if command -v dotnet &> /dev/null; then
    echo "🔨 Applying EF Core migrations..."
    
    # Check if we're in the project root
    if [ -f "AiTradingRace.sln" ]; then
        dotnet ef database update \
            --project AiTradingRace.Infrastructure/AiTradingRace.Infrastructure.csproj \
            --startup-project AiTradingRace.Web/AiTradingRace.Web.csproj \
            --context TradingDbContext \
            --connection "Server=localhost,1433;Database=$DB_NAME;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True"
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ Migrations applied successfully${NC}"
        else
            echo -e "${YELLOW}⚠️  Migration failed - you may need to apply manually${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Not in project root directory, skipping migrations${NC}"
        echo "   Run this script from the project root, or apply migrations manually"
    fi
else
    echo -e "${YELLOW}⚠️  .NET SDK not found, skipping migrations${NC}"
    echo "   Install .NET SDK or use the generated SQL script"
    echo "   See: scripts/generate-migration-script.sh"
fi

echo ""
echo "================================================"
echo -e "${GREEN}✅ Database setup complete!${NC}"
echo ""
echo "📌 Connection Info:"
echo "   Server: localhost,1433"
echo "   Database: $DB_NAME"
echo "   User: sa"
echo "   Password: $SA_PASSWORD"
echo ""
echo "🔗 Connection String:"
echo "   Server=localhost,1433;Database=$DB_NAME;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True"
echo ""
echo "📝 Next Steps:"
echo "   1. Run seed data: scripts/seed-database.sh"
echo "   2. Start backend: dotnet run --project AiTradingRace.Web"
echo "   3. Test connection: docker exec -it $CONTAINER_NAME /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P '$SA_PASSWORD'"
echo ""
