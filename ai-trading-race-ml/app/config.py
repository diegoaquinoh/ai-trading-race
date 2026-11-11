"""Application configuration using pydantic-settings.

Every variable uses the ``ML_SERVICE_`` prefix. Credentials come from the
environment or secret storage; strategy behaviour is not hidden in environment
state - the non-secret resolved settings are reported by
``GET /internal/v1/capabilities`` (spec 18.2).
"""

import os
from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """ML Service configuration loaded from environment variables."""

    # Model settings
    model_path: str = "models/trading_model.pkl"
    model_version: str = "1.0.0"

    # Logging
    log_level: str = "INFO"

    # Security
    api_key: str = ""  # Required: set via ML_SERVICE_API_KEY

    # CORS
    allowed_origin: str = ""  # Must be set explicitly via ML_SERVICE_ALLOWED_ORIGIN

    # Redis settings for idempotency
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_enabled: bool = False  # Enable when Redis is available
    redis_ttl_seconds: int = 3600  # 1 hour cache

    # ------------------------------------------------------------------ #
    # Internal research API v1 (/internal/v1/*)
    # ------------------------------------------------------------------ #
    # HMAC key shared with .NET (ResearchEngine:SigningKey). Signs TransitionProposals
    # and StrategyResults. Required outside ENVIRONMENT=development.
    signing_key: str = ""
    # Strategy model provider: reference | recorded | anthropic | openai. Chosen
    # here, never by request fields.
    strategy_provider: Literal["reference", "recorded", "anthropic", "openai"] = "reference"
    strategy_model: str = ""  # pinned model id for anthropic/openai ("" = provider default)
    strategy_base_url: str = ""  # optional OpenAI-compatible / Anthropic base URL
    recorded_responses_dir: str = ""  # recorded-responses-v1 directory (provider=recorded)
    # Decisions run in a bounded pool; saturation returns 429 + Retry-After.
    max_concurrent_decisions: int = 4
    decision_retry_after_seconds: int = 5
    decision_deadline_margin_seconds: int = 5
    # Evidence: "active" loads the active READY index from FI_RESEARCH_HOME when one
    # exists; "fixtures" ingests the offline Fed fixtures and builds/activates the
    # default index at startup (never inside a request); "off" disables evidence.
    evidence_autoload: Literal["active", "fixtures", "off"] = "active"
    evidence_include_synthetic: bool = False
    # Admin jobs: ingestion is offline (pinned fixtures) unless explicitly enabled.
    ingestion_online: bool = False
    activate_index_builds: bool = True
    # Build all curves in a background thread after startup (sessions/admission).
    warm_curves: bool = True

    class Config:
        env_file = ".env"
        env_prefix = "ML_SERVICE_"


def environment() -> str:
    return os.getenv("ENVIRONMENT", "development")


def is_development() -> bool:
    return environment() == "development"


settings = Settings()
