"""RFC 9457 problem+json errors for the internal API (spec 14.6).

* 400/422 invalid request, unsupported schema/convention or units; 422 also for
  deterministic engine rejections (ledger invariants such as
  ``ledger_invariant_violation`` / ``withdrawal_exceeds_available_cash``, numerical
  ``calculation_rejected``) - they depend only on the request and never mean an outage;
* 401 authentication failure;
* 404 unknown resource;
* 409 state-hash/snapshot mismatch, stale version, idempotency payload mismatch;
* 429 decision concurrency limit (with ``Retry-After``);
* 503 dependency or numerical capability unavailable.

Domain outcomes (HOLD, abstention, stale data) are 200 results, never errors.
Only unexpected exceptions surface as 500.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_BASE = "https://ai-trading-race.local/problems/"

TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


class ProblemError(Exception):
    """Raised by internal endpoints; rendered as problem+json."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        *,
        errors: Optional[list[dict[str, Any]]] = None,
        headers: Optional[dict[str, str]] = None,
        extra: Optional[dict[str, Any]] = None,
    ):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.errors = errors
        self.headers = headers or {}
        self.extra = extra or {}


def bad_request(code: str, detail: str, **kw: Any) -> ProblemError:
    return ProblemError(400, code, detail, **kw)


def unprocessable(code: str, detail: str, **kw: Any) -> ProblemError:
    return ProblemError(422, code, detail, **kw)


def not_found(code: str, detail: str, **kw: Any) -> ProblemError:
    return ProblemError(404, code, detail, **kw)


def conflict(code: str, detail: str, **kw: Any) -> ProblemError:
    return ProblemError(409, code, detail, **kw)


def unavailable(code: str, detail: str, **kw: Any) -> ProblemError:
    return ProblemError(503, code, detail, **kw)


def problem_body(
    status: int,
    code: str,
    detail: str,
    instance: Optional[str] = None,
    errors: Optional[list[dict[str, Any]]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": PROBLEM_BASE + code,
        "title": TITLES.get(status, "Error"),
        "status": status,
        "code": code,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    if errors:
        body["errors"] = errors
    if extra:
        body.update(extra)
    return body


def problem_response(
    status: int,
    code: str,
    detail: str,
    *,
    instance: Optional[str] = None,
    errors: Optional[list[dict[str, Any]]] = None,
    headers: Optional[dict[str, str]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=problem_body(status, code, detail, instance, errors, extra),
        headers=headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def validation_errors(exc: ValidationError | RequestValidationError) -> list[dict[str, Any]]:
    out = []
    for item in exc.errors():
        loc = [str(part) for part in item.get("loc", ())]
        out.append({"loc": loc, "msg": str(item.get("msg", "")), "type": item.get("type", "")})
    return out[:50]


def is_internal(request: Request) -> bool:
    return request.url.path.startswith("/internal/")


async def problem_error_handler(request: Request, exc: ProblemError) -> JSONResponse:
    return problem_response(
        exc.status,
        exc.code,
        exc.detail,
        instance=request.url.path,
        errors=exc.errors,
        headers=exc.headers,
        extra=exc.extra,
    )
