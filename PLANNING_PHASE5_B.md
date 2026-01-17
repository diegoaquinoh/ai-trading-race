# Phase 5b – Custom ML Model Integration (Python + FastAPI)

> **Objective:** Create a trading agent powered by a custom ML model (scikit-learn → PyTorch), exposed via a Python FastAPI service.

> **Prerequisites:** Phase 5 completed ✅ (LLM agent integration with `IAgentModelClient`, `AgentRunner`, risk validation)

> **Date:** 17/01/2026

---

## Architecture Overview

```
┌─────────────────────────┐       HTTP/REST        ┌────────────────────────────┐
│   .NET Application      │  ───────────────────►  │   Python FastAPI           │
│   (AiTradingRace)       │                        │   (ML Model Service)       │
│                         │  ◄───────────────────  │   - scikit-learn           │
│   CustomMlAgentClient   │      JSON Response     │   - PyTorch                │
│   implements            │                        │   - pandas                 │
│   IAgentModelClient     │                        │   - Technical indicators   │
└─────────────────────────┘                        └────────────────────────────┘
        ▲                                                     ▲
        │                                                     │
        │ Uses existing                                       │ Trained on
        │ AgentRunner +                                       │ historical
        │ RiskValidator                                       │ MarketCandle data
        ▼                                                     ▼
┌─────────────────────────┐                        ┌────────────────────────────┐
│   PortfolioService      │                        │   Training Pipeline        │
│   EquityService         │                        │   - Feature engineering    │
│   (Phase 4)             │                        │   - Model training         │
└─────────────────────────┘                        │   - Model persistence      │
                                                   └────────────────────────────┘
```

---

## Production Enhancements (Cross-Phase)

> [!IMPORTANT]
> The following 5 enhancements improve reliability, security, and explainability across the .NET ↔ Python integration.

| Enhancement                   | Phase | Rationale                                   |
| ----------------------------- | ----- | ------------------------------------------- |
| **Contract Versioning**       | 5b    | Low complexity, essential for API evolution |
| **Structured Explainability** | 5b    | ML-specific, enables decision auditability  |
| **API Key Security**          | 5b    | Simple auth for service-to-service calls    |
| **Idempotency**               | 8     | Requires cache infrastructure (Redis)       |
| **Observability**             | 9     | OpenTelemetry, monitoring phase             |

### Implemented in Phase 5b

#### 1. Contract Versioning

Add version fields to all API contracts for safe evolution:

- `schemaVersion`: API schema version (e.g., "1.0")
- `modelVersion`: ML model version (e.g., "v1.2.0")
- `requestId`: Unique request identifier for tracing

#### 2. Structured Explainability

Replace `reasoning: str` with structured signals:

```python
class ExplanationSignal(BaseModel):
    feature: str           # e.g., "rsi_14"
    value: float           # e.g., 27.3
    rule: str              # e.g., "<30 = oversold"
    fired: bool            # True if rule triggered
    contribution: str      # "bullish" | "bearish" | "neutral"

signals: list[ExplanationSignal]  # Replaces reasoning string
```

#### 3. API Key Security

Simple service-to-service authentication:

- Python: `X-API-Key` header validation middleware
- .NET: API key from `appsettings.json` sent with requests
- Reject requests without valid key (401 Unauthorized)

### Deferred to Later Phases

#### Phase 8: Idempotency

- `Idempotency-Key` header for retry safety
- Cache layer (Redis) stores `(key -> response)` with TTL
- Prevents duplicate decision generation on .NET retries

#### Phase 9: Observability

- OpenTelemetry tracing across .NET ↔ Python
- `X-Request-Id` / `traceparent` header propagation
- Metrics: latency, error rate, action distribution (BUY/SELL/HOLD)

---

## Current State Audit

### What Already Exists ✅

