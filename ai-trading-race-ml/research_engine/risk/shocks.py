"""Zero-rate shock shapes applied at curve nodes (continuous ACT/365F).

* Parallel: constant shift at every node -> exact parallel shift of the
  continuous zero curve inside the validated horizon.
* Key-rate: triangular ("tent") bumps on the key tenors ``KEY_RATE_TENORS_V1``.
  The first key is flat towards the curve start, the last key flat towards the
  horizon, so the bump weights form a partition of unity:
  ``SUM_k w_k(t) = 1`` for every t. Because node shocks enter ln D linearly and
  ln D is interpolated linearly, the sum of all key-rate shocks equals the
  parallel shock exactly; key-rate DV01s therefore sum to the parallel DV01 up
  to O(bump^2) cross-convexity terms (central differences cancel the first
  even-order term).
* Piecewise-linear scenario shapes: linear in time between scenario nodes,
  flat extension of the nearest node outside them.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Sequence

from research_engine.pricing.curve_model import ShiftFunction

BP = 0.0001
KEY_RATE_TENORS_V1: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)
KEY_RATE_SET_ID = "krd-triangular-1-2-5-10-30-v1"


def triangular_weight(t: float, keys: Sequence[float], index: int) -> float:
    key = keys[index]
    last = len(keys) - 1
    if t <= key:
        if index == 0:
            return 1.0
        left = keys[index - 1]
        return 0.0 if t <= left else (t - left) / (key - left)
    if index == last:
        return 1.0
    right = keys[index + 1]
    return 0.0 if t >= right else (right - t) / (right - key)


def key_rate_shift(keys: Sequence[float], index: int, size: float) -> ShiftFunction:
    keys = tuple(keys)
    return lambda t: size * triangular_weight(t, keys, index)


def parallel_shift(size: float) -> ShiftFunction:
    return lambda _t: size


def piecewise_linear_shift(tenors: Sequence[float], shifts: Sequence[float]) -> ShiftFunction:
    """Linear in time between nodes; flat extension of the nearest node outside."""
    xs = list(tenors)
    ys = list(shifts)
    if len(xs) != len(ys) or not xs:
        raise ValueError("tenors and shifts must be non-empty and equally long")
    if any(b <= a for a, b in zip(xs[:-1], xs[1:])):
        raise ValueError("scenario tenors must be strictly increasing")

    def shift(t: float) -> float:
        if t <= xs[0]:
            return ys[0]
        if t >= xs[-1]:
            return ys[-1]
        i = bisect_right(xs, t) - 1
        x0, x1, y0, y1 = xs[i], xs[i + 1], ys[i], ys[i + 1]
        return y0 + (y1 - y0) * (t - x0) / (x1 - x0)

    return shift
