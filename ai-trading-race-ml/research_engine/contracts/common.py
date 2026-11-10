"""Shared contract primitives used across every research-engine boundary.

Rules (spec sections 8.1, 14.1):

* Wire format is camelCase JSON. Python attributes are snake_case.
* Money, face, prices, rates and weights cross the boundary as decimal strings.
  Floats are rejected for decimal contract fields: construct ``Decimal`` explicitly.
* Instants are UTC ISO-8601 strings ending in ``Z``. Naive datetimes are rejected.
* Contractual dates remain ``YYYY-MM-DD`` dates.
* Hashed payloads are canonical JSON (sorted keys, compact separators, ASCII
  escaping, no floats). The same canonicalization is implemented in .NET
  (``CanonicalJson``) and pinned by ``contracts/test-vectors/canonical-json.json``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
)
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = "1.0"
SCHEMA_MAJOR = 1

CASH_SECURITY_ID = "CASH-USD"
HASH_PREFIX = "sha256:"
SIGNATURE_PREFIX = "hmac-sha256:"


# --------------------------------------------------------------------------- #
# Decimal strings
# --------------------------------------------------------------------------- #


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("booleans are not decimal values")
    if isinstance(value, float):
        raise ValueError(
            "floats are not accepted for decimal contract fields; "
            "construct Decimal explicitly or send a decimal string"
        )
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError(f"invalid decimal string: {value!r}") from exc
    else:
        raise ValueError(f"unsupported decimal input type: {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("NaN and infinite values are rejected")
    return result


def decimal_to_str(value: Decimal) -> str:
    """Fixed-point representation without exponent; ``-0`` normalizes to ``0``."""
    text = format(value, "f")
    if text.startswith("-") and Decimal(text) == 0:
        text = text[1:]
    return text


DecimalStr = Annotated[
    Decimal,
    BeforeValidator(_to_decimal),
    PlainSerializer(decimal_to_str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": r"^-?\d+(\.\d+)?$"}),
]


def money(value: Decimal | int | str, places: int = 2) -> Decimal:
    """Round a cash amount to the ledger posting precision (cents by default).

    Uses banker's-free ROUND_HALF_UP, the documented posting rule.
    """
    from decimal import ROUND_HALF_UP

    quantum = Decimal(1).scaleb(-places)
    return _to_decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# UTC instants
# --------------------------------------------------------------------------- #


def _to_utc(value: Any) -> datetime:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if not isinstance(value, datetime):
        raise ValueError("expected an ISO-8601 instant with offset")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetimes are not permitted; supply an offset")
    return value.astimezone(timezone.utc)


def utc_to_str(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDatetime = Annotated[
    datetime,
    BeforeValidator(_to_utc),
    PlainSerializer(utc_to_str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


def utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Identifiers (distinct names so schemas document intent)
# --------------------------------------------------------------------------- #

_OPAQUE = r"^[A-Za-z0-9][A-Za-z0-9_\-\.:]{0,159}$"

OpaqueId = Annotated[str, StringConstraints(pattern=_OPAQUE)]
SecurityId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9\-\.]{1,63}$")]
StrategyId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
PortfolioId = Annotated[str, StringConstraints(pattern=_OPAQUE)]
SourceId = Annotated[str, StringConstraints(pattern=_OPAQUE)]
ContentHash = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


# --------------------------------------------------------------------------- #
# Base model
# --------------------------------------------------------------------------- #


class ContractModel(BaseModel):
    """Immutable, strict, camelCase-on-the-wire contract base."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        alias_generator=to_camel,
        use_enum_values=False,
        validate_default=True,
    )

    def to_wire(self) -> dict[str, Any]:
        """JSON-compatible dict with camelCase keys and decimal strings."""
        return self.model_dump(mode="json", by_alias=True)

    def compute_hash(self) -> str:
        """Content hash of the canonical wire form (``sha256:<hex>``)."""
        return content_hash(self)


class DataMode(str, Enum):
    SYNTHETIC_CURVE = "synthetic_curve"
    OBSERVED_SECURITY = "observed_security"


class InformationPolicy(str, Enum):
    """How ``available_at`` was established (spec 6.2)."""

    FORWARD_RECEIPT = "forward_receipt_v1"
    RECONSTRUCTED_PUBLICATION_PLUS_LAG = "reconstructed_publication_plus_lag_v1"


class Unit(str, Enum):
    USD = "USD"
    USD_FACE = "USD_FACE"
    PRICE_PER_100 = "PRICE_PER_100"
    DECIMAL_RATE = "DECIMAL_ANNUAL_RATE"
    BASIS_POINTS = "BASIS_POINTS"
    YEARS = "YEARS"
    WEIGHT = "WEIGHT_FRACTION"
    RATIO = "RATIO"
    COUNT = "COUNT"
    USD_PER_BP = "USD_PER_BP"


# --------------------------------------------------------------------------- #
# Canonical JSON, hashing and signing
# --------------------------------------------------------------------------- #


def _reject_floats(data: Any, path: str = "$") -> None:
    if isinstance(data, float):
        raise TypeError(f"float at {path}: hashed contract payloads must use decimal strings")
    if isinstance(data, dict):
        for key, item in data.items():
            if not isinstance(key, str):
                raise TypeError(f"non-string key at {path}")
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(data, (list, tuple)):
        for index, item in enumerate(data):
            _reject_floats(item, f"{path}[{index}]")


def _jsonable(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json", by_alias=True)
    if isinstance(data, Decimal):
        return decimal_to_str(data)
    if isinstance(data, datetime):
        return utc_to_str(data)
    if isinstance(data, date):
        return data.isoformat()
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, dict):
        return {str(k): _jsonable(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_jsonable(v) for v in data]
    return data


def canonical_json(data: Any, *, allow_floats: bool = False) -> str:
    """Deterministic JSON text used for every content hash.

    ``allow_floats`` exists only for Python-internal research artifacts that are
    never re-hashed by another runtime; float formatting is not portable.
    """
    payload = _jsonable(data)
    if not allow_floats:
        _reject_floats(payload)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def sha256_text(text: str) -> str:
    return HASH_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(raw).hexdigest()


def content_hash(data: Any, *, allow_floats: bool = False) -> str:
    return sha256_text(canonical_json(data, allow_floats=allow_floats))


def short_id(prefix: str, data: Any, length: int = 16) -> str:
    """Content-addressed identifier, e.g. ``calc-3f9a...``."""
    digest = content_hash(data, allow_floats=True)[len(HASH_PREFIX) :]
    return f"{prefix}-{digest[:length]}"


def sign_hash(hash_value: str, key: bytes) -> str:
    """HMAC-SHA256 over the ASCII hash string (not over re-serialized JSON)."""
    if not key:
        raise ValueError("signing key must be configured")
    mac = hmac.new(key, hash_value.encode("ascii"), hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + mac


def verify_signature(hash_value: str, signature: str, key: bytes) -> bool:
    if not key or not signature:
        return False
    return hmac.compare_digest(sign_hash(hash_value, key), signature)


def check_schema_version(version: str) -> None:
    """Reject unknown schema major versions (spec 14.1)."""
    try:
        major = int(version.split(".", 1)[0])
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"malformed schema version: {version!r}") from exc
    if major != SCHEMA_MAJOR:
        raise ValueError(f"unsupported schema major version {major}; expected {SCHEMA_MAJOR}")
