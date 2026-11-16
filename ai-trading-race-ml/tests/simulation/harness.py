"""Test harness: a single portfolio driven through propose_transition + store.commit."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Optional

from research_engine.contracts.common import CASH_SECURITY_ID, DataMode
from research_engine.contracts.portfolio import (
    CommandType,
    DecisionAction,
    Lot,
    MarketSnapshotRef,
    OrderIntent,
    OrderStatus,
    PortfolioState,
    Position,
    Side,
    TargetWeight,
)
from research_engine.simulation.clock import (
    CAPITAL_TIME,
    decision_at,
    make_id,
    ny_instant,
    session_end_at,
    valuation_at,
)
from research_engine.simulation.engine import build_request, propose_transition
from research_engine.simulation.store import OfflineStateStore

from .fakes import make_ports

KEY = b"test-signing-key"
UNIVERSE = "synthetic-universe-v1"


def weights(**pairs) -> list[TargetWeight]:
    out = []
    for sid, w in pairs.items():
        sid = CASH_SECURITY_ID if sid == "cash" else f"SYN-USD-NOTE-{sid[1:].zfill(3)}"
        out.append(TargetWeight(security_id=sid, weight=Decimal(w)))
    return out


def snapshot_ref(market, day: date) -> MarketSnapshotRef:
    sid, digest = market.market_snapshot_id(day)
    return MarketSnapshotRef(
        market_snapshot_id=sid,
        content_hash=digest,
        curve_snapshot_id=f"curve-{day.isoformat()}",
        session_date=day,
        data_mode=DataMode.SYNTHETIC_CURVE,
    )


def lot(sid, face, settle, clean="100", principal=None, accrued="0", trade=None) -> Lot:
    face = Decimal(face)
    return Lot(
        lot_id=f"lot-{sid}-{settle.isoformat()}-{face}",
        security_id=sid,
        face=face,
        trade_date=trade or settle,
        settlement_date=settle,
        clean_price_per_100=Decimal(clean),
        principal_cost_usd=(
            Decimal(principal) if principal is not None else face * Decimal(clean) / 100
        ),
        accrued_purchased_usd=Decimal(accrued),
    )


def position(sid, lots, settled=None) -> Position:
    face = sum((ln.face for ln in lots), Decimal("0"))
    return Position(
        security_id=sid,
        economic_face=face,
        settled_face=face if settled is None else Decimal(settled),
        lots=lots,
    )


def open_order(
    sid, side, face, submitted_day, eligible_day, reserved="0", priority=0, decision="dec-x"
) -> OrderIntent:
    return OrderIntent(
        order_id=make_id("ord", decision, sid),
        decision_id=decision,
        security_id=sid,
        side=side,
        face=Decimal(face),
        submitted_at=decision_at(submitted_day),
        eligible_session_date=eligible_day,
        expires_at=session_end_at(eligible_day),
        status=OrderStatus.ACCEPTED,
        reserved_cash_usd=Decimal(reserved),
        batch_priority=priority,
    )


def book_state(
    as_of_day: date,
    cash: str,
    positions=(),
    orders=(),
    pending=(),
    pid="pf-1",
    strategy="quant_duration",
    **extra,
) -> PortfolioState:
    """A consistent hand-built state; capital is set so the trial balance closes."""
    principal = sum((ln.principal_cost_usd for p in positions for ln in p.lots), Decimal("0"))
    accrued = sum((ln.accrued_purchased_usd for p in positions for ln in p.lots), Decimal("0"))
    receivable = sum((s.cash_usd for s in pending if s.side == Side.SELL), Decimal("0"))
    payable = sum((s.cash_usd for s in pending if s.side == Side.BUY), Decimal("0"))
    capital = Decimal(cash) + principal + accrued + receivable - payable
    return PortfolioState(
        portfolio_id=pid,
        strategy_id=strategy,
        run_id="run-test",
        version=extra.pop("version", 5),
        as_of=extra.pop("as_of", valuation_at(as_of_day)),
        cash_usd=Decimal(cash),
        reserved_cash_usd=sum((o.reserved_cash_usd for o in orders), Decimal("0")),
        positions=list(positions),
        open_orders=list(orders),
        pending_settlements=list(pending),
        external_capital_usd=capital,
        **extra,
    )


class Harness:
    def __init__(self, state: Optional[PortfolioState] = None, mark_source=None, **port_kwargs):
        port_kwargs.setdefault("wobble", 0.0)
        self.pricing, self.market = make_ports(**port_kwargs)
        self.store = OfflineStateStore(KEY)
        self.mark_source = mark_source
        self.counter = 0
        if state is None:
            state = PortfolioState(
                portfolio_id="pf-1",
                strategy_id="quant_duration",
                run_id="run-test",
                version=0,
                as_of=ny_instant(date(2024, 1, 2), time(0)),
                cash_usd=Decimal("0"),
            )
        self.store.register(state)
        self.pid = state.portfolio_id

    @property
    def state(self) -> PortfolioState:
        return self.store.state(self.pid)

    def request(self, command_type, advance_to, **kwargs):
        self.counter += 1
        command_id = kwargs.pop("command_id", f"cmd-{self.counter}")
        return build_request(
            kwargs.pop("state", self.state),
            command_id=command_id,
            command_type=command_type,
            advance_to=advance_to,
            instrument_universe_version=UNIVERSE,
            **kwargs,
        )

    def propose(self, request):
        return propose_transition(
            request, self.pricing, self.market, KEY, mark_source=self.mark_source
        )

    def apply(self, command_type, advance_to, **kwargs):
        request = self.request(command_type, advance_to, **kwargs)
        proposal = self.propose(request)
        self.store.commit(proposal, request)
        return proposal

    def capital(self, day=date(2024, 1, 2), amount="1000000"):
        return self.apply(
            CommandType.CAPITAL_FLOW,
            ny_instant(day, CAPITAL_TIME),
            capital_amount_usd=Decimal(amount),
        )

    def decide(self, day, targets, action=DecisionAction.REBALANCE, decision_id=None, **kwargs):
        self.counter += 0
        return self.apply(
            CommandType.SUBMIT_DECISION,
            kwargs.pop("at", decision_at(day)),
            market_snapshot=kwargs.pop("market_snapshot", snapshot_ref(self.market, day)),
            decision_id=decision_id or f"dec-{day.isoformat()}-{self.counter}",
            action=action,
            target_weights=targets,
            **kwargs,
        )

    def process(self, day, at=None):
        return self.apply(CommandType.PROCESS_EVENTS, at or decision_at(day))

    def value(self, day, snapshot_day=None, at=None):
        snap = snapshot_day or day
        return self.apply(
            CommandType.VALUE_PORTFOLIO,
            at or valuation_at(day),
            market_snapshot=snapshot_ref(self.market, snap),
        )
