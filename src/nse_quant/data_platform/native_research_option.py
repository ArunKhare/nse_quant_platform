"""Read-only research IV candidate from two explicit pinned native Gold price roles."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_option_model import (
    ResearchIvCandidate,
    ScenarioTerms,
    compute_research_iv,
    scenario_terms_sha256,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.gold_quote_reader import GoldQuoteEvidence

VERSION = "native-gold-research-iv-candidate@1"


@dataclass(frozen=True)
class NativeResearchIvCandidate:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    option_build_id: str
    spot_build_id: str
    scenario_terms_sha256: str
    option_before: GoldQuoteEvidence | None = None
    spot_before: GoldQuoteEvidence | None = None
    option_after: GoldQuoteEvidence | None = None
    spot_after: GoldQuoteEvidence | None = None
    calculation: ResearchIvCandidate | None = None
    source_option_event_ts: str | None = None
    source_spot_event_ts: str | None = None
    native_price_inputs_rechecked: bool = False
    evidence_fingerprint: str | None = None
    scenario_terms_authoritative: bool = False
    option_underlying_identity_binding_verified: bool = False
    canonical_contract_id: None = None
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def build_native_research_iv_candidate(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    gold: Any,
    *,
    option_build_id: str,
    spot_build_id: str,
    terms: ScenarioTerms,
    expected_scenario_terms_sha256: str,
) -> NativeResearchIvCandidate:
    """Explicit scenario roles, NOT inferred canonical contract/underlying association.

    Reads native Gold service twice per role, preserving exact input prices and
    original unknown event times. No storage/publication or decision-loop writes.
    """
    from nse_quant.data_platform import gold_quote_reader as native
    from nse_quant.data_platform.gold_quote_features import (
        ExactPriceFeature,
        GoldQuoteCandidate,
        exact_price_decimal,
    )

    if native.READER_VERSION != "gold-provider-price-consumer@1":
        raise ValueError("UNSUPPORTED_RESEARCH_IV_GOLD_READER_VERSION")
    if (
        not _pin(option_build_id)
        or not _pin(spot_build_id)
        or option_build_id == spot_build_id
        or not _pin(expected_scenario_terms_sha256)
    ):
        raise ValueError("TWO_DISTINCT_EXACT_GOLD_PINS_AND_SCENARIO_PIN_REQUIRED")
    if type(terms) is not ScenarioTerms:
        raise TypeError("TYPED_NATIVE_RESEARCH_SCENARIO_REQUIRED")
    checked = ScenarioTerms(**asdict(terms))
    terms_pin = scenario_terms_sha256(checked)
    if terms_pin != expected_scenario_terms_sha256:
        raise ValueError("RESEARCH_SCENARIO_TERMS_PIN_MISMATCH")

    def observe(pin: str) -> native.GoldQuoteEvidence:
        return native.read_quote_price_build(
            bronze, frame_silver, reference_silver, assessments, gold, build_id=pin
        )

    def complete(value: native.GoldQuoteEvidence, pin: str) -> bool:
        return (
            type(value) is native.GoldQuoteEvidence
            and value.reader_version == native.READER_VERSION
            and value.build_id == pin
            and value.status == "verified_current"
            and value.active_build_ids == (pin,)
            and bool(value.successful_attempt_job_ids)
            and _pin(value.evidence_fingerprint)
            and type(value.candidate) is GoldQuoteCandidate
            and value.candidate.build_id == pin
            and value.candidate.status == "candidate"
            and value.candidate.feature_version == "provider-packet-price-fields@1"
            and value.candidate.canonical_contract_id is None
            and all(
                x is None
                for x in (
                    value.candidate.published_at,
                    value.candidate.effective_from,
                    value.candidate.effective_to,
                )
            )
            and all(
                flag is False
                for flag in (
                    value.publication_asserted,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                    value.candidate.decision_eligibility_asserted,
                )
            )
        )

    def price(value: native.GoldQuoteEvidence) -> str:
        candidate = value.candidate
        if candidate is None:
            raise ValueError("RESEARCH_IV_SOURCE_CANDIDATE_MISSING")
        selected = [item for item in candidate.features if item.name == "last_price"]
        if len(selected) != 1 or type(selected[0]) is not ExactPriceFeature:
            raise ValueError("EXACT_SINGLE_NATIVE_LAST_PRICE_REQUIRED")
        field = selected[0]
        if (
            type(field.numerator) is not int
            or not 0 <= field.numerator < 2**32
            or candidate.price_divisor != field.denominator
            or field.decimal_value != exact_price_decimal(field.numerator, field.denominator)
        ):
            raise ValueError("NATIVE_PRICE_RATIO_AND_DECIMAL_DISAGREE")
        return field.decimal_value

    option_before, spot_before = observe(option_build_id), observe(spot_build_id)
    base: dict[str, Any] = dict(
        version=VERSION,
        option_build_id=option_build_id,
        spot_build_id=spot_build_id,
        scenario_terms_sha256=terms_pin,
        option_before=option_before,
        spot_before=spot_before,
        source_option_event_ts=(
            option_before.candidate.event_ts if option_before.candidate is not None else None
        ),
        source_spot_event_ts=(
            spot_before.candidate.event_ts if spot_before.candidate is not None else None
        ),
    )
    if not complete(option_before, option_build_id) or not complete(spot_before, spot_build_id):
        return NativeResearchIvCandidate(
            status="review_required",
            reason_codes=("NATIVE_RESEARCH_PRICE_SOURCE_NOT_CURRENT",),
            **base,
        )
    option_price, spot_price = price(option_before), price(spot_before)
    if float(option_price) <= 0 or float(spot_price) <= 0:
        return NativeResearchIvCandidate(
            status="review_required", reason_codes=("OBSERVED_NONPOSITIVE_LAST_PRICE",), **base
        )
    calculation = compute_research_iv(
        spot_decimal=spot_price, premium_decimal=option_price, terms=checked
    )
    option_after, spot_after = observe(option_build_id), observe(spot_build_id)
    common = dict(**base, option_after=option_after, spot_after=spot_after, calculation=calculation)
    if (
        not complete(option_after, option_build_id)
        or not complete(spot_after, spot_build_id)
        or asdict(option_before) != asdict(option_after)
        or asdict(spot_before) != asdict(spot_after)
    ):
        return NativeResearchIvCandidate(
            status="review_required",
            reason_codes=("NATIVE_RESEARCH_PRICE_OBSERVATION_DRIFT",),
            **common,
        )
    if calculation.status != "computed_research_scenario":
        return NativeResearchIvCandidate(
            status="review_required", reason_codes=calculation.reason_codes, **common
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                VERSION,
                asdict(checked),
                asdict(option_before),
                asdict(spot_before),
                asdict(option_after),
                asdict(spot_after),
                asdict(calculation),
            ],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return NativeResearchIvCandidate(
        status="research_iv_candidate",
        reason_codes=("EXPLICIT_SCENARIO_AND_PINNED_NATIVE_PRICES",),
        native_price_inputs_rechecked=True,
        evidence_fingerprint=fingerprint,
        **common,
    )
