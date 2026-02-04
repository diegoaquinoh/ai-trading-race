# Database Setup Guide

## Overview

The AI Trading Race uses SQL Server for data persistence. This guide covers local development setup, connection strings, migrations, and troubleshooting.

## Quick Start

### 1. Start SQL Server (Docker)

```bash
cd .
docker-compose up -d sqlserver
```

### 2. Initialize Database

```bash
./scripts/setup-database.sh
```

### 3. Seed Test Data

```bash
./scripts/seed-database.sh
```

That's it! Your database is ready with:
- ✅ Schema created (migrations applied)
- ✅ Assets: BTC, ETH, USD
- ✅ 5 test agents with different strategies
- ✅ Portfolios with $100,000 starting balance

---

## Connection Strings

### Local Development (Host Machine)

Use when running applications **outside Docker** but SQL Server **in Docker**:

```
Server=localhost,1433;Database=AiTradingRaceDb;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True;
```

**When to use:**
- Running `dotnet run` from host machine
- Visual Studio or VS Code debugging
- Running tests locally

### Docker Internal (Container-to-Container)

Use when running applications **inside Docker containers**:

```
Server=sqlserver,1433;Database=AiTradingRaceDb;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True;
```

**When to use:**
- Docker Compose with multiple services
- Containerized applications
- CI/CD pipelines

### External SQL Server

Use when connecting to a remote SQL Server instance:

```
Server=your-server.database.windows.net,1433;Database=AiTradingRaceDb;User Id=your-user;Password=your-password;Encrypt=True;TrustServerCertificate=False;
```

**When to use:**
- Azure SQL Database
- Remote SQL Server instances
- Production deployments

---

## Configuration by Service

### AiTradingRace.Web (.NET API)

**File:** `AiTradingRace.Web/appsettings.Development.json`

```json
{
  "ConnectionStrings": {
    "DefaultConnection": "Server=localhost,1433;Database=AiTradingRaceDb;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True;"
  }
}
```

**Environment Variable:**
```bash
export ConnectionStrings__DefaultConnection="Server=localhost,1433;..."
```

### AiTradingRace.Functions (Azure Functions)

**File:** `AiTradingRace.Functions/local.settings.json`

```json
{
  "Values": {
    "SqlConnectionString": "Server=localhost,1433;Database=AiTradingRaceDb;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True;"
  }
}
```

**Environment Variable:**
```bash
export SqlConnectionString="Server=localhost,1433;..."
```

### Docker Compose

**File:** `docker-compose.yml`

```yaml
services:
  sqlserver:
    environment:
      - ACCEPT_EULA=Y
      - SA_PASSWORD=$SA_PASSWORD
      - MSSQL_PID=Express
```

---

## Database Scripts

### setup-database.sh

**Purpose:** Initialize database schema from EF Core migrations

**Usage:**
```bash
# Basic usage (uses defaults)
./scripts/setup-database.sh

# Custom connection
./scripts/setup-database.sh --server localhost --port 1433 --database MyDb --user sa --password MyPass

# Inside Docker container
./scripts/setup-database.sh --docker
```

**What it does:**
1. Checks if SQL Server is running (Docker or host)
2. Waits for SQL Server health check (up to 60 seconds)
3. Creates database if it doesn't exist
4. Applies EF Core migrations
5. Outputs connection string for verification

**Requirements:**
- Docker (for containerized SQL Server) OR
- `sqlcmd` (for host SQL Server)
- `dotnet` CLI with EF Core tools (for migrations)

### seed-database.sh

**Purpose:** Populate database with initial test data

**Usage:**
```bash
# Basic usage (uses defaults)
./scripts/seed-database.sh

# Custom starting balance
./scripts/seed-database.sh --balance 50000

# Custom connection
./scripts/seed-database.sh --server localhost --database MyDb --user sa --password MyPass

# Inside Docker container
./scripts/seed-database.sh --docker
```

**What it seeds:**
- **Assets:** BTC (Bitcoin), ETH (Ethereum), USD (US Dollar)
- **Agents:** 5 test agents with different strategies:
  1. Llama Momentum Trader (follows trends)
  2. Llama Value Investor (long-term holder)
  3. CustomML Technical Analyst (ML predictions)
  4. Llama Contrarian Trader (goes against crowd)
  5. Llama Balanced Trader (risk-managed)
- **Portfolios:** Starting balance of $100,000 per agent

**Requirements:**
- Database must exist (run `setup-database.sh` first)
- Docker (for containerized SQL Server) OR `sqlcmd`

### generate-migration-script.sh

**Purpose:** Generate idempotent SQL script from EF Core migrations

**Usage:**
```bash
# Generate SQL script
./scripts/generate-migration-script.sh

# Output: database-scripts/migrations.sql
```

**What it does:**
1. Checks for `dotnet` CLI and EF Core tools
2. Generates SQL script from all migrations
3. Creates idempotent script (safe to run multiple times)
4. Saves to `database-scripts/migrations.sql`

**Use cases:**
- Manual review of schema changes
- Deployment to production (DBA review)
- Version control of SQL changes
- Environments without EF Core tools

