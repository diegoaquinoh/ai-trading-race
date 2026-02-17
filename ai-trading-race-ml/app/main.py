"""FastAPI application for the ML trading service."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.middleware.auth import verify_api_key
from app.middleware.idempotency import IdempotencyMiddleware
from app.ml.predictor import TradingPredictor
from app.models.schemas import (
    AgentContextRequest,
    AgentDecisionResponse,
    HealthResponse,
    SCHEMA_VERSION,
)
from app.services.decision_service import DecisionService
from app.services.cache_service import cache_service

# Global instances (initialized in lifespan)
predictor: Optional[TradingPredictor] = None
decision_service: Optional[DecisionService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application resources."""
    global predictor, decision_service

    # Initialize predictor and decision service
    model_path = Path(settings.model_path)
    predictor = TradingPredictor(model_path)
    decision_service = DecisionService(predictor)

    yield

    # Cleanup
    cache_service.close()
    predictor = None
    decision_service = None


# Rate limiter (per IP, 5 requests/minute on /predict)
limiter = Limiter(key_func=get_remote_address)

# Disable docs in production
is_dev = os.getenv("ENVIRONMENT", "development") == "development"

# Create FastAPI app
app = FastAPI(
    title="AI Trading Race - ML Service",
    description="Custom ML model for trading decisions with explainability",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if is_dev else None,
    redoc_url="/redoc" if is_dev else None,
    openapi_url="/openapi.json" if is_dev else None,
)

# Rate limit state and 429 handler
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


# Add idempotency middleware (must be before auth)
app.add_middleware(IdempotencyMiddleware)

# Add API key authentication middleware
app.middleware("http")(verify_api_key)

# Configure CORS based on environment
if settings.allowed_origin:
    origins = [settings.allowed_origin]
else:
    # Development fallback
    if os.getenv("ENVIRONMENT", "development") == "development":
        origins = ["http://localhost:5173", "http://localhost:3000"]
    else:
        origins = []  # No CORS in production without explicit config

if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["POST", "GET"],
        allow_headers=["X-API-Key", "Content-Type"],
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns service status and model information.
    Does not require API key authentication.
    """
    return HealthResponse(
        status="healthy",
        model_loaded=predictor.is_loaded if predictor else False,
        model_version=settings.model_version,
        schema_version=SCHEMA_VERSION,
    )


@app.post("/predict", response_model=AgentDecisionResponse)
@limiter.limit("5/minute")
async def predict(request: Request, context: AgentContextRequest):
    """
    Generate a trading decision for an agent.

    Requires X-API-Key header for authentication.

    Args:
        context: Agent context with portfolio and market candles

    Returns:
        Trading decision with orders and explanation signals
    """
    if decision_service is None:
        raise HTTPException(
            status_code=503,
            detail="Service not initialized",
        )

    try:
        return decision_service.generate_decision(context)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(e)}",
        )
