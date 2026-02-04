"""Application configuration using pydantic-settings."""

from typing import Optional
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

    class Config:
        env_file = ".env"
        env_prefix = "ML_SERVICE_"


settings = Settings()
