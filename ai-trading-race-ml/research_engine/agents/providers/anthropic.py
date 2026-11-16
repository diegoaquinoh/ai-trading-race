"""Anthropic Messages API client over httpx (no SDK dependency).

* Endpoint ``POST {base_url}/v1/messages`` with ``x-api-key`` (from
  ``ANTHROPIC_API_KEY`` unless given) and ``anthropic-version: 2026-10-21``.
* The model id is pinned from configuration (default ``claude-sonnet-5-5``);
  aliases are never resolved silently.
* Structured output: when the request carries a JSON schema the body sends
  ``output_config.format = {"type": "json_schema", "schema": ...}``.
* No sampling parameters are sent (the 2026-10-21 API version rejects them).
  Thinking is left at the model default; only ``text`` blocks are read and
  thinking content is never requested, stored or exposed.
* Input tokens = ``input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens`` so every resent token counts against the budget.
* One HTTP call per ``generate``; 429/5xx/network errors raise a transient
  :class:`ProviderError` and the workflow decides whether to retry.
* A refusal (``stop_reason = refusal``) raises :class:`ProviderRefusal` carrying
  the reported usage, so the refused call's tokens still count against the budget.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Optional

import httpx

from .base import (
    ModelRequest,
    ModelResponse,
    ProviderConfigurationError,
    ProviderError,
    ProviderRefusal,
    ProviderTimeout,
)

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2026-10-21"
API_KEY_ENV = "ANTHROPIC_API_KEY"


class AnthropicProvider:
    provider = "anthropic"
    deterministic = False
    priced = True

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        structured_output: bool = True,
        effort: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        clock: Callable[[], float] = time.perf_counter,
    ):
        if not model:
            raise ProviderConfigurationError("a pinned Anthropic model id is required")
        self.model = model
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.structured_output = structured_output
        self.effort = effort
        self._transport = transport
        self._clock = clock

    def _key(self) -> str:
        key = self._api_key or os.environ.get(API_KEY_ENV, "")
        if not key:
            raise ProviderConfigurationError(f"{API_KEY_ENV} is not set")
        return key

    def build_body(self, request: ModelRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "system": request.system,
            "messages": [m.to_wire() for m in request.messages],
        }
        output_config: dict[str, Any] = {}
        if self.structured_output and request.json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
        if self.effort:
            output_config["effort"] = self.effort
        if output_config:
            body["output_config"] = output_config
        return body

    def generate(self, request: ModelRequest) -> ModelResponse:
        headers = {
            "x-api-key": self._key(),
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        started = self._clock()
        try:
            with httpx.Client(transport=self._transport, timeout=self.timeout_seconds) as client:
                reply = client.post(
                    f"{self.base_url}/v1/messages", headers=headers, json=self.build_body(request)
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"anthropic request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic transport error: {exc}", transient=True) from exc
        latency_ms = int((self._clock() - started) * 1000)
        if reply.status_code != 200:
            transient = reply.status_code == 429 or reply.status_code >= 500
            raise ProviderError(
                f"anthropic HTTP {reply.status_code}: {_error_message(reply)}",
                transient=transient,
                status=reply.status_code,
            )
        try:
            data = reply.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("anthropic returned non-JSON body", transient=True) from exc
        stop_reason = data.get("stop_reason")
        input_tokens, output_tokens = usage_tokens(data)
        if stop_reason == "refusal":
            details = data.get("stop_details") or {}
            has_usage = isinstance(data.get("usage"), dict)
            raise ProviderRefusal(
                f"model declined (category={details.get('category')})",
                input_tokens=input_tokens if has_usage else None,
                output_tokens=output_tokens if has_usage else None,
                model=str(data.get("model") or self.model),
            )
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return ModelResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider=self.provider,
            model=str(data.get("model") or self.model),
            latency_ms=latency_ms,
            stop_reason=stop_reason,
            response_id=data.get("id"),
        )


def usage_tokens(data: Any) -> tuple[int, int]:
    """(input, output) tokens; input includes cache creation and cache reads."""
    usage = data.get("usage") if isinstance(data, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
    )
    return input_tokens, int(usage.get("output_tokens") or 0)


def _error_message(reply: httpx.Response) -> str:
    try:
        data = reply.json()
    except ValueError:
        return reply.text[:200]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return f"{error.get('type')}: {error.get('message')}"
    return str(data)[:200]
