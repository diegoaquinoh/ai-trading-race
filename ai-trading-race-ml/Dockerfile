# Python ML Service - Production Multi-stage Dockerfile
# Stage 1: Builder - install dependencies
# Stage 2: Runtime - minimal production image

FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# ----------------------------------
# Stage 2: Runtime
# ----------------------------------
FROM python:3.11-slim as runtime

WORKDIR /app

# Install runtime dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy installed packages from builder and set ownership
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code and set ownership
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser models/ ./models/

# Switch to non-root user
USER appuser

# Environment variables (can be overridden at runtime)
ENV ML_SERVICE_MODEL_PATH=models/trading_model.pkl \
    ML_SERVICE_MODEL_VERSION=1.0.0 \
    ML_SERVICE_LOG_LEVEL=INFO \
    ML_SERVICE_API_KEY="" \
    ML_SERVICE_ALLOWED_ORIGIN="" \
    ML_SERVICE_REDIS_ENABLED=false \
    ML_SERVICE_REDIS_HOST=redis \
    ML_SERVICE_REDIS_PORT=6379 \
    ML_SERVICE_REDIS_DB=0 \
    ML_SERVICE_REDIS_TTL_SECONDS=3600

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
