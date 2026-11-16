"""Yield-to-maturity quote conversion (street convention ``street_semiannual_act_act_icma_v1``).

The yield is a *quote-conversion tool*, not a substitute for the discount
curve (spec 8.3). Declared convention:

* semiannual compounding, also inside the final coupon period;
* exponent of the k-th remaining flow (k = 0, 1, ...) is ``w + k`` where
  ``w = days(s, next_coupon) / days(quasi_start, next_coupon)`` is the ACT/ACT
  (ICMA) fraction of the current period remaining after settlement ``s``;
* exponents use *unadjusted* coupon dates (holiday-shifted payments are not
  re-timed), while the set of flows follows the entitlement rule
  (payment_date > s);
* dirty price ``P(y) = SUM CF_k / (1 + y/2)^(w + k)``; clean = P - accrued.

Yield-based modified duration ``-(1/P) dP/dy`` and convexity ``(1/P) d2P/dy2``
are computed analytically from the same function and are labelled separately
from curve-based effective duration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from research_engine.instruments.schedule import InstrumentModel, InstrumentNotTradableError

YIELD_CONVENTION = "street_semiannual_act_act_icma_v1"


class YieldSolveError(ValueError):
    pass


def _exponents(model: InstrumentModel, settlement: date) -> tuple[list[float], list[float]]:
    periods = model.entitled_periods(settlement)
    if not periods:
        raise InstrumentNotTradableError(f"{model.security_id}: no flows after {settlement}")
    first = periods[0]
    quasi = (first.accrual_end - first.reference_start).days
    w = (first.accrual_end - settlement).days / quasi
    exps = [w + k for k in range(len(periods))]
    amounts = [float(p.amount_per_100) for p in periods]
    return exps, amounts


def dirty_from_yield(model: InstrumentModel, settlement: date, y: float) -> float:
    exps, amounts = _exponents(model, settlement)
    base = 1.0 + y / 2.0
    return sum(a * base ** (-e) for a, e in zip(amounts, exps))


@dataclass(frozen=True)
class YieldRisk:
    ytm: float
    dirty_per_100: float
    modified_duration: float
    convexity: float


def yield_risk(model: InstrumentModel, settlement: date, y: float) -> YieldRisk:
    exps, amounts = _exponents(model, settlement)
    base = 1.0 + y / 2.0
    price = sum(a * base ** (-e) for a, e in zip(amounts, exps))
    d1 = sum(-e / 2.0 * a * base ** (-e - 1) for a, e in zip(amounts, exps))
    d2 = sum(e * (e + 1) / 4.0 * a * base ** (-e - 2) for a, e in zip(amounts, exps))
    return YieldRisk(y, price, -d1 / price, d2 / price)


def solve_ytm(
    model: InstrumentModel,
    settlement: date,
    dirty_per_100: float,
    *,
    tolerance: float = 1e-12,
    max_iterations: int = 200,
) -> float:
    """Yield such that ``dirty_from_yield == dirty_per_100`` (bisection + Newton)."""
    if not dirty_per_100 > 0:
        raise YieldSolveError("price must be positive")
    lo, hi = -0.5, 1.0

    def f(y: float) -> float:
        return dirty_from_yield(model, settlement, y) - dirty_per_100

    f_lo, f_hi = f(lo), f(hi)
    if f_lo < 0 or f_hi > 0:
        raise YieldSolveError("yield outside the supported bracket [-50%, 100%]")
    y = 0.5 * (lo + hi)
    for _ in range(max_iterations):
        value = f(y)
        if abs(value) < tolerance:
            return y
        if value > 0:
            lo = y
        else:
            hi = y
        risk = yield_risk(model, settlement, y)
        slope = -risk.modified_duration * risk.dirty_per_100
        candidate = y - value / slope if slope != 0 else 0.5 * (lo + hi)
        y = candidate if lo < candidate < hi else 0.5 * (lo + hi)
        if hi - lo < 1e-15:
            return y
    raise YieldSolveError("yield solver did not converge")
