"""Application-owned QuantLib wrapper: global settings isolation and conversions.

QuantLib keeps ``Settings.instance().evaluationDate`` as mutable process-global
state. Rate helpers and instruments read it lazily, so two concurrent requests
with different as-of dates could contaminate each other (spec 8.3). Every
evaluation-date-dependent QuantLib call in this package runs inside
``evaluation_date(...)``, which

* acquires one process-wide re-entrant lock (serializing all such blocks),
* sets the evaluation date for the block, and
* restores the previous evaluation date on exit, even on error.

Pure calendar arithmetic does not read the evaluation date and does not need
the lock, but taking it is harmless.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import date
from typing import Iterator

import QuantLib as ql

ENGINE_NAME = "research_engine.numerical"
ENGINE_SEMVER = "1.0.0"
QUANTLIB_VERSION = ql.__version__
ENGINE_VERSION = f"{ENGINE_SEMVER}+quantlib-{QUANTLIB_VERSION}"
LIBRARY = f"QuantLib {QUANTLIB_VERSION}"
CONVENTIONS_VERSION = "usd-treasury-conventions-v1"

_QL_LOCK = threading.RLock()


def ql_lock() -> threading.RLock:
    """The single lock guarding QuantLib global settings."""
    return _QL_LOCK


def to_ql_date(value: date) -> ql.Date:
    return ql.Date(value.day, value.month, value.year)


def from_ql_date(value: ql.Date) -> date:
    return date(value.year(), value.month(), value.dayOfMonth())


@contextmanager
def evaluation_date(value: date) -> Iterator[ql.Date]:
    """Serialize a QuantLib block under ``value`` and restore the prior date."""
    with _QL_LOCK:
        settings = ql.Settings.instance()
        previous = settings.evaluationDate
        target = to_ql_date(value)
        settings.evaluationDate = target
        try:
            yield target
        finally:
            settings.evaluationDate = previous


def current_evaluation_date() -> date:
    with _QL_LOCK:
        return from_ql_date(ql.Settings.instance().evaluationDate)
