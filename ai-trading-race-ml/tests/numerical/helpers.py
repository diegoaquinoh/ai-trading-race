"""Test helpers: hand-built curves, terms and observations (no fixtures)."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from research_engine.contracts.common import InformationPolicy, content_hash
from research_engine.contracts.instruments import (
    InstrumentClassification,
    SecurityDates,
    SecurityEconomics,
    SecurityIdentity,
    SecurityTerms,
    TermsProvenance,
    ValidationStatus,
)
from research_engine.contracts.market import (
    CurveNode,
    CurveObservation,
    CurveSnapshot,
    CurveStatus,
    ParYieldPoint,
    SourceArtifactRef,
    TenorUnit,
    TimestampConfidence,
)
from research_engine.market.curves import DEFAULT_CURVE_SPEC
from research_engine.pricing.quantlib_env import ENGINE_VERSION

TEST_KEY = b"numerical-test-signing-key"
FLAT_REF = date(2023, 3, 15)


def flat_node_dates(reference: date, years: int = 31) -> list[date]:
    return [reference] + [
        date(reference.year + k, reference.month, min(reference.day, 28))
        for k in range(1, years + 1)
    ]


def flat_snapshot(reference: date = FLAT_REF, rate: float = 0.04, years: int = 31) -> CurveSnapshot:
    """READY snapshot of a flat continuous ACT/365F curve: D(t) = exp(-r * days/365)."""
    nodes = []
    for d in flat_node_dates(reference, years):
        t = (d - reference).days / 365.0
        nodes.append(
            CurveNode(
                node_date=d,
                time_years=Decimal(repr(t)).quantize(Decimal("1e-12")),
                discount_factor=Decimal(repr(math.exp(-rate * t))),
                zero_rate=Decimal(repr(rate if t else 0.0)),
            )
        )
    obs_time = datetime.combine(reference, time(20, 30), tzinfo=timezone.utc)
    snap = CurveSnapshot(
        curve_snapshot_id=f"curve-flat-{reference.isoformat()}-{rate}",
        curve_id="TEST-FLAT",
        version="test",
        session_date=reference,
        reference_date=reference,
        valuation_at=obs_time,
        available_at=obs_time + timedelta(hours=2, minutes=30),
        input_observation_ids=["test-flat"],
        input_observation_hashes=["sha256:" + "0" * 64],
        specification=DEFAULT_CURVE_SPEC,
        status=CurveStatus.READY,
        nodes=nodes,
        validated_horizon_date=nodes[-1].node_date,
        engine_version=ENGINE_VERSION,
    )
    return snap.model_copy(update={"content_hash": content_hash(snap.hash_payload())})


def make_terms(
    security_id: str,
    dated: date,
    maturity: date,
    coupon: str,
    *,
    first_coupon: date | None = None,
) -> SecurityTerms:
    return SecurityTerms(
        terms_version=f"{security_id}-test",
        terms_effective_from=dated - timedelta(days=7),
        identity=SecurityIdentity(
            security_id=security_id,
            classification=InstrumentClassification.SYNTHETIC,
            issuer_id="TEST",
            display_name=f"test {security_id}",
        ),
        economics=SecurityEconomics(coupon_rate=Decimal(coupon)),
        dates=SecurityDates(
            original_issue_date=dated,
            dated_date=dated,
            maturity_date=maturity,
            first_coupon_date=first_coupon,
        ),
        provenance=TermsProvenance(
            source_id="test",
            source_artifact="tests",
            available_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            validation_status=ValidationStatus.HYPOTHETICAL,
        ),
    )


def make_observation(
    session: date, yields_pct: dict[str, str], *, missing: tuple[str, ...] = ()
) -> CurveObservation:
    units = {"W": TenorUnit.WEEKS, "M": TenorUnit.MONTHS, "Y": TenorUnit.YEARS}
    points = [
        ParYieldPoint(
            tenor=t,
            period_count=int(t[:-1]),
            period_unit=units[t[-1]],
            par_yield=Decimal(v) / 100,
        )
        for t, v in yields_pct.items()
    ]
    observed = datetime.combine(session, time(20, 30), tzinfo=timezone.utc)
    return CurveObservation(
        observation_id=f"test-obs-{session.isoformat()}-{content_hash(yields_pct)[7:15]}",
        source_id="test-source",
        session_date=session,
        observed_at=observed,
        available_at=observed + timedelta(hours=2, minutes=30),
        ingested_at=observed + timedelta(days=1),
        information_policy=InformationPolicy.RECONSTRUCTED_PUBLICATION_PLUS_LAG,
        availability_reconstructed=True,
        timestamp_confidence=TimestampConfidence.RECONSTRUCTED,
        points=points,
        missing_tenors=list(missing),
        source_artifact=SourceArtifactRef(
            artifact_id="test-artifact",
            source_id="test-source",
            uri="test://",
            sha256="sha256:" + "1" * 64,
            size_bytes=0,
            retrieved_at=observed + timedelta(days=1),
        ),
    )
