# FastAPI ML Service - Architecture Schema

**AI Trading Race - ML Microservice**  
Version: 1.0.0

---

## Overview

Python microservice providing ML-powered trading decisions with explainable AI signals.

**Key Features:** FastAPI, Scikit-learn, Redis idempotency, API key auth, contract versioning

---

## Architecture

```
.NET Backend (C#)
└─ CustomMlAgentModelClient
   │ POST /predict
   │ Headers: X-API-Key, Idempotency-Key
   ↓
FastAPI ML Service (Python)
├─ Middleware: Idempotency → Auth → CORS
├─ DecisionService: Orchestrates predictions
├─ TradingPredictor: Runs ML model / rules
└─ CacheService: Redis idempotency cache
```


---

## Request/Response Flow

```
1. Client → POST /predict
   Headers: X-API-Key, Idempotency-Key
   Body: AgentContextRequest

2. IdempotencyMiddleware
   Check Redis → If cached, return immediately
   
3. AuthMiddleware
   Validate X-API-Key → 401 if invalid

4. DecisionService
   For each asset:
   - Convert candles → DataFrame
   - Compute indicators (RSI, MACD, BB)
   - Call TradingPredictor

5. TradingPredictor
   - Run ML model or rule-based logic
   - Generate explanation signals
   - Return action + confidence

6. Build AgentDecisionResponse
   - Create trade orders
   - Add explanation signals
   - Return JSON response

7. Cache response in Redis (1 hour TTL)
```


---

## API Endpoints

### GET /health

**No authentication required**

**Response:**
```json
{
  "status": "healthy",
  "modelLoaded": true,
  "modelVersion": "1.0.0",
  "schemaVersion": "1.0"
}
```

---

### POST /predict

**Authentication:** `X-API-Key` header required  
**Optional:** `Idempotency-Key` for caching

**Request:**
```json
{
  "agentId": "uuid",
  "portfolio": {
    "cash": 10000.00,
    "totalValue": 15000.00,
    "positions": [{"symbol": "BTC", "quantity": 0.1, "averagePrice": 45000}]
  },
  "candles": [
    {"symbol": "BTC", "timestamp": "2026-01-20T14:00:00Z", 
     "open": 45000, "high": 45500, "low": 44800, "close": 45200, "volume": 1234567}
  ]
}
```