| Component                | Location                     | Status                                     |
| ------------------------ | ---------------------------- | ------------------------------------------ |
| `IAgentModelClient`      | `Application/Agents/`        | ✅ Interface ready for new implementations |
| `AgentRunner`            | `Infrastructure/Agents/`     | ✅ Full orchestration with risk validation |
| `IRiskValidator`         | `Application/Agents/`        | ✅ Server-side constraint enforcement      |
| `AgentContext`           | `Application/Common/Models/` | ✅ Portfolio, candles, instructions        |
| `AgentDecision`          | `Application/Common/Models/` | ✅ Orders with side, quantity, asset       |
| `ModelProvider.CustomML` | `Domain/Entities/`           | ✅ Enum value already defined              |
| `Agent.ModelProvider`    | `Domain/Entities/`           | ✅ Field exists on Agent entity            |
| Market data              | Phase 3                      | ✅ BTC/ETH candles in DB                   |
| Portfolio engine         | Phase 4                      | ✅ Trade execution with PnL                |

### What's Missing ❌

| Component                  | Description                                    | Priority |
| -------------------------- | ---------------------------------------------- | -------- |
| `ai-trading-race-ml/`      | Python project with FastAPI                    | P0       |
| `/predict` endpoint        | Receives context, returns decision             | P0       |
| Pydantic models            | `AgentContextRequest`, `AgentDecisionResponse` | P0       |
| ML training pipeline       | Feature engineering + model training           | P0       |
| `CustomMlAgentModelClient` | .NET HTTP client to Python service             | P0       |
| `CustomMlAgentOptions`     | Configuration (BaseUrl, timeout)               | P0       |
| DI registration            | Select client based on `ModelProvider`         | P0       |
| Health check endpoint      | `/health` for service readiness                | P1       |
| Dockerfile                 | Containerize Python service                    | P1       |
| Unit tests (Python)        | Test predictor and endpoint                    | P0       |
| Integration tests (.NET)   | Test full flow with Python service             | P1       |

---

## Proposed Changes

### Component 1: Python Project Structure

#### [NEW] `ai-trading-race-ml/`

```
ai-trading-race-ml/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration (model paths, hyperparams)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py       # Pydantic models (request/response)
│   │   └── enums.py         # TradeSide enum
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── features.py      # Feature engineering (RSI, SMA, MACD)
│   │   ├── predictor.py     # Model loading + inference
│   │   └── trainer.py       # Training script
│   └── services/
│       ├── __init__.py
│       └── decision_service.py  # Orchestrates prediction
├── models/                  # Saved models (.pkl, .pt)
│   └── .gitkeep
├── data/                    # Training datasets
│   └── .gitkeep
├── notebooks/               # Jupyter notebooks for exploration
│   └── exploration.ipynb
├── tests/
│   ├── __init__.py
│   ├── test_features.py
│   ├── test_predictor.py
│   └── test_api.py
├── Dockerfile
├── requirements.txt
├── pyproject.toml           # Optional: Poetry/PDM config
└── README.md
```

---

### Component 2: Python Dependencies

#### [NEW] `requirements.txt`

```txt
# Web framework
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
pydantic-settings>=2.1.0

# ML & Data
numpy>=1.26.0
pandas>=2.1.0
scikit-learn>=1.4.0
torch>=2.1.0
joblib>=1.3.0

# Technical indicators
ta>=0.11.0

# HTTP client (for fetching data)
httpx>=0.26.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.23.0

# Development
python-dotenv>=1.0.0
```

---

### Component 3: Pydantic Models

#### [NEW] `app/models/schemas.py`

