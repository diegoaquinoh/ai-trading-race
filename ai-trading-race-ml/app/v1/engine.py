"""Shared, read-only engine objects for the internal API.

The numerical ports, calculation store and evidence index are loaded once
(application lifespan) and shared by every request. Tests and alternative
deployments inject their own :class:`Engine` through ``app.dependency_overrides``
on :func:`get_engine`.

Signing: one shared key (``ML_SERVICE_SIGNING_KEY`` = .NET
``ResearchEngine:SigningKey``) signs TransitionProposals and StrategyResults.
Outside ``ENVIRONMENT=development`` the internal endpoints refuse to serve
(503) without it; development falls back to a fixed key with a loud warning.
The calculation store keeps its own ``RESEARCH_SIGNING_KEY``.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Request

from app.config import Settings, environment, is_development
from research_engine.contracts.common import short_id

from .errors import ProblemError, conflict, not_found, unavailable
from .jobs import JobManager
from .strategies import StrategyService
from .wire import RequestRegistry, ResponseCache

log = logging.getLogger(__name__)

DEV_SIGNING_KEY = b"dev-only-insecure-research-engine-signing-key"


def evidence_snapshot_id(member_version_ids) -> str:
    """Evidence snapshot = the exact set of document versions of a corpus manifest."""
    return short_id("evs", {"versions": sorted(member_version_ids)}, 20)


def resolve_signing_key(settings: Settings) -> tuple[Optional[bytes], bool, Optional[str]]:
    """``(key, configured, error)``."""
    if settings.signing_key:
        return settings.signing_key.encode("utf-8"), True, None
    if is_development():
        log.warning(
            "!!! ML_SERVICE_SIGNING_KEY is not set: TransitionProposals and StrategyResults are "
            "signed with the PUBLIC development key. Never run like this outside development. !!!"
        )
        return DEV_SIGNING_KEY, False, None
    message = (
        f"ML_SERVICE_SIGNING_KEY is required when ENVIRONMENT={environment()}; "
        "internal research endpoints are disabled"
    )
    log.error(message)
    return None, False, message


class EvidenceState:
    """Loaded READY index builds (read-only) and the evidence home."""

    def __init__(self) -> None:
        self.home: Any = None
        self.indexes: dict[str, Any] = {}
        self.active_build_id: Optional[str] = None
        self.status = "disabled"
        self.error: Optional[str] = None
        self.lock = threading.RLock()

    def attach(self, home: Any, index: Any = None, *, activate: bool = True) -> None:
        with self.lock:
            self.home = home
            if index is not None:
                self.indexes[index.build_id] = index
                if activate or self.active_build_id is None:
                    self.active_build_id = index.build_id
                self.status = "ready"
                self.error = None

    @property
    def store(self) -> Any:
        if self.home is None:
            raise unavailable(
                "evidence_unavailable", self.error or "the evidence store is not configured"
            )
        return self.home.store

    def index(self, build_id: Optional[str] = None) -> Any:
        """Loaded READY index (``None`` = active). Never builds or ingests."""
        with self.lock:
            if not self.indexes:
                raise unavailable(
                    "evidence_index_unavailable",
                    self.error
                    or "no READY evidence index is loaded; run an admin index build first",
                )
            if build_id is None:
                return self.indexes[self.active_build_id]
            hit = self.indexes.get(build_id)
            if hit is not None:
                return hit
        build = self.home.store.get_index_build(build_id) if self.home is not None else None
        if build is None:
            raise not_found("unknown_index_build", f"index build {build_id!r} does not exist")
        if build.status.value != "READY":
            raise conflict(
                "index_build_not_ready", f"index build {build_id!r} is {build.status.value}"
            )
        raise unavailable(
            "index_build_not_loaded",
            f"index build {build_id!r} is READY but not loaded by this engine instance",
        )

    def resolve(self, evidence_snapshot: Optional[str], build_id: Optional[str]) -> Any:
        """Pick the index for an (evidence snapshot, index build) pair."""
        if build_id is not None or evidence_snapshot is None:
            index = self.index(build_id)
            if evidence_snapshot is not None and (
                evidence_snapshot_id(index.build.member_version_ids) != evidence_snapshot
            ):
                raise conflict(
                    "evidence_snapshot_mismatch",
                    f"index build {index.build_id} does not cover evidence snapshot "
                    f"{evidence_snapshot}",
                )
            return index
        with self.lock:
            candidates = [
                idx
                for idx in self.indexes.values()
                if evidence_snapshot_id(idx.build.member_version_ids) == evidence_snapshot
            ]
            active = self.indexes.get(self.active_build_id) if self.active_build_id else None
        if not candidates:
            self.index(None)  # raises 503 when nothing is loaded
            raise not_found(
                "unknown_evidence_snapshot",
                f"no loaded READY index covers evidence snapshot {evidence_snapshot!r}",
            )
        if active is not None and active in candidates:
            return active
        return sorted(candidates, key=lambda i: i.build_id)[0]


class Engine:
    def __init__(
        self,
        *,
        pricing: Any,
        market: Any,
        settings: Settings,
        signing_key: Optional[bytes],
        signing_configured: bool,
        signing_error: Optional[str] = None,
        strategies: Optional[StrategyService] = None,
    ):
        self.pricing = pricing
        self.market = market
        self.calc_store = pricing.calc_store
        self.settings = settings
        self.signing_key = signing_key
        self.signing_configured = signing_configured
        self.signing_error = signing_error
        self.max_decisions = max(1, settings.max_concurrent_decisions)
        self.decision_slots = threading.BoundedSemaphore(self.max_decisions)
        self.decision_executor = ThreadPoolExecutor(
            max_workers=self.max_decisions, thread_name_prefix="research-decision"
        )
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self.jobs = JobManager()
        self.requests = RequestRegistry()
        self.transition_cache = ResponseCache(256)
        self.decision_cache = ResponseCache(256)
        self.evidence = EvidenceState()
        self.strategies = strategies or StrategyService(settings)
        self.warmup: dict[str, Any] = {"curves": "disabled", "admission": None}
        self.started_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------ #
    # Decision concurrency
    # ------------------------------------------------------------------ #
    def try_acquire_decision(self) -> bool:
        if not self.decision_slots.acquire(blocking=False):
            return False
        with self._inflight_lock:
            self._inflight += 1
        return True

    def release_decision(self) -> None:
        with self._inflight_lock:
            self._inflight -= 1
        self.decision_slots.release()

    @property
    def decisions_in_flight(self) -> int:
        with self._inflight_lock:
            return self._inflight

    def evidence_port(self, index: Any) -> Any:
        """Agents' evidence port over a loaded READY index (never ingests or builds)."""
        from research_engine.agents.ports import RetrievalEvidencePort

        port = RetrievalEvidencePort(self.evidence.store, index)
        port.evidence_snapshot_id = evidence_snapshot_id(index.build.member_version_ids)
        return port

    def require_signing(self) -> bytes:
        if self.signing_key is None:
            raise unavailable(
                "signing_not_configured", self.signing_error or "signing key not configured"
            )
        return self.signing_key

    def shutdown(self) -> None:
        self.jobs.shutdown()
        self.decision_executor.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------- #
