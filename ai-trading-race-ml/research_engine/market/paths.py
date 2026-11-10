"""Fixture locations for the numerical core.

``RESEARCH_FIXTURES_DIR`` overrides the default ``ai-trading-race-ml/fixtures``.
"""

from __future__ import annotations

import os
from pathlib import Path


def fixtures_root() -> Path:
    override = os.environ.get("RESEARCH_FIXTURES_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "fixtures"


def treasury_fixture_dir() -> Path:
    return fixtures_root() / "market" / "treasury"


def fred_fixture_dir() -> Path:
    return fixtures_root() / "market" / "fred"


def instruments_fixture_dir() -> Path:
    return fixtures_root() / "instruments"
