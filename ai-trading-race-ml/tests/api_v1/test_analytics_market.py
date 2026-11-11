"""Analytics price, market sessions, curves and instruments."""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from research_engine.contracts.common import utc_to_str

from .conftest import NEXT_SESSION, SESSION, make_engine
from .helpers import market_ref, post_json, session_row


def price_request(client, **overrides):
    body = {
        "schemaVersion": "1.0",
        "requestId": "price-1",
        "curveSnapshotId": market_ref(client, SESSION)["curveSnapshotId"],
        "valuationDate": SESSION.isoformat(),
        "securityIds": ["SYN-USD-NOTE-003", "SYN-USD-NOTE-006"],
    }
    body.update(overrides)
    return body


def test_price_batch_returns_signed_calculations(client, engine):
    response = post_json(
        client, "/internal/v1/analytics/price", price_request(client, faceUsd="250000")
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["priceType"] == "curve_model" and body["marketQuote"] is False
    assert len(body["items"]) == 2
    for item in body["items"]:
        clean, accrued, dirty = (
            Decimal(item[k]) for k in ("cleanPricePer100", "accruedPer100", "dirtyPricePer100")
        )
        assert clean + accrued == dirty
        assert item["position"]["faceUsd"] == "250000"
    for calc in body["calculations"]:
        assert engine.calc_store.verify(calc["calculationId"])
    assert set(body["calculationIds"]) == {c["calculationId"] for c in body["calculations"]}


def test_price_validation(client):
    path = "/internal/v1/analytics/price"
    assert (
        post_json(client, path, price_request(client, requestId="p2", faceUsd=100.5)).status_code
        == 422
    )
    response = post_json(
        client, path, price_request(client, requestId="p3", valuationDate="2024-03-04")
    )
    assert response.status_code == 422 and response.json()["code"] == "valuation_date_mismatch"
    response = post_json(
        client, path, price_request(client, requestId="p4", curveSnapshotId="curve-nope")
    )
    assert response.status_code == 404
    response = post_json(
        client, path, price_request(client, requestId="p5", securityIds=["SYN-USD-NOTE-999"])
    )
    assert response.status_code == 404
    # requestId reuse with a different payload is an idempotency conflict.
    assert post_json(client, path, price_request(client, requestId="p6")).status_code == 200
    response = post_json(
        client, path, price_request(client, requestId="p6", securityIds=["SYN-USD-NOTE-001"])
    )
    assert response.status_code == 409 and response.json()["code"] == "idempotency_key_reused"


def test_concurrent_prices_match_sequential(client):
    """Interleaved requests on different curves give the sequential answers."""
    days = [SESSION, NEXT_SESSION]
    curves = {d: market_ref(client, d)["curveSnapshotId"] for d in days}

    def body(day, n):
        return price_request(
            client,
            requestId=f"conc-{day}-{n}",
            curveSnapshotId=curves[day],
            valuationDate=day.isoformat(),
        )

    expected = {
        d: [
            i["dirtyPricePer100"]
            for i in post_json(client, "/internal/v1/analytics/price", body(d, "seq")).json()[
                "items"
            ]
        ]
        for d in days
    }
    results = []

    def worker(day, n):
        items = post_json(client, "/internal/v1/analytics/price", body(day, n)).json()["items"]
        results.append((day, [i["dirtyPricePer100"] for i in items]))

    threads = [threading.Thread(target=worker, args=(days[i % 2], i)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 8
    for day, dirty in results:
        assert dirty == expected[day]


def test_sessions_never_available_before_available_at(client):
    response = client.get(
        "/internal/v1/market/sessions", params={"start": "2024-01-01", "end": "2024-03-31"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dataMode"] == "synthetic_curve"
    assert body["universeVersion"] == "synthetic_universe_v1.0"
    assert body["sessions"]
    for row in body["sessions"]:
        assert row["decisionAsOf"].endswith("Z")
        if not row["gap"]:
            assert row["curveStatus"] == "READY"
            assert row["availableAt"] <= row["decisionAsOf"]
            assert row["marketSnapshotId"] and row["marketSnapshotHash"].startswith("sha256:")
            assert row["executionObservationAt"] > row["decisionAsOf"]
        else:
            assert row["gapReason"] and row["marketSnapshotId"] is None
    # 19:00 America/New_York: EST in January, EDT in late March.
    first = session_row(client, date(2024, 1, 2))
    assert first["decisionAsOf"] == "2024-01-03T00:00:00Z"
    late = session_row(client, date(2024, 3, 28))
    assert late["decisionAsOf"] == "2024-03-28T23:00:00Z"


def test_late_curve_is_flagged_as_gap(ports, client_for):
    """A curve whose availableAt is after 19:00 New York is not usable that session."""
    from research_engine.market.store import CurveMarketDataPort
    from research_engine.market.treasury import default_treasury_dataset
    from research_engine.pricing.calc_store import CalculationStore
    from research_engine.pricing.port import QuantLibPricingPort

    pricing, market = ports
    observations = dict(default_treasury_dataset().observations)
    late = observations[SESSION]
    observations[SESSION] = late.model_copy(
        update={"available_at": late.available_at + timedelta(hours=3)}
    )
    late_market = CurveMarketDataPort(
        observations, market.universe_contract, start=date(2024, 2, 1), end=date(2024, 3, 29)
    )
    late_pricing = QuantLibPricingPort(
        market.universe_contract, late_market, calc_store=CalculationStore(key=b"late")
    )
    engine = make_engine(late_pricing, late_market)
    client = client_for(engine)
    row = session_row(client, SESSION)
    assert row["gap"] is True
    assert row["gapReason"] == "curve_not_available_by_decision_time"
    assert row["marketSnapshotId"] is None
    assert row["availableAt"] > row["decisionAsOf"]
    assert session_row(client, NEXT_SESSION)["gap"] is False
    engine.shutdown()


def test_sessions_validation(client):
    assert (
        client.get(
            "/internal/v1/market/sessions", params={"start": "2024-03-08", "end": "2024-03-01"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/internal/v1/market/sessions", params={"start": "03/01/2024", "end": "2024-03-01"}
        ).status_code
        == 422
    )
    assert (
        client.get("/internal/v1/market/sessions", params={"start": "2024-03-01"}).status_code
        == 422
    )


def test_curve_document(client):
    curve_id = market_ref(client, SESSION)["curveSnapshotId"]
    response = client.get(f"/internal/v1/curves/{curve_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["curveSnapshotId"] == curve_id
    assert body["nodes"] and body["specification"]["specId"]
    assert body["inputs"] and body["inputs"][0]["sessionDate"] == SESSION.isoformat()
    assert body["diagnostics"]["status"] == "READY"
    assert body["labels"]["executable"] is False
    assert client.get("/internal/v1/curves/curve-doesnotexist").status_code == 404


def test_instrument_list_is_point_in_time_and_paged(client):
    everything = client.get("/internal/v1/instruments").json()
    assert everything["total"] == 10 and everything["classification"] == "synthetic"
    early = client.get("/internal/v1/instruments", params={"asOf": "2023-01-03"}).json()
    assert early["total"] <= everything["total"]
    for item in early["items"]:
        assert item["terms"]["dates"]["originalIssueDate"] <= "2023-01-03"
        assert item["status"] in ("outstanding", "matured")
    paged = client.get("/internal/v1/instruments", params={"page": 2, "pageSize": 3}).json()
    assert len(paged["items"]) == 3 and paged["page"] == 2
    one = client.get("/internal/v1/instruments", params={"securityId": "SYN-USD-NOTE-004"}).json()
    assert [i["securityId"] for i in one["items"]] == ["SYN-USD-NOTE-004"]
    assert (
        client.get("/internal/v1/instruments", params={"universeVersion": "other"}).status_code
        == 404
    )
    assert client.get("/internal/v1/instruments", params={"pageSize": 0}).status_code == 422


def test_instrument_valuation_labels_synthetic_prices(client):
    response = client.get(
        "/internal/v1/instruments/SYN-USD-NOTE-003/valuation", params={"date": SESSION.isoformat()}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["synthetic"] is True
    assert body["price"]["priceType"] == "curve_model"
    assert body["price"]["marketQuote"] is False
    assert body["relativeValue"]["status"] == "unavailable_synthetic_same_curve"
    assert body["yieldToMaturity"] is not None
    assert body["dv01"]["parallelDv01Usd"] and len(body["dv01"]["keyRateDv01"]) == 5
    assert {s["scenarioId"] for s in body["scenarios"]} >= {"parallel_up_25", "parallel_down_100"}
    assert all(s["priceType"] == "curve_model" for s in body["scenarios"])
    assert all(cf["paymentDate"] > body["valuationDate"] for cf in body["upcomingCashFlows"])
    assert body["curveAvailableAt"] <= utc_to_str(datetime(2024, 3, 2, 0, 0, tzinfo=timezone.utc))
    assert body["provenance"]["validationStatus"] == "hypothetical"


def test_instrument_valuation_uses_latest_available_curve(client):
    weekend = client.get(
        "/internal/v1/instruments/SYN-USD-NOTE-003/valuation", params={"date": "2024-03-02"}
    ).json()
    assert weekend["curveSessionDate"] == SESSION.isoformat() and weekend["curveStale"] is True
    assert (
        client.get(
            "/internal/v1/instruments/SYN-USD-NOTE-999/valuation", params={"date": "2024-03-01"}
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/internal/v1/instruments/SYN-USD-NOTE-003/valuation", params={"date": "2020-01-01"}
        ).status_code
        == 404
    )