```python
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field

# API Schema version for contract evolution
SCHEMA_VERSION = "1.0"

class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class SignalContribution(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

class CandleData(BaseModel):
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

class PositionData(BaseModel):
    symbol: str
    quantity: Decimal
    average_price: Decimal

class PortfolioState(BaseModel):
    cash: Decimal
    positions: list[PositionData]
    total_value: Decimal

class AgentContextRequest(BaseModel):
    """Request with contract versioning for safe API evolution."""
    schema_version: str = Field(default=SCHEMA_VERSION, alias="schemaVersion")
    request_id: str = Field(default_factory=lambda: str(uuid4()), alias="requestId")
    agent_id: str = Field(alias="agentId")
    portfolio: PortfolioState
    candles: list[CandleData]
    instructions: str = ""

    class Config:
        populate_by_name = True

class ExplanationSignal(BaseModel):
    """Structured signal explaining why a decision was made."""
    feature: str           # e.g., "rsi_14"
    value: float           # e.g., 27.3
    rule: str              # e.g., "<30 = oversold"
    fired: bool            # True if rule triggered
    contribution: SignalContribution

class TradeOrderResponse(BaseModel):
    asset_symbol: str = Field(alias="assetSymbol")
    side: TradeSide
    quantity: Decimal
    limit_price: Decimal | None = Field(default=None, alias="limitPrice")

    class Config:
        populate_by_name = True

class AgentDecisionResponse(BaseModel):
    """Response with contract versioning and structured explainability."""
    schema_version: str = Field(default=SCHEMA_VERSION, alias="schemaVersion")
    model_version: str = Field(alias="modelVersion")
    request_id: str = Field(alias="requestId")
    agent_id: str = Field(alias="agentId")
    created_at: datetime = Field(alias="createdAt")
    orders: list[TradeOrderResponse]
    signals: list[ExplanationSignal] = []  # Structured explainability
    reasoning: str = ""  # Human-readable summary

    class Config:
        populate_by_name = True

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str
    schema_version: str = SCHEMA_VERSION
```

---

### Component 4: Feature Engineering

#### [NEW] `app/ml/features.py`

```python
import pandas as pd
import numpy as np
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands

def engineer_features(candles_df: pd.DataFrame) -> pd.DataFrame:
    """
    Create technical indicators from OHLCV data.

    Expected columns: open, high, low, close, volume
    Returns DataFrame with additional feature columns.
    """
    df = candles_df.copy()
    close = df['close']

    # Moving averages
    df['sma_7'] = SMAIndicator(close, window=7).sma_indicator()
    df['sma_21'] = SMAIndicator(close, window=21).sma_indicator()

    # RSI
    df['rsi_14'] = RSIIndicator(close, window=14).rsi()

    # MACD
    macd = MACD(close)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()

    # Bollinger Bands
    bb = BollingerBands(close)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / close

    # Price momentum
    df['returns_1'] = close.pct_change(1)
    df['returns_7'] = close.pct_change(7)

    # Volatility
    df['volatility_7'] = df['returns_1'].rolling(7).std()

    # Volume momentum
    df['volume_sma_7'] = df['volume'].rolling(7).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma_7']

    return df.dropna()

def prepare_inference_features(candles_df: pd.DataFrame) -> np.ndarray:
    """Prepare features for model inference (latest row only)."""
    df = engineer_features(candles_df)
    feature_cols = [
        'sma_7', 'sma_21', 'rsi_14', 'macd', 'macd_signal', 'macd_diff',
        'bb_width', 'returns_1', 'returns_7', 'volatility_7', 'volume_ratio'
    ]
    return df[feature_cols].iloc[-1:].values
```

---

### Component 5: ML Predictor

#### [NEW] `app/ml/predictor.py`

```python
import joblib
import numpy as np
from pathlib import Path
from enum import IntEnum

class PredictedAction(IntEnum):
    SELL = 0
    HOLD = 1
    BUY = 2

class TradingPredictor:
    """Loads a trained model and generates predictions."""

    def __init__(self, model_path: Path):
        self.model = None
        self.model_path = model_path
        self._load_model()

    def _load_model(self):
        if self.model_path.exists():
            self.model = joblib.load(self.model_path)
        else:
            # Fallback: simple rule-based for development
            self.model = None

    def predict(self, features: np.ndarray) -> tuple[PredictedAction, float]:
        """
        Returns (action, confidence) tuple.
        Action: 0=SELL, 1=HOLD, 2=BUY
        """
        if self.model is None:
            # Rule-based fallback
            return self._rule_based_predict(features)

        probas = self.model.predict_proba(features)[0]
        action = PredictedAction(np.argmax(probas))
        confidence = float(np.max(probas))
        return action, confidence

    def _rule_based_predict(self, features: np.ndarray) -> tuple[PredictedAction, float]:
        """Simple RSI-based strategy as fallback."""
        # Assuming RSI is at index 2
        rsi = features[0, 2] if features.shape[1] > 2 else 50

        if rsi < 30:
            return PredictedAction.BUY, 0.6
        elif rsi > 70:
            return PredictedAction.SELL, 0.6
        return PredictedAction.HOLD, 0.5

    @property
    def is_loaded(self) -> bool:
        return self.model is not None
```

