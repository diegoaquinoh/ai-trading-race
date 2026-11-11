"""Recorded responses: :class:`RecordingProvider` (capture) and
:class:`RecordedResponseProvider` (replay without provider access).

Storage (``recorded-responses-v1``), one directory per experiment:

* ``manifest.json`` - format, provider label, model id, disclosure;
* ``responses.jsonl`` - one record per response, sorted by key, holding the
  request fingerprint, occurrence index, decision id, role, purpose, prompt
  version, messages hash, response text, token counts and latency.

The key is ``<fingerprint>#<occurrence>``: the fingerprint covers decision id,
agent role, attempt purpose, prompt version and the hash of the exact messages,
so any change to prompts, tool outputs or evidence produces a different key and
replay fails explicitly with :class:`RecordingMissing` instead of serving a
response that was produced for different inputs. Request texts are not stored
(they are reproducible from the frozen inputs); only their hashes are.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from .base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderConfigurationError,
    RecordingMissing,
    recorded_response_id,
)

RECORDING_FORMAT = "recorded-responses-v1"
MANIFEST = "manifest.json"
RESPONSES = "responses.jsonl"


class RecordingStore:
    """Thread-safe, deterministic on-disk store of recorded responses."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self.manifest: dict[str, Any] = {}
        manifest_path = self.directory / MANIFEST
        if manifest_path.exists():
            self.manifest = json.loads(manifest_path.read_text())
            if self.manifest.get("format") != RECORDING_FORMAT:
                raise ProviderConfigurationError(
                    f"unsupported recording format {self.manifest.get('format')!r}"
                )
        responses = self.directory / RESPONSES
        if responses.exists():
            for line in responses.read_text().splitlines():
                if line.strip():
                    record = json.loads(line)
                    self._records[record["key"]] = record

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def get(self, key: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._records.get(key)

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._records)

    def init_manifest(self, provider: str, model: str, disclosure: str) -> None:
        with self._lock:
            if self.manifest:
                if (self.manifest["provider"], self.manifest["model"]) != (provider, model):
                    raise ProviderConfigurationError(
                        f"recording directory holds {self.manifest['provider']}/"
                        f"{self.manifest['model']}, not {provider}/{model}"
                    )
                return
            self.manifest = {
                "format": RECORDING_FORMAT,
                "provider": provider,
                "model": model,
                "disclosure": disclosure,
                "requestTextsStored": False,
            }
            self.directory.mkdir(parents=True, exist_ok=True)
            _atomic_write(
                self.directory / MANIFEST, json.dumps(self.manifest, indent=2, sort_keys=True)
            )

    def put(self, record: dict[str, Any]) -> None:
        with self._lock:
            existing = self._records.get(record["key"])
            if existing is not None and existing["text"] != record["text"]:
                raise ProviderConfigurationError(
                    f"recording {record['key']} already holds a different response"
                )
            self._records[record["key"]] = record
            lines = [
                json.dumps(self._records[k], sort_keys=True, separators=(",", ":"))
                for k in sorted(self._records)
            ]
            self.directory.mkdir(parents=True, exist_ok=True)
            _atomic_write(self.directory / RESPONSES, "\n".join(lines) + "\n")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class _OccurrenceCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: dict[str, int] = {}

    def next(self, fingerprint: str) -> int:
        with self._lock:
            index = self._seen.get(fingerprint, 0)
            self._seen[fingerprint] = index + 1
            return index


class RecordedResponseProvider:
    """Replays recorded responses; never contacts a provider."""

    deterministic = True
    priced = False
    replay = True

    def __init__(self, directory: Path | str):
        self.store = RecordingStore(directory)
        if not self.store.manifest:
            raise ProviderConfigurationError(f"no recordings found in {directory}")
        self.provider = self.store.manifest["provider"]
        self.model = self.store.manifest["model"]
        self._counter = _OccurrenceCounter()

    def generate(self, request: ModelRequest) -> ModelResponse:
        fingerprint = request.fingerprint()
        occurrence = self._counter.next(fingerprint)
        record = self.store.get(f"{fingerprint}#{occurrence}")
        if record is None:
            raise RecordingMissing(fingerprint, request.metadata)
        return ModelResponse(
            text=record["text"],
            input_tokens=int(record["inputTokens"]),
            output_tokens=int(record["outputTokens"]),
            provider=record["provider"],
            model=record["model"],
            latency_ms=int(record["latencyMs"]),
            stop_reason=record.get("stopReason"),
            response_id=record.get("responseId"),
            recorded_response_id=record["recordedResponseId"],
        )


class RecordingProvider:
    """Wraps a provider and persists every response for later replay."""

    replay = False
    capturing = True  # fresh inference whose responses are being recorded

    def __init__(self, inner: ModelProvider, directory: Path | str, *, disclosure: str = ""):
        self.inner = inner
        self.provider = inner.provider
        self.model = inner.model
        self.deterministic = inner.deterministic
        self.priced = inner.priced
        self.store = RecordingStore(directory)
        self.store.init_manifest(
            inner.provider, inner.model, disclosure or getattr(inner, "disclosure", "")
        )
        self._counter = _OccurrenceCounter()

    def generate(self, request: ModelRequest) -> ModelResponse:
        response = self.inner.generate(request)
        fingerprint = request.fingerprint()
        occurrence = self._counter.next(fingerprint)
        rid = recorded_response_id(fingerprint, occurrence)
        meta = request.metadata
        self.store.put(
            {
                "key": f"{fingerprint}#{occurrence}",
                "fingerprint": fingerprint,
                "occurrence": occurrence,
                "decisionId": meta.decision_id,
                "role": meta.role,
                "purpose": meta.purpose,
                "promptVersion": meta.prompt_version,
                "messagesHash": request.messages_hash(),
                "provider": response.provider,
                "model": response.model,
                "text": response.text,
                "inputTokens": response.input_tokens,
                "outputTokens": response.output_tokens,
                "latencyMs": response.latency_ms,
                "stopReason": response.stop_reason,
                "responseId": response.response_id,
                "recordedResponseId": rid,
            }
        )
        return replace(response, recorded_response_id=rid)
