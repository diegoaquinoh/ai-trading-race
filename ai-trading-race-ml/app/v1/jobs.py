"""Background job runner for operator-triggered ingestion and index builds.

Jobs run on a single worker thread (serialized writes to the research store),
never inside a decision request (spec 14.3). Job ids are derived from the job
kind and the caller's ``requestId``; resubmitting the same request returns the
same job, a different payload under the same ``requestId`` is a 409.
"""

from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from research_engine.contracts.common import content_hash, short_id, utc_to_str
from research_engine.contracts.decisions import JobState

from .errors import conflict

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    job_id: str
    kind: str
    request_id: str
    request_hash: str
    request: dict[str, Any]
    state: JobState = JobState.QUEUED
    created_at: datetime = field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    def to_wire(self) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "kind": self.kind,
            "state": self.state.value,
            "requestId": self.request_id,
            "requestHash": self.request_hash,
            "request": self.request,
            "createdAt": utc_to_str(self.created_at),
            "startedAt": utc_to_str(self.started_at) if self.started_at else None,
            "completedAt": utc_to_str(self.completed_at) if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "links": {"self": f"/internal/v1/admin/jobs/{self.job_id}"},
        }


class JobManager:
    def __init__(self, clock: Callable[[], datetime] = utc_now, max_jobs: int = 500):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-job")
        self._clock = clock
        self._max = max_jobs

    def submit(
        self, kind: str, request_id: str, request: dict[str, Any], work: Callable[[], dict]
    ) -> tuple[Job, bool]:
        """Return ``(job, created)``; identical resubmission returns the existing job."""
        request_hash = content_hash(request, allow_floats=True)
        job_id = short_id("job", {"kind": kind, "requestId": request_id}, 20)
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise conflict(
                        "idempotency_key_reused",
                        f"requestId {request_id!r} was already used with a different payload",
                    )
                return existing, False
            job = Job(
                job_id=job_id,
                kind=kind,
                request_id=request_id,
                request_hash=request_hash,
                request=request,
                created_at=self._clock(),
            )
            self._jobs[job_id] = job
            self._order.append(job_id)
            while len(self._order) > self._max:
                old = self._order.pop(0)
                if self._jobs[old].state in (JobState.QUEUED, JobState.RUNNING):
                    self._order.insert(0, old)
                    break
                self._jobs.pop(old, None)
        self._executor.submit(self._run, job, work)
        return job, True

    def _run(self, job: Job, work: Callable[[], dict]) -> None:
        with self._lock:
            job.state = JobState.RUNNING
            job.started_at = self._clock()
        try:
            result = work()
            with self._lock:
                job.result = result
                job.state = (
                    JobState.FAILED
                    if isinstance(result, dict) and result.get("failed")
                    else JobState.COMPLETED
                )
        except Exception as exc:  # job failures are reported, never raised
            log.error("job %s failed: %s\n%s", job.job_id, exc, traceback.format_exc())
            with self._lock:
                job.state = JobState.FAILED
                job.error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                job.completed_at = self._clock()

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def wait(self, job_id: str, timeout: float = 30.0) -> Optional[Job]:
        """Test helper: block until the job leaves QUEUED/RUNNING."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get(job_id)
            if job is None or job.state not in (JobState.QUEUED, JobState.RUNNING):
                return job
            time.sleep(0.02)
        return self.get(job_id)

    def recent(self, kind: Optional[str] = None, limit: int = 20) -> list[Job]:
        with self._lock:
            jobs = [self._jobs[j] for j in reversed(self._order) if j in self._jobs]
        if kind:
            jobs = [j for j in jobs if j.kind == kind]
        return jobs[:limit]

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
