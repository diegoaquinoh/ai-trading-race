"""API Key authentication middleware for service-to-service security."""

import hmac
import os
from fastapi import HTTPException, Request

from app.config import settings

# Public endpoints (no auth required)
PUBLIC_PATHS = {"/health", "/"}

# Docs endpoints (only accessible in development)
DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}


async def verify_api_key(request: Request, call_next):
    """
    Middleware to verify API key for service-to-service authentication.

    Security fixes:
    - Fail closed if API key not configured (no bypass)
    - Timing-safe comparison to prevent timing attacks
    - Docs only accessible in development
    """
    # Allow health check unconditionally
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    # Docs only in development
    if request.url.path in DOCS_PATHS:
        if os.getenv("ENVIRONMENT", "development") == "development":
            return await call_next(request)
        else:
            raise HTTPException(status_code=404, detail="Not found")

    # SECURITY FIX: Fail closed if API key not configured
    if not settings.api_key:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: API key not set",
        )

    # Check API key header
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key",
        )

    # SECURITY FIX: Timing-safe comparison
    if not hmac.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    return await call_next(request)
