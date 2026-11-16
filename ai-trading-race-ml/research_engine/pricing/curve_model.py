"""Discount-curve model reconstructed from a ``CurveSnapshot``'s published nodes.

The stored nodes fully determine the curve: QuantLib ``DiscountCurve`` with
``LogLinear`` interpolation on ACT/365F time reproduces the bootstrapped
``PiecewiseLogLinearDiscount`` exactly between nodes. Pricing therefore depends
only on the content-addressed snapshot, never on a live bootstrap object.

Extrapolation is rejected: ``discount(t)`` raises ``ExtrapolationError`` for any
date beyond ``validated_horizon_date`` (and before the reference date).

Curve shocks are expressed as continuous ACT/365F zero-rate shifts applied at
the nodes: ``ln D'(t_i) = ln D(t_i) - shift(t_i) * t_i``, then log-linear
interpolation as usual. A constant shift is therefore an exact parallel shift
of the continuous zero curve at every date inside the horizon.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Callable, Iterable, Optional, Protocol

import QuantLib as ql

from research_engine.contracts.market import CurveSnapshot, CurveStatus

from .quantlib_env import ql_lock, to_ql_date

ShiftFunction = Callable[[float], float]  # time in years -> decimal zero-rate shift


class ExtrapolationError(ValueError):
    """A date outside [reference_date, validated_horizon_date] was requested."""


class CurveNotReadyError(ValueError):
    pass


class CurveSource(Protocol):
    def get_curve_snapshot(self, curve_snapshot_id: str) -> CurveSnapshot: ...


class InMemoryCurveSource:
    def __init__(self, snapshots: Iterable[CurveSnapshot] = ()):
        self._items = {s.curve_snapshot_id: s for s in snapshots}

    def add(self, snapshot: CurveSnapshot) -> None:
        self._items[snapshot.curve_snapshot_id] = snapshot

    def get_curve_snapshot(self, curve_snapshot_id: str) -> CurveSnapshot:
        return self._items[curve_snapshot_id]


def year_fraction(reference: date, target: date) -> float:
    """ACT/365F time used for node times and zero rates."""
    return (target - reference).days / 365.0


class DiscountCurveModel:
    def __init__(
        self,
        reference_date: date,
        node_dates: list[date],
        discount_factors: list[float],
        *,
        curve_snapshot_id: str = "adhoc",
        description: str = "base",
    ):
        if len(node_dates) < 2 or node_dates[0] != reference_date:
            raise ValueError("nodes must start at the reference date and contain >= 2 dates")
        if any(b <= a for a, b in zip(node_dates[:-1], node_dates[1:])):
            raise ValueError("node dates must be strictly increasing")
        for df in discount_factors:
            if not (df > 0.0 and math.isfinite(df)):
                raise ValueError("discount factors must be positive and finite")
        self.reference_date = reference_date
        self.horizon = node_dates[-1]
        self.node_dates = list(node_dates)
        self.discount_factors = list(discount_factors)
        self.node_times = [year_fraction(reference_date, d) for d in node_dates]
        self.curve_snapshot_id = curve_snapshot_id
        self.description = description
        with ql_lock():
            self._ql = ql.DiscountCurve(
                [to_ql_date(d) for d in node_dates], list(discount_factors), ql.Actual365Fixed()
            )

    @classmethod
    def from_snapshot(cls, snapshot: CurveSnapshot) -> "DiscountCurveModel":
        if snapshot.status is not CurveStatus.READY:
            raise CurveNotReadyError(
                f"curve {snapshot.curve_snapshot_id} is {snapshot.status.value}: "
                + "; ".join(snapshot.failure_reasons)
            )
        return cls(
            snapshot.reference_date,
            [n.node_date for n in snapshot.nodes],
            [float(n.discount_factor) for n in snapshot.nodes],
            curve_snapshot_id=snapshot.curve_snapshot_id,
        )

    # -- evaluation ------------------------------------------------------------
    def _check(self, day: date) -> None:
        if day < self.reference_date:
            raise ExtrapolationError(f"{day} precedes curve reference date {self.reference_date}")
        if day > self.horizon:
            raise ExtrapolationError(
                f"{day} beyond validated horizon {self.horizon} (extrapolation rejected)"
            )

    def discount(self, day: date) -> float:
        self._check(day)
        with ql_lock():
            return float(self._ql.discount(to_ql_date(day)))

    def discounts(self, days: list[date]) -> list[float]:
        for day in days:
            self._check(day)
        with ql_lock():
            return [float(self._ql.discount(to_ql_date(d))) for d in days]

    def zero_rate(self, day: date) -> float:
        """Continuous ACT/365F zero rate; at the reference date returns 0."""
        t = year_fraction(self.reference_date, day)
        if t <= 0:
            return 0.0
        return -math.log(self.discount(day)) / t

    def anchored_discount(self, anchor: date, day: date) -> float:
        """D(v, day) / D(v, anchor): discounting from ``day`` back to ``anchor``."""
        d_anchor, d_day = self.discounts([anchor, day])
        return d_day / d_anchor

    # -- shocks ----------------------------------------------------------------
    def shifted(self, shift: ShiftFunction, description: str = "shifted") -> "DiscountCurveModel":
        dfs = [
            df * math.exp(-shift(t) * t) if t > 0 else df
            for df, t in zip(self.discount_factors, self.node_times)
        ]
        return DiscountCurveModel(
            self.reference_date,
            self.node_dates,
            dfs,
            curve_snapshot_id=self.curve_snapshot_id,
            description=description,
        )

    def parallel(self, shift: float) -> "DiscountCurveModel":
        return self.shifted(lambda _t: shift, description=f"parallel{shift:+.6f}")


def flat_curve(
    reference_date: date,
    rate: float,
    horizon_years: int = 31,
    *,
    node_dates: Optional[list[date]] = None,
) -> DiscountCurveModel:
    """Flat continuous ACT/365F curve (testing and documentation helper)."""
    if node_dates is None:
        node_dates = [reference_date] + [
            date(reference_date.year + y, reference_date.month, min(reference_date.day, 28))
            for y in range(1, horizon_years + 1)
        ]
    dfs = [math.exp(-rate * year_fraction(reference_date, d)) for d in node_dates]
    return DiscountCurveModel(reference_date, node_dates, dfs, description=f"flat{rate}")
