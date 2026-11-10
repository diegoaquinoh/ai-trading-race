"""Content-addressed, HMAC-signed registry of calculation results (spec 14.7).

Other components resolve a model-supplied ``calculation_id`` here and call
``verify`` before trusting it: a plausible-looking id that was never produced
by the engine, or a tampered payload, fails verification.

Signing key: ``RESEARCH_SIGNING_KEY`` (UTF-8). If unset, a fixed development
key is used and a warning is logged once; never use it outside development.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from research_engine.contracts.calculations import CalculationResult
from research_engine.contracts.common import content_hash, short_id, sign_hash, verify_signature

log = logging.getLogger(__name__)

SIGNING_KEY_ENV = "RESEARCH_SIGNING_KEY"
DEV_SIGNING_KEY = b"dev-only-insecure-research-signing-key"
_warned = False


def signing_key_from_env() -> bytes:
    global _warned
    value = os.environ.get(SIGNING_KEY_ENV)
    if value:
        return value.encode("utf-8")
    if not _warned:
        log.warning(
            "%s is not set; using the development signing key. Calculation signatures "
            "are NOT secure in this mode.",
            SIGNING_KEY_ENV,
        )
        _warned = True
    return DEV_SIGNING_KEY


class CalculationConflictError(RuntimeError):
    pass


def calculation_id_for(result: CalculationResult) -> str:
    return short_id("calc", result.id_payload())


class CalculationStore:
    def __init__(self, key: Optional[bytes] = None, path: Optional[Path] = None):
        self._key = key if key is not None else signing_key_from_env()
        self._path = Path(path) if path else None
        self._items: dict[str, CalculationResult] = {}
        self._lock = threading.Lock()
        if self._path and self._path.exists():
            for line in self._path.read_text().splitlines():
                if line.strip():
                    item = CalculationResult.model_validate(json.loads(line))
                    if item.calculation_id:
                        self._items[item.calculation_id] = item

    def seal(self, result: CalculationResult) -> CalculationResult:
        """Assign id, content hash and signature (pure; does not store)."""
        bare = result.model_copy(
            update={"calculation_id": None, "content_hash": None, "signature": None}
        )
        with_id = bare.model_copy(update={"calculation_id": calculation_id_for(bare)})
        digest = content_hash(with_id.hash_payload())
        return with_id.model_copy(
            update={"content_hash": digest, "signature": sign_hash(digest, self._key)}
        )

    def register(self, result: CalculationResult) -> CalculationResult:
        sealed = self.seal(result)
        calc_id = sealed.calculation_id
        assert calc_id is not None
        with self._lock:
            existing = self._items.get(calc_id)
            if existing is not None:
                if existing.content_hash != sealed.content_hash:
                    raise CalculationConflictError(f"{calc_id} already stored with other content")
                return existing
            self._items[calc_id] = sealed
            if self._path:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a") as handle:
                    handle.write(json.dumps(sealed.to_wire(), sort_keys=True) + "\n")
        return sealed

    def get(self, calc_id: str) -> Optional[CalculationResult]:
        with self._lock:
            return self._items.get(calc_id)

    def __contains__(self, calc_id: str) -> bool:
        return self.get(calc_id) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def verify_result(self, result: CalculationResult) -> bool:
        """Id, hash and signature all match the payload under this store's key."""
        if not result.calculation_id or not result.content_hash or not result.signature:
            return False
        if calculation_id_for(result) != result.calculation_id:
            return False
        if content_hash(result.hash_payload()) != result.content_hash:
            return False
        return verify_signature(result.content_hash, result.signature, self._key)

    def verify(self, calc_id: str) -> bool:
        result = self.get(calc_id)
        return result is not None and self.verify_result(result)
