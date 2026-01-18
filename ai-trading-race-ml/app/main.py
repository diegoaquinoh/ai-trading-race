"""FastAPI application for the ML trading service."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware.auth import verify_api_key
from app.ml.predictor import TradingPredictor
from app.models.schemas import (
    AgentContextRequest,
    AgentDecisionResponse,
    HealthResponse,
    SCHEMA_VERSION,
)
from app.services.decision_service import DecisionService

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
    predictor = None
    decision_service = None


# Create FastAPI app
app = FastAPI(
    title="AI Trading Race - ML Service",
    description="Custom ML model for trading decisions with explainability",
    version="1.0.0",
    lifespan=lifespan,
)

# Add API key authentication middleware
app.middleware("http")(verify_api_key)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
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
async def predict(context: AgentContextRequest):
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
