# ML Service Deployment Guide

## 📦 Sprint 8.5 - ML Service & Redis Integration

This guide covers the deployment of the Python ML service with Redis-backed idempotency caching.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    .NET Backend                          │
│         (CustomMlAgentModelClient)                       │
│                                                          │
│  • Generates idempotency keys                            │
│  • Sends Idempotency-Key header                          │
│  • Retries safe with cached responses                    │
└───────────────────┬──────────────────────────────────────┘
                    │
                    │ HTTP POST /predict
                    │ Headers: X-API-Key, Idempotency-Key
                    ▼
┌─────────────────────────────────────────────────────────┐
│              Python ML Service (FastAPI)                 │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │     IdempotencyMiddleware                  │         │
│  │  • Check Redis for cached response         │         │
│  │  • Return cached if found (cache hit)      │         │
│  │  • Process request if not found (miss)     │         │
│  │  • Cache successful responses (2xx)        │         │
│  └────────────────┬───────────────────────────┘         │
│                   │                                      │
│                   ▼                                      │
│  ┌────────────────────────────────────────────┐         │
│  │     TradingPredictor (ML Model)            │         │
│  │  • Generate trading decision               │         │
│  │  • Return orders + reasoning               │         │
│  └────────────────────────────────────────────┘         │
│                                                          │
└───────────────────┬──────────────────────────────────────┘
                    │
                    │ Cache SET (if cache miss)
                    ▼
┌─────────────────────────────────────────────────────────┐
│              Redis Cache (Port 6379)                     │
│                                                          │
│  Key format: idempotency:{key}                           │
│  Value: JSON response (body + headers + status)          │
│  TTL: 1 hour (configurable)                              │
│                                                          │
│  Cache Hit Rate Target: > 80% for duplicate requests     │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Local Development Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local dev without Docker)
- Redis (via Docker or local install)

### Option 1: Docker Compose (Recommended)

```bash
# Build and start all services
docker-compose up --build

# Check service health
curl http://localhost:8000/health

# Test Redis connection
docker exec ai-trading-redis redis-cli ping
# Should return: PONG

# View logs
docker-compose logs -f ml-service
docker-compose logs -f redis

# Stop services
docker-compose down

# Stop and remove volumes (clears Redis cache)
docker-compose down -v
```

### Option 2: Local Python Development

```bash
cd ai-trading-race-ml

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Redis (separate terminal)
docker run --name redis -p 6379:6379 -d redis:7-alpine

# Copy environment template
cp .env.example .env

# Edit .env and set:
# - ML_SERVICE_API_KEY=your-secret-key
# - ML_SERVICE_REDIS_ENABLED=true

# Run service
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Test endpoints
curl http://localhost:8000/health
```

## 🧪 Testing Idempotency

### Test 1: Basic Cache Hit

```bash
# First request (cache miss - will process)
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: $ML_SERVICE_API_KEY" \
  -H "Idempotency-Key: test-request-001" \
  -H "Content-Type: application/json" \
  -d @test_request.json

# Second request with same key (cache hit - instant response)
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: $ML_SERVICE_API_KEY" \
  -H "Idempotency-Key: test-request-001" \
  -H "Content-Type: application/json" \
  -d @test_request.json

# Check logs - should see "Cache HIT" message
```

### Test 2: Cache Miss with Different Key

```bash
# Different idempotency key = new request
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: $ML_SERVICE_API_KEY" \
  -H "Idempotency-Key: test-request-002" \
  -H "Content-Type: application/json" \
  -d @test_request.json

# Should see "Cache MISS" and process new request
```

### Test 3: No Idempotency Key

```bash
# Request without idempotency key - always processes
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: $ML_SERVICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d @test_request.json

# Each request will be processed (no caching)
```

### Test 4: Verify Redis Cache

