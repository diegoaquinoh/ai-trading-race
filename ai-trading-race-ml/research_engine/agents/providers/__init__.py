"""Model providers behind the provider-neutral ``ModelProvider`` interface.

``build_provider(name, ...)`` constructs one by name:

* ``reference`` - :class:`ReferenceHeuristicProvider` (deterministic, offline,
  rule-based; reported as provider ``reference``, never as a hosted LLM);
* ``recorded`` - :class:`RecordedResponseProvider` over a recordings directory;
* ``anthropic`` - :class:`AnthropicProvider` (key from ``ANTHROPIC_API_KEY``);
* ``openai`` / ``openai_compatible`` - :class:`OpenAICompatibleProvider`
  (OpenAI, Azure OpenAI, Groq-hosted Llama, local servers via ``base_url``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .anthropic import AnthropicProvider
from .base import (
    ChatMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderConfigurationError,
    ProviderError,
    ProviderRefusal,
    ProviderTimeout,
    RecordingMissing,
    RequestMetadata,
)
from .openai_compat import OpenAICompatibleProvider
from .recorded import RecordedResponseProvider, RecordingProvider, RecordingStore
from .reference import REFERENCE_MODEL_ID, ReferenceHeuristicProvider

__all__ = [
    "AnthropicProvider",
    "ChatMessage",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "OpenAICompatibleProvider",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderRefusal",
    "ProviderTimeout",
    "REFERENCE_MODEL_ID",
    "RecordedResponseProvider",
    "RecordingMissing",
    "RecordingProvider",
    "RecordingStore",
    "ReferenceHeuristicProvider",
    "RequestMetadata",
    "build_provider",
]


def build_provider(
    name: str,
    *,
    model: Optional[str] = None,
    recordings: Optional[Path | str] = None,
    base_url: Optional[str] = None,
    **options: Any,
) -> ModelProvider:
    name = (name or "reference").lower()
    if name == "reference":
        return ReferenceHeuristicProvider()
    if name == "recorded":
        if recordings is None:
            raise ProviderConfigurationError("recorded replay needs a recordings directory")
        return RecordedResponseProvider(recordings)
    if name == "anthropic":
        kwargs = dict(options)
        if base_url:
            kwargs["base_url"] = base_url
        return AnthropicProvider(model or "claude-sonnet-5-5", **kwargs)
    if name in ("openai", "openai_compatible"):
        if not model:
            raise ProviderConfigurationError("openai-compatible providers need a pinned model id")
        kwargs = dict(options)
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAICompatibleProvider(model, **kwargs)
    raise ProviderConfigurationError(f"unknown provider {name!r}")
