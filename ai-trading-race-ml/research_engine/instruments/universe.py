"""Instrument universe fixtures.

``synthetic_universe_v1`` holds ten *hypothetical* notes (internal IDs
``SYN-USD-NOTE-001``..``010``). They are clearly labelled synthetic, carry no
external identifiers and must not be presented as actual Treasury securities.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from research_engine.contracts.common import sha256_bytes
from research_engine.contracts.instruments import InstrumentUniverse
from research_engine.market.paths import instruments_fixture_dir
from research_engine.simulation.ports import InstrumentInfo

from .schedule import InstrumentModel

DEFAULT_UNIVERSE_ID = "synthetic_universe_v1"


def universe_path(universe_id: str = DEFAULT_UNIVERSE_ID, root: Optional[Path] = None) -> Path:
    return (root or instruments_fixture_dir()) / f"{universe_id}.json"


@lru_cache(maxsize=8)
def _load(path: str) -> InstrumentUniverse:
    return InstrumentUniverse.model_validate(json.loads(Path(path).read_text()))


def load_universe(
    universe_id: str = DEFAULT_UNIVERSE_ID, root: Optional[Path] = None
) -> InstrumentUniverse:
    return _load(str(universe_path(universe_id, root)))


def universe_artifact_checksum(universe_id: str = DEFAULT_UNIVERSE_ID) -> str:
    return sha256_bytes(universe_path(universe_id).read_bytes())


def instrument_info(model: InstrumentModel) -> InstrumentInfo:
    terms = model.terms
    return InstrumentInfo(
        security_id=terms.security_id,
        synthetic=terms.identity.classification.value == "synthetic",
        coupon_rate=terms.economics.coupon_rate,
        coupon_frequency=terms.economics.coupon_frequency,
        issue_date=terms.dates.original_issue_date,
        dated_date=terms.dates.dated_date,
        maturity_date=terms.dates.maturity_date,
        settlement_lag_business_days=terms.conventions.settlement_lag_business_days,
        min_face_usd=terms.trading_units.min_face_usd,
        face_increment_usd=terms.trading_units.face_increment_usd,
        calendar_id=terms.conventions.calendar_id,
        day_count=terms.conventions.day_count.value,
        terms_version=terms.terms_version,
    )


def outstanding(models: list[InstrumentModel], as_of: date) -> list[InstrumentModel]:
    """Issued on/before ``as_of`` and final payment date after ``as_of``."""
    return [m for m in models if m.is_outstanding(as_of)]
