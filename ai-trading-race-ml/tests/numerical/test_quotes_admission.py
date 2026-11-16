"""Observed-quote validation, observed-security gate and dataset release gate."""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from research_engine.contracts.market import InstrumentStatus, ObservedQuote, PriceBasis
from research_engine.contracts.portfolio import QuoteKind
from research_engine.market.admission import build_dataset_admission_report, coverage_report
from research_engine.market.paths import treasury_fixture_dir
from research_engine.market.quotes import admit_observed_security, validate_observed_quote
from research_engine.market.treasury import default_treasury_dataset

OBS = datetime(2023, 3, 15, 20, 0, tzinfo=timezone.utc)


def quote(**overrides) -> ObservedQuote:
    base = dict(
        quote_id="q-1",
        security_id="SYN-USD-NOTE-009",
        source_id="test-licensed-feed",
        kind=QuoteKind.OBSERVED_MID,
        bid_per_100=Decimal("87.60"),
        ask_per_100=Decimal("87.64"),
        mid_per_100=Decimal("87.62"),
        price_basis=PriceBasis.CLEAN,
        settlement_date=date(2023, 3, 16),
        executable=False,
        observed_at=OBS,
        published_at=OBS + timedelta(minutes=5),
        available_at=OBS + timedelta(minutes=10),
        ingested_at=OBS + timedelta(minutes=11),
    )
    base.update(overrides)
    return ObservedQuote(**base)


AS_OF = OBS + timedelta(hours=3)


def test_valid_quote(universe):
    result = validate_observed_quote(quote(), as_of=AS_OF, terms=universe.get("SYN-USD-NOTE-009"))
    assert result.valid, result.reasons


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"bid_per_100": Decimal("87.70")}, "crossed_market:bid_above_ask"),
        ({"mid_per_100": Decimal("87.70")}, "mid_inconsistent_with_bid_ask"),
        ({"currency": "EUR"}, "currency_mismatch:EUR"),
        ({"instrument_status": InstrumentStatus.SUSPENDED}, "instrument_status:suspended"),
        ({"mid_per_100": None, "kind": QuoteKind.OBSERVED_MID}, "missing_mid_for_observed_mid"),
        ({"bid_per_100": Decimal("8762"), "ask_per_100": None, "mid_per_100": None}, None),
        ({"kind": QuoteKind.SYNTHETIC_MODEL}, "synthetic_model_price_is_not_an_observed_quote"),
        (
            {"kind": QuoteKind.OBSERVED_INDICATIVE, "executable": True},
            "indicative_quote_marked_executable",
        ),
        (
            {"available_at": OBS - timedelta(minutes=1)},
            "timestamp_order:available_before_observed",
        ),
        ({"ingested_at": OBS - timedelta(minutes=1)}, "timestamp_order:ingested_before_observed"),
        ({"settlement_date": date(2023, 3, 14)}, "settlement_before_observation"),
        ({"settlement_date": date(2033, 1, 3)}, "settlement_outside_instrument_life"),
    ],
)
def test_invalid_quotes_have_explicit_reasons(universe, overrides, reason):
    result = validate_observed_quote(
        quote(**overrides), as_of=AS_OF, terms=universe.get("SYN-USD-NOTE-009")
    )
    assert not result.valid
    if reason is None:  # scale error (price quoted per 10,000 instead of per 100)
        assert "price_scale_out_of_range:bid" in result.reasons
    else:
        assert reason in result.reasons


def test_stale_and_not_yet_available():
    stale = validate_observed_quote(quote(), as_of=OBS + timedelta(days=5))
    assert "stale_quote" in stale.reasons
    early = validate_observed_quote(quote(), as_of=OBS + timedelta(minutes=5))
    assert "not_yet_available" in early.reasons


def test_observed_security_admission_closed_without_licensed_source(universe):
    decision = admit_observed_security(universe.get("SYN-USD-NOTE-001"))
    assert not decision.admitted
    assert "no_licensed_quote_source_configured" in decision.reasons
    assert "synthetic_instrument_not_eligible_for_observed_mode" in decision.reasons
    other = admit_observed_security(universe.get("SYN-USD-NOTE-001"), quote_source_id="vendor-x")
    assert "quote_source_not_licensed:vendor-x" in other.reasons


def test_dataset_admission_report_on_fixtures(market):
    dataset = default_treasury_dataset()
    report = build_dataset_admission_report(
        dataset, date(2023, 1, 1), date(2024, 12, 31), market=market
    )
    assert report.eligible_for_benchmark, report.gate_failures
    assert report.market_mode.value == "synthetic_curve"
    assert "SYNTHETIC" in report.market_mode_label
    assert report.coverage.expected_sessions == 500 == report.coverage.observed_sessions
    assert report.coverage.session_coverage_ratio == Decimal("1")
    assert all(c.verified for c in report.checksum_manifest) and len(report.checksum_manifest) == 2
    assert report.curve_builds.ready == 500 and report.curve_builds.failed == 0
    assert "reconstructed" in report.timestamp_confidence["available_at"]
    assert report.revision_policy
    assert report.instrument_universe_id == "synthetic_universe_v1"
    assert report.content_hash.startswith("sha256:")


def test_admission_gate_fails_on_coverage_and_checksum(tmp_path, market):
    dataset = default_treasury_dataset()
    thin = {d: o for i, (d, o) in enumerate(dataset.observations.items()) if i % 10}
    cov = coverage_report(thin, date(2023, 1, 1), date(2024, 12, 31))
    assert cov.observed_sessions == 450 and len(cov.missing_sessions) == 50
    shutil.copytree(treasury_fixture_dir(), tmp_path / "t")
    (tmp_path / "t" / "daily_treasury_par_yield_curve_2023.csv").write_bytes(b"Date\n")
    thin_ds = type(dataset)(thin, dataset.artifacts, {}, [], [])
    report = build_dataset_admission_report(
        thin_ds, date(2023, 1, 1), date(2024, 12, 31), root=tmp_path / "t"
    )
    assert not report.eligible_for_benchmark
    assert any(f.startswith("session_coverage") for f in report.gate_failures)
    assert any(f.startswith("checksum_mismatch") for f in report.gate_failures)
    assert "curve_builds_not_evaluated" in report.gate_failures
