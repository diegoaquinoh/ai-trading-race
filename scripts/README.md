# Database Scripts

This directory contains scripts for managing the AI Trading Race database.

## Environment Variables

All scripts and Docker Compose now use environment variables for configuration. This improves security and flexibility.

### Setup

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the `.env` file with your values:**
   ```bash
   # At minimum, set a strong SA password
   SA_PASSWORD=YourSecurePassword123!
   ```

3. **Docker Compose automatically reads `.env`** - no need to source it manually for Docker
   ```bash
   docker compose up -d  # Automatically uses .env
   ```

4. **For running scripts, source the environment variables:**
   ```bash
   source .env
   ./scripts/setup-database.sh
   ```

### Supported Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SA_PASSWORD` | `YourStrong!Passw0rd` | SQL Server SA password (⚠️ **REQUIRED**) |
| `SQL_CONTAINER_NAME` | `ai-trading-sqlserver` | Docker container name |
| `SQL_DATABASE_NAME` | `AiTradingRace` | Database name |
| `SQL_SERVER` | `localhost` | SQL Server host |
| `SQL_PORT` | `1433` | SQL Server port |
| `SQL_USER` | `sa` | SQL Server username |
| `STARTING_BALANCE` | `100000.00` | Initial portfolio balance |
| `ML_SERVICE_API_KEY` | `test-api-key-12345` | ML service API key |

> **Note:** Docker Compose automatically reads the `.env` file in the project root. You don't need to source it for Docker commands.

## Scripts

### 1. `setup-database.sh`

Sets up the SQL Server database and applies EF Core migrations.

```bash
# With environment variables
source .env
./scripts/setup-database.sh

# Or inline
SA_PASSWORD='MyPassword123!' ./scripts/setup-database.sh
```

**What it does:**
- Checks if Docker is running
- Verifies SQL Server container is healthy
- Creates the database if it doesn't exist
- Applies EF Core migrations

### 2. `seed-database.sh`

Populates the database with initial test data.

```bash
# With environment variables
source .env
./scripts/seed-database.sh

# Or inline
SA_PASSWORD='MyPassword123!' ./scripts/seed-database.sh
```

**What it does:**
- Adds tradeable assets (BTC, ETH)
- Creates test agents with different AI providers
- Sets up portfolios with starting balance

### 3. `generate-migration-script.sh`

Generates a SQL script from EF Core migrations for manual review/application.

```bash
./scripts/generate-migration-script.sh
```

**What it does:**
- Generates an idempotent SQL script
- Outputs to `database-scripts/migrations.sql`
- Useful for production deployments or manual review

## Complete Workflow

```bash
# 1. Setup environment
cp .env.example .env
nano .env  # Edit SA_PASSWORD

# 2. Start Docker services (automatically uses .env)
docker compose up -d

# 3. Source variables for scripts
source .env

# 4. Setup database
./scripts/setup-database.sh

# 5. Seed with test data
./scripts/seed-database.sh

# 6. Verify
docker exec ai-trading-sqlserver /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$SA_PASSWORD" -C \
  -Q "SELECT name FROM sys.databases WHERE name = 'AiTradingRace';"
```

## Security Best Practices

1. **Never commit `.env` files** - They're already in `.gitignore`
2. **Use strong passwords** - At least 8 characters, mixed case, numbers, symbols
3. **Rotate passwords regularly** - Especially for production environments
4. **Limit access** - Only share credentials with authorized team members
5. **Use different passwords** - Never reuse passwords across environments

## Troubleshooting

### "SA_PASSWORD environment variable is required"

The scripts now validate that `SA_PASSWORD` is set. Make sure you:
```bash
export SA_PASSWORD='YourPassword'
```

Or source your `.env` file:
```bash
source .env
```

### "Docker is not running"

Start Docker Desktop and wait for it to be ready:
```bash
docker ps  # Should show running containers
```

### "SQL Server container is not healthy"

Check container logs:
```bash
docker logs ai-trading-sqlserver
```

Wait a few seconds and try again - SQL Server takes time to start.

### Connection Issues

Verify the connection string matches your environment variables:
```bash
echo "Server=$SQL_SERVER,$SQL_PORT;Database=$SQL_DATABASE_NAME;User Id=$SQL_USER;Password=$SA_PASSWORD"
```

## CI/CD Integration

For automated workflows, set environment variables in your CI/CD platform:

**GitHub Actions:**
```yaml
env:
  SA_PASSWORD: ${{ secrets.SA_PASSWORD }}
  SQL_DATABASE_NAME: AiTradingRace_Test
```

**Azure Pipelines:**
```yaml
variables:
  - name: SA_PASSWORD
    value: $(SA_PASSWORD_SECRET)
```

Then scripts will automatically use these values.