**Requirements:**
- `dotnet` CLI (7.0 or 8.0)
- `dotnet ef` tools: `dotnet tool install --global dotnet-ef`

---

## Database Migrations

### Creating a New Migration

```bash
cd AiTradingRace.Infrastructure

# Add new migration
dotnet ef migrations add YourMigrationName --startup-project ../AiTradingRace.Web

# Review the migration files in Migrations/ folder
```

### Applying Migrations

**Option 1: EF Core (Automatic)**
```bash
cd AiTradingRace.Web
dotnet ef database update --project ../AiTradingRace.Infrastructure
```

**Option 2: Shell Script (Recommended)**
```bash
./scripts/setup-database.sh
```

**Option 3: SQL Script (Production)**
```bash
# Generate script
./scripts/generate-migration-script.sh

# Review script
cat database-scripts/migrations.sql

# Apply manually or via deployment pipeline
sqlcmd -S localhost,1433 -U sa -P $SA_PASSWORD -i database-scripts/migrations.sql
```

### Rolling Back Migrations

```bash
cd AiTradingRace.Web

# List migrations
dotnet ef migrations list --project ../AiTradingRace.Infrastructure

# Rollback to specific migration
dotnet ef database update PreviousMigrationName --project ../AiTradingRace.Infrastructure

# Remove last migration (if not applied)
dotnet ef migrations remove --project ../AiTradingRace.Infrastructure
```

---

## Database Schema

### Core Tables

#### Assets
- **Purpose:** Tradeable cryptocurrencies and currencies
- **Key Fields:** `Symbol` (BTC, ETH), `Name`, `AssetType` (Crypto/Fiat), `IsActive`
- **Relationships:** Referenced by `Candles`, `PortfolioHoldings`, `Trades`

#### Agents
- **Purpose:** AI trading agents with different strategies
- **Key Fields:** `Name`, `ModelProvider` (Llama/CustomMl/Mock), `SystemPrompt`, `ModelConfiguration`
- **Relationships:** Has one `Portfolio`, has many `AgentDecisions`, `Trades`

#### Portfolios
- **Purpose:** Agent's asset holdings and cash balance
- **Key Fields:** `AgentId`, `CashBalance`, `TotalValue`
- **Relationships:** Belongs to `Agent`, has many `PortfolioHoldings`, `Trades`, `EquitySnapshots`

#### Candles
- **Purpose:** OHLCV market data at 15-minute intervals
- **Key Fields:** `AssetId`, `Timestamp`, `Open`, `High`, `Low`, `Close`, `Volume`
- **Relationships:** Belongs to `Asset`
- **Indexes:** `(AssetId, Timestamp)` for efficient queries

#### Trades
- **Purpose:** Trade execution history
- **Key Fields:** `PortfolioId`, `AssetId`, `TradeType` (Buy/Sell), `Quantity`, `Price`, `TotalValue`
- **Relationships:** Belongs to `Portfolio` and `Asset`

#### AgentDecisions
- **Purpose:** AI decision-making history
- **Key Fields:** `AgentId`, `ModelProvider`, `Decision` (JSON), `Reasoning`, `ExecutionTimeMs`
- **Relationships:** Belongs to `Agent`

#### EquitySnapshots
- **Purpose:** Daily portfolio value tracking
- **Key Fields:** `PortfolioId`, `Timestamp`, `TotalEquity`
- **Relationships:** Belongs to `Portfolio`
- **Purpose:** Track portfolio performance over time

---

## Troubleshooting

### Cannot Connect to SQL Server

**Symptoms:**
```
A network-related or instance-specific error occurred while establishing a connection to SQL Server.
```

**Solutions:**

1. **Check if SQL Server is running:**
   ```bash
   docker ps | grep sqlserver
   # Should show: ai-trading-sqlserver
   ```

2. **Start SQL Server:**
   ```bash
   docker-compose up -d sqlserver
   ```

3. **Check SQL Server logs:**
   ```bash
   docker logs ai-trading-sqlserver
   # Look for: "SQL Server is now ready for client connections"
   ```

4. **Verify connection:**
   ```bash
   # Via Docker
   docker exec -it ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd \
     -S localhost -U sa -P '$SA_PASSWORD' -Q "SELECT @@VERSION"
   
   # Via host (if sqlcmd installed)
   sqlcmd -S localhost,1433 -U sa -P '$SA_PASSWORD' -Q "SELECT @@VERSION"
   ```

### Database Does Not Exist

**Symptoms:**
```
Cannot open database "AiTradingRaceDb" requested by the login.
```

**Solution:**
```bash
./scripts/setup-database.sh
```

### Login Failed for User 'sa'

**Symptoms:**
```
Login failed for user 'sa'. Reason: Password did not match that for the login provided.
```

**Solution:**
1. Check password in connection string matches SQL Server password
2. Default password: `$SA_PASSWORD`
3. Password set in `docker-compose.yml` under `sqlserver.environment.SA_PASSWORD`

### Migrations Not Applied

