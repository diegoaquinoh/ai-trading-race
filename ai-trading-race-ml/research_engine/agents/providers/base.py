"""Provider-neutral model interface (``model-provider-v1``).

A :class:`ModelRequest` carries a system prompt, the exact message list, an
optional JSON schema for the expected output and request metadata (decision id,
agent role, attempt purpose, prompt version). A provider returns a
:class:`ModelResponse` with the response text, input/output token counts, the
provider label, the model id and the latency.

Providers perform exactly one model call per ``generate``. Retries after
transient failures are separate generation attempts decided by the agent
workflow, so every call consumes the decision-wide budget (spec 10.4).

The recording fingerprint (:meth:`ModelRequest.fingerprint`) is a hash over the
decision id, role, attempt purpose, prompt version and the hash of the exact
messages (system prompt, messages and output schema). It never includes wall
clock values, so a replay of the same decision reproduces it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from research_engine.contracts.common import HASH_PREFIX, content_hash

PROVIDER_INTERFACE_VERSION = "model-provider-v1"
TOKEN_ESTIMATOR_VERSION = "char4-estimate-v1"


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str

    def to_wire(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class RequestMetadata:
    decision_id: str
    role: str
    purpose: str
    prompt_version: str
    attempt_number: int = 0  # informational only; not part of the fingerprint


@dataclass(frozen=True)
class ModelRequest:
    system: str
    messages: tuple[ChatMessage, ...]
    metadata: RequestMetadata
    json_schema: Optional[dict[str, Any]] = None
    schema_name: str = "agent_output"
    max_output_tokens: int = 2048

    def payload_text(self) -> str:
        """Everything the model reads, used for worst-case token estimates."""
        parts = [self.system] + [m.content for m in self.messages]
        if self.json_schema is not None:
            from research_engine.contracts.common import canonical_json

            parts.append(canonical_json(self.json_schema))
        return "\n".join(parts)

    def messages_hash(self) -> str:
        return content_hash(
            {
                "system": self.system,
                "messages": [m.to_wire() for m in self.messages],
                "schemaName": self.schema_name,
                "schema": self.json_schema,
            }
        )

    def fingerprint(self) -> str:
        meta = self.metadata
        return content_hash(
            {
                "decisionId": meta.decision_id,
                "role": meta.role,
                "purpose": meta.purpose,
                "promptVersion": meta.prompt_version,
                "messagesHash": self.messages_hash(),
            }
        )


@dataclass(frozen=True)
class ModelResponse:
    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str
    latency_ms: int
    stop_reason: Optional[str] = None
    response_id: Optional[str] = None
    recorded_response_id: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    """A model call failed. ``transient`` marks retryable failures (429/5xx/network).

    ``input_tokens`` / ``output_tokens`` carry the usage the provider reported for
    the failed call (e.g. a refusal still bills its tokens); ``None`` when the
    provider reported none. The workflow commits them against the budget.
    """

    kind = "provider_error"

    def __init__(
        self,
        message: str,
        *,
        transient: bool = False,
        status: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ):
        super().__init__(message)
        self.transient = transient
        self.status = status
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model

    @property
    def reported_usage(self) -> bool:
        return self.input_tokens is not None or self.output_tokens is not None


class ProviderConfigurationError(ProviderError):
    kind = "provider_configuration"


class ProviderRefusal(ProviderError):
    kind = "provider_refusal"


class ProviderTimeout(ProviderError):
    kind = "timeout"

    def __init__(self, message: str):
        super().__init__(message, transient=True)


class RecordingMissing(ProviderError):
    """Recorded replay has no response for this exact request fingerprint."""

    kind = "recording_missing"

    def __init__(self, fingerprint: str, metadata: RequestMetadata):
        super().__init__(
            f"no recorded response for fingerprint {fingerprint} "
            f"(decision={metadata.decision_id}, role={metadata.role}, "
            f"purpose={metadata.purpose}, prompt={metadata.prompt_version})"
        )
        self.fingerprint = fingerprint
        self.metadata = metadata


@runtime_checkable
class ModelProvider(Protocol):
    provider: str  # label reported everywhere, e.g. "anthropic", "reference"
    model: str  # pinned model identifier
    deterministic: bool  # recorded and fresh responses are identical
    priced: bool  # fresh calls incur provider charges

    def generate(self, request: ModelRequest) -> ModelResponse: ...


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate (``char4-estimate-v1``): ceil(chars / 4)."""
    return max(1, math.ceil(len(text) / 4))


WORST_CASE_ESTIMATOR_VERSION = "char3.5-upper-v1"


def worst_case_tokens(text: str) -> int:
    """Upper estimate for budget reservations (``char3.5-upper-v1``): ceil(chars/3.5) + 64.

    If a provider reports more than was reserved, the actual count is still
    recorded and a crossed ceiling ends the decision ``failed_budget``.
    """
    return max(1, math.ceil(len(text) * 2 / 7) + 64)


def recorded_response_id(fingerprint: str, occurrence: int) -> str:
    digest = fingerprint[len(HASH_PREFIX) :][:24]
    return f"rec-{digest}" if occurrence == 0 else f"rec-{digest}-{occurrence}"
