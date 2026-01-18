"""API Key authentication middleware for service-to-service security."""

from fastapi import HTTPException, Request

from app.config import settings


async def verify_api_key(request: Request, call_next):
    """
    Middleware to verify API key for service-to-service authentication.

    Checks for X-API-Key header on all endpoints except /health.
    """
    # Skip auth for health check endpoint
    if request.url.path == "/health":
        return await call_next(request)

    # Check API key header
    api_key = request.headers.get("X-API-Key")

    if not settings.api_key:
        # No API key configured - allow requests (dev mode)
        return await call_next(request)

    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )

    return await call_next(request)
