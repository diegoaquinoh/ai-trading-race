"""Market-data contracts: curve observations, curve specifications and snapshots,
macro vintages, observed quotes and dataset admission (spec 6.1, 7, 8.2).

Rates are decimal annual rates (0.0469 = 4.69%); percentages from sources are
converted at the adapter boundary. Missing source values stay missing: they are
listed in ``missing_tenors`` and never zero-filled or forward-filled.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .common import (
    SCHEMA_VERSION,
    ContentHash,
    ContractModel,
    DataMode,
    DecimalStr,
    InformationPolicy,
    OpaqueId,
    SecurityId,
    SourceId,
    UtcDatetime,
)
from .portfolio import QuoteKind

# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #


class SourceArtifactRef(ContractModel):
    """Immutable raw source bytes the observation was parsed from."""

    artifact_id: OpaqueId
    source_id: SourceId
    uri: str  # retrieval URL (credentials stripped)
    local_path: Optional[str] = None  # path relative to the fixtures root
    sha256: ContentHash
    size_bytes: int = Field(ge=0)
    retrieved_at: UtcDatetime
    license_note: str = ""
    row_ref: Optional[str] = None  # row locator for observation-level references


class TimestampConfidence(str, Enum):
    VERIFIED = "verified"  # publication instant verified against a source record
    RECONSTRUCTED = "reconstructed"  # declared policy applied to a date-only source
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Curve observations
# --------------------------------------------------------------------------- #


class TenorUnit(str, Enum):
    WEEKS = "W"
    MONTHS = "M"
    YEARS = "Y"


class ParYieldPoint(ContractModel):
    tenor: str  # canonical label, e.g. "1M", "6W", "2Y"
    period_count: int = Field(gt=0)
    period_unit: TenorUnit
    par_yield: DecimalStr  # decimal annual rate, bond-equivalent basis


class CurveObservation(ContractModel):
    """One session's published par yields (spec 7.1, 7.2)."""

    schema_version: str = SCHEMA_VERSION
    observation_id: OpaqueId  # content-addressed
    source_id: SourceId
    currency: Literal["USD"] = "USD"
    session_date: date
    observed_at: UtcDatetime  # measurement time (declared convention)
    published_at: Optional[UtcDatetime] = None  # None: historical instant unknown
    available_at: UtcDatetime  # earliest permitted use under information_policy
    ingested_at: UtcDatetime  # when this platform obtained the source bytes
    information_policy: InformationPolicy
    availability_reconstructed: bool
    timestamp_confidence: TimestampConfidence
    quote_basis: Literal["indicative_bid_side_par_yield"] = "indicative_bid_side_par_yield"
    executable: Literal[False] = False  # never an execution quote
    rate_unit: Literal["DECIMAL_ANNUAL_RATE"] = "DECIMAL_ANNUAL_RATE"
    points: list[ParYieldPoint]
    missing_tenors: list[str] = Field(default_factory=list)  # column present, value blank
    source_artifact: SourceArtifactRef
    quality_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _times(self) -> "CurveObservation":
        if self.available_at < self.observed_at:
            raise ValueError("available_at precedes observed_at")
        if self.published_at is not None and self.available_at < self.published_at:
            raise ValueError("available_at precedes published_at")
        tenors = [p.tenor for p in self.points]
        if len(tenors) != len(set(tenors)):
            raise ValueError("duplicate tenor in observation")
        if set(tenors) & set(self.missing_tenors):
            raise ValueError("a tenor cannot be both present and missing")
        return self

    def yield_for(self, tenor: str) -> Optional[DecimalStr]:
        for point in self.points:
            if point.tenor == tenor:
                return point.par_yield
        return None


# --------------------------------------------------------------------------- #
# Curve specification and snapshot
# --------------------------------------------------------------------------- #


class CalibrationInstrumentKind(str, Enum):
    ZERO_COUPON = "zero_coupon"  # single payment at tenor maturity
    PAR_BOND = "par_bond"  # fixed-coupon bullet priced at 100


class CurveInstrumentDefinition(ContractModel):
    tenor: str
    period_count: int
    period_unit: TenorUnit
    kind: CalibrationInstrumentKind
    quote_convention: str  # e.g. "simple_act365f" or "semiannual_par_coupon_act_act_icma"
    day_count: str
    coupon_frequency: Optional[int] = None  # par bonds only
    start: Literal["curve_reference_date"] = "curve_reference_date"
    maturity_rule: str = "reference_date_plus_tenor_following_us_govbond"


class ShortEndTreatment(ContractModel):
    max_zero_coupon_tenor_months: int = 12
    quote_convention: str = "simple_act365f"
    description: str
    anchor: Literal["curve_reference_date_df_1"] = "curve_reference_date_df_1"


