"""Numerical contracts, the synthetic universe fixture, ports and the calculation store."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from research_engine.contracts.calculations import (
    CalculationResult,
    RelativeValueEstimate,
    RelativeValueStatus,
)
from research_engine.contracts.instruments import (
    ExternalIdentifier,
    SecurityEconomics,
    SecurityIdentity,
)
from research_engine.instruments.schedule import InstrumentModel
from research_engine.pricing.calc_store import CalculationStore
from research_engine.simulation.ports import MarketDataPort, PricingPort
from tests.numerical.helpers import TEST_KEY, make_observation, make_terms


def test_economics_rejects_floats_and_bounds():
    with pytest.raises(ValidationError):
        SecurityEconomics(coupon_rate=0.045)
    with pytest.raises(ValidationError):
        SecurityEconomics(coupon_rate=Decimal("4.5"))  # percent, not decimal rate


def test_synthetic_identity_rules():
    terms = make_terms("SYN-USD-NOTE-950", date(2023, 1, 17), date(2025, 1, 15), "0.04")
    with pytest.raises(ValidationError):
        terms.model_validate(
            {**terms.to_wire(), "identity": {**terms.identity.to_wire(), "securityId": "ABC123"}}
        )
    with pytest.raises(ValidationError):
        with_cusip = SecurityIdentity(
            security_id="SYN-USD-NOTE-950",
            classification="synthetic",
            issuer_id="X",
            display_name="x",
            external_identifiers=[ExternalIdentifier(scheme="CUSIP", value="000000000")],
        )
        terms.model_validate({**terms.to_wire(), "identity": with_cusip.to_wire()})


def test_synthetic_universe_fixture_properties(universe):
    secs = universe.securities
    assert universe.universe_id == "synthetic_universe_v1"
    assert 8 <= len(secs) <= 10
    assert "HYPOTHETICAL" in universe.hypothetical_notice
    start, end = date(2023, 1, 1), date(2024, 12, 31)
    terms_years = set()
    for s in secs:
        assert s.security_id.startswith("SYN-USD-NOTE-")
        assert s.identity.external_identifiers == []
        assert s.provenance.validation_status.value == "hypothetical"
        assert "Not an actual security" in s.provenance.notes
        assert s.trading_units.min_face_usd == Decimal(1000)
        assert s.trading_units.face_increment_usd == Decimal(1000)
        assert s.conventions.settlement_lag_business_days == 1
        assert 2020 <= s.dates.original_issue_date.year <= 2024
        terms_years.add(s.dates.maturity_date.year - s.dates.original_issue_date.year)
        assert s.provenance.available_at.date() < s.dates.original_issue_date
    assert terms_years == {2, 5, 10}
    assert any(start <= InstrumentModel(s).final_payment_date <= end for s in secs)
    assert any(start <= s.dates.original_issue_date <= end for s in secs)
    assert any(s.dates.original_issue_date < start for s in secs)


def test_ports_satisfy_protocols(pricing, market):
    assert isinstance(pricing, PricingPort)
    assert isinstance(market, MarketDataPort)
    assert pricing.engine_version.endswith("+quantlib-1.44")
    assert market.data_mode.value == "synthetic_curve"


def test_curve_observation_time_order():
    obs = make_observation(date(2023, 1, 3), {"1M": "4.0"})
    with pytest.raises(ValidationError):
        obs.model_validate({**obs.to_wire(), "availableAt": "2023-01-03T20:00:00Z"})


def test_relative_value_cannot_be_manufactured():
    with pytest.raises(ValidationError):
        RelativeValueEstimate(
            status=RelativeValueStatus.MECHANICALLY_NEUTRAL,
            reason="same curve",
            clean_price_residual_per_100=Decimal("0.1"),
        )


def test_calculation_store_sign_verify_and_tamper(pricing, market, tmp_path):
    session = date(2023, 6, 1)
    curve_id = market.curve_for_session(session).curve_snapshot_id
    price = pricing.price("SYN-USD-NOTE-009", curve_id, date(2023, 6, 2))
    store = pricing.calc_store
    calc = store.get(price.calculation_id)
    assert calc is not None and store.verify(price.calculation_id)
    assert calc.as_of > datetime(2023, 6, 1, tzinfo=timezone.utc)
    assert calc.output("dirty_price_per_100").anchor.value == "settlement"
    assert calc.output("valuation_pv_per_100").anchor.value == "valuation"
    # Re-registering identical content is idempotent (content-addressed id).
    assert store.register(calc).calculation_id == calc.calculation_id
    # A plausible but unknown id is not trusted.
    assert not store.verify("calc-0000000000000000")
    # Tampered payload with the original id/hash/signature fails verification.
    outputs = [o.model_copy(update={"value": Decimal("101")}) for o in calc.outputs]
    assert not store.verify_result(calc.model_copy(update={"outputs": outputs}))
    # A different key cannot validate the signature.
    assert not CalculationStore(key=b"other-key").verify_result(calc)
    # JSONL persistence round trip.
    path = tmp_path / "calcs.jsonl"
    persisted = CalculationStore(key=TEST_KEY, path=path)
    persisted.register(calc)
    reloaded = CalculationStore(key=TEST_KEY, path=path)
    assert reloaded.verify(calc.calculation_id)
    line = json.loads(path.read_text().splitlines()[0])
    assert CalculationResult.model_validate(line) == calc


def test_dev_key_warning(monkeypatch, caplog):
    from research_engine.pricing import calc_store

    monkeypatch.delenv(calc_store.SIGNING_KEY_ENV, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(calc_store, "_warned", False)
    with caplog.at_level("WARNING"):
        key = calc_store.signing_key_from_env()
    assert key == calc_store.DEV_SIGNING_KEY
    assert "development signing key" in caplog.text
    monkeypatch.setenv(calc_store.SIGNING_KEY_ENV, "prod-key")
    assert calc_store.signing_key_from_env() == b"prod-key"


def test_public_dev_key_is_never_used_outside_development(monkeypatch, caplog):
    from research_engine.pricing import calc_store

    monkeypatch.delenv(calc_store.SIGNING_KEY_ENV, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(calc_store, "_warned", False)
    monkeypatch.setattr(calc_store, "_process_key", None)
    with caplog.at_level("WARNING"):
        key = calc_store.signing_key_from_env()
    assert key != calc_store.DEV_SIGNING_KEY
    assert len(key) == 32
    assert "random per-process key" in caplog.text
    # Stable within the process, so separate stores verify each other's results.
    assert calc_store.signing_key_from_env() == key
    assert calc_store.CalculationStore()._key == key
    monkeypatch.setenv(calc_store.SIGNING_KEY_ENV, "prod-key")
    assert calc_store.signing_key_from_env() == b"prod-key"


def test_cli_registers_numerical_commands(capsys):
    from research_engine.cli.main import build_parser, main

    parser = build_parser()
    args = parser.parse_args(["price", "--security", "SYN-USD-NOTE-009", "--date", "2023-06-01"])
    assert args.func.__name__ == "cmd_price"
    assert main(["curve", "build", "--date", "2023-06-01"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "READY" and out["sessionDate"] == "2023-06-01"
    assert (
        main(
            [
                "scenario",
                "--security",
                "SYN-USD-NOTE-007",
                "--date",
                "2023-06-01",
                "--scenario",
                "steepener_v1",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["scenarioId"] == "steepener_v1"
