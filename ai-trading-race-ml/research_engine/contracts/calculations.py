"""Calculation, risk and scenario result contracts (spec 8.4, 8.5, 8.6, 14.5).

A ``CalculationResult`` is a content-addressed, HMAC-signed engine output. A
model-supplied calculation id is only trusted after the calculation store
resolves and verifies it (spec 14.7).

Units are explicit on every value: ``basis`` distinguishes per-100-face prices
from face-scaled USD amounts so portfolio aggregation never double-scales face.
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
    OpaqueId,
    SecurityId,
    Unit,
    UtcDatetime,
)


class CalculationType(str, Enum):
    PRICE = "price"  # settlement-anchored per-100 price
    POSITION_VALUATION = "position_valuation"  # valuation-date PV, face-scaled
    YIELD_CONVERSION = "yield_conversion"  # price <-> yield quote conversion
    RISK = "risk"  # DV01, key-rate, durations
    SCENARIO = "scenario"  # full-repricing scenario
    PORTFOLIO_RISK = "portfolio_risk"
    MARKET_FEATURES = "market_features"  # curve levels/changes + numerical macro values


class Completeness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"  # some outputs unavailable; see diagnostics
    UNAVAILABLE = "unavailable"


class ValueBasis(str, Enum):
    PER_100_FACE = "per_100_face"
    FACE_SCALED = "face_scaled"  # already multiplied by face/100
    UNSCALED = "unscaled"  # rates, durations, ratios


class Anchor(str, Enum):
    SETTLEMENT = "settlement"  # values at settlement date s: D(v,t)/D(v,s)
    VALUATION = "valuation"  # values at valuation date v: D(v,t)
    NONE = "none"


class CalculatedValue(ContractModel):
    name: str
    value: Optional[DecimalStr] = None  # None: unavailable (see diagnostics)
    unit: Unit
    basis: ValueBasis
    anchor: Anchor = Anchor.NONE
    anchor_date: Optional[date] = None
    definition: str = ""


class EngineProvenance(ContractModel):
    engine_name: str = "research_engine.numerical"
    engine_version: str
    library: str  # e.g. "QuantLib 1.44"
    conventions_version: str  # e.g. "usd-treasury-conventions-v1"


class CalculationResult(ContractModel):
    """Signed numerical output.

    ``calculation_id`` = ``calc-<16 hex>`` over the payload without id, hash and
    signature; ``content_hash`` = sha256 over the canonical wire form without
    ``contentHash`` and ``signature``; ``signature`` = HMAC-SHA256 over that hash.
    """

    schema_version: str = SCHEMA_VERSION
    calculation_id: Optional[OpaqueId] = None
    calculation_type: CalculationType
    calculation_version: str
    data_mode: DataMode = DataMode.SYNTHETIC_CURVE
    security_id: Optional[SecurityId] = None
    curve_snapshot_id: Optional[OpaqueId] = None
    input_hashes: dict[str, str]
    as_of: UtcDatetime  # information time: availability of the latest input
    valuation_date: Optional[date] = None
    settlement_date: Optional[date] = None
    face_usd: Optional[DecimalStr] = None
    outputs: list[CalculatedValue]
    completeness: Completeness
    diagnostics: list[str] = Field(default_factory=list)
    tolerances: dict[str, str] = Field(default_factory=dict)
    engine: EngineProvenance
    content_hash: Optional[ContentHash] = None
    signature: Optional[str] = None

    def id_payload(self) -> dict:
        wire = self.to_wire()
        for key in ("calculationId", "contentHash", "signature"):
            wire.pop(key, None)
        return wire

    def hash_payload(self) -> dict:
        wire = self.to_wire()
        wire.pop("contentHash", None)
        wire.pop("signature", None)
        return wire

    def output(self, name: str) -> CalculatedValue:
        for item in self.outputs:
            if item.name == name:
                return item
        raise KeyError(name)


# --------------------------------------------------------------------------- #
# Relative value (spec 8.4)
# --------------------------------------------------------------------------- #


class RelativeValueStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    MECHANICALLY_NEUTRAL = "mechanically_neutral"


class RelativeValueEstimate(ContractModel):
    status: RelativeValueStatus
    reference_model: Optional[str] = None
    clean_price_residual_per_100: Optional[DecimalStr] = None
    yield_residual: Optional[DecimalStr] = None
    reason: str

    @model_validator(mode="after")
    def _values(self) -> "RelativeValueEstimate":
        if self.status is not RelativeValueStatus.AVAILABLE and (
            self.clean_price_residual_per_100 is not None or self.yield_residual is not None
        ):
            raise ValueError("unavailable/neutral relative value must not carry residuals")
        return self


SYNTHETIC_RELATIVE_VALUE = RelativeValueEstimate(
    status=RelativeValueStatus.MECHANICALLY_NEUTRAL,
    reference_model="same curve and model as execution marks",
    reason=(
        "synthetic same-curve mode: execution marks and the valuation benchmark use the "
        "same curve and model, so any rich/cheap difference is identically zero and is "
        "not a relative-value signal (spec 3.2, 8.4)"
    ),
)


# --------------------------------------------------------------------------- #
# Scenarios (spec 8.6)
# --------------------------------------------------------------------------- #


class ScenarioNodeShift(ContractModel):
    tenor_years: DecimalStr
    shift_bp: DecimalStr


class ScenarioDefinition(ContractModel):
    scenario_id: str
    library_version: str
    description: str
    kind: Literal["parallel", "piecewise_linear_tenor"]
    parallel_shift_bp: Optional[DecimalStr] = None
    node_shifts: list[ScenarioNodeShift] = Field(default_factory=list)
    applies_to: Literal["zero_rate_curve_nodes_continuous_act365f"] = (
        "zero_rate_curve_nodes_continuous_act365f"
    )
    interpolation_between_nodes: Literal["linear_in_time"] = "linear_in_time"
    outside_nodes: Literal["flat_extension_of_nearest_node"] = "flat_extension_of_nearest_node"
    valuation_horizon: Literal["instantaneous_at_valuation_date"] = (
        "instantaneous_at_valuation_date"
    )
    settlement_treatment: Literal["valuation_date_pv_no_settlement_lag"] = (
        "valuation_date_pv_no_settlement_lag"
    )
    holdings_fixed: Literal[True] = True
    hypothetical: Literal[True] = True  # not a calibrated forecast


class ScenarioResult(ContractModel):
    scenario_id: str
    library_version: str
    curve_snapshot_id: OpaqueId
    valuation_date: date
    security_id: Optional[SecurityId] = None  # None = portfolio
    face_usd: Optional[DecimalStr] = None
    base_pv_usd: DecimalStr
    scenario_pv_usd: DecimalStr
    pnl_usd: DecimalStr  # authoritative full repricing
    dv01_approx_pnl_usd: DecimalStr  # first order from parallel or key-rate DV01
    dv01_approx_error_usd: DecimalStr  # approx - full
    convexity_approx_pnl_usd: Optional[DecimalStr] = None  # parallel scenarios only
    convexity_approx_error_usd: Optional[DecimalStr] = None
    approximation_method: str
    calculation_id: Optional[OpaqueId] = None


# --------------------------------------------------------------------------- #
# Risk report (spec 8.5)
# --------------------------------------------------------------------------- #


class KeyRateExposure(ContractModel):
    key_tenor_years: DecimalStr
    dv01_usd: DecimalStr  # positive = gain for 1bp downward bump at this key


class PositionRisk(ContractModel):
    security_id: SecurityId
    face_usd: DecimalStr
    valuation_date: date
    settlement_date: date  # standard settlement for a trade on valuation_date
    # Settlement-anchored values are None when the note is no longer tradable at
    # standard settlement (final payment on/before settlement); see diagnostics.
    clean_price_per_100: Optional[DecimalStr] = None
    accrued_per_100: Optional[DecimalStr] = None
    dirty_price_per_100: Optional[DecimalStr] = None
    settlement_consideration_usd: Optional[DecimalStr] = None  # face/100 * dirty, before fees
    clean_value_usd: Optional[DecimalStr] = None  # face/100 * clean
    accrued_interest_usd: Optional[DecimalStr] = None  # face/100 * accrued
    economic_value_usd: DecimalStr  # valuation-date PV of remaining flows (payment > valuation)
    ytm: Optional[DecimalStr] = None  # street semiannual ACT/ACT-ICMA
    yield_modified_duration_years: Optional[DecimalStr] = None  # yield-based
    yield_convexity: Optional[DecimalStr] = None  # yield-based
    effective_duration_years: DecimalStr  # curve-based (parallel zero shift)
    effective_convexity: DecimalStr  # curve-based
    parallel_dv01_usd: DecimalStr
    key_rate_dv01: list[KeyRateExposure]
    key_rate_sum_minus_parallel_usd: DecimalStr
    remaining_maturity_years: DecimalStr
    maturity_bucket: str
    relative_value: RelativeValueEstimate = SYNTHETIC_RELATIVE_VALUE
    calculation_id: Optional[OpaqueId] = None


class ConcentrationEntry(ContractModel):
    security_id: SecurityId
    economic_value_usd: DecimalStr
    weight_of_bonds: DecimalStr
    weight_of_nav: Optional[DecimalStr] = None


class MaturityBucket(ContractModel):
    bucket: str  # e.g. "0-1y"
    economic_value_usd: DecimalStr
    parallel_dv01_usd: DecimalStr
    security_ids: list[SecurityId]


class RiskReport(ContractModel):
    schema_version: str = SCHEMA_VERSION
    report_id: Optional[OpaqueId] = None
    curve_snapshot_id: OpaqueId
    portfolio_snapshot_id: Optional[OpaqueId] = None
    as_of: UtcDatetime
    valuation_date: date
    data_mode: DataMode = DataMode.SYNTHETIC_CURVE
    positions: list[PositionRisk]
    total_economic_value_usd: DecimalStr
    total_parallel_dv01_usd: DecimalStr  # sum of face-scaled position DV01s
    total_key_rate_dv01: list[KeyRateExposure]
    portfolio_effective_duration_years: Optional[DecimalStr] = None
    concentration: list[ConcentrationEntry]
    maturity_buckets: list[MaturityBucket]
    cash_available_usd: Optional[DecimalStr] = None
    pending_settlement_payables_usd: Optional[DecimalStr] = None
    pending_settlement_receivables_usd: Optional[DecimalStr] = None
    turnover_usd: Optional[DecimalStr] = None
    nav_usd: Optional[DecimalStr] = None
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    relative_value: RelativeValueEstimate = SYNTHETIC_RELATIVE_VALUE
    definitions: dict[str, str] = Field(default_factory=dict)
    calculation_ids: list[OpaqueId] = Field(default_factory=list)
    completeness: Completeness = Completeness.COMPLETE
    diagnostics: list[str] = Field(default_factory=list)
