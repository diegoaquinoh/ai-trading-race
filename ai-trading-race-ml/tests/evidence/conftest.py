"""Shared offline evidence fixtures: one corpus per session, no network, no Neo4j."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from research_engine.evidence.ingest import EvidenceHome, FedIngestor
from research_engine.knowledge.graph_store import InMemoryGraphStore
from research_engine.retrieval.index import activate_index, build_index, load_index


class TickClock:
    """Deterministic operational clock: every call advances one second."""

    def __init__(self, start: datetime = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)):
        self.now = start

    def __call__(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def clock() -> TickClock:
    return TickClock()


@pytest.fixture(scope="session")
def home(tmp_path_factory, clock) -> EvidenceHome:
    evidence_home = EvidenceHome.open(tmp_path_factory.mktemp("evidence-home"))
    report = FedIngestor(evidence_home, offline=True, clock=clock).run(include_synthetic=True)
    assert report.fetch_run.outcome.value == "success", report
    assert len(report.new_version_ids) == 33  # 32 Fed documents + 1 synthetic correction
    return evidence_home


@pytest.fixture(scope="session")
def graph() -> InMemoryGraphStore:
    return InMemoryGraphStore()


@pytest.fixture(scope="session")
def default_index(home, graph, clock):
    """Default agent index: real Fed documents only (no synthetic correction)."""
    build = build_index(home.store, graph, include_synthetic=False, clock=clock)
    assert build.status.value == "READY", build.error
    activate_index(home.store, build.build_id, clock)
    return load_index(home.store, build.build_id, graph=graph)


@pytest.fixture(scope="session")
def synthetic_index(home, graph, clock):
    """Benchmark/test index including the labelled synthetic correction."""
    build = build_index(home.store, graph, include_synthetic=True, clock=clock)
    assert build.status.value == "READY", build.error
    return load_index(home.store, build.build_id, graph=graph)