---

### Component 6: Decision Service

#### [NEW] `app/services/decision_service.py`

```python
from datetime import datetime, timezone
from decimal import Decimal
import pandas as pd

from app.models.schemas import (
    AgentContextRequest, AgentDecisionResponse,
    TradeOrderResponse, TradeSide, CandleData
)
from app.ml.predictor import TradingPredictor, PredictedAction
from app.ml.features import prepare_inference_features

class DecisionService:
    def __init__(self, predictor: TradingPredictor):
        self.predictor = predictor

    def generate_decision(
        self,
        context: AgentContextRequest
    ) -> AgentDecisionResponse:
        orders = []
        reasoning_parts = []

        # Process each asset separately
        for symbol in ["BTC", "ETH"]:
            symbol_candles = [c for c in context.candles if c.symbol == symbol]
            if len(symbol_candles) < 21:  # Need enough for indicators
                continue

            # Convert to DataFrame
            df = self._candles_to_dataframe(symbol_candles)

            # Get features and predict
            features = prepare_inference_features(df)
            action, confidence = self.predictor.predict(features)

            # Generate order if not HOLD
            order = self._action_to_order(
                action, confidence, symbol, context
            )
            if order:
                orders.append(order)
                reasoning_parts.append(
                    f"{symbol}: {action.name} (confidence: {confidence:.2%})"
                )

        return AgentDecisionResponse(
            agent_id=context.agent_id,
            created_at=datetime.now(timezone.utc),
            orders=orders,
            reasoning="; ".join(reasoning_parts) if reasoning_parts else "No signals"
        )

    def _candles_to_dataframe(self, candles: list[CandleData]) -> pd.DataFrame:
        data = [{
            'timestamp': c.timestamp,
            'open': float(c.open),
            'high': float(c.high),
            'low': float(c.low),
            'close': float(c.close),
            'volume': float(c.volume)
        } for c in candles]
        return pd.DataFrame(data).sort_values('timestamp')

    def _action_to_order(
        self,
        action: PredictedAction,
        confidence: float,
        symbol: str,
        context: AgentContextRequest
    ) -> TradeOrderResponse | None:
        if action == PredictedAction.HOLD:
            return None

        # Calculate position size based on confidence
        base_size = Decimal("0.1")  # 10% of portfolio
        size_multiplier = Decimal(str(min(confidence, 0.9)))

        portfolio_value = context.portfolio.total_value
        trade_value = portfolio_value * base_size * size_multiplier

        # Get current price
        latest_candle = next(
            (c for c in reversed(context.candles) if c.symbol == symbol),
            None
        )
        if not latest_candle:
            return None

        current_price = latest_candle.close
        quantity = trade_value / current_price

        return TradeOrderResponse(
            asset_symbol=symbol,
            side=TradeSide.BUY if action == PredictedAction.BUY else TradeSide.SELL,
            quantity=quantity.quantize(Decimal("0.00000001")),
            limit_price=None
        )
```

---

### Component 7: FastAPI Application

#### [NEW] `app/main.py`

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models.schemas import (
    AgentContextRequest, AgentDecisionResponse, HealthResponse
)
from app.ml.predictor import TradingPredictor
from app.services.decision_service import DecisionService
from app.config import settings

# Global instances
predictor: TradingPredictor | None = None
decision_service: DecisionService | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor, decision_service

    model_path = Path(settings.model_path)
    predictor = TradingPredictor(model_path)
    decision_service = DecisionService(predictor)

    yield

    predictor = None
    decision_service = None

app = FastAPI(
    title="AI Trading Race - ML Service",
    description="Custom ML model for trading decisions",
    version="1.0.0",
    lifespan=lifespan
)

# Security: API Key middleware (see Component 7b below)
from app.middleware.auth import verify_api_key
app.middleware("http")(verify_api_key)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],  # Restrict in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        model_loaded=predictor.is_loaded if predictor else False,
        model_version=settings.model_version,
    )

