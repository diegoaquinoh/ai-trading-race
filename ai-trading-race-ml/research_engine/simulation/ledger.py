"""Double-entry ledger: mutable working book, posting templates, reconciliation.

Posting templates are specified in ``docs/fixed-income/accounting.md``. Every
template produces a balanced :class:`~research_engine.contracts.portfolio.Journal`
whose id derives from the triggering event id (``jnl:<event_id>[:<suffix>]``)
and whose line ids derive from the journal id (``<journal_id>:<nn>``).

Money is rounded to cents (``contracts.common.money``, ROUND_HALF_UP) only at
the posting boundaries documented in the accounting guide. Each template keeps
the working :class:`Book` balances in lock-step with its journal lines so the
reconciliation can prove ``prior balances + journal lines == new balances``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Optional

from research_engine.contracts.common import CASH_SECURITY_ID, money
from research_engine.contracts.portfolio import (
    AccountCode,
    CashFlowRecord,
    Fill,
    Journal,
    JournalLine,
    Lot,
    OrderIntent,
    PendingSettlement,
    PortfolioState,
    Position,
    ReconciliationReport,
    Side,
    ValuationSnapshot,
)

from .clock import make_id, ny_date

ZERO = Decimal("0")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")
MILLION = Decimal("1000000")

CAPITAL_FLOW_V1 = "capital_flow_v1"
BUY_FILL_V1 = "buy_fill_v1"
BUY_SETTLEMENT_V1 = "buy_settlement_v1"
SELL_FILL_V1 = "sell_fill_v1"
SELL_SETTLEMENT_V1 = "sell_settlement_v1"
COUPON_PAYMENT_V1 = "coupon_payment_v1"
REDEMPTION_V1 = "redemption_v1"
MARK_TO_MARKET_V1 = "mark_to_market_v1"
CASH_INTEREST_V1 = "cash_interest_v1"

POSTING_TEMPLATES = (
    CAPITAL_FLOW_V1,
    BUY_FILL_V1,
    BUY_SETTLEMENT_V1,
    SELL_FILL_V1,
    SELL_SETTLEMENT_V1,
    COUPON_PAYMENT_V1,
    REDEMPTION_V1,
    MARK_TO_MARKET_V1,
    CASH_INTEREST_V1,
)
LOT_METHOD = "fifo_v1"


class LedgerInvariantError(RuntimeError):
    """An accounting invariant would be violated (e.g. negative settled cash).

    Deterministic for a given request: the API maps it to 422 with ``code``.
    """

    code = "ledger_invariant_violation"


class WithdrawalExceedsAvailableCash(LedgerInvariantError):
    """A negative capital flow larger than settled cash - reservations - payables."""

    code = "withdrawal_exceeds_available_cash"


# --------------------------------------------------------------------------- #
# Mutable working book
# --------------------------------------------------------------------------- #


@dataclass
class WorkingLot:
    lot_id: str
    security_id: str
    face: Decimal
    trade_date: date
    settlement_date: date
    clean_price_per_100: Decimal
    principal_cost_usd: Decimal
    accrued_purchased_usd: Decimal

    def to_contract(self) -> Lot:
        return Lot(
            lot_id=self.lot_id,
            security_id=self.security_id,
            face=self.face,
            trade_date=self.trade_date,
            settlement_date=self.settlement_date,
            clean_price_per_100=self.clean_price_per_100,
            principal_cost_usd=self.principal_cost_usd,
            accrued_purchased_usd=self.accrued_purchased_usd,
        )


@dataclass
class WorkingPosition:
    security_id: str
    economic_face: Decimal = ZERO
    settled_face: Decimal = ZERO
    lots: list[WorkingLot] = field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            self.economic_face == 0
            and self.settled_face == 0
            and all(lot.face == 0 and lot.accrued_purchased_usd == 0 for lot in self.lots)
        )


@dataclass
class Book:
    """Mutable copy of a :class:`PortfolioState` used inside one transition."""

    schema_version: str
    portfolio_id: str
    strategy_id: str
    run_id: str
    version: int
    as_of: datetime
    cash: Decimal
    reserved: Decimal
    positions: dict[str, WorkingPosition]
    open_orders: dict[str, OrderIntent]
    pending: dict[str, PendingSettlement]
    capital: Decimal
    income: Decimal
    realized: Decimal
    fees: Decimal
    spread: Decimal
    unrealized: Decimal
    cash_flows_through: Optional[date]
    last_valuation_id: Optional[str]
    risk_breaches: list[str]
    blocked_reason: Optional[str]

    @classmethod
    def from_state(cls, state: PortfolioState) -> "Book":
        positions = {
            p.security_id: WorkingPosition(
                security_id=p.security_id,
                economic_face=p.economic_face,
                settled_face=p.settled_face,
                lots=[
                    WorkingLot(
                        lot_id=lot.lot_id,
                        security_id=lot.security_id,
                        face=lot.face,
                        trade_date=lot.trade_date,
                        settlement_date=lot.settlement_date,
                        clean_price_per_100=lot.clean_price_per_100,
                        principal_cost_usd=lot.principal_cost_usd,
                        accrued_purchased_usd=lot.accrued_purchased_usd,
                    )
                    for lot in p.lots
                ],
            )
            for p in state.positions
        }
        return cls(
            schema_version=state.schema_version,
            portfolio_id=state.portfolio_id,
            strategy_id=state.strategy_id,
            run_id=state.run_id,
            version=state.version,
            as_of=state.as_of,
            cash=state.cash_usd,
            reserved=state.reserved_cash_usd,
            positions=positions,
            open_orders={o.order_id: o for o in state.open_orders},
            pending={s.settlement_id: s for s in state.pending_settlements},
            capital=state.external_capital_usd,
            income=state.interest_income_usd,
            realized=state.realized_gain_loss_usd,
            fees=state.transaction_fees_usd,
            spread=state.spread_cost_usd,
            unrealized=state.booked_unrealized_usd,
            cash_flows_through=state.cash_flows_processed_through,
            last_valuation_id=state.last_valuation_id,
            risk_breaches=list(state.risk_breaches),
            blocked_reason=state.blocked_reason,
        )

    # -- queries -------------------------------------------------------------

    def position(self, security_id: str) -> WorkingPosition:
        if security_id not in self.positions:
            self.positions[security_id] = WorkingPosition(security_id=security_id)
        return self.positions[security_id]

    def economic_face(self, security_id: str) -> Decimal:
        pos = self.positions.get(security_id)
        return pos.economic_face if pos else ZERO

    def held_securities(self) -> list[str]:
        return sorted(
            sid
            for sid, p in self.positions.items()
            if p.economic_face > 0 or p.settled_face > 0 or p.lots
        )

    def payables(self) -> Decimal:
        return sum((s.cash_usd for s in self.pending.values() if s.side == Side.BUY), ZERO)

    def receivables(self) -> Decimal:
        return sum((s.cash_usd for s in self.pending.values() if s.side == Side.SELL), ZERO)

    def principal(self) -> Decimal:
        return sum(
            (lot.principal_cost_usd for p in self.positions.values() for lot in p.lots), ZERO
        )

    def accrued_purchased(self) -> Decimal:
        return sum(
            (lot.accrued_purchased_usd for p in self.positions.values() for lot in p.lots), ZERO
        )

    def available_funding(self, exclude_reservation: Decimal = ZERO) -> Decimal:
        """Settled cash minus reservations minus committed payables (spec 9.4).

        Unsettled sale receivables never fund purchases.
        """
        return self.cash - (self.reserved - exclude_reservation) - self.payables()

    def book_equity(self) -> Decimal:
        return self.capital + self.income + self.realized + self.unrealized - self.fees

    def balances(self) -> dict[AccountCode, Decimal]:
        return balances_from_values(
            cash=self.cash,
            principal=self.principal(),
            accrued=self.accrued_purchased(),
            receivable=self.receivables(),
            payable=self.payables(),
            mark=self.unrealized,
            capital=self.capital,
            income=self.income,
            realized=self.realized,
            fees=self.fees,
        )

    # -- conversion ----------------------------------------------------------

    def cleanup(self) -> None:
        referenced = {s.security_id for s in self.pending.values()}
        for sid in list(self.positions):
            pos = self.positions[sid]
            pos.lots = [
                lot for lot in pos.lots if not (lot.face == 0 and lot.accrued_purchased_usd == 0)
            ]
            if pos.is_empty() and not pos.lots and sid not in referenced:
                del self.positions[sid]
        leftover = [
            lot.lot_id
            for p in self.positions.values()
            for lot in p.lots
            if lot.face == 0 and lot.accrued_purchased_usd != 0
        ]
        if leftover:
            raise LedgerInvariantError(f"zero-face lots with unrecovered accrued: {leftover}")

    def to_state(self, version: int, as_of: datetime) -> PortfolioState:
        self.cleanup()
        positions = [
            Position(
                security_id=sid,
                economic_face=self.positions[sid].economic_face,
                settled_face=self.positions[sid].settled_face,
                lots=[lot.to_contract() for lot in self.positions[sid].lots],
            )
            for sid in sorted(self.positions)
        ]
        return PortfolioState(
            schema_version=self.schema_version,
            portfolio_id=self.portfolio_id,
            strategy_id=self.strategy_id,
            run_id=self.run_id,
            version=version,
            as_of=as_of,
            cash_usd=self.cash,
            reserved_cash_usd=self.reserved,
            positions=positions,
            open_orders=[self.open_orders[k] for k in sorted(self.open_orders)],
            pending_settlements=[self.pending[k] for k in sorted(self.pending)],
            external_capital_usd=self.capital,
            interest_income_usd=self.income,
            realized_gain_loss_usd=self.realized,
            transaction_fees_usd=self.fees,
            spread_cost_usd=self.spread,
            booked_unrealized_usd=self.unrealized,
            cash_flows_processed_through=self.cash_flows_through,
            last_valuation_id=self.last_valuation_id,
            risk_breaches=sorted(set(self.risk_breaches)),
            blocked_reason=self.blocked_reason,
        )


def balances_from_values(
    *,
    cash: Decimal,
    principal: Decimal,
    accrued: Decimal,
    receivable: Decimal,
    payable: Decimal,
    mark: Decimal,
    capital: Decimal,
    income: Decimal,
    realized: Decimal,
    fees: Decimal,
) -> dict[AccountCode, Decimal]:
    """Signed account balances (debit positive). A valid book sums to zero."""
    return {
        AccountCode.CASH: cash,
        AccountCode.BOND_PRINCIPAL: principal,
        AccountCode.ACCRUED_INTEREST_PURCHASED: accrued,
        AccountCode.SETTLEMENT_RECEIVABLE: receivable,
        AccountCode.SETTLEMENT_PAYABLE: -payable,
        AccountCode.MARK_ADJUSTMENT: mark,
        AccountCode.CAPITAL: -capital,
        AccountCode.INTEREST_INCOME: -income,
        AccountCode.REALIZED_GAIN_LOSS: -realized,
        AccountCode.UNREALIZED_GAIN_LOSS: -mark,
        AccountCode.TRANSACTION_FEES: fees,
    }


def state_balances(state: PortfolioState) -> dict[AccountCode, Decimal]:
    return Book.from_state(state).balances()


# --------------------------------------------------------------------------- #
# Journal construction
# --------------------------------------------------------------------------- #


class JournalBuilder:
    """Collects signed postings; ``post(account, +x)`` debits, ``-x`` credits."""

    def __init__(
        self,
        event_id: str,
        event_type,
        effective_at: datetime,
        template: str,
        suffix: Optional[str] = None,
    ) -> None:
        self.journal_id = make_id("jnl", event_id, suffix) if suffix else make_id("jnl", event_id)
        self.event_id = event_id
        self.event_type = event_type
        self.effective_at = effective_at
        self.template = template
        self._lines: list[tuple[AccountCode, Optional[str], Decimal, Optional[str]]] = []

    def post(
        self,
        account: AccountCode,
        signed_amount: Decimal,
        security_id: Optional[str] = None,
        memo: Optional[str] = None,
    ) -> None:
        if signed_amount != signed_amount.quantize(CENT):
            raise LedgerInvariantError(f"posting not rounded to cents: {signed_amount}")
        if signed_amount != 0:
            self._lines.append((account, security_id, signed_amount, memo))

    def debit(self, account, amount, security_id=None, memo=None) -> None:
        self.post(account, amount, security_id, memo)

    def credit(self, account, amount, security_id=None, memo=None) -> None:
        self.post(account, -amount, security_id, memo)

    def build(self) -> Optional[Journal]:
        if not self._lines:
            return None
        lines = []
        for index, (account, security_id, amount, memo) in enumerate(self._lines, start=1):
            lines.append(
                JournalLine(
                    # ``<journal_id>:<nn>``; ``make_id`` keeps it an OpaqueId (<= 160).
                    line_id=make_id(self.journal_id, f"{index:02d}"),
                    account=account,
                    security_id=security_id,
                    debit_usd=amount if amount > 0 else ZERO,
                    credit_usd=-amount if amount < 0 else ZERO,
                    memo=memo,
                )
            )
        return Journal(
            journal_id=self.journal_id,
            event_id=self.event_id,
            event_type=self.event_type,
            effective_at=self.effective_at,
            template=self.template,
            lines=lines,
        )


def journal_deltas(journals: Iterable[Journal]) -> dict[AccountCode, Decimal]:
    totals: dict[AccountCode, Decimal] = {code: ZERO for code in AccountCode}
    for journal in journals:
        for line in journal.lines:
            totals[line.account] += line.debit_usd - line.credit_usd
    return totals


def journal_is_balanced(journal: Journal) -> bool:
    debits = sum((line.debit_usd for line in journal.lines), ZERO)
    credits = sum((line.credit_usd for line in journal.lines), ZERO)
    return debits == credits and len(journal.lines) >= 2


# --------------------------------------------------------------------------- #
# Posting templates (see docs/fixed-income/accounting.md)
# --------------------------------------------------------------------------- #


def post_capital_flow(book: Book, event) -> tuple[Optional[Journal], CashFlowRecord]:
    amount = money(event.amount_usd)
    if amount < 0:
        # Withdrawals are limited to cash that is free: settled cash minus purchase
        # reservations minus committed settlement payables (no leverage, spec 9.3).
        available = book.available_funding()
        if -amount > available:
            raise WithdrawalExceedsAvailableCash(
                f"capital withdrawal {-amount} exceeds available cash {available} "
                f"(settled {book.cash}, reserved {book.reserved}, payables {book.payables()})"
            )
    jb = JournalBuilder(event.event_id, event.type, event.effective_at, CAPITAL_FLOW_V1)
    jb.post(AccountCode.CASH, amount, memo=event.reason)
    jb.post(AccountCode.CAPITAL, -amount, memo=event.reason)
    book.cash += amount
    book.capital += amount
    record = CashFlowRecord(
        cash_flow_id=make_id("cf", event.event_id),
        security_id=CASH_SECURITY_ID,
        kind="CAPITAL",
        payment_date=ny_date(event.effective_at),
        entitled_face=ZERO,
        amount_usd=amount,
    )
    return jb.build(), record


def _settlement_for_fill(fill: Fill, cash: Decimal) -> PendingSettlement:
    return PendingSettlement(
        settlement_id=make_id("stl", fill.fill_id),
        fill_id=fill.fill_id,
        security_id=fill.security_id,
        side=fill.side,
        face=fill.face,
        settlement_date=fill.settlement_date,
        cash_usd=cash,
    )


def post_buy_fill(
    book: Book, event, fill: Fill, trade_date: date
) -> tuple[Optional[Journal], PendingSettlement]:
    """buy_fill_v1: Dr principal (clean cost), Dr accrued purchased, Cr payable; fees."""
    principal = money(fill.face * fill.execution_clean_price_per_100 / HUNDRED)
    accrued = fill.consideration_usd - principal
    jb = JournalBuilder(event.event_id, event.type, event.effective_at, BUY_FILL_V1)
    jb.post(AccountCode.BOND_PRINCIPAL, principal, fill.security_id, "clean cost")
    jb.post(AccountCode.ACCRUED_INTEREST_PURCHASED, accrued, fill.security_id, "accrued paid")
    jb.post(AccountCode.SETTLEMENT_PAYABLE, -fill.consideration_usd, fill.security_id)
    jb.post(AccountCode.TRANSACTION_FEES, fill.fees_usd, fill.security_id, "fees")
    jb.post(AccountCode.SETTLEMENT_PAYABLE, -fill.fees_usd, fill.security_id, "fees payable")
    position = book.position(fill.security_id)
    position.economic_face += fill.face
    position.lots.append(
        WorkingLot(
            lot_id=make_id("lot", fill.fill_id),
            security_id=fill.security_id,
            face=fill.face,
            trade_date=trade_date,
            settlement_date=fill.settlement_date,
            clean_price_per_100=fill.execution_clean_price_per_100,
            principal_cost_usd=principal,
            accrued_purchased_usd=accrued,
        )
    )
    book.fees += fill.fees_usd
    book.spread += fill.spread_cost_usd
    settlement = _settlement_for_fill(fill, fill.consideration_usd + fill.fees_usd)
    book.pending[settlement.settlement_id] = settlement
    return jb.build(), settlement


def relieve_fifo(position: WorkingPosition, face: Decimal) -> tuple[Decimal, Decimal]:
    """Remove ``face`` from lots FIFO; returns (principal relieved, accrued relieved).

    Partial lots are relieved pro rata and rounded to cents; a fully consumed
    lot releases its exact remaining balances so no residual cents remain.
    """
    remaining = face
    principal = ZERO
    accrued = ZERO
    for lot in position.lots:
        if remaining <= 0:
            break
        if lot.face <= 0:
            continue
        take = min(lot.face, remaining)
        if take == lot.face:
            p_part, a_part = lot.principal_cost_usd, lot.accrued_purchased_usd
        else:
            p_part = money(lot.principal_cost_usd * take / lot.face)
            a_part = money(lot.accrued_purchased_usd * take / lot.face)
        lot.face -= take
        lot.principal_cost_usd -= p_part
        lot.accrued_purchased_usd -= a_part
        principal += p_part
        accrued += a_part
        remaining -= take
    if remaining > 0:
        raise LedgerInvariantError(
            f"long-only: cannot relieve {face} face of {position.security_id}"
        )
    return principal, accrued


def post_sell_fill(book: Book, event, fill: Fill) -> tuple[Optional[Journal], PendingSettlement]:
    """sell_fill_v1: FIFO relief, realized clean gain, accrued split, receivable."""
    position = book.position(fill.security_id)
    if fill.face > position.economic_face:
        raise LedgerInvariantError("long-only: sale exceeds economic face")
    clean_proceeds = money(fill.face * fill.execution_clean_price_per_100 / HUNDRED)
    accrued_received = fill.consideration_usd - clean_proceeds
    principal, accrued_relieved = relieve_fifo(position, fill.face)
    realized = clean_proceeds - principal
    income = accrued_received - accrued_relieved
    receivable = fill.consideration_usd - fill.fees_usd
    jb = JournalBuilder(event.event_id, event.type, event.effective_at, SELL_FILL_V1)
    jb.post(AccountCode.SETTLEMENT_RECEIVABLE, receivable, fill.security_id)
    jb.post(AccountCode.TRANSACTION_FEES, fill.fees_usd, fill.security_id, "fees")
    jb.post(AccountCode.BOND_PRINCIPAL, -principal, fill.security_id, "FIFO clean cost")
    jb.post(
        AccountCode.ACCRUED_INTEREST_PURCHASED,
        -accrued_relieved,
        fill.security_id,
        "purchased accrued recovered",
    )
    jb.post(AccountCode.REALIZED_GAIN_LOSS, -realized, fill.security_id, "clean gain/loss")
    jb.post(AccountCode.INTEREST_INCOME, -income, fill.security_id, "accrued earned")
    position.economic_face -= fill.face
    book.realized += realized
    book.income += income
    book.fees += fill.fees_usd
    book.spread += fill.spread_cost_usd
    settlement = _settlement_for_fill(fill, receivable)
    book.pending[settlement.settlement_id] = settlement
    return jb.build(), settlement


def post_settlement(book: Book, event, settlement: PendingSettlement) -> Optional[Journal]:
    """buy_settlement_v1 / sell_settlement_v1: cash moves, face is delivered."""
    position = book.position(settlement.security_id)
    if settlement.side == Side.BUY:
        if book.cash - settlement.cash_usd < 0:
            raise LedgerInvariantError(
                f"settlement {settlement.settlement_id} exceeds settled cash (no leverage)"
            )
        jb = JournalBuilder(event.event_id, event.type, event.effective_at, BUY_SETTLEMENT_V1)
        jb.post(AccountCode.SETTLEMENT_PAYABLE, settlement.cash_usd, settlement.security_id)
        jb.post(AccountCode.CASH, -settlement.cash_usd, settlement.security_id)
        book.cash -= settlement.cash_usd
        position.settled_face += settlement.face
    else:
        if position.settled_face < settlement.face:
            raise LedgerInvariantError("cannot deliver face that has not settled")
        jb = JournalBuilder(event.event_id, event.type, event.effective_at, SELL_SETTLEMENT_V1)
        jb.post(AccountCode.CASH, settlement.cash_usd, settlement.security_id)
        jb.post(AccountCode.SETTLEMENT_RECEIVABLE, -settlement.cash_usd, settlement.security_id)
        book.cash += settlement.cash_usd
        position.settled_face -= settlement.face
    del book.pending[settlement.settlement_id]
    return jb.build()


def post_coupon(
    book: Book, event, entitled_face: Decimal
) -> tuple[Optional[Journal], Optional[CashFlowRecord]]:
    """coupon_payment_v1: Dr cash; Cr purchased-accrued recovery; Cr interest income.

    Recovery covers held lots that settled strictly before the payment date
    (including lots zeroed by a same-day redemption, which keep their accrued
    balance until this coupon is processed).
    """
    if entitled_face <= 0:
        return None, None
    amount = money(entitled_face * event.coupon_per_100 / HUNDRED)
    recovery = ZERO
    position = book.positions.get(event.security_id)
    if position is not None:
        for lot in position.lots:
            if lot.settlement_date < event.payment_date and lot.accrued_purchased_usd != 0:
                recovery += lot.accrued_purchased_usd
                lot.accrued_purchased_usd = ZERO
    income = amount - recovery
    jb = JournalBuilder(event.event_id, event.type, event.effective_at, COUPON_PAYMENT_V1)
    jb.post(AccountCode.CASH, amount, event.security_id, "coupon received")
    jb.post(
        AccountCode.ACCRUED_INTEREST_PURCHASED,
        -recovery,
        event.security_id,
        "purchased accrued recovered",
    )
    jb.post(AccountCode.INTEREST_INCOME, -income, event.security_id, "coupon income")
    book.cash += amount
    book.income += income
    record = CashFlowRecord(
        cash_flow_id=make_id("cf", event.event_id),
        security_id=event.security_id,
        kind="COUPON",
        payment_date=event.payment_date,
        entitled_face=entitled_face,
        amount_usd=amount,
    )
    return jb.build(), record


def post_redemption(
    book: Book, event, entitled_face: Decimal
) -> tuple[Optional[Journal], Optional[CashFlowRecord]]:
    """redemption_v1: principal credited exactly once; realized vs clean cost."""
    if entitled_face <= 0:
        return None, None
    position = book.position(event.security_id)
    amount = money(entitled_face * event.redemption_per_100 / HUNDRED)
    principal = ZERO
    remaining = entitled_face
    for lot in position.lots:
        if remaining <= 0:
            break
        take = min(lot.face, remaining)
        if take <= 0:
            continue
        if take == lot.face:
            part = lot.principal_cost_usd
        else:
            part = money(lot.principal_cost_usd * take / lot.face)
        lot.face -= take
        lot.principal_cost_usd -= part
        principal += part
        remaining -= take
    if remaining > 0:
        raise LedgerInvariantError("redemption exceeds held lots")
    realized = amount - principal
    jb = JournalBuilder(event.event_id, event.type, event.effective_at, REDEMPTION_V1)
    jb.post(AccountCode.CASH, amount, event.security_id, "principal redeemed")
    jb.post(AccountCode.BOND_PRINCIPAL, -principal, event.security_id, "clean cost relieved")
    jb.post(AccountCode.REALIZED_GAIN_LOSS, -realized, event.security_id, "redemption vs cost")
    book.cash += amount
    book.realized += realized
    position.economic_face -= entitled_face
    position.settled_face -= entitled_face
    record = CashFlowRecord(
        cash_flow_id=make_id("cf", event.event_id),
        security_id=event.security_id,
        kind="REDEMPTION",
        payment_date=event.payment_date,
        entitled_face=entitled_face,
        amount_usd=amount,
    )
    return jb.build(), record


def post_mark_to_market(book: Book, event, economic_equity: Decimal) -> Optional[Journal]:
    """mark_to_market_v1: book the delta so book equity equals economic NAV."""
    delta = money(economic_equity) - book.book_equity()
    jb = JournalBuilder(event.event_id, event.type, event.effective_at, MARK_TO_MARKET_V1)
    jb.post(AccountCode.MARK_ADJUSTMENT, delta, memo="valuation adjustment")
    jb.post(AccountCode.UNREALIZED_GAIN_LOSS, -delta, memo="unrealized gain/loss")
    book.unrealized += delta
    return jb.build()


def post_cash_interest(book: Book, event, amount: Decimal) -> Optional[Journal]:
    """cash_interest_v1: zero under the default execution model."""
    amount = money(amount)
    if amount == 0:
        return None
    jb = JournalBuilder(
        event.event_id, event.type, event.effective_at, CASH_INTEREST_V1, suffix="cash-interest"
    )
    jb.post(AccountCode.CASH, amount, memo="cash interest")
    jb.post(AccountCode.INTEREST_INCOME, -amount, memo="cash interest")
    book.cash += amount
    book.income += amount
    return jb.build()


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #


def reconcile(
    prior: PortfolioState,
    journals: list[Journal],
    new_state: PortfolioState,
    valuation: Optional[ValuationSnapshot] = None,
    require_economic_match: bool = False,
) -> ReconciliationReport:
    """Prove ``prior balances + journal lines == new balances`` and face consistency."""
    messages: list[str] = []
    balanced = all(journal_is_balanced(j) for j in journals)
    if not balanced:
        messages.append("unbalanced journal")
    before = state_balances(prior)
    after = state_balances(new_state)
    deltas = journal_deltas(journals)
    for code in AccountCode:
        expected = before[code] + deltas[code]
        if expected != after[code]:
            messages.append(f"{code.value}: ledger {expected} != state {after[code]}")
    if sum(after.values(), ZERO) != 0:
        messages.append("trial balance does not sum to zero")

    face_ok = True
    pending_buy: dict[str, Decimal] = {}
    pending_sell: dict[str, Decimal] = {}
    for s in new_state.pending_settlements:
        bucket = pending_buy if s.side == Side.BUY else pending_sell
        bucket[s.security_id] = bucket.get(s.security_id, ZERO) + s.face
    for position in new_state.positions:
        lot_face = sum((lot.face for lot in position.lots), ZERO)
        if lot_face != position.economic_face:
            face_ok = False
            messages.append(f"{position.security_id}: lots {lot_face} != economic face")
        expected_settled = (
            position.economic_face
            - pending_buy.get(position.security_id, ZERO)
            + pending_sell.get(position.security_id, ZERO)
        )
        if expected_settled != position.settled_face:
            face_ok = False
            messages.append(f"{position.security_id}: settled face inconsistent with pending")
    held = {p.security_id for p in new_state.positions}
    for sid in set(pending_buy) | set(pending_sell):
        if sid not in held:
            face_ok = False
            messages.append(f"{sid}: pending settlement without position")
    reserved = sum((o.reserved_cash_usd for o in new_state.open_orders), ZERO)
    if reserved != new_state.reserved_cash_usd:
        messages.append("reserved cash does not equal open order reservations")

    ledger_cash = before[AccountCode.CASH] + deltas[AccountCode.CASH]
    book_equity = (
        new_state.external_capital_usd
        + new_state.interest_income_usd
        + new_state.realized_gain_loss_usd
        + new_state.booked_unrealized_usd
        - new_state.transaction_fees_usd
    )
    economic = None
    difference = None
    if valuation is not None and valuation.complete and valuation.equity_usd is not None:
        economic = valuation.equity_usd
        difference = book_equity - economic
        if require_economic_match and difference != 0:
            messages.append(f"book equity differs from economic NAV by {difference}")
    ok = not messages and balanced and face_ok
    return ReconciliationReport(
        ok=ok,
        journals_balanced=balanced,
        ledger_cash_usd=ledger_cash,
        state_cash_usd=new_state.cash_usd,
        ledger_principal_face_check=face_ok,
        book_equity_usd=book_equity,
        economic_equity_usd=economic,
        difference_usd=difference,
        messages=messages,
    )


def ledger_totals(journals: Iterable[Journal]) -> dict[str, str]:
    """Cumulative signed totals per account (debit positive), as decimal strings."""
    totals = journal_deltas(journals)
    return {code.value: format(totals[code], "f") for code in AccountCode}