**Symptoms:**
```
Invalid object name 'Agents'.
```

**Solution:**
```bash
# Apply migrations
cd AiTradingRace.Web
dotnet ef database update --project ../AiTradingRace.Infrastructure

# Or use script
./scripts/setup-database.sh
```

### Port 1433 Already in Use

**Symptoms:**
```
Error starting userland proxy: listen tcp4 0.0.0.0:1433: bind: address already in use
```

**Solution:**

1. **Find process using port:**
   ```bash
   lsof -i :1433
   ```

2. **Stop conflicting service:**
   ```bash
   # If another SQL Server instance
   sudo systemctl stop mssql-server  # Linux
   # or stop from Services on Windows
   ```

3. **Change port in docker-compose.yml:**
   ```yaml
   sqlserver:
     ports:
       - "1434:1433"  # Map host:1434 to container:1433
   ```
   
   Then update connection strings to use port `1434`.

### SSL Certificate Error

**Symptoms:**
```
A connection was successfully established with the server, but then an error occurred during the login process.
```

**Solution:**
Add `TrustServerCertificate=True` to connection string:
```
Server=localhost,1433;Database=AiTradingRaceDb;User Id=sa;Password=$SA_PASSWORD;TrustServerCertificate=True;
```

### Performance Issues

**Symptoms:**
- Slow queries
- High CPU usage
- Timeout errors

**Solutions:**

1. **Check indexes:**
   ```sql
   -- Missing indexes
   SELECT * FROM sys.dm_db_missing_index_details;
   ```

2. **Optimize queries:**
   - Use `AsNoTracking()` for read-only queries
   - Add proper indexes on foreign keys
   - Limit result sets with pagination

3. **Monitor performance:**
   ```sql
   -- Long-running queries
   SELECT 
       r.session_id,
       r.start_time,
       r.total_elapsed_time,
       t.text
   FROM sys.dm_exec_requests r
   CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
   WHERE r.database_id = DB_ID('AiTradingRaceDb')
   ORDER BY r.total_elapsed_time DESC;
   ```

---

## Backup and Restore

### Backup Database

```bash
# Create backup
docker exec ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P '$SA_PASSWORD' \
  -Q "BACKUP DATABASE AiTradingRaceDb TO DISK='/var/opt/mssql/data/AiTradingRaceDb.bak'"

# Copy backup to host
docker cp ai-trading-sqlserver:/var/opt/mssql/data/AiTradingRaceDb.bak ./backups/
```

### Restore Database

```bash
# Copy backup to container
docker cp ./backups/AiTradingRaceDb.bak ai-trading-sqlserver:/var/opt/mssql/data/

# Restore backup
docker exec ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P '$SA_PASSWORD' \
  -Q "RESTORE DATABASE AiTradingRaceDb FROM DISK='/var/opt/mssql/data/AiTradingRaceDb.bak' WITH REPLACE"
```

---

## Security Best Practices

### Development

✅ **DO:**
- Use `.env.example` templates
- Add `.env` and `local.settings.json` to `.gitignore`
- Rotate passwords regularly
- Use strong passwords (min 8 chars, uppercase, lowercase, digits, symbols)

❌ **DON'T:**
- Commit passwords to Git
- Use default passwords in production
- Share connection strings publicly
- Use `sa` account in production

### Production

✅ **DO:**
- Use managed identity or Azure Key Vault
- Enable SSL/TLS encryption (`Encrypt=True`)
- Use least-privilege database users
- Enable audit logging
- Regular backups with retention policy
- Network isolation (private endpoints)

❌ **DON'T:**
- Use SQL authentication (prefer Windows/Azure AD auth)
- Expose database ports publicly
- Store connection strings in code
- Disable encryption

---

## Additional Resources

- [Entity Framework Core Documentation](https://learn.microsoft.com/en-us/ef/core/)
- [SQL Server in Docker](https://learn.microsoft.com/en-us/sql/linux/quickstart-install-connect-docker)
- [Connection String Reference](https://www.connectionstrings.com/sql-server/)
- [EF Core Migrations](https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/)

---

## Quick Reference

| Task | Command |
|------|---------|
| Start SQL Server | `docker-compose up -d sqlserver` |
| Stop SQL Server | `docker-compose stop sqlserver` |
| Initialize Database | `./scripts/setup-database.sh` |
| Seed Test Data | `./scripts/seed-database.sh` |
| Add Migration | `dotnet ef migrations add <Name> --startup-project ../AiTradingRace.Web` |
| Apply Migrations | `dotnet ef database update --project ../AiTradingRace.Infrastructure` |
| Generate SQL Script | `./scripts/generate-migration-script.sh` |
| View Logs | `docker logs ai-trading-sqlserver` |
| SQL Shell | `docker exec -it ai-trading-sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P '$SA_PASSWORD'` |
| Backup Database | See [Backup and Restore](#backup-and-restore) section |

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review SQL Server logs: `docker logs ai-trading-sqlserver`
3. Verify connection strings match your environment
4. Ensure all prerequisites are installed (`dotnet`, `docker`, `sqlcmd`)