@app.post("/predict", response_model=AgentDecisionResponse)
async def predict(context: AgentContextRequest):
    if decision_service is None:
        raise HTTPException(503, "Service not initialized")

    try:
        return decision_service.generate_decision(context)
    except Exception as e:
        raise HTTPException(500, f"Prediction failed: {str(e)}")
```

---

### Component 7b: API Key Authentication Middleware

#### [NEW] `app/middleware/auth.py`

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings

async def verify_api_key(request: Request, call_next):
    """Middleware to verify API key for service-to-service authentication."""
    # Skip auth for health check
    if request.url.path == "/health":
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )

    return await call_next(request)
```

#### [MODIFY] `app/config.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_path: str = "models/trading_model.pkl"
    model_version: str = "1.0.0"
    log_level: str = "INFO"
    api_key: str = ""  # Set via environment variable ML_SERVICE_API_KEY
    allowed_origin: str = "*"  # Restrict in production

    class Config:
        env_file = ".env"
        env_prefix = "ML_SERVICE_"

settings = Settings()
```

---

### Component 8: .NET Client Implementation

#### [NEW] `CustomMlAgentOptions.cs`

Location: `AiTradingRace.Infrastructure/Agents/`

```csharp
namespace AiTradingRace.Infrastructure.Agents;

public class CustomMlAgentOptions
{
    public const string SectionName = "CustomMlAgent";

    /// <summary>Base URL of the Python FastAPI service</summary>
    public string BaseUrl { get; set; } = "http://localhost:8000";

    /// <summary>Request timeout in seconds</summary>
    public int TimeoutSeconds { get; set; } = 30;

    /// <summary>Number of retry attempts on transient failures</summary>
    public int MaxRetries { get; set; } = 2;

    /// <summary>API key for service-to-service authentication</summary>
    public string ApiKey { get; set; } = "";
}
```

#### [NEW] `CustomMlAgentModelClient.cs`

Location: `AiTradingRace.Infrastructure/Agents/`

```csharp
using System.Net.Http.Json;
using System.Text.Json;
using AiTradingRace.Application.Agents;
using AiTradingRace.Application.Common.Models;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace AiTradingRace.Infrastructure.Agents;

public sealed class CustomMlAgentModelClient : IAgentModelClient
{
    private readonly HttpClient _httpClient;
    private readonly CustomMlAgentOptions _options;
    private readonly ILogger<CustomMlAgentModelClient> _logger;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public CustomMlAgentModelClient(
        HttpClient httpClient,
        IOptions<CustomMlAgentOptions> options,
        ILogger<CustomMlAgentModelClient> logger)
    {
        _httpClient = httpClient;
        _options = options.Value;
        _logger = logger;

        _httpClient.BaseAddress = new Uri(_options.BaseUrl);
        _httpClient.Timeout = TimeSpan.FromSeconds(_options.TimeoutSeconds);
    }

    public async Task<AgentDecision> GenerateDecisionAsync(
        AgentContext context,
        CancellationToken cancellationToken = default)
    {
        var request = MapToRequest(context);

        _logger.LogDebug(
            "Calling ML service for agent {AgentId} with {CandleCount} candles",
            context.AgentId, context.RecentCandles.Count);

        // Add API key header for authentication
        using var httpRequest = new HttpRequestMessage(HttpMethod.Post, "/predict");
        httpRequest.Headers.Add("X-API-Key", _options.ApiKey);
        httpRequest.Content = JsonContent.Create(request, options: JsonOptions);

        var response = await _httpClient.SendAsync(httpRequest, cancellationToken);

        response.EnsureSuccessStatusCode();

        var mlResponse = await response.Content.ReadFromJsonAsync<MlDecisionResponse>(
            JsonOptions, cancellationToken);

        return MapToDecision(context.AgentId, mlResponse!);
    }

    private static MlContextRequest MapToRequest(AgentContext context)
    {
        return new MlContextRequest
        {
            AgentId = context.AgentId.ToString(),
            Portfolio = new MlPortfolioState
            {
                Cash = context.Portfolio.Cash,
                TotalValue = context.Portfolio.TotalValue,
                Positions = context.Portfolio.Positions.Select(p => new MlPosition
                {
                    Symbol = p.Symbol,
                    Quantity = p.Quantity,
                    AveragePrice = p.AveragePrice
                }).ToList()
            },
            Candles = context.RecentCandles.Select(c => new MlCandle
            {
                Symbol = c.Symbol,
                Timestamp = c.Timestamp,
                Open = c.Open,
                High = c.High,
                Low = c.Low,
                Close = c.Close,
                Volume = c.Volume
            }).ToList(),
            Instructions = context.Instructions
        };
    }

