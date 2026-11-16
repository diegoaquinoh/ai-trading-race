"""Curve-consistent bond valuation (spec 8.3, 9.1).

Anchors (v = curve reference/valuation date, s = settlement date, t = payment date):

* Settlement value, per 100 face::

      dirty(s) = SUM_{t_i > s} CF_i * D(v, t_i) / D(v, s)
      clean(s) = dirty(s) - accrued(s)          (ACT/ACT-ICMA accrued)

* Valuation-date present value, per 100 face (economic value at valuation date u >= v)::

      pv(u) = SUM_{t_i > u} CF_i * D(v, t_i) / D(v, u)

  With u = v this is the plain PV ``SUM CF_i * D(v, t_i)``.

The two differ by the settlement-lag discount ``D(v, s) / D(v, u)`` and by any
flow paid in (u, s]. Each result records its anchor date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from research_engine.instruments.schedule import InstrumentModel, InstrumentNotTradableError

from .curve_model import DiscountCurveModel


class AnchorError(ValueError):
    """Requested anchor precedes the curve reference date."""


@dataclass(frozen=True)
class SettlementPrice:
    security_id: str
    valuation_date: date  # curve reference date v
    settlement_date: date  # anchor s
    dirty_per_100: float
    accrued_per_100: Decimal  # exact convention value
    clean_per_100: float
    discount_to_settlement: float  # D(v, s)
    flows: tuple[tuple[date, float, float], ...]  # (payment date, amount per 100, D(v,t))


@dataclass(frozen=True)
class ValuationPV:
    security_id: str
    curve_reference_date: date
    valuation_date: date  # anchor u
    pv_per_100: float
    flows: tuple[tuple[date, float, float], ...]


def settlement_price(
    model: InstrumentModel, curve: DiscountCurveModel, settlement: date
) -> SettlementPrice:
    if settlement < curve.reference_date:
        raise AnchorError(
            f"settlement {settlement} precedes curve reference date {curve.reference_date}"
        )
    if settlement < model.terms.dates.original_issue_date:
        raise InstrumentNotTradableError(
            f"{model.security_id}: settlement {settlement} precedes original issue date"
        )
    if settlement >= model.final_payment_date:
        raise InstrumentNotTradableError(
            f"{model.security_id}: no entitled flows after settlement {settlement}"
        )
    periods = model.entitled_periods(settlement)
    pay_dates = [p.payment_date for p in periods]
    dfs = curve.discounts([settlement] + pay_dates)
    d_s, flow_dfs = dfs[0], dfs[1:]
    amounts = [float(p.amount_per_100) for p in periods]
    pv = sum(a * df for a, df in zip(amounts, flow_dfs))
    dirty = pv / d_s
    accrued = model.accrued_per_100(settlement)
    return SettlementPrice(
        security_id=model.security_id,
        valuation_date=curve.reference_date,
        settlement_date=settlement,
        dirty_per_100=dirty,
        accrued_per_100=accrued,
        clean_per_100=dirty - float(accrued),
        discount_to_settlement=d_s,
        flows=tuple(zip(pay_dates, amounts, flow_dfs)),
    )


def valuation_pv(
    model: InstrumentModel, curve: DiscountCurveModel, valuation_date: date
) -> ValuationPV:
    """PV per 100 at ``valuation_date`` of flows with payment_date > valuation_date."""
    if valuation_date < curve.reference_date:
        raise AnchorError(
            f"valuation date {valuation_date} precedes curve reference {curve.reference_date}"
        )
    periods = [p for p in model.periods if p.payment_date > valuation_date]
    if not periods:
        return ValuationPV(model.security_id, curve.reference_date, valuation_date, 0.0, ())
    pay_dates = [p.payment_date for p in periods]
    dfs = curve.discounts([valuation_date] + pay_dates)
    d_u, flow_dfs = dfs[0], dfs[1:]
    amounts = [float(p.amount_per_100) for p in periods]
    pv = sum(a * df for a, df in zip(amounts, flow_dfs)) / d_u
    return ValuationPV(
        model.security_id,
        curve.reference_date,
        valuation_date,
        pv,
        tuple(zip(pay_dates, amounts, flow_dfs)),
    )
