"""Offline state store that applies transition proposals like the .NET commit path.

Mirrors spec 9.5 / 14.6 checks, in this order:

1. proposal hash recomputed over ``hash_payload()`` and HMAC signature verified;
   ``new_state_hash`` recomputed; journals re-summed (balanced, >= 2 lines);
2. logical command id: a retry with the same ``request_hash`` returns the
   already committed result; the same id with a different request hash is an
   :class:`IdempotencyConflict` (HTTP 409);
3. blocked portfolio refuses further commits (:class:`PortfolioBlocked`);
4. expected version must equal the current version, else
   :class:`StaleStateVersion` (HTTP 409) - stale results are never merged;
5. the proposal's ``input_hashes.portfolioState`` must be the current state hash;
6. event and journal ids are unique across all committed transitions
   (one financial effect per economic event);
7. a failed reconciliation blocks the portfolio and raises
   :class:`ReconciliationFailed`.

Persistence is in memory, optionally appended to a JSONL log (one committed
transition per line) that is replayed on construction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from research_engine.contracts.common import content_hash, verify_signature
from research_engine.contracts.portfolio import (
    PortfolioState,
    TransitionProposal,
    TransitionRequest,
)

from .ledger import journal_is_balanced


class CommitError(RuntimeError):
    code = "commit_error"


class InvalidProposal(CommitError):
    code = "invalid_proposal"


class IdempotencyConflict(CommitError):
    code = "idempotency_conflict"


class StaleStateVersion(CommitError):
    code = "stale_state_version"


class PortfolioBlockedError(CommitError):
    code = "portfolio_blocked"


class DuplicateFinancialEffect(CommitError):
    code = "duplicate_financial_effect"


class ReconciliationFailed(CommitError):
    code = "reconciliation_failed"


class UnknownPortfolio(CommitError):
    code = "unknown_portfolio"


@dataclass(frozen=True)
class CommitResult:
    proposal: TransitionProposal
    sequence: int
    duplicate: bool = False

    @property
    def state(self) -> PortfolioState:
        return self.proposal.new_state


def verify_proposal(proposal: TransitionProposal, signing_key: bytes) -> None:
    """Integrity checks shared by commit and parity verification."""
    if proposal.proposal_hash is None or proposal.signature is None:
        raise InvalidProposal("proposal is not hashed and signed")
    if content_hash(proposal.hash_payload()) != proposal.proposal_hash:
        raise InvalidProposal("proposal hash does not match its content")
    if not verify_signature(proposal.proposal_hash, proposal.signature, signing_key):
        raise InvalidProposal("proposal signature is invalid")
    if proposal.new_state.compute_hash() != proposal.new_state_hash:
        raise InvalidProposal("new_state_hash does not match new_state")
    if proposal.new_state.portfolio_id != proposal.portfolio_id:
        raise InvalidProposal("new state belongs to a different portfolio")
    for journal in proposal.journals:
        if not journal_is_balanced(journal):
            raise InvalidProposal(f"unbalanced journal {journal.journal_id}")
    for key in ("portfolioState", "marketSnapshot", "riskPolicy", "executionModel"):
        if key not in proposal.input_hashes:
            raise InvalidProposal(f"missing input hash {key}")


class OfflineStateStore:
    """In-memory (optionally JSONL-backed) authoritative store for offline research."""

    def __init__(self, signing_key: bytes, path: Optional[Path] = None) -> None:
        if not signing_key:
            raise ValueError("signing key must be configured")
        self._key = signing_key
        self._path = Path(path) if path else None
        self._states: dict[str, PortfolioState] = {}
        self._commands: dict[str, CommitResult] = {}
        self._event_ids: set[str] = set()
        self._journal_ids: set[str] = set()
        self._log: list[CommitResult] = []
        self._blocked: dict[str, str] = {}
        self._requests: dict[str, TransitionRequest] = {}
        if self._path is not None and self._path.exists():
            self._replay_log()

    # -- queries -------------------------------------------------------------

    def register(self, state: PortfolioState) -> None:
        """Register an initial (version 0) portfolio state."""
        existing = self._states.get(state.portfolio_id)
        if existing is not None:
            if existing.compute_hash() != state.compute_hash() and existing.version == 0:
                raise IdempotencyConflict("portfolio already registered with different state")
            return
        self._states[state.portfolio_id] = state
        if self._path is not None:
            self._append({"kind": "register", "state": state.to_wire()})

    def state(self, portfolio_id: str) -> PortfolioState:
        try:
            return self._states[portfolio_id]
        except KeyError as exc:
            raise UnknownPortfolio(portfolio_id) from exc

    def portfolios(self) -> list[str]:
        return sorted(self._states)

    def has_command(self, command_id: str) -> bool:
        return command_id in self._commands

    def result(self, command_id: str) -> CommitResult:
        return self._commands[command_id]

    def committed(self, portfolio_id: Optional[str] = None) -> list[TransitionProposal]:
        return [
            r.proposal
            for r in self._log
            if portfolio_id is None or r.proposal.portfolio_id == portfolio_id
        ]

    def request_for(self, command_id: str) -> Optional[TransitionRequest]:
        return self._requests.get(command_id)

    def blocked_reason(self, portfolio_id: str) -> Optional[str]:
        return self._blocked.get(portfolio_id)

    # -- commit --------------------------------------------------------------

    def commit(
        self, proposal: TransitionProposal, request: Optional[TransitionRequest] = None
    ) -> CommitResult:
        verify_proposal(proposal, self._key)
        prior = self._commands.get(proposal.command_id)
        if prior is not None:
            if prior.proposal.request_hash == proposal.request_hash:
                return CommitResult(prior.proposal, prior.sequence, duplicate=True)
            raise IdempotencyConflict(
                f"command {proposal.command_id} already committed with a different request"
            )
        pid = proposal.portfolio_id
        if pid in self._blocked:
            raise PortfolioBlockedError(f"{pid} blocked: {self._blocked[pid]}")
        current = self.state(pid)
        if current.blocked_reason:
            raise PortfolioBlockedError(f"{pid} blocked: {current.blocked_reason}")
        if proposal.expected_version != current.version:
            raise StaleStateVersion(
                f"{pid}: expected version {proposal.expected_version}, current {current.version}"
            )
        if proposal.input_hashes["portfolioState"] != current.compute_hash():
            raise InvalidProposal("proposal was computed from a different state")
        if request is not None and request.compute_hash() != proposal.request_hash:
            raise InvalidProposal("request does not match proposal request hash")
        event_ids = [e.event_id for e in proposal.events]
        journal_ids = [j.journal_id for j in proposal.journals]
        if len(set(event_ids)) != len(event_ids) or self._event_ids.intersection(event_ids):
            raise DuplicateFinancialEffect("event id already committed")
        if len(set(journal_ids)) != len(journal_ids) or self._journal_ids.intersection(journal_ids):
            raise DuplicateFinancialEffect("journal id already committed")
        if not proposal.reconciliation.ok:
            reason = "reconciliation_failed:" + ";".join(proposal.reconciliation.messages)
            self._blocked[pid] = reason
            if self._path is not None:
                self._append({"kind": "blocked", "portfolioId": pid, "reason": reason})
            raise ReconciliationFailed(reason)
        result = self._apply(proposal, request)
        if self._path is not None:
            record = {"kind": "commit", "proposal": proposal.to_wire()}
            if request is not None:
                record["request"] = request.to_wire()
            self._append(record)
        return result

    def _apply(
        self, proposal: TransitionProposal, request: Optional[TransitionRequest]
    ) -> CommitResult:
        result = CommitResult(proposal, len(self._log) + 1)
        self._commands[proposal.command_id] = result
        self._log.append(result)
        self._event_ids.update(e.event_id for e in proposal.events)
        self._journal_ids.update(j.journal_id for j in proposal.journals)
        self._states[proposal.portfolio_id] = proposal.new_state
        if request is not None:
            self._requests[proposal.command_id] = request
        return result

    # -- persistence ---------------------------------------------------------

    def _append(self, record: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()

    def _replay_log(self) -> None:
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            kind = record["kind"]
            if kind == "register":
                state = PortfolioState.model_validate(record["state"])
                self._states.setdefault(state.portfolio_id, state)
            elif kind == "commit":
                proposal = TransitionProposal.model_validate(record["proposal"])
                verify_proposal(proposal, self._key)
                request = (
                    TransitionRequest.model_validate(record["request"])
                    if "request" in record
                    else None
                )
                current = self.state(proposal.portfolio_id)
                if proposal.expected_version != current.version:
                    raise StaleStateVersion("corrupt log: version gap during replay")
                self._apply(proposal, request)
            elif kind == "blocked":
                self._blocked[record["portfolioId"]] = record["reason"]

    def iter_log(self) -> Iterable[CommitResult]:
        return iter(self._log)