    private static AgentDecision MapToDecision(Guid agentId, MlDecisionResponse response)
    {
        var orders = response.Orders.Select(o => new TradeOrder(
            AssetSymbol: o.AssetSymbol,
            Side: ParseSide(o.Side),
            Quantity: o.Quantity,
            LimitPrice: o.LimitPrice
        )).ToList();

        return new AgentDecision(agentId, DateTimeOffset.UtcNow, orders);
    }

    private static TradeSide ParseSide(string side) => side.ToUpperInvariant() switch
    {
        "BUY" => TradeSide.Buy,
        "SELL" => TradeSide.Sell,
        _ => TradeSide.Hold
    };

    #region DTOs for Python API

    private record MlContextRequest
    {
        public required string AgentId { get; init; }
        public required MlPortfolioState Portfolio { get; init; }
        public required List<MlCandle> Candles { get; init; }
        public string Instructions { get; init; } = "";
    }

    private record MlPortfolioState
    {
        public decimal Cash { get; init; }
        public decimal TotalValue { get; init; }
        public required List<MlPosition> Positions { get; init; }
    }

    private record MlPosition
    {
        public required string Symbol { get; init; }
        public decimal Quantity { get; init; }
        public decimal AveragePrice { get; init; }
    }

    private record MlCandle
    {
        public required string Symbol { get; init; }
        public DateTimeOffset Timestamp { get; init; }
        public decimal Open { get; init; }
        public decimal High { get; init; }
        public decimal Low { get; init; }
        public decimal Close { get; init; }
        public decimal Volume { get; init; }
    }

    private record MlDecisionResponse
    {
        public required string AgentId { get; init; }
        public DateTimeOffset CreatedAt { get; init; }
        public required List<MlOrder> Orders { get; init; }
        public string Reasoning { get; init; } = "";
    }

    private record MlOrder
    {
        public required string AssetSymbol { get; init; }
        public required string Side { get; init; }
        public decimal Quantity { get; init; }
        public decimal? LimitPrice { get; init; }
    }

    #endregion
}
```

---

### Component 9: Agent Model Client Factory

#### [NEW] `IAgentModelClientFactory.cs`

Location: `AiTradingRace.Application/Agents/`

```csharp
using AiTradingRace.Domain.Entities;

namespace AiTradingRace.Application.Agents;

public interface IAgentModelClientFactory
{
    IAgentModelClient GetClient(ModelProvider provider);
}
```

#### [NEW] `AgentModelClientFactory.cs`

Location: `AiTradingRace.Infrastructure/Agents/`

```csharp
using AiTradingRace.Application.Agents;
using AiTradingRace.Domain.Entities;
using Microsoft.Extensions.DependencyInjection;

namespace AiTradingRace.Infrastructure.Agents;

public sealed class AgentModelClientFactory : IAgentModelClientFactory
{
    private readonly IServiceProvider _serviceProvider;

    public AgentModelClientFactory(IServiceProvider serviceProvider)
    {
        _serviceProvider = serviceProvider;
    }

    public IAgentModelClient GetClient(ModelProvider provider)
    {
        return provider switch
        {
            ModelProvider.AzureOpenAI => _serviceProvider
                .GetRequiredService<AzureOpenAiAgentModelClient>(),
            ModelProvider.CustomML => _serviceProvider
                .GetRequiredService<CustomMlAgentModelClient>(),
            ModelProvider.Mock => _serviceProvider
                .GetRequiredService<TestAgentModelClient>(),
            _ => throw new ArgumentException($"Unsupported provider: {provider}")
        };
    }
}
```

---

### Component 10: Update AgentRunner

#### [MODIFY] `AgentRunner.cs`

Update to use factory based on agent's ModelProvider:

```csharp
// Change: Inject IAgentModelClientFactory instead of IAgentModelClient
public sealed class AgentRunner : IAgentRunner
{
    private readonly IAgentModelClientFactory _clientFactory;  // Changed
    private readonly TradingDbContext _dbContext;  // Add for agent lookup
    // ... other dependencies

