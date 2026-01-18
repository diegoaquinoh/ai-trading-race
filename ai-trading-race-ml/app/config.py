"""Application configuration using pydantic-settings."""

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
    allowed_origin: str = "*"  # Restrict in production

    class Config:
        env_file = ".env"
        env_prefix = "ML_SERVICE_"


settings = Settings()
