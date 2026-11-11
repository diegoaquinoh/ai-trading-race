"""Shared fixtures for numerical-core tests.

Oracles in these tests are hand-worked closed forms (flat continuously
compounded curves, explicit schedule arithmetic), not the QuantLib wrapper
calling itself.
"""

from __future__ import annotations

import pytest

from research_engine.instruments.universe import load_universe
from research_engine.market.store import load_default_market
from research_engine.pricing.calc_store import CalculationStore
from research_engine.pricing.curve_model import InMemoryCurveSource
from research_engine.pricing.port import QuantLibPricingPort
from tests.numerical.helpers import TEST_KEY, flat_snapshot


@pytest.fixture(scope="session")
def ports():
    return load_default_market(calc_store=CalculationStore(key=TEST_KEY))


@pytest.fixture(scope="session")
def pricing(ports):
    return ports[0]


@pytest.fixture(scope="session")
def market(ports):
    return ports[1]


@pytest.fixture(scope="session")
def universe():
    return load_universe()


@pytest.fixture()
def flat_pricing(universe):
    """(pricing port, snapshot id, rate) over a flat 4% continuous curve at FLAT_REF."""
    snap = flat_snapshot()
    port = QuantLibPricingPort(
        universe, InMemoryCurveSource([snap]), CalculationStore(key=TEST_KEY)
    )
    return port, snap.curve_snapshot_id, 0.04
