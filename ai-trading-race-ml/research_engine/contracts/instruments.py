"""Security-master contracts (spec 8.1).

Every instrument carries the seven field groups required by the specification:
identity, economics, dates, schedule rules, conventions, trading units and
provenance, plus a ``terms_version`` with effective dates.

Units: ``coupon_rate`` is a decimal annual rate (0.045 = 4.5%); prices and
redemption amounts are per 100 face; face amounts are USD.

Synthetic instruments use internal identifiers ``SYN-USD-NOTE-NNN`` and carry no
external identifiers. External identifiers (CUSIP/ISIN) are never fabricated;
a synthetic instrument that declares one is rejected.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .common import (
    SCHEMA_VERSION,
    ContentHash,
    ContractModel,
    DecimalStr,
    OpaqueId,
    SecurityId,
    SourceId,
    UtcDatetime,
)

SYNTHETIC_ID_PATTERN = re.compile(r"^SYN-USD-NOTE-\d{3}$")


class InstrumentClassification(str, Enum):
    SYNTHETIC = "synthetic"  # hypothetical terms; must not impersonate an actual security
    ACTUAL = "actual"  # sourced contractual terms (observed-security mode only)


class InstrumentType(str, Enum):
    FIXED_RATE_NOTE = "fixed_rate_note"  # USD nominal, non-callable, bullet principal


class DayCountConvention(str, Enum):
    ACT_ACT_ICMA = "ACT/ACT-ICMA"  # QuantLib ActualActual(ISMA); U.S. Treasury coupon accrual
    ACT_365_FIXED = "ACT/365F"
    ACT_360 = "ACT/360"


class BusinessDayConvention(str, Enum):
    FOLLOWING = "FOLLOWING"
    MODIFIED_FOLLOWING = "MODIFIED_FOLLOWING"
    UNADJUSTED = "UNADJUSTED"


class ValidationStatus(str, Enum):
    HYPOTHETICAL = "hypothetical"  # synthetic fixture: internally consistent, not sourced
    PROVISIONAL = "provisional"  # inferred schedule pending validation (not admissible observed)
    VALIDATED = "validated"  # sourced terms validated against the source artifact
    REJECTED = "rejected"


class ExternalIdentifier(ContractModel):
    scheme: Literal["CUSIP", "ISIN", "FIGI", "SOURCE_NATIVE"]
    value: str = Field(min_length=1, max_length=64)


class SecurityIdentity(ContractModel):
    security_id: SecurityId
    classification: InstrumentClassification
    issuer_id: OpaqueId  # e.g. "US-TREASURY-HYPOTHETICAL" for synthetic notes
    external_identifiers: list[ExternalIdentifier] = Field(default_factory=list)
    display_name: str


class SecurityEconomics(ContractModel):
    currency: Literal["USD"] = "USD"
    instrument_type: InstrumentType = InstrumentType.FIXED_RATE_NOTE
    coupon_rate: DecimalStr  # decimal annual rate
    coupon_frequency: Literal[2] = 2  # semiannual
    redemption_per_100: DecimalStr = Decimal("100")
    callable: Literal[False] = False

    @model_validator(mode="after")
    def _bounds(self) -> "SecurityEconomics":
        if self.coupon_rate < 0 or self.coupon_rate > Decimal("0.25"):
            raise ValueError("coupon_rate must be a decimal annual rate in [0, 0.25]")
        if self.redemption_per_100 <= 0:
            raise ValueError("redemption_per_100 must be positive")
        return self


class SecurityDates(ContractModel):
    original_issue_date: date
    dated_date: date  # accrual start of the first coupon period
    maturity_date: date  # unadjusted contractual maturity
    first_coupon_date: Optional[date] = None  # None = regular schedule backward from maturity

    @model_validator(mode="after")
    def _order(self) -> "SecurityDates":
        if not self.dated_date <= self.original_issue_date < self.maturity_date:
            raise ValueError("require dated_date <= original_issue_date < maturity_date")
        if self.first_coupon_date is not None and not (
            self.dated_date < self.first_coupon_date <= self.maturity_date
        ):
            raise ValueError("first_coupon_date must fall in (dated_date, maturity_date]")
        return self


class ScheduleRules(ContractModel):
    generation: Literal["backward_from_maturity"] = "backward_from_maturity"
    accrual_dates: Literal["unadjusted"] = "unadjusted"
    payment_adjustment: BusinessDayConvention = BusinessDayConvention.FOLLOWING
    end_of_month: bool = False
    stub: Literal["short_first_if_irregular"] = "short_first_if_irregular"
    # A flow belongs to the holder whose settlement date is strictly before its
    # adjusted payment date (docs/fixed-income/numerical-methods.md#entitlement).
    entitlement_rule: Literal["settlement_strictly_before_payment_v1"] = (
        "settlement_strictly_before_payment_v1"
    )
    ex_coupon_days: Literal[0] = 0


class SecurityConventions(ContractModel):
    day_count: DayCountConvention = DayCountConvention.ACT_ACT_ICMA
    business_day_adjustment: BusinessDayConvention = BusinessDayConvention.FOLLOWING
    calendar_id: str = "US-GovernmentBond"
    calendar_version: str = "quantlib-1.44"
    settlement_lag_business_days: int = Field(default=1, ge=0, le=5)
    price_quote_basis: Literal["clean_per_100"] = "clean_per_100"
    yield_convention: Literal["street_semiannual_act_act_icma_v1"] = (
        "street_semiannual_act_act_icma_v1"
    )


class TradingUnits(ContractModel):
    min_face_usd: DecimalStr = Decimal("1000")
    face_increment_usd: DecimalStr = Decimal("1000")

    @model_validator(mode="after")
    def _positive(self) -> "TradingUnits":
        if self.min_face_usd <= 0 or self.face_increment_usd <= 0:
            raise ValueError("face amounts must be positive")
        return self


class TermsProvenance(ContractModel):
    source_id: SourceId
    source_artifact: str  # path or URI of the artifact holding the terms
    source_row: Optional[str] = None  # row / record locator inside the artifact
    checksum: Optional[ContentHash] = None  # sha256 of the artifact bytes
    available_at: UtcDatetime  # earliest permitted use of these terms
    validation_status: ValidationStatus
    notes: str = ""


class SecurityTerms(ContractModel):
    schema_version: str = SCHEMA_VERSION
    terms_version: OpaqueId
    terms_effective_from: date
    terms_effective_to: Optional[date] = None
    identity: SecurityIdentity
    economics: SecurityEconomics
    dates: SecurityDates
    schedule: ScheduleRules = Field(default_factory=ScheduleRules)
    conventions: SecurityConventions = Field(default_factory=SecurityConventions)
    trading_units: TradingUnits = Field(default_factory=TradingUnits)
    provenance: TermsProvenance

    @property
    def security_id(self) -> str:
        return self.identity.security_id

    @model_validator(mode="after")
    def _identity_rules(self) -> "SecurityTerms":
        ident = self.identity
        if ident.classification is InstrumentClassification.SYNTHETIC:
            if not SYNTHETIC_ID_PATTERN.match(ident.security_id):
                raise ValueError("synthetic instruments use internal IDs SYN-USD-NOTE-NNN")
            if ident.external_identifiers:
                raise ValueError("synthetic instruments must not carry external identifiers")
            if self.provenance.validation_status is not ValidationStatus.HYPOTHETICAL:
                raise ValueError("synthetic instrument provenance must be 'hypothetical'")
        else:
            if ident.security_id.startswith("SYN-"):
                raise ValueError("actual instruments must not use the synthetic ID namespace")
        if self.terms_effective_to is not None and self.terms_effective_to < (
            self.terms_effective_from
        ):
            raise ValueError("terms_effective_to precedes terms_effective_from")
        return self


class InstrumentUniverse(ContractModel):
    schema_version: str = SCHEMA_VERSION
    universe_id: OpaqueId  # e.g. "synthetic_universe_v1"
    version: OpaqueId
    classification: InstrumentClassification
    description: str
    hypothetical_notice: str = ""
    securities: list[SecurityTerms]

    @model_validator(mode="after")
    def _unique(self) -> "InstrumentUniverse":
        ids = [s.security_id for s in self.securities]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate security_id in universe")
        for sec in self.securities:
            if sec.identity.classification is not self.classification:
                raise ValueError("universe mixes synthetic and actual instruments")
        return self

    def get(self, security_id: str) -> SecurityTerms:
        for sec in self.securities:
            if sec.security_id == security_id:
                return sec
        raise KeyError(security_id)