**Response:**
```json
{
  "agentId": "uuid",
  "createdAt": "2026-01-20T14:30:00Z",
  "orders": [
    {"assetSymbol": "BTC", "side": "BUY", "quantity": 0.05, "limitPrice": 45000}
  ],
  "signals": [
    {"feature": "rsi_14", "value": 27.3, "rule": "<30 = oversold", 
     "fired": true, "contribution": "BULLISH"}
  ],
  "reasoning": "BTC: BUY (confidence: 85%)"
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid request
- `401` - Missing/invalid API key
- `500` - Prediction failed
- `503` - Service not ready


---

## Data Models

### AgentContextRequest
```python
class AgentContextRequest(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    agent_id: str
    portfolio: PortfolioState
    candles: list[CandleData]
    instructions: str = ""
```

### AgentDecisionResponse
```python
class AgentDecisionResponse(BaseModel):
    schema_version: str
    model_version: str
    request_id: str
    agent_id: str
    created_at: datetime
    orders: list[TradeOrderResponse]
    signals: list[ExplanationSignal]
    reasoning: str
```

### ExplanationSignal (Explainable AI)
```python
class ExplanationSignal(BaseModel):
    feature: str         # "rsi_14", "macd_diff", etc.
    value: float         # Actual feature value
    rule: str            # "<30 = oversold"
    fired: bool          # True if rule triggered
    contribution: str    # "BULLISH", "BEARISH", "NEUTRAL"
```

**Common Signals:**

| Feature | Rule | Contribution | Meaning |
|---------|------|--------------|---------|
| `rsi_14` | `<30` | BULLISH | Oversold |
| `rsi_14` | `>70` | BEARISH | Overbought |
| `macd_diff` | `>0` | BULLISH | Bullish crossover |
| `macd_diff` | `<0` | BEARISH | Bearish crossover |
| `returns_7` | `>5%` | BULLISH | Strong uptrend |
| `returns_7` | `<-5%` | BEARISH | Strong downtrend |


---

## Middleware Stack

### 1. IdempotencyMiddleware
- **Purpose:** Prevent duplicate ML predictions using Redis cache
- **Header:** `Idempotency-Key`
- **TTL:** 1 hour (3600 seconds)
- **Logic:** Same key within TTL → return cached response

### 2. AuthMiddleware
- **Purpose:** Service-to-service authentication
- **Header:** `X-API-Key`
- **Bypass:** `/health` endpoint
- **Dev Mode:** Empty API key = allow all requests

### 3. CORSMiddleware
- **Purpose:** Cross-origin requests from web frontend
- **Config:** `ML_SERVICE_ALLOWED_ORIGIN` (default: `*`)


---

## ML Pipeline

### Technical Indicators

| Feature | Description | Formula |
|---------|-------------|---------|
| `rsi_14` | Relative Strength Index | RSI = 100 - (100 / (1 + RS)) |
| `macd`, `macd_signal`, `macd_diff` | MACD (12,26,9) | EMA(12) - EMA(26) |
| `bb_upper`, `bb_middle`, `bb_lower` | Bollinger Bands | SMA(20) ± 2*std |
| `bb_width` | BB width % | (upper - lower) / middle |
| `returns_1/7/14/30` | Price returns | (close / close[-n]) - 1 |
| `volume_ratio` | Volume vs avg | volume / SMA(volume, 20) |

**Minimum:** 21 candles required

### Prediction Logic

**ML Model (if exists):**
```python
probas = model.predict_proba(features)  # [0.1, 0.2, 0.7]
action = argmax(probas)                  # BUY
confidence = max(probas)                 # 0.7
```

**Rule-Based Fallback:**
```python
# Count bullish/bearish signals
if bullish_count > bearish_count: BUY
elif bearish_count > bullish_count: SELL
else: HOLD
```

### Order Generation

```python
# 20% of available cash per trade
order_size = portfolio.cash * 0.2
order_quantity = order_size / current_price
limit_price = last_candle.close
```


---

## Configuration

### Environment Variables (prefix: `ML_SERVICE_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PATH` | `models/trading_model.pkl` | Path to ML model |
| `MODEL_VERSION` | `1.0.0` | Model version |
| `API_KEY` | `""` | Authentication key (required in prod) |
| `ALLOWED_ORIGIN` | `*` | CORS origin |
| `REDIS_ENABLED` | `false` | Enable caching |
| `REDIS_HOST` | `localhost` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_TTL_SECONDS` | `3600` | Cache TTL (1 hour) |

### Example .env
```bash
ML_SERVICE_MODEL_PATH=models/trading_model.pkl
ML_SERVICE_API_KEY=your-secret-key
ML_SERVICE_REDIS_ENABLED=true
ML_SERVICE_REDIS_HOST=redis
```


---

## Integration with .NET Backend

### C# Client Configuration
```json
{
  "CustomMlAgent": {
    "BaseUrl": "http://localhost:8000",
    "ApiKey": "your-secret-key",
    "TimeoutSeconds": 30
  }
}
```

### Request Flow (CustomMlAgentModelClient.cs)
```csharp
// 1. Add authentication
httpRequest.Headers.Add("X-API-Key", _options.ApiKey);

// 2. Add idempotency key (format: {agentId}-{timestamp})
var idempotencyKey = $"{agentId}-{lastCandleTimestamp}";
httpRequest.Headers.Add("Idempotency-Key", idempotencyKey);

// 3. Send request
var response = await _httpClient.PostAsJsonAsync("/predict", request);

// 4. Deserialize and map to domain models
var mlResponse = await response.Content.ReadFromJsonAsync<MlDecisionResponse>();
return MapToDecision(agentId, mlResponse);
```

### Docker Deployment
```yaml
services:
  ml-service:
    build: ./ai-trading-race-ml
    ports:
      - "8000:8000"
    environment:
      - ML_SERVICE_API_KEY=${ML_SERVICE_API_KEY}
      - ML_SERVICE_REDIS_ENABLED=true
      - ML_SERVICE_REDIS_HOST=redis
    depends_on:
      - redis
```


---

## Error Handling

| Status | Scenario | Solution |
|--------|----------|----------|
| `200` | Success | - |
| `400` | Invalid request schema | Check request matches `AgentContextRequest` |
| `401` | Missing/invalid API key | Add `X-API-Key` header |
| `500` | Prediction failed | Check logs, verify model |
| `503` | Service not ready | Wait for startup, check `/health` |

---

## Performance & Caching

### Performance Metrics
- Response time: 100-300ms (without cache), 10-20ms (cached)
- Throughput: 100-200 req/s per instance
- Cache hit rate: ~70% in production

### Caching Strategy
- **Key format:** `{agentId}-{lastCandleTimestamp}`
- **TTL:** 1 hour
- **Benefit:** Same agent + same market data = instant response

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run with hot reload
uvicorn app.main:app --reload --port 8000

# Access
# - API: http://localhost:8000
# - Swagger UI: http://localhost:8000/docs
# - OpenAPI: http://localhost:8000/openapi.json
```

---

## Key Files

```
ai-trading-race-ml/
├── app/
│   ├── main.py                    # FastAPI app + endpoints
│   ├── config.py                  # Configuration (pydantic-settings)
│   ├── middleware/
│   │   ├── auth.py                # API key authentication
│   │   └── idempotency.py         # Redis caching
│   ├── ml/
│   │   ├── predictor.py           # ML model + rule-based logic
│   │   └── features.py            # Technical indicators
│   ├── models/
│   │   ├── schemas.py             # Pydantic request/response models
│   │   └── enums.py               # TradeSide, SignalContribution
│   └── services/
│       ├── decision_service.py    # Orchestrates predictions
│       └── cache_service.py       # Redis client
├── models/
│   └── trading_model.pkl          # Trained ML model
└── requirements.txt               # Python dependencies
```

---

**Version:** 1.0.0  
**Maintained By:** AI Trading Race Team