# Construction and warm-up
# ---------------------------------------------------------------------- #


def build_engine(settings: Settings) -> Engine:
    """Load the numerical ports (fixtures; no network) and resolve signing."""
    from research_engine.market.store import load_default_market
    from research_engine.pricing.calc_store import CalculationStore

    key, configured, error = resolve_signing_key(settings)
    pricing, market = load_default_market(calc_store=CalculationStore())
    engine = Engine(
        pricing=pricing,
        market=market,
        settings=settings,
        signing_key=key,
        signing_configured=configured,
        signing_error=error,
    )
    engine.evidence.status = "loading" if settings.evidence_autoload != "off" else "disabled"
    return engine


def load_evidence(engine: Engine, mode: str) -> None:
    """Load (``active``) or bootstrap from fixtures (``fixtures``) the evidence index."""
    from research_engine.evidence.ingest import DB_URL_ENV, EvidenceHome, default_home
    from research_engine.retrieval import load_index, open_default_evidence

    state = engine.evidence
    if mode == "off":
        state.status = "disabled"
        return
    try:
        if mode == "fixtures":
            home, index = open_default_evidence(
                None, include_synthetic=engine.settings.evidence_include_synthetic
            )
            state.attach(home, index)
            return
        root = default_home()
        if not os.environ.get(DB_URL_ENV) and not (Path(root) / "research.sqlite").exists():
            state.status = "unavailable"
            state.error = (
                f"evidence home {root} is not initialized; run an admin ingestion and index "
                "build, or set ML_SERVICE_EVIDENCE_AUTOLOAD=fixtures"
            )
            return
        home = EvidenceHome.open(root)
        state.attach(home)
        active = home.store.active_index_id()
        if not active:
            state.status = "unavailable"
            state.error = "no active READY index build; POST /internal/v1/admin/index-builds"
            return
        state.attach(home, load_index(home.store, active))
    except Exception as exc:  # evidence failures never block numerical endpoints
        log.exception("evidence load failed")
        state.status = "failed"
        state.error = f"{type(exc).__name__}: {exc}"


def warm_curves(engine: Engine) -> None:
    from research_engine.market.admission import build_dataset_admission_report
    from research_engine.market.treasury import default_treasury_dataset

    engine.warmup["curves"] = "building"
    try:
        market = engine.market
        market.build_all()
        report = build_dataset_admission_report(
            default_treasury_dataset(), market.start, market.end, market=market
        )
        engine.warmup["admission"] = report
        engine.warmup["curves"] = "ready"
    except Exception as exc:
        log.exception("curve warm-up failed")
        engine.warmup["curves"] = f"failed:{type(exc).__name__}"


def start_background_loading(engine: Engine) -> threading.Thread:
    settings = engine.settings

    def run() -> None:
        load_evidence(engine, settings.evidence_autoload)
        if settings.warm_curves:
            warm_curves(engine)

    if settings.warm_curves:
        engine.warmup["curves"] = "pending"
    thread = threading.Thread(target=run, name="research-engine-warmup", daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------- #
# Dependencies
# ---------------------------------------------------------------------- #


def get_engine(request: Request) -> Engine:
    """FastAPI dependency (override in tests)."""
    engine = getattr(request.app.state, "research_engine", None)
    if engine is None:
        error = getattr(request.app.state, "research_engine_error", None)
        raise ProblemError(
            503,
            "engine_unavailable",
            error or "the research engine is not initialized",
        )
    return engine