    public async Task<AgentRunResult> RunAgentOnceAsync(
        Guid agentId, CancellationToken ct)
    {
        // 1. Get agent to determine ModelProvider
        var agent = await _dbContext.Agents
            .FirstOrDefaultAsync(a => a.Id == agentId, ct)
            ?? throw new InvalidOperationException($"Agent {agentId} not found");

        // 2. Get appropriate client
        var modelClient = _clientFactory.GetClient(agent.ModelProvider);

        // 3. Build context
        var context = await _contextBuilder.BuildContextAsync(agentId, ct);

        // 4. Get decision from AI/ML
        var rawDecision = await modelClient.GenerateDecisionAsync(context, ct);

        // ... rest unchanged (risk validation, apply trades, snapshot)
    }
}
```

---

### Component 11: DI Registration Updates

#### [MODIFY] `InfrastructureServiceCollectionExtensions.cs`

```csharp
// Add Custom ML agent configuration
services.Configure<CustomMlAgentOptions>(
    configuration.GetSection(CustomMlAgentOptions.SectionName));

// Register CustomMlAgentModelClient with typed HttpClient
services.AddHttpClient<CustomMlAgentModelClient>()
    .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
    {
        // Allow self-signed certs in dev
    });

// Register factory
services.AddScoped<IAgentModelClientFactory, AgentModelClientFactory>();

// Keep individual client registrations for factory resolution
services.AddScoped<AzureOpenAiAgentModelClient>();
services.AddScoped<CustomMlAgentModelClient>();
services.AddScoped<TestAgentModelClient>();
```

---

### Component 12: Configuration

#### [MODIFY] `appsettings.json`

```json
{
  "CustomMlAgent": {
    "BaseUrl": "http://localhost:8000",
    "TimeoutSeconds": 30,
    "MaxRetries": 2
  }
}
```

---

### Component 13: Docker Support

#### [NEW] `ai-trading-race-ml/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY models/ ./models/

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### [MODIFY] `docker-compose.yml` (root)

Add Python service:

```yaml
services:
  ml-service:
    build: ./ai-trading-race-ml
    ports:
      - "8000:8000"
    volumes:
      - ./ai-trading-race-ml/models:/app/models
    environment:
      - MODEL_PATH=/app/models/trading_model.pkl
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Implementation Order

| Step | Task                                       | Files                              | Priority | Effort |
| ---- | ------------------------------------------ | ---------------------------------- | -------- | ------ |
| 1    | Create Python project structure            | `ai-trading-race-ml/`              | P0       | 30min  |
| 2    | Implement Pydantic schemas (versioned)     | `app/models/schemas.py`            | P0       | 30min  |
| 3    | Add `ExplanationSignal` for explainability | `app/models/schemas.py`            | P0       | 15min  |
| 4    | Implement feature engineering              | `app/ml/features.py`               | P0       | 45min  |
| 5    | Implement predictor with signal output     | `app/ml/predictor.py`              | P0       | 45min  |
| 6    | Implement decision service with signals    | `app/services/decision_service.py` | P0       | 30min  |
| 7    | Add API key middleware                     | `app/middleware/auth.py`           | P0       | 20min  |
| 8    | Implement FastAPI endpoints                | `app/main.py`                      | P0       | 20min  |
| 9    | Add Python tests                           | `tests/`                           | P0       | 30min  |
| 10   | Create `CustomMlAgentOptions`              | Infrastructure                     | P0       | 10min  |
| 11   | Create `CustomMlAgentModelClient`          | Infrastructure                     | P0       | 45min  |
| 12   | Add API key header to .NET client          | Infrastructure                     | P0       | 10min  |
| 13   | Create `IAgentModelClientFactory`          | Application/Infrastructure         | P0       | 20min  |
| 14   | Update `AgentRunner`                       | Infrastructure                     | P0       | 20min  |
| 15   | Update DI registrations                    | Infrastructure                     | P0       | 15min  |
| 16   | Add configuration (incl. API key)          | Web/appsettings.json               | P0       | 10min  |
| 17   | Add .NET integration tests                 | Tests                              | P1       | 30min  |
| 18   | Create Dockerfile                          | ai-trading-race-ml                 | P1       | 15min  |
| 19   | Update docker-compose                      | Root                               | P1       | 10min  |
| 20   | Train initial ML model                     | notebooks/                         | P2       | 2h     |

**Estimated Total: ~9-10 hours**

---

## Verification Plan

### Automated Tests

#### Python Tests

```bash
cd ai-trading-race-ml
python -m pytest tests/ -v
```

Tests to create:

- `test_features.py`: Feature engineering output shapes
- `test_predictor.py`: Predictor returns valid actions
- `test_api.py`: `/predict` and `/health` endpoints

#### .NET Tests

```bash
dotnet test AiTradingRace.Tests
```

Tests to create:

- `CustomMlAgentModelClientTests`: Mock HTTP responses
- `AgentModelClientFactoryTests`: Correct client resolution
- `AgentRunnerIntegrationTests`: Full flow with CustomML agent

---

### Manual Verification

1. **Start Python service:**

   ```bash
   cd ai-trading-race-ml
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

