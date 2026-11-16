"""Projected payment calendar of a portfolio state (spec 17.3).

Upcoming contractual coupons and redemptions of the securities a portfolio
holds or has traded but not yet settled, with the face that would be entitled
under the platform's settlement-before-payment rule:

``entitled face = settled face + pending purchases settling strictly before the
payment date - pending sales settling strictly before the payment date``

Amounts use the ledger's posting arithmetic (``coupon_payment_v1`` /
``redemption_v1``: ``money(face * per_100 / 100)``). The calendar is a
projection from the current state only: later trades, expiries and
cancellations are not anticipated and nothing here is a committed cash flow.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from research_engine.contracts.common import money
from research_engine.contracts.portfolio import PortfolioState, Side

HUNDRED = Decimal(100)
ZERO = Decimal(0)
BASIS = "projected_from_current_state_v1"


def held_securities(state: PortfolioState) -> list[str]:
    ids = {p.security_id for p in state.positions if p.economic_face > 0 or p.settled_face > 0}
    ids |= {s.security_id for s in state.pending_settlements}
    return sorted(ids)


def projected_entitled_face(state: PortfolioState, security_id: str, payment_date: date) -> Decimal:
    position = next((p for p in state.positions if p.security_id == security_id), None)
    face = position.settled_face if position is not None else ZERO
    for settlement in state.pending_settlements:
        if settlement.security_id != security_id or settlement.settlement_date >= payment_date:
            continue
        face += settlement.face if settlement.side == Side.BUY else -settlement.face
    return face


def payment_calendar(state: PortfolioState, pricing, *, after: date, through: date) -> list[dict]:
    """Payments with ``after < payment_date <= through``, ordered by date, security, kind."""
    items: list[dict] = []
    for security_id in held_securities(state):
        for cf in pricing.cash_flows(security_id):
            if not after < cf.payment_date <= through:
                continue
            face = projected_entitled_face(state, security_id, cf.payment_date)
            if face <= 0:
                continue
            for kind, per_100 in (
                ("COUPON", cf.coupon_per_100),
                ("REDEMPTION", cf.principal_per_100),
            ):
                if per_100 <= 0:
                    continue
                items.append(
                    {
                        "securityId": security_id,
                        "kind": kind,
                        "paymentDate": cf.payment_date.isoformat(),
                        "unadjustedDate": cf.unadjusted_date.isoformat(),
                        "accrualStart": cf.accrual_start.isoformat(),
                        "accrualEnd": cf.accrual_end.isoformat(),
                        "amountPer100": format(per_100, "f"),
                        "projectedEntitledFaceUsd": format(face, "f"),
                        "projectedAmountUsd": format(money(face * per_100 / HUNDRED), "f"),
                    }
                )
    items.sort(key=lambda i: (i["paymentDate"], i["securityId"], i["kind"]))
    return items


def totals(items: list[dict]) -> dict[str, Optional[str]]:
    coupon = sum((Decimal(i["projectedAmountUsd"]) for i in items if i["kind"] == "COUPON"), ZERO)
    redemption = sum(
        (Decimal(i["projectedAmountUsd"]) for i in items if i["kind"] == "REDEMPTION"), ZERO
    )
    return {
        "couponsUsd": format(coupon, "f"),
        "redemptionsUsd": format(redemption, "f"),
        "totalUsd": format(coupon + redemption, "f"),
    }
