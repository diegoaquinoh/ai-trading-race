"""Idempotency middleware using Redis cache."""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle request idempotency using Redis cache.
    
    Clients can send an 'Idempotency-Key' header with a unique identifier.
    If the same key is seen within the TTL window (1 hour), the cached
    response is returned without re-processing the request.
    
    This prevents duplicate processing of ML predictions which can be expensive.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with idempotency check.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
            
        Returns:
            Response (either cached or freshly generated)
        """
        # Only apply to POST /predict endpoint
        if request.method != "POST" or not request.url.path.endswith("/predict"):
            return await call_next(request)

        # Get idempotency key from header
        idempotency_key = request.headers.get("Idempotency-Key")
        
        if not idempotency_key:
            # No idempotency key provided, process normally
            logger.debug("No idempotency key provided, processing request")
            return await call_next(request)

        # Check cache for existing response
        if cache_service.is_available:
            cached_response = cache_service.get(idempotency_key)
            
            if cached_response:
                logger.info(f"Returning cached response for key: {idempotency_key}")
                return Response(
                    content=cached_response["body"],
                    status_code=cached_response["status_code"],
                    headers=cached_response["headers"],
                    media_type="application/json",
                )

        # Process request normally
        response = await call_next(request)

        # Cache successful responses (2xx status codes)
        if idempotency_key and cache_service.is_available and 200 <= response.status_code < 300:
            try:
                # Read response body
                body_bytes = b""
                async for chunk in response.body_iterator:
                    body_bytes += chunk

                # Cache the response
                cache_data = {
                    "body": body_bytes.decode("utf-8"),
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                }
                cache_service.set(idempotency_key, cache_data)

                # Create new response with consumed body
                return Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception as e:
                logger.error(f"Error caching response: {e}")
                # Return original response if caching fails
                return response

        return response
