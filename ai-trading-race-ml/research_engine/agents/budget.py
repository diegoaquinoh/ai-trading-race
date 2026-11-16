"""Decision-wide budget ledger (spec 10.4, 14.4, 15.2).

One :class:`BudgetLedger` per decision is shared by the lead, every specialist
and every tool. Resources:

==========================  =====================================================
generation_calls            every provider call: task assignment, tool-selection
                            turns, specialist turns, synthesis, malformed
                            responses and repairs
tool_calls                  every executed tool call (denied calls never run)
evidence_calls              ``retrieve_evidence`` and ``expand_evidence_graph``
unique_evidence_chunks      distinct chunks delivered to any agent (counted once)
evidence_tokens             tokens of those distinct chunks
input_tokens/output_tokens  provider-reported; every resend counts
cost_usd                    versioned price schedule, when configured
deadline                    wall-clock research deadline (monotonic clock)
==========================  =====================================================

Protocol: ``reserve`` atomically checks *committed + outstanding reservations +
request <= limit* for every resource and records the worst case; ``commit``
replaces the reservation with actual usage; ``release`` drops an unused
reservation. Parallel specialists therefore cannot jointly overspend: the
second reservation that would exceed a ceiling is denied
(:class:`BudgetExceeded`). Actual usage is always recorded, even when a
provider reports more than was reserved; the ledger is then marked exhausted
and the decision ends ``failed_budget``.

:class:`TaskAllowance` adds per-task caps (a specialist's reserved block) on
top of the global ledger. Unique-chunk registration is global and atomic.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Iterable, Literal, Optional

from research_engine.contracts.common import ContractModel, DecimalStr, OpaqueId
from research_engine.contracts.decisions import DecisionBudget, UsageSummary

log = logging.getLogger(__name__)

RESOURCES = (
    "generation_calls",
    "tool_calls",
    "evidence_calls",
    "unique_evidence_chunks",
    "evidence_tokens",
    "input_tokens",
    "output_tokens",
)
MILLION = Decimal(1_000_000)
COST_QUANTUM = Decimal("0.000001")


class ModelPrice(ContractModel):
    provider: str
    model: str
    input_usd_per_million_tokens: DecimalStr
    output_usd_per_million_tokens: DecimalStr


class PriceSchedule(ContractModel):
    """Versioned provider price schedule. Values must come from the operator."""

    schedule_id: OpaqueId
    effective_date: date
    currency: Literal["USD"] = "USD"
    source: str
    prices: list[ModelPrice]

    def price(self, provider: str, model: str) -> Optional[ModelPrice]:
        for item in self.prices:
            if item.provider == provider and item.model == model:
                return item
        return None

    def cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        item = self.price(provider, model)
        if item is None:
            raise KeyError(f"price schedule {self.schedule_id} has no entry for {provider}/{model}")
        value = (
            Decimal(input_tokens) * item.input_usd_per_million_tokens
            + Decimal(output_tokens) * item.output_usd_per_million_tokens
        ) / MILLION
        return value.quantize(COST_QUANTUM, rounding=ROUND_HALF_UP)


REFERENCE_ZERO_COST = PriceSchedule(
    schedule_id="reference-zero-cost-v1",
    effective_date=date(2026, 1, 1),
    source="ReferenceHeuristicProvider runs locally and has no provider charge",
    prices=[
        ModelPrice(
            provider="reference",
            model="reference-heuristic-v1",
            input_usd_per_million_tokens=Decimal("0"),
            output_usd_per_million_tokens=Decimal("0"),
        )
    ],
)


class BudgetExceeded(RuntimeError):
    def __init__(self, resource: str, message: str):
        super().__init__(message)
        self.resource = resource


@dataclass
class Reservation:
    reservation_id: int
    label: str
    amounts: dict[str, int]
    cost: Decimal = Decimal("0")
    allowance: Optional["TaskAllowance"] = None
    settled: bool = False


def _zero() -> dict[str, int]:
    return {name: 0 for name in RESOURCES}


class BudgetLedger:
    def __init__(
        self,
        budget: DecisionBudget,
        *,
        price_schedule: Optional[PriceSchedule] = None,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.budget = budget
        self.limits = {
            "generation_calls": budget.max_generation_calls,
            "tool_calls": budget.max_tool_calls,
            "evidence_calls": budget.max_evidence_calls,
            "unique_evidence_chunks": budget.max_unique_evidence_chunks,
            "evidence_tokens": budget.max_evidence_tokens,
            "input_tokens": budget.max_input_tokens,
            "output_tokens": budget.max_output_tokens,
        }
        self.cost_limit: Optional[Decimal] = budget.max_cost_usd
        self.price_schedule = price_schedule
        self._monotonic = monotonic
        self._deadline = monotonic() + budget.deadline_seconds
        self._lock = threading.RLock()
        self.committed = _zero()
        self.committed_cost = Decimal("0")
        self._outstanding: dict[int, Reservation] = {}
        self._next = 1
        self._chunks: dict[str, int] = {}  # chunk id -> tokens (decision-wide registry)
        self.exhausted: Optional[str] = None
        self.denials: list[str] = []

    # ------------------------------------------------------------------ helpers

    def _pending(self) -> tuple[dict[str, int], Decimal]:
        totals = _zero()
        cost = Decimal("0")
        for item in self._outstanding.values():
            for name, value in item.amounts.items():
                totals[name] += value
            cost += item.cost
        return totals, cost

    def remaining(self) -> dict[str, int]:
        with self._lock:
            pending, _ = self._pending()
            return {
                name: max(0, self.limits[name] - self.committed[name] - pending[name])
                for name in RESOURCES
            }

    def remaining_cost(self) -> Optional[Decimal]:
        if self.cost_limit is None:
            return None
        with self._lock:
            _, pending = self._pending()
            return max(Decimal("0"), self.cost_limit - self.committed_cost - pending)

    def seconds_left(self) -> float:
        return self._deadline - self._monotonic()

    def check_deadline(self) -> None:
        if self.seconds_left() <= 0:
            with self._lock:
                self.exhausted = self.exhausted or "deadline"
                self.denials.append("deadline")
            raise BudgetExceeded("deadline", "research deadline elapsed")

    def estimate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int):
        if self.price_schedule is None or self.price_schedule.price(provider, model) is None:
            return None
        return self.price_schedule.cost(provider, model, input_tokens, output_tokens)

    # ------------------------------------------------------------------ protocol

    def reserve(
        self,
        label: str,
        *,
        cost: Decimal = Decimal("0"),
        allowance: Optional["TaskAllowance"] = None,
        **amounts: int,
    ) -> Reservation:
        unknown = set(amounts) - set(RESOURCES)
        if unknown:
            raise ValueError(f"unknown budget resources: {sorted(unknown)}")
        self.check_deadline()
        with self._lock:
            if self.exhausted:
                raise BudgetExceeded(self.exhausted, f"budget already exhausted ({self.exhausted})")
            pending, pending_cost = self._pending()
            for name, value in amounts.items():
                if value < 0:
                    raise ValueError("reservations are non-negative")
                if self.committed[name] + pending[name] + value > self.limits[name]:
                    self.denials.append(f"{label}:{name}")
                    raise BudgetExceeded(
                        name,
                        f"{label}: {name} ceiling {self.limits[name]} would be exceeded "
                        f"(committed {self.committed[name]}, reserved {pending[name]}, "
                        f"requested {value})",
                    )
            if self.cost_limit is not None and (
                self.committed_cost + pending_cost + cost > self.cost_limit
            ):
                self.denials.append(f"{label}:cost_usd")
                raise BudgetExceeded("cost_usd", f"{label}: monetary ceiling would be exceeded")
            if allowance is not None:
                allowance._check(label, amounts)
            reservation = Reservation(self._next, label, dict(amounts), cost, allowance)
            self._next += 1
            self._outstanding[reservation.reservation_id] = reservation
            if allowance is not None:
                allowance._hold(reservation)
            return reservation

    def commit(
        self, reservation: Reservation, *, cost: Optional[Decimal] = None, **actual: int
    ) -> None:
        with self._lock:
            if reservation.settled:
                raise RuntimeError(f"reservation {reservation.reservation_id} already settled")
            reservation.settled = True
            self._outstanding.pop(reservation.reservation_id, None)
            for name, value in actual.items():
                self.committed[name] += value
                if self.committed[name] > self.limits[name] and not self.exhausted:
                    self.exhausted = name
            if cost is not None:
                self.committed_cost += cost
                if self.cost_limit is not None and self.committed_cost > self.cost_limit:
                    self.exhausted = self.exhausted or "cost_usd"
            if reservation.allowance is not None:
                reservation.allowance._settle(reservation, actual)

    def release(self, reservation: Reservation) -> None:
        with self._lock:
            if reservation.settled:
                return
            reservation.settled = True
            self._outstanding.pop(reservation.reservation_id, None)
            if reservation.allowance is not None:
                reservation.allowance._settle(reservation, {})

    def mark_exhausted(self, resource: str) -> None:
        with self._lock:
            self.exhausted = self.exhausted or resource

    # ------------------------------------------------------------------ evidence registry

    def register_chunks(
        self, chunks: Iterable[tuple[str, int]], *, allowance: Optional["TaskAllowance"] = None
    ) -> tuple[list[str], list[str]]:
        """Admit delivered chunks into the decision-wide evidence registry.

        Already-registered chunks are admitted free (counted once); new chunks are
        admitted in the given (rank) order while the unique-chunk and evidence-token
        ceilings allow. Returns (admitted ids, rejected ids). Atomic.
        """
        admitted: list[str] = []
        rejected: list[str] = []
        with self._lock:
            pending, _ = self._pending()
            for chunk_id, tokens in chunks:
                if chunk_id in self._chunks:
                    admitted.append(chunk_id)
                    continue
                over_count = (
                    self.committed["unique_evidence_chunks"] + pending["unique_evidence_chunks"] + 1
                    > self.limits["unique_evidence_chunks"]
                )
                over_tokens = (
                    self.committed["evidence_tokens"] + pending["evidence_tokens"] + tokens
                    > self.limits["evidence_tokens"]
                )
                if (
                    over_count
                    or over_tokens
                    or (allowance is not None and not allowance._admit_chunk(tokens))
                ):
                    rejected.append(chunk_id)
                    continue
                self._chunks[chunk_id] = tokens
                self.committed["unique_evidence_chunks"] += 1
                self.committed["evidence_tokens"] += tokens
                admitted.append(chunk_id)
        return admitted, rejected

    def registered_chunks(self) -> dict[str, int]:
        with self._lock:
            return dict(self._chunks)

    # ------------------------------------------------------------------ reporting

    def usage(self, duration_ms: int = 0) -> UsageSummary:
        with self._lock:
            cost = None
            schedule_id = None
            if self.price_schedule is not None:
                cost = self.committed_cost.quantize(COST_QUANTUM)
                schedule_id = self.price_schedule.schedule_id
            return UsageSummary(
                generation_calls=self.committed["generation_calls"],
                tool_calls=self.committed["tool_calls"],
                evidence_calls=self.committed["evidence_calls"],
                unique_evidence_chunks=self.committed["unique_evidence_chunks"],
                evidence_tokens=self.committed["evidence_tokens"],
                input_tokens=self.committed["input_tokens"],
                output_tokens=self.committed["output_tokens"],
                duration_ms=duration_ms,
                estimated_cost_usd=cost,
                price_schedule_id=schedule_id,
                budget_exhausted=self.exhausted,
            )


@dataclass
class TaskAllowance:
    """Per-task caps (e.g. one specialist's reserved block) on top of the ledger."""

    label: str
    caps: dict[str, int]
    used: dict[str, int] = field(default_factory=_zero)
    held: dict[int, dict[str, int]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def _check(self, label: str, amounts: dict[str, int]) -> None:
        with self.lock:
            for name, value in amounts.items():
                cap = self.caps.get(name)
                if cap is None:
                    continue
                pending = sum(h.get(name, 0) for h in self.held.values())
                if self.used[name] + pending + value > cap:
                    raise BudgetExceeded(
                        name, f"{label}: task allowance {self.label} {name} cap {cap} reached"
                    )

    def _hold(self, reservation: Reservation) -> None:
        with self.lock:
            self.held[reservation.reservation_id] = dict(reservation.amounts)

    def _settle(self, reservation: Reservation, actual: dict[str, int]) -> None:
        with self.lock:
            self.held.pop(reservation.reservation_id, None)
            for name, value in actual.items():
                self.used[name] += value

    def _admit_chunk(self, tokens: int) -> bool:
        with self.lock:
            cap_n = self.caps.get("unique_evidence_chunks")
            cap_t = self.caps.get("evidence_tokens")
            if cap_n is not None and self.used["unique_evidence_chunks"] + 1 > cap_n:
                return False
            if cap_t is not None and self.used["evidence_tokens"] + tokens > cap_t:
                return False
            self.used["unique_evidence_chunks"] += 1
            self.used["evidence_tokens"] += tokens
            return True

    def usage(self) -> dict[str, int]:
        with self.lock:
            return {k: v for k, v in self.used.items() if v}
