"""Fixtures for the internal API v1 tests (offline; fixtures only).

One engine (numerical ports + offline Fed evidence index in a temp home) is
built per session and injected through ``app.dependency_overrides[get_engine]``
so the application lifespan does not build a second one.
"""

from __future__ import annotations

import os
from datetime import date, time
from decimal import Decimal

import pytest

os.environ.setdefault("ML_SERVICE_API_KEY", "test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import app  # noqa: E402
from app.v1.engine import Engine, get_engine  # noqa: E402
from research_engine.contracts.portfolio import PortfolioState  # noqa: E402
from research_engine.simulation.clock import ny_instant  # noqa: E402

API_KEY = os.environ["ML_SERVICE_API_KEY"]
SIGNING_KEY = "test-api-v1-signing-key"
CALC_KEY = b"test-api-v1-calc-key"
SESSION = date(2024, 3, 1)  # Friday; next session 2024-03-04
NEXT_SESSION = date(2024, 3, 4)
RUN_ID = "run-api-v1"


def make_settings(**overrides) -> Settings:
    values = dict(
        signing_key=SIGNING_KEY,
        warm_curves=False,
        evidence_autoload="off",
        max_concurrent_decisions=2,
        decision_retry_after_seconds=7,
        strategy_provider="reference",
    )
    values.update(overrides)
    return Settings(**values)


def make_engine(pricing, market, settings=None, *, signing_key=SIGNING_KEY.encode()) -> Engine:
    return Engine(
        pricing=pricing,
        market=market,
        settings=settings or make_settings(),
        signing_key=signing_key,
        signing_configured=signing_key is not None,
        signing_error=None if signing_key is not None else "signing key missing (test)",
    )


@pytest.fixture(scope="session")
def ports():
    from research_engine.market.store import load_default_market
    from research_engine.pricing.calc_store import CalculationStore

    return load_default_market(calc_store=CalculationStore(key=CALC_KEY))


@pytest.fixture(scope="session")
def evidence(tmp_path_factory):
    from research_engine.retrieval import open_default_evidence

    home, index = open_default_evidence(tmp_path_factory.mktemp("evidence-home"))
    return home, index


@pytest.fixture(scope="session")
def engine(ports, evidence) -> Engine:
    pricing, market = ports
    built = make_engine(pricing, market)
    home, index = evidence
    built.evidence.attach(home, index)
    yield built
    built.shutdown()


@pytest.fixture()
def client(engine):
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            test_client.headers.update({"X-API-Key": API_KEY})
            yield test_client
    finally:
        app.dependency_overrides.pop(get_engine, None)


@pytest.fixture()
def client_for():
    """Client bound to an arbitrary engine (signing disabled, other market, ...)."""
    clients = []

    def make(custom_engine: Engine) -> TestClient:
        app.dependency_overrides[get_engine] = lambda: custom_engine
        test_client = TestClient(app)
        test_client.__enter__()
        test_client.headers.update({"X-API-Key": API_KEY})
        clients.append(test_client)
        return test_client

    yield make
    for test_client in clients:
        test_client.__exit__(None, None, None)
    app.dependency_overrides.pop(get_engine, None)


def initial_state(strategy_id: str = "static_ladder") -> PortfolioState:
    return PortfolioState(
        portfolio_id=f"pf-{RUN_ID}-{strategy_id}",
        strategy_id=strategy_id,
        run_id=RUN_ID,
        version=0,
        as_of=ny_instant(SESSION, time(0, 0)),
        cash_usd=Decimal("0"),
    )