```bash
# Connect to Redis CLI
docker exec -it ai-trading-redis redis-cli

# List all idempotency keys
KEYS idempotency:*

# Get cached value
GET idempotency:test-request-001

# Check TTL (time to live)
TTL idempotency:test-request-001

# Manual cache invalidation
DEL idempotency:test-request-001
```

## 📊 Monitoring & Metrics

### Key Metrics to Track

| Metric                  | Target     | Description                          |
| ----------------------- | ---------- | ------------------------------------ |
| Cache Hit Rate          | > 80%      | % of requests served from cache      |
| Cache Miss Rate         | < 20%      | % of requests requiring processing   |
| Response Time (hit)     | < 10ms     | Cached response latency              |
| Response Time (miss)    | < 500ms    | ML inference latency                 |
| Redis Connection Errors | 0          | Redis connectivity issues            |
| Failed Cache Writes     | < 1%       | Errors storing in Redis              |

### Health Check Endpoints

```bash
# Service health
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "model_loaded": true,
  "model_version": "1.0.0",
  "schema_version": "1.0"
}
```

### Log Analysis

```bash
# Check cache hit rate
docker-compose logs ml-service | grep "Cache HIT" | wc -l
docker-compose logs ml-service | grep "Cache MISS" | wc -l

# Check Redis connection status
docker-compose logs ml-service | grep "Redis cache connected"

# Check for errors
docker-compose logs ml-service | grep "ERROR"
```

## 🔧 Configuration

### Environment Variables

| Variable                          | Default        | Description                      |
| --------------------------------- | -------------- | -------------------------------- |
| `ML_SERVICE_MODEL_PATH`           | `models/...`   | Path to ML model file            |
| `ML_SERVICE_MODEL_VERSION`        | `1.0.0`        | Model version for tracking       |
| `ML_SERVICE_LOG_LEVEL`            | `INFO`         | Logging level                    |
| `ML_SERVICE_API_KEY`              | (required)     | API key for authentication       |
| `ML_SERVICE_ALLOWED_ORIGIN`       | `*`            | CORS allowed origins             |
| `ML_SERVICE_REDIS_ENABLED`        | `false`        | Enable/disable Redis caching     |
| `ML_SERVICE_REDIS_HOST`           | `localhost`    | Redis server hostname            |
| `ML_SERVICE_REDIS_PORT`           | `6379`         | Redis server port                |
| `ML_SERVICE_REDIS_DB`             | `0`            | Redis database number            |
| `ML_SERVICE_REDIS_PASSWORD`       | (optional)     | Redis authentication password    |
| `ML_SERVICE_REDIS_TTL_SECONDS`    | `3600`         | Cache TTL (1 hour)               |

### .NET Backend Configuration

Update `appsettings.json`:

```json
{
  "CustomMlAgent": {
    "BaseUrl": "http://localhost:8000",
    "ApiKey": "$ML_SERVICE_API_KEY",
    "TimeoutSeconds": 60
  }
}
```

For Docker Compose integration:

```json
{
  "CustomMlAgent": {
    "BaseUrl": "http://ml-service:8000",
    "ApiKey": "${ML_SERVICE_API_KEY}",
    "TimeoutSeconds": 60
  }
}
```

## 🐳 Docker Build

### Build Image

```bash
cd ai-trading-race-ml

# Build with tag
docker build -t ai-trading-ml:latest .

# Build with version
docker build -t ai-trading-ml:1.0.0 .

# Check image size
docker images | grep ai-trading-ml
# Target: < 500 MB
```

### Run Container

```bash
# Run with environment variables
docker run -d \
  --name ml-service \
  -p 8000:8000 \
  -e ML_SERVICE_API_KEY=your-secret-key \
  -e ML_SERVICE_REDIS_ENABLED=true \
  -e ML_SERVICE_REDIS_HOST=redis \
  ai-trading-ml:latest

# Check logs
docker logs -f ml-service

# Execute commands in container
docker exec -it ml-service bash

# Stop container
docker stop ml-service
docker rm ml-service
```

