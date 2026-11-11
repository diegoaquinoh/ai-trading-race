"""Curve sensitivities by full repricing (spec 8.5).

All quantities here are per 100 face at the valuation anchor; callers scale by
``face / 100`` exactly once when building position outputs.

Sign convention: ``dv01 = (PV(shift down 1bp) - PV(shift up 1bp)) / 2``, so a
positive DV01 is the approximate gain for a 1bp *downward* shift and
``approx_pnl(up x bp) = -dv01 * x``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cached_property
from typing import Sequence

from research_engine.instruments.schedule import InstrumentModel
from research_engine.pricing.bond_pricer import valuation_pv
from research_engine.pricing.curve_model import DiscountCurveModel

from .shocks import BP, KEY_RATE_TENORS_V1, key_rate_shift


@dataclass(frozen=True)
class CurveSensitivity:
    valuation_date: date
    bump: float
    pv: float
    pv_up: float
    pv_down: float
    parallel_dv01: float
    effective_duration: float
    effective_convexity: float
    key_tenors: tuple[float, ...]
    key_rate_dv01: tuple[float, ...]

    @property
    def key_rate_sum(self) -> float:
        return sum(self.key_rate_dv01)


def pv_per_100(model: InstrumentModel, curve: DiscountCurveModel, valuation_date: date) -> float:
    return valuation_pv(model, curve, valuation_date).pv_per_100


class ShockedCurves:
    """Base curve plus lazily built (and cached) parallel and key-rate bumped curves."""

    def __init__(
        self,
        base: DiscountCurveModel,
        bump: float = BP,
        key_tenors: Sequence[float] = KEY_RATE_TENORS_V1,
    ):
        self.base = base
        self.bump = bump
        self.key_tenors = tuple(key_tenors)

    @cached_property
    def up(self) -> DiscountCurveModel:
        return self.base.parallel(self.bump)

    @cached_property
    def down(self) -> DiscountCurveModel:
        return self.base.parallel(-self.bump)

    @cached_property
    def key_rate_pairs(self) -> tuple[tuple[DiscountCurveModel, DiscountCurveModel], ...]:
        """(down, up) curve pairs per key tenor."""
        return tuple(
            (
                self.base.shifted(key_rate_shift(self.key_tenors, i, -self.bump)),
                self.base.shifted(key_rate_shift(self.key_tenors, i, self.bump)),
            )
            for i in range(len(self.key_tenors))
        )


def curve_sensitivity(
    model: InstrumentModel,
    curves: ShockedCurves | DiscountCurveModel,
    valuation_date: date,
    *,
    include_key_rates: bool = True,
) -> CurveSensitivity:
    if isinstance(curves, DiscountCurveModel):
        curves = ShockedCurves(curves)
    bump = curves.bump
    pv = pv_per_100(model, curves.base, valuation_date)
    pv_up = pv_per_100(model, curves.up, valuation_date)
    pv_down = pv_per_100(model, curves.down, valuation_date)
    dv01 = (pv_down - pv_up) / 2.0 * (BP / bump)
    if pv != 0:
        eff_dur = (pv_down - pv_up) / (2.0 * pv * bump)
        eff_cvx = (pv_down + pv_up - 2.0 * pv) / (pv * bump * bump)
    else:
        eff_dur = eff_cvx = 0.0
    krs: list[float] = []
    if include_key_rates:
        for down, up in curves.key_rate_pairs:
            krs.append(
                (pv_per_100(model, down, valuation_date) - pv_per_100(model, up, valuation_date))
                / 2.0
                * (BP / bump)
            )
    return CurveSensitivity(
        valuation_date=valuation_date,
        bump=bump,
        pv=pv,
        pv_up=pv_up,
        pv_down=pv_down,
        parallel_dv01=dv01,
        effective_duration=eff_dur,
        effective_convexity=eff_cvx,
        key_tenors=curves.key_tenors if include_key_rates else (),
        key_rate_dv01=tuple(krs),
    )


MATURITY_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-1y", 0.0, 1.0),
    ("1-3y", 1.0, 3.0),
    ("3-5y", 3.0, 5.0),
    ("5-7y", 5.0, 7.0),
    ("7-10y", 7.0, 10.0),
    ("10y+", 10.0, float("inf")),
)


def maturity_bucket(remaining_years: float) -> str:
    for label, lo, hi in MATURITY_BUCKETS:
        if lo <= remaining_years < hi:
            return label
    return MATURITY_BUCKETS[-1][0]
