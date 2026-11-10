"""OpenAI-compatible Chat Completions client over httpx.

Covers OpenAI, Azure OpenAI deployments, Groq-hosted Llama and local
OpenAI-compatible servers (vLLM, Ollama, llama.cpp) through configuration:

* standard: ``POST {base_url}/chat/completions`` with ``Authorization: Bearer``;
* Azure: ``POST {base_url}/openai/deployments/{deployment}/chat/completions
  ?api-version=...`` with an ``api-key`` header;
* local servers may run without a key (``api_key_required=False``).

``response_format`` is ``json_schema`` (strict schema), ``json_object`` or
``none``. Usage is read from ``usage.prompt_tokens`` / ``completion_tokens``.
Temperature and an optional seed are pinned when the server supports them; a
seed is not a guarantee of identical hosted responses (spec 16.2).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Literal, Optional

import httpx

from .base import (
    ModelRequest,
    ModelResponse,
    ProviderConfigurationError,
    ProviderError,
    ProviderTimeout,
)


class OpenAICompatibleProvider:
    deterministic = False

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key: Optional[str] = None,
        api_key_env: str = "OPENAI_API_KEY",
        api_key_required: bool = True,
        azure_deployment: Optional[str] = None,
        azure_api_version: Optional[str] = None,
        provider_label: str = "openai_compatible",
        response_format: Literal["json_schema", "json_object", "none"] = "json_schema",
        priced: bool = True,
        temperature: Optional[str] = "0",
        seed: Optional[int] = None,
        timeout_seconds: float = 60.0,
        transport: Optional[httpx.BaseTransport] = None,
        clock: Callable[[], float] = time.perf_counter,
    ):
        if not model:
            raise ProviderConfigurationError("a pinned model id is required")
        if azure_deployment and not azure_api_version:
            raise ProviderConfigurationError("Azure deployments require azure_api_version")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.api_key_env = api_key_env
        self.api_key_required = api_key_required
        self.azure_deployment = azure_deployment
        self.azure_api_version = azure_api_version
        self.provider = provider_label
        self.response_format = response_format
        self.priced = priced
        self.temperature = temperature
        self.seed = seed
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._clock = clock

    def _key(self) -> str:
        key = self._api_key or os.environ.get(self.api_key_env, "")
        if not key and self.api_key_required:
            raise ProviderConfigurationError(f"{self.api_key_env} is not set")
        return key

    def endpoint(self) -> tuple[str, dict[str, str]]:
        key = self._key()
        if self.azure_deployment:
            url = (
                f"{self.base_url}/openai/deployments/{self.azure_deployment}"
                f"/chat/completions?api-version={self.azure_api_version}"
            )
            headers = {"api-key": key} if key else {}
        else:
            url = f"{self.base_url}/chat/completions"
            headers = {"authorization": f"Bearer {key}"} if key else {}
        headers["content-type"] = "application/json"
        return url, headers

    def build_body(self, request: ModelRequest) -> dict[str, Any]:
        messages = [{"role": "system", "content": request.system}] + [
            m.to_wire() for m in request.messages
        ]
        body: dict[str, Any] = {
            "model": self.azure_deployment or self.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
        }
        if self.temperature is not None:
            body["temperature"] = float(self.temperature)
        if self.seed is not None:
            body["seed"] = self.seed
        if self.response_format == "json_schema" and request.json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "schema": request.json_schema,
                    "strict": True,
                },
            }
        elif self.response_format in ("json_object", "json_schema"):
            body["response_format"] = {"type": "json_object"}
        return body

    def generate(self, request: ModelRequest) -> ModelResponse:
        url, headers = self.endpoint()
        started = self._clock()
        try:
            with httpx.Client(transport=self._transport, timeout=self.timeout_seconds) as client:
                reply = client.post(url, headers=headers, json=self.build_body(request))
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.provider} request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.provider} transport error: {exc}", transient=True) from exc
        latency_ms = int((self._clock() - started) * 1000)
        if reply.status_code != 200:
            transient = reply.status_code == 429 or reply.status_code >= 500
            raise ProviderError(
                f"{self.provider} HTTP {reply.status_code}: {reply.text[:200]}",
                transient=transient,
                status=reply.status_code,
            )
        try:
            data = reply.json()
            choice = data["choices"][0]
            message = choice["message"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.provider} returned an unexpected body") from exc
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        if message.get("refusal"):
            from .base import ProviderRefusal

            raise ProviderRefusal(
                f"{self.provider} model declined: {message['refusal'][:200]}",
                input_tokens=int(usage.get("prompt_tokens") or 0) if usage else None,
                output_tokens=int(usage.get("completion_tokens") or 0) if usage else None,
                model=str(data.get("model") or self.model),
            )
        usage = usage or {}
        return ModelResponse(
            text=message.get("content") or "",
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            provider=self.provider,
            model=str(data.get("model") or self.model),
            latency_ms=latency_ms,
            stop_reason=choice.get("finish_reason"),
            response_id=data.get("id"),
        )