2. **Test health endpoint:**

   ```bash
   curl http://localhost:8000/health
   ```

3. **Test predict endpoint:**

   ```bash
   curl -X POST http://localhost:8000/predict \
     -H "Content-Type: application/json" \
     -d '{
       "agent_id": "test-agent",
       "portfolio": {"cash": 10000, "positions": [], "total_value": 10000},
       "candles": [...],
       "instructions": ""
     }'
   ```

4. **Create CustomML agent in .NET:**

   ```bash
   # Update existing agent to use CustomML provider
   curl -X PUT https://localhost:7XXX/api/agents/{id} \
     -H "Content-Type: application/json" \
     -d '{"modelProvider": "CustomML"}'
   ```

5. **Run agent:**
   ```bash
   curl -X POST https://localhost:7XXX/api/agents/{id}/run
   ```

---

## Exit Criteria

Phase 5b is complete when:

### Core ML Integration

- [ ] Python project `ai-trading-race-ml/` created with FastAPI
- [ ] `/predict` endpoint receives `AgentContext` and returns `AgentDecision`
- [ ] `/health` endpoint returns service status
- [ ] Feature engineering pipeline implemented (RSI, SMA, MACD, etc.)
- [ ] Rule-based predictor works as fallback
- [ ] `CustomMlAgentModelClient` implemented in .NET
- [ ] `IAgentModelClientFactory` selects client based on `ModelProvider`
- [ ] `AgentRunner` uses factory to get appropriate client
- [ ] DI registrations updated
- [ ] Python tests pass
- [ ] .NET tests pass
- [ ] Manual verification: CustomML agent executes via API
- [ ] Dockerfile created for Python service

### Production Enhancements

- [ ] **Contract Versioning:** `schemaVersion`, `modelVersion`, `requestId` in all API contracts
- [ ] **Structured Explainability:** `ExplanationSignal` with feature/rule/contribution
- [ ] **API Key Security:** `X-API-Key` middleware in Python, header sent from .NET

---

## Risks & Mitigations

| Risk                       | Impact                     | Mitigation                                 |
| -------------------------- | -------------------------- | ------------------------------------------ |
| Python service unavailable | Agent fails to execute     | Circuit breaker + fallback to HOLD         |
| Slow ML inference          | Timeout errors             | Set appropriate timeouts, async processing |
| Model overfitting          | Poor live performance      | Use holdout test set, monitor live PnL     |
| Feature drift              | Degraded predictions       | Retrain periodically, monitor metrics      |
| Network latency            | Increased agent cycle time | Consider gRPC for production               |

---

## Future Improvements (Out of Scope)

- [ ] PyTorch neural network model
- [ ] Reinforcement learning agent
- [ ] Ensemble of multiple models
- [ ] Real-time model retraining
- [ ] Model versioning and A/B testing
- [ ] gRPC instead of REST
- [ ] GPU inference support
