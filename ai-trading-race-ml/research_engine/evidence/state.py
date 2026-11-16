"""Ingestion state machine and source health (spec 11.3, 15.3, 16.6, 18.3).

::

    discovered -> downloaded -> parsed -> chunked -> extracted -> indexed -> active
                       \\-> failed_retryable / quarantined / review_required

Every attempt is recorded as an ``IngestionAttempt`` (even unchanged re-fetches).
A source outage is recorded as a ``SourceFetchRun`` with outcome ``outage``; it
never advances ``last_success_at``, so freshness cannot be falsely refreshed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from research_engine.contracts.evidence import (
    FetchRunOutcome,
    IngestionState,
    Source,
    SourceFetchRun,
    SourceHealth,
    SourceHealthStatus,
)

S = IngestionState
_FAILURES = {S.FAILED_RETRYABLE, S.QUARANTINED, S.REVIEW_REQUIRED}

ALLOWED_TRANSITIONS: dict[Optional[IngestionState], set[IngestionState]] = {
    None: {S.DISCOVERED},
    S.DISCOVERED: {S.DOWNLOADED, S.FAILED_RETRYABLE, S.QUARANTINED},
    # In-progress states may restart from DISCOVERED after an interrupted run.
    S.DOWNLOADED: {S.PARSED, S.DISCOVERED} | _FAILURES,
    S.PARSED: {S.CHUNKED, S.DISCOVERED} | _FAILURES,
    S.CHUNKED: {S.EXTRACTED, S.DISCOVERED, S.FAILED_RETRYABLE, S.REVIEW_REQUIRED},
    S.EXTRACTED: {S.INDEXED, S.FAILED_RETRYABLE, S.DISCOVERED},
    S.INDEXED: {S.ACTIVE, S.INDEXED, S.DISCOVERED},
    S.ACTIVE: {S.ACTIVE, S.INDEXED, S.DISCOVERED},
    S.FAILED_RETRYABLE: {S.DISCOVERED, S.QUARANTINED},
    S.REVIEW_REQUIRED: {S.DISCOVERED},
    S.QUARANTINED: {S.DISCOVERED},  # explicit operator re-admission only
}


class IllegalTransition(RuntimeError):
    pass


def check_transition(current: Optional[IngestionState], target: IngestionState) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise IllegalTransition(f"{current.value if current else None} -> {target.value}")


def next_health(previous: SourceHealth, run: SourceFetchRun) -> SourceHealth:
    """Fold one fetch run into source health. Only SUCCESS advances freshness."""
    if run.outcome == FetchRunOutcome.SUCCESS:
        return SourceHealth(
            status=SourceHealthStatus.HEALTHY,
            last_attempt_at=run.completed_at,
            last_success_at=max(
                (t for t in (previous.last_success_at, run.source_observed_at) if t),
                default=None,
            ),
            last_outcome=run.outcome,
            consecutive_failures=0,
            last_error=None,
        )
    status = (
        SourceHealthStatus.OUTAGE
        if run.outcome == FetchRunOutcome.OUTAGE
        else SourceHealthStatus.DEGRADED
    )
    return SourceHealth(
        status=status,
        last_attempt_at=run.completed_at,
        last_success_at=previous.last_success_at,
        last_outcome=run.outcome,
        consecutive_failures=previous.consecutive_failures + 1,
        last_error=run.error,
    )


def freshness(source: Source, now: datetime) -> SourceHealth:
    """Health as seen at ``now``: STALE when the last success is too old."""
    health = source.health
    if health.status in (SourceHealthStatus.OUTAGE, SourceHealthStatus.DEGRADED):
        return health
    if health.last_success_at is None:
        return health.model_copy(update={"status": SourceHealthStatus.UNKNOWN})
    if now - health.last_success_at > timedelta(hours=source.freshness_expectation_hours):
        return health.model_copy(update={"status": SourceHealthStatus.STALE})
    return health