class SolverTolerances(ContractModel):
    bootstrap_accuracy: DecimalStr  # QuantLib iterative bootstrap accuracy
    max_iterations: int
    max_abs_price_residual_per_100: DecimalStr  # par bonds
    max_abs_rate_residual: DecimalStr  # zero-coupon instruments, decimal rate


class CurveSpecification(ContractModel):
    schema_version: str = SCHEMA_VERSION
    spec_id: OpaqueId
    version: OpaqueId
    currency: Literal["USD"] = "USD"
    curve_family: Literal["usd_treasury_par_bootstrap"] = "usd_treasury_par_bootstrap"
    input_source_id: SourceId
    reference_date_rule: Literal["session_date"] = "session_date"
    calendar_id: str = "US-GovernmentBond"
    calendar_version: str = "quantlib-1.44"
    time_day_count: Literal["ACT/365F"] = "ACT/365F"  # node time and zero-rate measure
    zero_rate_convention: Literal["continuous_act365f"] = "continuous_act365f"
    short_end_treatment: ShortEndTreatment
    instruments: list[CurveInstrumentDefinition]
    interpolation: Literal["piecewise_linear_log_discount"] = "piecewise_linear_log_discount"
    extrapolation: Literal["reject_beyond_validated_horizon"] = "reject_beyond_validated_horizon"
    monotone_discount_constraint: Literal[False] = False  # negative rates permitted
    required_tenors: list[str]  # tenors whose absence fails the build
    min_nodes: int = 4
    tolerances: SolverTolerances
    engine: str  # bootstrap implementation, e.g. "QuantLib PiecewiseLogLinearDiscount"


class CurveStatus(str, Enum):
    READY = "READY"
    FAILED = "FAILED"


class CurveNode(ContractModel):
    node_date: date
    time_years: DecimalStr  # ACT/365F from the reference date
    discount_factor: DecimalStr
    zero_rate: DecimalStr  # continuous ACT/365F; equals 0 at the reference node
    source_tenor: Optional[str] = None  # None for the reference node


class CalibrationResidual(ContractModel):
    tenor: str
    kind: CalibrationInstrumentKind
    input_quote: DecimalStr  # decimal rate
    model_quote: DecimalStr  # decimal rate implied by the fitted curve
    rate_residual: DecimalStr  # model - input, decimal rate
    price_residual_per_100: Optional[DecimalStr] = None  # par bonds: model price - 100
    within_tolerance: bool


class CurveSnapshot(ContractModel):
    """Content-addressed curve build result (spec 8.2).

    ``curve_snapshot_id`` is derived from the inputs (observation hash, spec,
    engine version, session); ``content_hash`` covers the whole payload except
    itself. ``generated_at`` is intentionally absent so rebuilds are byte-stable.
    """

    schema_version: str = SCHEMA_VERSION
    curve_snapshot_id: OpaqueId
    curve_id: OpaqueId  # logical curve, e.g. "USD-TSY-PAR-BOOTSTRAP"
    version: OpaqueId  # spec version used
    currency: Literal["USD"] = "USD"
    data_mode: DataMode = DataMode.SYNTHETIC_CURVE
    session_date: date
    reference_date: date  # valuation anchor v with D(v, v) = 1
    valuation_at: UtcDatetime  # observation instant the curve describes
    available_at: UtcDatetime  # inherits the latest input availability
    input_observation_ids: list[OpaqueId]
    input_observation_hashes: list[ContentHash]
    specification: CurveSpecification
    status: CurveStatus
    failure_reasons: list[str] = Field(default_factory=list)
    used_tenors: list[str] = Field(default_factory=list)
    excluded_tenors: list[str] = Field(default_factory=list)
    residuals: list[CalibrationResidual] = Field(default_factory=list)
    max_abs_price_residual_per_100: Optional[DecimalStr] = None
    max_abs_rate_residual: Optional[DecimalStr] = None
    nodes: list[CurveNode] = Field(default_factory=list)
    validated_horizon_date: Optional[date] = None  # last node; beyond it D(v,t) is rejected
    engine_version: str
    content_hash: Optional[ContentHash] = None

    @model_validator(mode="after")
    def _status(self) -> "CurveSnapshot":
        if self.status is CurveStatus.READY:
            if self.failure_reasons:
                raise ValueError("READY curve cannot carry failure reasons")
            if len(self.nodes) < 2:
                raise ValueError("READY curve needs nodes")
            for node in self.nodes:
                if node.discount_factor <= 0:
                    raise ValueError("discount factors must be positive")
        elif not self.failure_reasons:
            raise ValueError("FAILED curve must state failure reasons")
        return self

    def hash_payload(self) -> dict:
        wire = self.to_wire()
        wire.pop("contentHash", None)
        return wire


# --------------------------------------------------------------------------- #
# Macro observations and vintages (ALFRED)
# --------------------------------------------------------------------------- #


