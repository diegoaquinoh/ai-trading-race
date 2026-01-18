# Python ML Service - Multi-stage Dockerfile
# Stage 1: Builder - install dependencies
# Stage 2: Runtime - minimal production image

FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
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

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY app/ ./app/
COPY models/ ./models/

# Create non-root user for security
RUN useradd --create-home appuser
USER appuser

# Environment variables (can be overridden at runtime)
ENV ML_SERVICE_MODEL_PATH=models/trading_model.pkl
ENV ML_SERVICE_MODEL_VERSION=1.0.0
ENV ML_SERVICE_LOG_LEVEL=INFO
ENV ML_SERVICE_API_KEY=""
ENV ML_SERVICE_ALLOWED_ORIGIN="*"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