## 🔐 Security Best Practices

### 1. API Key Management

```bash
# Generate secure API key
openssl rand -hex 32

# Store in environment (never commit to git)
export ML_SERVICE_API_KEY=<generated-key>

# Use same key in .NET appsettings (or Azure Key Vault)
```

### 2. Redis Security

```bash
# Use password in production
docker run -d \
  --name redis \
  redis:7-alpine \
  redis-server --requirepass your-redis-password

# Update ML service env
ML_SERVICE_REDIS_PASSWORD=your-redis-password
```

### 3. Network Isolation

```yaml
# docker-compose.yml
networks:
  ai-trading-network:
    driver: bridge
    internal: true  # Isolate from external access
```

## 🚀 Production Deployment (Future - Azure)

### Azure Container Apps

```bash
# Login to Azure
az login

# Create Container Apps environment
az containerapp env create \
  --name ml-service-env \
  --resource-group rg-ai-trading-race-prod \
  --location westeurope

# Deploy container
az containerapp create \
  --name ml-service \
  --resource-group rg-ai-trading-race-prod \
  --environment ml-service-env \
  --image <registry>/ai-trading-ml:latest \
  --target-port 8000 \
  --ingress external \
  --env-vars \
    ML_SERVICE_API_KEY=secretref:ml-api-key \
    ML_SERVICE_REDIS_ENABLED=true \
    ML_SERVICE_REDIS_HOST=<redis-host>
```

### Azure Cache for Redis

```bash
# Create Redis cache
az redis create \
  --name redis-ai-trading-race \
  --resource-group rg-ai-trading-race-prod \
  --location westeurope \
  --sku Basic \
  --vm-size C0

# Get connection string
az redis list-keys \
  --name redis-ai-trading-race \
  --resource-group rg-ai-trading-race-prod
```

## 📈 Performance Optimization

### 1. Cache Hit Rate Optimization

- Use consistent idempotency key format
- Round timestamps to reduce uniqueness
- Increase TTL for stable predictions
- Monitor cache statistics

### 2. Redis Connection Pooling

Already implemented via `redis.Redis` client with automatic connection pooling.

### 3. ML Model Optimization

- Use quantized models (smaller size)
- Cache model predictions
- Batch predictions if possible

## 🐛 Troubleshooting

### Redis Connection Failed

```bash
# Check Redis is running
docker ps | grep redis

# Test connection
docker exec ai-trading-redis redis-cli ping

# Check network connectivity
docker exec ml-service ping redis

# View Redis logs
docker logs ai-trading-redis
```

### Cache Not Working

```bash
# Verify Redis is enabled
docker exec ml-service env | grep REDIS

# Check cache service logs
docker-compose logs ml-service | grep -i redis

# Test cache manually
docker exec -it ai-trading-redis redis-cli
> SET test-key "test-value"
> GET test-key
> DEL test-key
```

### High Memory Usage

```bash
# Check Redis memory
docker exec ai-trading-redis redis-cli INFO memory

# Clear all cache
docker exec ai-trading-redis redis-cli FLUSHDB

# Monitor memory usage
docker stats ai-trading-redis
```

## ✅ Verification Checklist

Sprint 8.5 complete when:

- [ ] Redis runs in Docker container
- [ ] ML service connects to Redis successfully
- [ ] IdempotencyMiddleware caches responses
- [ ] .NET client sends Idempotency-Key headers
- [ ] Cache hit returns instant response (< 10ms)
- [ ] Cache miss processes and caches result
- [ ] TTL expires cached entries after 1 hour
- [ ] Docker Compose starts all services
- [ ] Health check passes for both services
- [ ] Tests verify cache behavior

---

**Created**: January 20, 2026  
**Phase**: 8 - Deployment & CI/CD  
**Sprint**: 8.5 - ML Service & Redis ✅  
**Status**: Complete (Local/Docker deployment ready)
