"""API Key authentication middleware for service-to-service security.

Every path except ``/health`` and ``/`` requires ``X-API-Key``; this includes
all ``/internal/*`` research endpoints. The middleware fails closed when no key
is configured. Responses are returned (not raised) so the status codes reach
the client; ``/internal/*`` paths answer with ``application/problem+json``.
"""

import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

# Public endpoints (no auth required)
PUBLIC_PATHS = {"/health", "/"}

# Docs endpoints (only accessible in development)
DOCS_PATHS = {"/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"}

PROBLEM_BASE = "https://ai-trading-race.local/problems/"


def _deny(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    if request.url.path.startswith("/internal/"):
        titles = {401: "Unauthorized", 404: "Not Found", 500: "Internal Server Error"}
        return JSONResponse(
            status_code=status,
            content={
                "type": PROBLEM_BASE + code,
                "title": titles.get(status, "Error"),
                "status": status,
                "code": code,
                "detail": detail,
                "instance": request.url.path,
            },
            media_type="application/problem+json",
        )
    return JSONResponse(status_code=status, content={"detail": detail})


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
        return _deny(request, 404, "not_found", "Not found")

    # SECURITY FIX: Fail closed if API key not configured
    if not settings.api_key:
        return _deny(
            request, 500, "server_misconfiguration", "Server misconfiguration: API key not set"
        )

    # Check API key header
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        return _deny(request, 401, "missing_api_key", "Missing API key")

    # SECURITY FIX: Timing-safe comparison
    if not hmac.compare_digest(api_key.encode("utf-8"), settings.api_key.encode("utf-8")):
        return _deny(request, 401, "invalid_api_key", "Invalid API key")

    return await call_next(request)
