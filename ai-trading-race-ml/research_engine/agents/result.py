"""StrategyResult assembly, hashing and signing (spec 14.5).

``result_hash = content_hash(result.hash_payload())`` and
``signature = sign_hash(result_hash, key)`` with the key from
``FI_RESULT_SIGNING_KEY`` (UTF-8). Without it a fixed development key is used
and a warning is logged once; never use it outside development.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from research_engine.contracts.common import content_hash, sign_hash, verify_signature
from research_engine.contracts.decisions import StrategyResult

log = logging.getLogger(__name__)

RESULT_SIGNING_KEY_ENV = "FI_RESULT_SIGNING_KEY"
DEV_RESULT_SIGNING_KEY = b"dev-only-insecure-strategy-result-key"
_warned = False


def result_signing_key() -> bytes:
    global _warned
    value = os.environ.get(RESULT_SIGNING_KEY_ENV)
    if value:
        return value.encode("utf-8")
    if not _warned:
        log.warning(
            "%s is not set; strategy results are signed with the development key " "(NOT secure).",
            RESULT_SIGNING_KEY_ENV,
        )
        _warned = True
    return DEV_RESULT_SIGNING_KEY


def seal_result(result: StrategyResult, key: Optional[bytes] = None) -> StrategyResult:
    key = key if key is not None else result_signing_key()
    bare = result.model_copy(update={"result_hash": None, "signature": None})
    digest = content_hash(bare.hash_payload())
    sealed = bare.model_copy(update={"result_hash": digest, "signature": sign_hash(digest, key)})
    return StrategyResult.model_validate(sealed.model_dump())


def verify_result(result: StrategyResult, key: Optional[bytes] = None) -> bool:
    key = key if key is not None else result_signing_key()
    if not result.result_hash or not result.signature:
        return False
    if content_hash(result.hash_payload()) != result.result_hash:
        return False
    return verify_signature(result.result_hash, result.signature, key)


def completion_time(decision_as_of: datetime, latency_ms: int, timing: str) -> datetime:
    """Logical timing keeps results reproducible: cutoff + recorded model latency."""
    if timing == "wall":
        return datetime.now(timezone.utc)
    return decision_as_of + timedelta(milliseconds=latency_ms)
