"""Observed security-quote validation and observed-security admission (spec 3.3, 7.2).

Observed-security mode is a *gated* capability. Until a licensed (or otherwise
permitted) security-level quote source with documented rights and coverage is
configured, every admission request returns ``admitted=False`` with the explicit
reason ``no_licensed_quote_source_configured``. Treasury par yields are never
admissible as security quotes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from research_engine.contracts.instruments import (
    InstrumentClassification,
    SecurityTerms,
    ValidationStatus,
)
from research_engine.contracts.market import (
    InstrumentStatus,
    ObservedQuote,
    ObservedSecurityAdmission,
    PriceBasis,
    QuoteValidationResult,
)
from research_engine.contracts.portfolio import QuoteKind
from research_engine.instruments.schedule import InstrumentModel

#: Registry of quote sources whose rights/coverage have been documented. Empty
#: by design: provider selection is an open implementation gate (spec 21).
LICENSED_QUOTE_SOURCES: frozenset[str] = frozenset()


@dataclass(frozen=True)
class QuoteValidationPolicy:
    policy_id: str = "observed-quote-validation-v1"
    currency: str = "USD"
    min_price_per_100: Decimal = Decimal("1")
    max_price_per_100: Decimal = Decimal("200")
    max_age: timedelta = timedelta(days=4)  # covers one business day across a weekend
    mid_tolerance_per_100: Decimal = Decimal("0.000001")


def validate_observed_quote(
    quote: ObservedQuote,
    *,
    as_of: datetime,
    terms: Optional[SecurityTerms] = None,
    policy: QuoteValidationPolicy = QuoteValidationPolicy(),
) -> QuoteValidationResult:
    reasons: list[str] = []
    if quote.kind is QuoteKind.SYNTHETIC_MODEL:
        reasons.append("synthetic_model_price_is_not_an_observed_quote")
    prices = {"bid": quote.bid_per_100, "ask": quote.ask_per_100, "mid": quote.mid_per_100}
    required = {
        QuoteKind.OBSERVED_BID: ("bid",),
        QuoteKind.OBSERVED_ASK: ("ask",),
        QuoteKind.OBSERVED_MID: ("mid",),
    }.get(quote.kind, ())
    for name in required:
        if prices[name] is None:
            reasons.append(f"missing_{name}_for_{quote.kind.value}")
    if all(v is None for v in prices.values()):
        reasons.append("no_price_fields")
    for name, value in prices.items():
        if value is None:
            continue
        if not value.is_finite():
            reasons.append(f"non_finite:{name}")
        elif not policy.min_price_per_100 <= value <= policy.max_price_per_100:
            reasons.append(f"price_scale_out_of_range:{name}")
    bid, ask, mid = prices["bid"], prices["ask"], prices["mid"]
    if bid is not None and ask is not None:
        if bid > ask:
            reasons.append("crossed_market:bid_above_ask")
        if mid is not None and abs(mid - (bid + ask) / 2) > policy.mid_tolerance_per_100:
            reasons.append("mid_inconsistent_with_bid_ask")
    if quote.currency != policy.currency:
        reasons.append(f"currency_mismatch:{quote.currency}")
    if quote.instrument_status is not InstrumentStatus.ACTIVE:
        reasons.append(f"instrument_status:{quote.instrument_status.value}")
    if quote.kind is QuoteKind.OBSERVED_INDICATIVE and quote.executable:
        reasons.append("indicative_quote_marked_executable")
    # Timestamp order: observed <= published <= available; ingestion after observation.
    if quote.published_at is not None and quote.published_at < quote.observed_at:
        reasons.append("timestamp_order:published_before_observed")
    if quote.available_at < quote.observed_at:
        reasons.append("timestamp_order:available_before_observed")
    if quote.published_at is not None and quote.available_at < quote.published_at:
        reasons.append("timestamp_order:available_before_published")
    if quote.ingested_at < quote.observed_at:
        reasons.append("timestamp_order:ingested_before_observed")
    if quote.available_at > as_of:
        reasons.append("not_yet_available")
    age = as_of - quote.observed_at
    if age > policy.max_age:
        reasons.append("stale_quote")
    if quote.settlement_date < quote.observed_at.date():
        reasons.append("settlement_before_observation")
    if terms is not None:
        if terms.security_id != quote.security_id:
            reasons.append("security_mismatch")
        model = InstrumentModel(terms)
        if not (
            terms.dates.original_issue_date <= quote.settlement_date < model.final_payment_date
        ):
            reasons.append("settlement_outside_instrument_life")
        if quote.price_basis is PriceBasis.DIRTY and mid is not None and bid is None:
            accrued = model.accrued_per_100(quote.settlement_date)
            if mid - accrued < 0:
                reasons.append("dirty_price_below_accrued")
    return QuoteValidationResult(
        quote_id=quote.quote_id,
        valid=not reasons,
        reasons=reasons,
        stale_age_seconds=int(age.total_seconds()),
    )


def to_clean_per_100(price: Decimal, basis: PriceBasis, accrued_per_100: Decimal) -> Decimal:
    """Normalize a quote to the clean basis at its own settlement date."""
    return price - accrued_per_100 if basis is PriceBasis.DIRTY else price


def admit_observed_security(
    terms: SecurityTerms, *, quote_source_id: Optional[str] = None
) -> ObservedSecurityAdmission:
    reasons: list[str] = []
    if terms.identity.classification is InstrumentClassification.SYNTHETIC:
        reasons.append("synthetic_instrument_not_eligible_for_observed_mode")
    if quote_source_id is None:
        reasons.append("no_licensed_quote_source_configured")
    elif quote_source_id not in LICENSED_QUOTE_SOURCES:
        reasons.append(f"quote_source_not_licensed:{quote_source_id}")
    if terms.provenance.validation_status is not ValidationStatus.VALIDATED:
        reasons.append(f"terms_not_validated:{terms.provenance.validation_status.value}")
    return ObservedSecurityAdmission(
        security_id=terms.security_id,
        admitted=not reasons,
        reasons=reasons,
        quote_source_id=quote_source_id,
    )