class MacroObservation(ContractModel):
    series_id: str
    reference_period: date  # economic reference period (not a publication time)
    value: Optional[DecimalStr] = None  # None: source reported missing (".")
    units: str
    realtime_start: date  # first date this value was the current vintage
    realtime_end: date  # last date it was current (9999-12-31 = still current)
    available_at: UtcDatetime  # under the adapter's information policy
    information_policy: str

    @model_validator(mode="after")
    def _realtime(self) -> "MacroObservation":
        if self.realtime_end < self.realtime_start:
            raise ValueError("realtime_end precedes realtime_start")
        return self


class MacroVintage(ContractModel):
    """Observations of one series as they were known at ``known_at``."""

    schema_version: str = SCHEMA_VERSION
    series_id: str
    known_at: UtcDatetime  # information cutoff used for selection
    vintage_realtime_date: date  # cutoff expressed as an ALFRED realtime date
    observations: list[MacroObservation]
    excluded_not_yet_available: int = 0
    source_artifact: Optional[SourceArtifactRef] = None
    content_hash: Optional[ContentHash] = None


# --------------------------------------------------------------------------- #
# Observed security quotes (observed-security mode; gated)
# --------------------------------------------------------------------------- #


class PriceBasis(str, Enum):
    CLEAN = "clean"
    DIRTY = "dirty"


class InstrumentStatus(str, Enum):
    ACTIVE = "active"
    NOT_ISSUED = "not_issued"
    MATURED = "matured"
    SUSPENDED = "suspended"


class ObservedQuote(ContractModel):
    quote_id: OpaqueId
    security_id: SecurityId
    source_id: SourceId
    kind: QuoteKind
    bid_per_100: Optional[DecimalStr] = None
    ask_per_100: Optional[DecimalStr] = None
    mid_per_100: Optional[DecimalStr] = None
    price_unit: Literal["PRICE_PER_100"] = "PRICE_PER_100"
    price_basis: PriceBasis
    currency: str = "USD"
    settlement_date: date
    executable: bool
    instrument_status: InstrumentStatus = InstrumentStatus.ACTIVE
    observed_at: UtcDatetime
    published_at: Optional[UtcDatetime] = None
    available_at: UtcDatetime
    ingested_at: UtcDatetime
    source_artifact: Optional[SourceArtifactRef] = None


class QuoteValidationResult(ContractModel):
    quote_id: OpaqueId
    valid: bool
    reasons: list[str] = Field(default_factory=list)
    stale_age_seconds: Optional[int] = None


class ObservedSecurityAdmission(ContractModel):
    security_id: SecurityId
    admitted: bool
    reasons: list[str] = Field(default_factory=list)
    quote_source_id: Optional[SourceId] = None


# --------------------------------------------------------------------------- #
# Coverage and dataset admission (spec 7.2, 7.3)
# --------------------------------------------------------------------------- #


class TenorCoverage(ContractModel):
    tenor: str
    columns_present_sessions: int  # sessions whose source file had this column
    observed_values: int
    missing_values: int  # column present, value blank


class CoverageReport(ContractModel):
    source_id: SourceId
    start: date
    end: date
    calendar_id: str
    expected_sessions: int  # calendar business days in range
    observed_sessions: int  # expected sessions with an observation
    missing_sessions: list[date] = Field(default_factory=list)
    observations_on_non_business_days: list[date] = Field(default_factory=list)
    tenor_coverage: list[TenorCoverage] = Field(default_factory=list)
    session_coverage_ratio: DecimalStr
    missing_value_ratio: DecimalStr  # blank values / (present columns x sessions)


class ArtifactChecksum(ContractModel):
    artifact_id: OpaqueId
    local_path: str
    expected_sha256: ContentHash
    actual_sha256: Optional[ContentHash] = None
    size_bytes: int
    verified: bool


class CurveBuildSummary(ContractModel):
    sessions_attempted: int
    ready: int
    failed: int
    failed_sessions: list[date] = Field(default_factory=list)
    failure_reason_counts: dict[str, int] = Field(default_factory=dict)
    max_abs_price_residual_per_100: Optional[DecimalStr] = None


class DatasetAdmissionReport(ContractModel):
    """Release gate output; only an eligible dataset may back benchmark reports."""

    schema_version: str = SCHEMA_VERSION
    dataset_id: OpaqueId
    dataset_version: OpaqueId
    market_mode: DataMode
    market_mode_label: str
    coverage: CoverageReport
    missingness: dict[str, str]  # tenor -> missing ratio (decimal string) + notes
    revision_policy: str
    timestamp_confidence: dict[str, str]  # field -> confidence/description
    information_policy: InformationPolicy
    checksum_manifest: list[ArtifactChecksum]
    curve_builds: Optional[CurveBuildSummary] = None
    instrument_universe_id: Optional[OpaqueId] = None
    instrument_universe_hash: Optional[ContentHash] = None
    eligible_for_benchmark: bool
    gate_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    content_hash: Optional[ContentHash] = None
