"""Internal research API v1 (``/internal/v1/*``): FastAPI transport over ``research_engine``.

``install(app)`` registers the routers, problem+json error handlers and the
OpenAPI contract schemas. Engine objects are created in the application
lifespan (``start(app)``) unless a test overrides :func:`engine.get_engine`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler

from . import openapi_models
from .engine import build_engine, get_engine, start_background_loading
from .errors import (
    ProblemError,
    is_internal,
    problem_error_handler,
    problem_response,
    validation_errors,
)
from .routers import (
    admin,
    analytics,
    capabilities,
    evidence,
    instruments,
    market,
    simulation,
    strategies,
)

log = logging.getLogger(__name__)

ROUTERS = (
    capabilities.router,
    simulation.router,
    strategies.router,
    analytics.router,
    evidence.router,
    admin.router,
    market.router,
    instruments.router,
)


async def _validation_handler(request: Request, exc: RequestValidationError):
    if is_internal(request):
        return problem_response(
            422,
            "invalid_request",
            "request parameters are invalid",
            instance=request.url.path,
            errors=validation_errors(exc),
        )
    return await request_validation_exception_handler(request, exc)


async def _http_handler(request: Request, exc: StarletteHTTPException):
    if is_internal(request):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return problem_response(
            exc.status_code,
            code,
            str(exc.detail),
            instance=request.url.path,
            headers=getattr(exc, "headers", None),
        )
    return await http_exception_handler(request, exc)


def install(app: FastAPI) -> None:
    for router in ROUTERS:
        app.include_router(router)
    app.add_exception_handler(ProblemError, problem_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    openapi_models.install(app)


def start(app: FastAPI, settings) -> None:
    """Lifespan hook: build the shared engine unless a test injected one."""
    app.state.research_engine = None
    app.state.research_engine_error = None
    if get_engine in app.dependency_overrides:
        return
    try:
        engine = build_engine(settings)
    except Exception as exc:  # legacy endpoints keep working without the engine
        log.exception("research engine failed to start")
        app.state.research_engine_error = f"{type(exc).__name__}: {exc}"
        return
    app.state.research_engine = engine
    start_background_loading(engine)


def stop(app: FastAPI) -> None:
    engine = getattr(app.state, "research_engine", None)
    if engine is not None:
        engine.shutdown()
    app.state.research_engine = None


__all__ = ["get_engine", "install", "start", "stop"]
