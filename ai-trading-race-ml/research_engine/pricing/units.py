"""Explicit float -> Decimal conversions at the contract boundary.

Solvers use binary floats; contract fields carry decimals. Conversion goes
through ``repr`` (shortest round-tripping text) and is then quantized:

* prices per 100 face: 10 dp
* decimal rates / yields: 12 dp
* USD values in calculation outputs: 6 dp (ledger cents are applied by the
  simulation engine at posting time, not here)
* years / durations / convexities: 10 dp
* discount factors: 14 dp
"""

from __future__ import annotations

import math
from decimal import Decimal

PRICE_Q = Decimal("1e-10")
RATE_Q = Decimal("1e-12")
USD_Q = Decimal("1e-6")
YEARS_Q = Decimal("1e-10")
DF_Q = Decimal("1e-14")


def to_decimal(value: float | Decimal, quantum: Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(quantum)
    if not math.isfinite(value):
        raise ValueError("non-finite numerical result cannot cross the contract boundary")
    return Decimal(repr(float(value))).quantize(quantum)


def price_dec(value: float | Decimal) -> Decimal:
    return to_decimal(value, PRICE_Q)


def rate_dec(value: float | Decimal) -> Decimal:
    return to_decimal(value, RATE_Q)


def usd_dec(value: float | Decimal) -> Decimal:
    return to_decimal(value, USD_Q)


def years_dec(value: float | Decimal) -> Decimal:
    return to_decimal(value, YEARS_Q)


def df_dec(value: float | Decimal) -> Decimal:
    return to_decimal(value, DF_Q)
