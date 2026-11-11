"""Strict request decoding for the internal API (spec 14.1).

* JSON bodies are decoded with ``NaN``/``Infinity`` rejected (400).
* Floats stay floats, so contract ``DecimalStr`` fields reject them (422):
  money, face, prices, rates and weights must be decimal strings.
* Unknown schema major versions are rejected (422).
* Request-hash bound idempotency for ``requestId`` scoped commands (409 on reuse
  with a different payload) and deterministic replay caches for transitions and
  decisions keyed by the canonical request hash.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from datetime import date
from typing import Any, Optional, TypeVar

from fastapi import Request
from pydantic import BaseModel, ValidationError

from research_engine.contracts.common import check_schema_version, content_hash

from .errors import ProblemError, bad_request, conflict, unprocessable, validation_errors

M = TypeVar("M", bound=BaseModel)

MAX_BODY_BYTES = 8 * 1024 * 1024


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-finite number {token} is not permitted")


def decode_json(raw: bytes) -> Any:
    if not raw or not raw.strip():
        raise bad_request("empty_body", "a JSON request body is required")
    if len(raw) > MAX_BODY_BYTES:
        raise ProblemError(413, "body_too_large", "request body exceeds 8 MiB")
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except ValueError as exc:
        if "non-finite" in str(exc):
            raise bad_request("non_finite_number", str(exc)) from exc
        raise bad_request("malformed_json", f"request body is not valid JSON: {exc}") from exc


async def read_object(request: Request) -> dict[str, Any]:
    body = decode_json(await request.body())
    if not isinstance(body, dict):
        raise unprocessable("invalid_request", "the request body must be a JSON object")
    check_version(body.get("schemaVersion"))
    return body


def check_version(version: Any, field: str = "schemaVersion") -> None:
    if version is None:
        return
    if not isinstance(version, str):
        raise unprocessable("unsupported_schema_version", f"{field} must be a string")
    try:
        check_schema_version(version)
    except ValueError as exc:
        raise unprocessable("unsupported_schema_version", str(exc)) from exc


def parse_model(model: type[M], data: Any, *, code: str = "invalid_request") -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise unprocessable(
            code, f"request does not satisfy {model.__name__}", errors=validation_errors(exc)
        ) from exc


def request_body_hash(body: Any) -> str:
    """``content_hash`` of a JSON request body exactly as received (request binding).

    The parsed body is hashed as-is (canonical JSON: sorted keys, compact separators,
    ASCII escaping), so omitted fields stay omitted and defaults are never filled in;
    the caller reproduces the value from the bytes it sent. Floats are not canonical
    (decimals travel as strings), so a body that still holds one after model
    validation is rejected with 422.
    """
    try:
        return content_hash(body)
    except TypeError as exc:
        raise unprocessable(
            "non_canonical_number",
            f"request body is not hashable canonical JSON: {exc}; send decimals as strings",
        ) from exc


def parse_date(value: Optional[str], field: str, *, required: bool = True) -> Optional[date]:
    if value is None or value == "":
        if required:
            raise unprocessable("invalid_request", f"{field} is required (YYYY-MM-DD)")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise unprocessable("invalid_request", f"{field} must be an ISO date YYYY-MM-DD") from exc


class RequestRegistry:
    """``(scope, requestId) -> request hash``: reuse with other content is a 409."""

    def __init__(self, max_entries: int = 20000):
        self._items: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._max = max_entries
        self._lock = threading.Lock()

    def bind(self, scope: str, request_id: str, payload: Any) -> str:
        digest = content_hash(payload, allow_floats=True)
        key = (scope, request_id)
        with self._lock:
            existing = self._items.get(key)
            if existing is not None and existing != digest:
                raise conflict(
                    "idempotency_key_reused",
                    f"requestId {request_id!r} was already used with a different payload",
                )
            self._items[key] = digest
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)
        return digest


class ResponseCache:
    """Bounded LRU of serialized response bodies keyed by canonical request hash."""

    def __init__(self, max_entries: int = 256):
        self._items: OrderedDict[str, bytes] = OrderedDict()
        self._max = max_entries
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items.move_to_end(key)
            return hit

    def put(self, key: str, body: bytes) -> bytes:
        with self._lock:
            existing = self._items.get(key)
            if existing is not None:
                return existing
            self._items[key] = body
            while len(self._items) > self._max:
                self._items.popitem(last=False)
            return body


def dumps(payload: Any) -> bytes:
    """Stable JSON bytes for responses (sorted keys, no NaN)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
