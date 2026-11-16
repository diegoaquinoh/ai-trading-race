"""Portfolio valuation (spec 8.4, 8.5, 9.1).

Economic equity = settled cash + economic bond value + PV(receivables) - PV(payables).

* Economic bond value is the *valuation-date* dirty PV of the economic face
  (``PricingPort.value_position``); accrued interest is inside that PV and is
  never added again.
* Pending settlement cash is discounted from its settlement date to the
  valuation date with ``PricingPort.discount_factor``; if that is unavailable
  the valuation is incomplete rather than mixing anchors.
* Unsettled trades straddling a payment date are entitlement-adjusted: a
  pending purchase is not entitled to payments in ``(valuation_date,
  settlement_date]`` and a pending sale still is (entitlement = settled
  strictly before the payment date).
* Mark policy is immutable per experiment. Synthetic mode uses curve-model
  marks (``synthetic_curve_model_v1``). Under an observed-mark policy the mark
  source supplies admitted quotes; a missing quote makes the valuation
  incomplete instead of silently substituting the model (spec 8.4).
* Mark age above ``RiskPolicy.max_mark_age_business_days`` flags the mark stale,
  the valuation incomplete, and blocks dependent discretionary actions.

Portfolio effective duration is ``parallel_dv01_usd * 10_000 / equity`` (cash has
zero duration), i.e. the PV-weighted duration over total NAV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Protocol, runtime_checkable

from research_engine.contracts.common import (
    ContractModel,
    DataMode,
    DecimalStr,
    SecurityId,
    UtcDatetime,
    money,
)
from research_engine.contracts.portfolio import (
    MarkType,
    PositionMark,
    RiskPolicy,
    Side,
    ValuationSnapshot,
)

from .clock import ny_date
from .ledger import HUNDRED, ZERO, Book

SYNTHETIC_MARK_POLICY = "synthetic_curve_model_v1"
CURVE_MODEL_MARK_POLICY = "curve_model_v1"
DURATION_QUANTUM = Decimal("0.000001")
BP_PER_UNIT = Decimal("10000")


class ObservedMark(ContractModel):
    """An admitted market mark (settlement-based clean price + accrued)."""

    security_id: SecurityId
    mark_type: MarkType
    clean_price_per_100: DecimalStr
    accrued_per_100: DecimalStr
    settlement_date: date
    observed_at: UtcDatetime
    observation_id: Optional[str] = None


@runtime_checkable
class MarkSource(Protocol):
    """Observed-mark policy port (observed-security mode or tests)."""

    mark_policy: str

    def mark(self, security_id: str, valuation_at: datetime) -> Optional[ObservedMark]:
        """Latest admitted mark with ``available_at <= valuation_at`` or ``None``."""
        ...


@dataclass(frozen=True)
class CurveRef:
    curve_snapshot_id: str
    session_date: date
    observed_at: Optional[datetime] = None


@dataclass
class ValuationDetail:
    """Per-security numbers used by policy checks (not part of the contract)."""

    pv: dict[str, Decimal] = field(default_factory=dict)
    dv01: dict[str, Decimal] = field(default_factory=dict)
    duration: dict[str, Decimal] = field(default_factory=dict)
    accrued_value: dict[str, Decimal] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    calc_ids: list[str] = field(default_factory=list)

    @property
    def total_dv01(self) -> Decimal:
        return sum(self.dv01.values(), ZERO)


def business_days_between(pricing, start: date, end: date) -> int:
    """Number of business days ``d`` with ``start < d <= end`` (0 if end <= start)."""
    if end <= start:
        return 0
    count = 0
    day = start
    while True:
        day = pricing.advance_business_days(day, 1)
        if day > end:
            return count
        count += 1


def mark_policy_label(data_mode: DataMode, mark_source: Optional[MarkSource]) -> str:
    if mark_source is not None:
        return mark_source.mark_policy
    if data_mode == DataMode.SYNTHETIC_CURVE:
        return SYNTHETIC_MARK_POLICY
    return CURVE_MODEL_MARK_POLICY


def _discount(pricing, curve_id: str, valuation_date: date, payment_date: date) -> Decimal:
    if payment_date <= valuation_date:
        return Decimal("1")
    factor = Decimal(pricing.discount_factor(curve_id, valuation_date, payment_date))
    if not factor.is_finite() or factor <= 0:
        raise ValueError("discount factor must be positive and finite")
    return factor


def _entitlement_adjustments(
    book: Book, pricing, curve_id: str, valuation_date: date
) -> dict[str, Decimal]:
    """PV corrections for unsettled trades around payment dates."""
    adjustments: dict[str, Decimal] = {}
    for settlement in sorted(book.pending.values(), key=lambda s: s.settlement_id):
        if settlement.settlement_date <= valuation_date:
            continue
        flows = [
            cf
            for cf in pricing.cash_flows(settlement.security_id)
            if valuation_date < cf.payment_date <= settlement.settlement_date
        ]
        if not flows:
            continue
        pv = ZERO
        for cf in flows:
            amount = settlement.face * (cf.coupon_per_100 + cf.principal_per_100) / HUNDRED
            pv += amount * _discount(pricing, curve_id, valuation_date, cf.payment_date)
        sign = Decimal("-1") if settlement.side == Side.BUY else Decimal("1")
        adjustments[settlement.security_id] = (
            adjustments.get(settlement.security_id, ZERO) + sign * pv
        )
    return {sid: money(v) for sid, v in adjustments.items()}


def value_book(
    book: Book,
    pricing,
    *,
    valuation_id: str,
    valuation_at: datetime,
    curve: Optional[CurveRef],
    data_mode: DataMode,
    policy: RiskPolicy,
    state_version: int,
    mark_source: Optional[MarkSource] = None,
    extra_reasons: tuple[str, ...] = (),
) -> tuple[ValuationSnapshot, ValuationDetail]:
    """Value a working book at ``valuation_at``; pure apart from port calls."""
    valuation_date = ny_date(valuation_at)
    reasons: list[str] = list(extra_reasons)
    detail = ValuationDetail()
    marks: list[PositionMark] = []
    curve_id = curve.curve_snapshot_id if curve else None
    if curve is None:
        reasons.append("no_curve_available")
    if data_mode == DataMode.OBSERVED_SECURITY and mark_source is None:
        reasons.append("observed_marks_unavailable")
    curve_age = None
    if curve is not None:
        curve_age = business_days_between(pricing, curve.session_date, valuation_date)

    for sid in book.held_securities():
        position = book.positions[sid]
        face = position.economic_face
        if face <= 0:
            continue
        if curve_id is None:
            detail.missing.append(sid)
            marks.append(
                PositionMark(security_id=sid, economic_face=face, mark_type=MarkType.UNAVAILABLE)
            )
            continue
        try:
            result = pricing.value_position(sid, curve_id, valuation_date, face)
        except Exception as exc:  # missing numerical output is never zero risk
            detail.missing.append(sid)
            reasons.append(f"missing_mark:{sid}:{type(exc).__name__}")
            marks.append(
                PositionMark(security_id=sid, economic_face=face, mark_type=MarkType.UNAVAILABLE)
            )
            continue
        detail.calc_ids.append(result.calculation_id)
        detail.dv01[sid] = Decimal(result.parallel_dv01_usd)
        detail.duration[sid] = Decimal(result.effective_duration_years)
        if mark_source is None:
            if data_mode == DataMode.OBSERVED_SECURITY:
                detail.missing.append(sid)
                marks.append(
                    PositionMark(
                        security_id=sid, economic_face=face, mark_type=MarkType.UNAVAILABLE
                    )
                )
                continue
            pv = money(result.pv_dirty_usd)
            age = curve_age
            stale = age is not None and age > policy.max_mark_age_business_days
            mark = PositionMark(
                security_id=sid,
                economic_face=face,
                mark_type=MarkType.CURVE_MODEL,
                clean_price_per_100=result.clean_price_per_100,
                accrued_per_100=result.accrued_per_100,
                pv_dirty_usd=pv,
                observed_at=curve.observed_at if curve else None,
                mark_age_business_days=age,
                stale=stale,
                calculation_id=result.calculation_id,
            )
            accrued_per_100 = result.accrued_per_100
        else:
            observed = mark_source.mark(sid, valuation_at)
            if observed is None:
                detail.missing.append(sid)
                reasons.append(f"missing_observed_mark:{sid}")
                marks.append(
                    PositionMark(
                        security_id=sid, economic_face=face, mark_type=MarkType.UNAVAILABLE
                    )
                )
                continue
            try:
                factor = _discount(pricing, curve_id, valuation_date, observed.settlement_date)
            except Exception as exc:
                detail.missing.append(sid)
                reasons.append(f"mark_anchor_unavailable:{sid}:{type(exc).__name__}")
                marks.append(
                    PositionMark(
                        security_id=sid, economic_face=face, mark_type=MarkType.UNAVAILABLE
                    )
                )
                continue
            dirty = observed.clean_price_per_100 + observed.accrued_per_100
            pv = money(face * dirty / HUNDRED * factor)
            age = business_days_between(pricing, ny_date(observed.observed_at), valuation_date)
            stale = age > policy.max_mark_age_business_days
            mark = PositionMark(
                security_id=sid,
                economic_face=face,
                mark_type=observed.mark_type,
                clean_price_per_100=observed.clean_price_per_100,
                accrued_per_100=observed.accrued_per_100,
                pv_dirty_usd=pv,
                observed_at=observed.observed_at,
                mark_age_business_days=age,
                stale=stale,
                calculation_id=observed.observation_id or result.calculation_id,
            )
            accrued_per_100 = observed.accrued_per_100
        if stale:
            detail.stale.append(sid)
            reasons.append(f"stale_mark:{sid}")
        detail.pv[sid] = pv
        detail.accrued_value[sid] = money(face * accrued_per_100 / HUNDRED)
        marks.append(mark)

    receivables_pv: Optional[Decimal] = None
    payables_pv: Optional[Decimal] = None
    pending_ok = True
    if book.pending:
        if curve_id is None:
            pending_ok = False
        else:
            try:
                recv = ZERO
                pay = ZERO
                for settlement in sorted(book.pending.values(), key=lambda s: s.settlement_id):
                    factor = _discount(
                        pricing, curve_id, valuation_date, settlement.settlement_date
                    )
                    if settlement.side == Side.SELL:
                        recv += money(settlement.cash_usd * factor)
                    else:
                        pay += money(settlement.cash_usd * factor)
                receivables_pv, payables_pv = recv, pay
                for sid, adj in _entitlement_adjustments(
                    book, pricing, curve_id, valuation_date
                ).items():
                    if adj == 0:
                        continue
                    if sid in detail.pv:
                        detail.pv[sid] += adj
                    elif sid not in detail.missing:
                        # Adjustment-only security (no economic face, e.g. fully sold
                        # but still entitled to a payment before its sale settles): a
                        # known cash amount with no rate exposure beyond it, so its
                        # risk output is an explicit zero DV01/duration, not missing.
                        detail.pv[sid] = adj
                        detail.dv01[sid] = ZERO
                        detail.duration[sid] = ZERO
                        marks.append(
                            PositionMark(
                                security_id=sid,
                                economic_face=book.economic_face(sid),
                                mark_type=MarkType.CURVE_MODEL,
                                pv_dirty_usd=adj,
                                observed_at=curve.observed_at if curve else None,
                                mark_age_business_days=curve_age,
                            )
                        )
            except Exception as exc:
                pending_ok = False
                reasons.append(f"pending_settlement_discount_unavailable:{type(exc).__name__}")
        if not pending_ok and "pending_settlement_discount_unavailable" not in " ".join(reasons):
            reasons.append("pending_settlement_discount_unavailable")
    else:
        receivables_pv, payables_pv = ZERO, ZERO

    values_available = not detail.missing and pending_ok and curve_id is not None
    complete = values_available and not detail.stale and not reasons
    bond_value = equity = dv01 = duration = None
    if values_available:
        bond_value = sum(detail.pv.values(), ZERO)
        equity = book.cash + bond_value + receivables_pv - payables_pv
        dv01 = money(detail.total_dv01)
        if equity > 0:
            duration = (detail.total_dv01 * BP_PER_UNIT / equity).quantize(DURATION_QUANTUM)
        else:
            duration = ZERO
    snapshot = ValuationSnapshot(
        valuation_id=valuation_id,
        portfolio_id=book.portfolio_id,
        state_version=state_version,
        valuation_at=valuation_at,
        data_mode=data_mode,
        curve_snapshot_id=curve_id,
        mark_policy=mark_policy_label(data_mode, mark_source),
        complete=complete,
        incomplete_reasons=sorted(set(reasons)),
        cash_usd=book.cash,
        bond_value_usd=bond_value,
        receivables_pv_usd=receivables_pv if values_available else None,
        payables_pv_usd=payables_pv if values_available else None,
        equity_usd=equity,
        marks=sorted(marks, key=lambda m: m.security_id),
        parallel_dv01_usd=dv01,
        effective_duration_years=duration,
        calculation_ids=sorted(set(detail.calc_ids)),
    )
    return snapshot, detail
