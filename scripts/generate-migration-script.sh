#!/bin/bash

# Generate SQL Migration Script from EF Core Migrations
# This script generates a SQL file that can be reviewed and applied manually

set -e

echo "🔨 Generating SQL Migration Script for AI Trading Race"
echo "======================================================="
echo ""

# Check if dotnet is installed
if ! command -v dotnet &> /dev/null; then
    echo "❌ Error: .NET SDK is not installed or not in PATH"
    echo "   Install from: https://dotnet.microsoft.com/download"
    exit 1
fi

# Check if Entity Framework tools are installed
if ! dotnet ef --version &> /dev/null; then
    echo "📦 Installing Entity Framework Core tools..."
    dotnet tool install --global dotnet-ef
    echo ""
fi

# Project paths
INFRASTRUCTURE_PROJECT="AiTradingRace.Infrastructure/AiTradingRace.Infrastructure.csproj"
WEB_PROJECT="AiTradingRace.Web/AiTradingRace.Web.csproj"
OUTPUT_DIR="database-scripts"
OUTPUT_FILE="$OUTPUT_DIR/migrations.sql"

# Check if projects exist
if [ ! -f "$INFRASTRUCTURE_PROJECT" ]; then
    echo "❌ Error: Infrastructure project not found at $INFRASTRUCTURE_PROJECT"
    exit 1
fi

if [ ! -f "$WEB_PROJECT" ]; then
    echo "❌ Error: Web project not found at $WEB_PROJECT"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "📝 Generating SQL script..."
echo "   From: Initial → Latest migration"
echo "   Output: $OUTPUT_FILE"
echo ""

# Generate SQL script from migrations
dotnet ef migrations script \
    --project "$INFRASTRUCTURE_PROJECT" \
    --startup-project "$WEB_PROJECT" \
    --output "$OUTPUT_FILE" \
    --idempotent \
    --context TradingDbContext

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SQL migration script generated successfully!"
    echo ""
    echo "📄 Script location: $OUTPUT_FILE"
    echo ""
    echo "Next steps:"
    echo "1. Review the generated SQL script"
    echo "2. Apply to database:"
    echo "   - Docker: docker exec -i ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P 'YourStrong!Passw0rd' -d AiTradingRace < $OUTPUT_FILE"
    echo "   - Local: sqlcmd -S localhost -U sa -P 'YourStrong!Passw0rd' -d AiTradingRace -i $OUTPUT_FILE"
    echo "   - Or use dotnet ef database update"
else
    echo ""
    echo "❌ Failed to generate SQL script"
    echo "   Check the error messages above"
    exit 1
fi
