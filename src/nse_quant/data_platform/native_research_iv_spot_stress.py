"""Native fixed-IV spot stress from exact reviewed, twice-revalidated research inputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_spot_stress import (
    ResearchIvSpotStress,
    canonical,
    compute_research_iv_spot_stress,
    validate_shocks,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_revalidation import ResearchIvRevalidation

VERSION = "native-research-iv-fixed-vol-spot-stress@1"
MAX_NATIVE_BYTES = 8388608


@dataclass(frozen=True)
class NativeResearchIvSpotStress:
    version: str
    build_id: str
    expected_archive_fingerprint: str
    expected_revalidation_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    before: ResearchIvRevalidation | None = None
    after: ResearchIvRevalidation | None = None
    provisional_study: ResearchIvSpotStress | None = None
    repeated_study: ResearchIvSpotStress | None = None
    study: ResearchIvSpotStress | None = None
    current_source_checked: bool = False
    exact_native_observations_matched: bool = False
    stress_results_reproduced: bool = False
    evidence_fingerprint: str | None = None
    source_option_event_ts: str | None = None
    source_spot_event_ts: str | None = None
    portfolio_pnl_asserted: bool = False
    volatility_response_modelled: bool = False
    option_underlying_identity_binding_verified: bool = False
    scenario_terms_authoritative: bool = False
    model_suitability_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    canonical_contract_id: None = None
    event_ts: None = None
    published_at: None = None


def build_native_research_iv_spot_stress(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    *,
    build_id_pin: str,
    expected_archive_fingerprint: str,
    expected_revalidation_fingerprint: str,
    shocks_bps: tuple[int, ...],
) -> NativeResearchIvSpotStress:
    """No caller result/terms/IV/spot DTO, rounding, clamping, writes or eligibility.

    Revalidation BEFORE -> actual kernel grid -> revalidation AFTER -> repeated grid.
    Unexpected errors propagate. Review may retain provisional research calculations,
    but accepted study/evidence fields remain None. No later-good selection.
    """
    from nse_quant.data_platform import native_research_option as candidate_api
    from nse_quant.data_platform import research_iv_record as record
    from nse_quant.data_platform import research_iv_revalidation as current
    from nse_quant.data_platform import research_option_model as model
    from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, exact_price_decimal

    if (
        current.VERSION != "research-iv-current-source-revalidation@1"
        or record.VERSION != "research-iv-build-record@1"
        or candidate_api.VERSION != "native-gold-research-iv-candidate@1"
        or model.VERSION != "research-european-bsm-iv@1"
    ):
        raise ValueError("UNSUPPORTED_NATIVE_RESEARCH_STRESS_DEPENDENCY_PROFILE")
    if not all(
        record.pin(p)
        for p in (
            build_id_pin,
            expected_archive_fingerprint,
            expected_revalidation_fingerprint,
        )
    ):
        raise ValueError("EXACT_REVIEWED_NATIVE_RESEARCH_STRESS_PINS_REQUIRED")
    validate_shocks(shocks_bps)

    def report(reasons: tuple[str, ...], **facts: Any) -> NativeResearchIvSpotStress:
        return NativeResearchIvSpotStress(
            VERSION,
            build_id_pin,
            expected_archive_fingerprint,
            expected_revalidation_fingerprint,
            "review_required",
            reasons,
            **facts,
        )

    def observe() -> tuple[current.ResearchIvRevalidation, bytes]:
        value = current.revalidate_research_iv_build(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            source_gold,
            archive,
            build_id_pin=build_id_pin,
            expected_archive_fingerprint=expected_archive_fingerprint,
        )
        if type(value) is not current.ResearchIvRevalidation:
            raise ValueError("TYPED_NATIVE_RESEARCH_STRESS_OBSERVATION_REQUIRED")
        raw = canonical(asdict(value))
        if not 0 < len(raw) <= MAX_NATIVE_BYTES:
            raise ValueError("NATIVE_RESEARCH_STRESS_OBSERVATION_BYTE_LIMIT")
        return value, raw

    def complete(value: current.ResearchIvRevalidation) -> bool:
        return (
            value.version == current.VERSION
            and value.build_id == build_id_pin
            and value.expected_archive_fingerprint == expected_archive_fingerprint
            and value.evidence_fingerprint == expected_revalidation_fingerprint
            and value.status == "matched_current_research_iv"
            and all(
                getattr(value, key) is True
                for key in (
                    "archived_recording_verified",
                    "current_source_checked",
                    "exact_recording_reproduced",
                    "archive_unchanged_observed",
                )
            )
            and all(
                getattr(value, key) is False
                for key in (
                    "publication_asserted",
                    "availability_evidence_verified",
                    "historical_validity_asserted",
                    "scenario_terms_authoritative",
                    "option_underlying_identity_binding_verified",
                    "decision_eligibility_asserted",
                    "atomic_cross_database_snapshot_asserted",
                )
            )
            and value.canonical_contract_id is None
            and value.archive_before is not None
            and value.archive_after is not None
            and value.fresh_before is not None
            and value.fresh_after is not None
            and value.comparison is not None
            and value.comparison.all_observations_match is True
        )

    def study(value: current.ResearchIvRevalidation) -> ResearchIvSpotStress:
        archived, fresh = value.archive_before, value.fresh_before
        if (
            archived is None
            or fresh is None
            or type(fresh) is not candidate_api.NativeResearchIvCandidate
        ):
            raise ValueError("NATIVE_RESEARCH_STRESS_INPUT_PROJECTION_MISSING")
        calculation = fresh.calculation
        if (
            type(calculation) is not model.ResearchIvCandidate
            or calculation.status != "computed_research_scenario"
            or calculation.greeks is None
            or type(calculation.implied_volatility) is not float
        ):
            raise ValueError("NATIVE_RESEARCH_STRESS_SOLVED_CALCULATION_REQUIRED")
        terms = model.ScenarioTerms(**record.checked_json(archived.terms_json, 4096))
        if model.scenario_terms_sha256(terms) != fresh.scenario_terms_sha256:
            raise ValueError("NATIVE_RESEARCH_STRESS_TERMS_PIN_MISMATCH")
        spot_observation = fresh.spot_before
        if spot_observation is None or spot_observation.candidate is None:
            raise ValueError("NATIVE_RESEARCH_STRESS_ACTUAL_SPOT_OBSERVATION_REQUIRED")
        source = spot_observation.candidate
        fields = [f for f in source.features if f.name == "last_price"]
        if len(fields) != 1 or type(fields[0]) is not ExactPriceFeature:
            raise ValueError("NATIVE_RESEARCH_STRESS_UNIQUE_EXACT_SPOT_REQUIRED")
        field = fields[0]
        if (
            type(field.numerator) is not int
            or not 0 <= field.numerator < 2**32
            or field.denominator != source.price_divisor
            or field.decimal_value != exact_price_decimal(field.numerator, field.denominator)
        ):
            raise ValueError("NATIVE_RESEARCH_STRESS_SPOT_RATIO_DISAGREES")
        result = compute_research_iv_spot_stress(
            spot_decimal=field.decimal_value,
            terms=terms,
            fixed_implied_volatility=calculation.implied_volatility,
            shocks_bps=shocks_bps,
        )
        if (
            asdict(result.baseline) != asdict(calculation.greeks)
            or result.scipy_version != calculation.scipy_version
            or result.python_version != calculation.python_version
        ):
            raise ValueError("NATIVE_RESEARCH_STRESS_BASELINE_OR_RUNTIME_DIFFERS")
        return result

    before, before_raw = observe()
    if not complete(before):
        return report(("NATIVE_RESEARCH_STRESS_NOT_EXACT_REVIEWED_CURRENT_BUILD",), before=before)
    first = study(before)
    after, after_raw = observe()
    facts: dict[str, Any] = dict(
        before=before, after=after, provisional_study=first, current_source_checked=True
    )
    if not complete(after) or before_raw != after_raw:
        return report(("NATIVE_RESEARCH_STRESS_SOURCE_OR_ARCHIVE_CHANGED",), **facts)
    second = study(after)
    facts.update(repeated_study=second, exact_native_observations_matched=True)
    if canonical(asdict(first)) != canonical(asdict(second)):
        return report(("NATIVE_RESEARCH_STRESS_NUMERICAL_RESULTS_CHANGED",), **facts)
    facts["stress_results_reproduced"] = True
    fresh = before.fresh_before
    if fresh is None:
        raise ValueError("NATIVE_RESEARCH_STRESS_COMPLETE_SOURCE_MISSING")
    fingerprint = record.sha(
        canonical(
            [
                VERSION,
                build_id_pin,
                expected_archive_fingerprint,
                expected_revalidation_fingerprint,
                record.sha(before_raw),
                record.sha(after_raw),
                asdict(first),
                asdict(second),
            ]
        )
    )
    return NativeResearchIvSpotStress(
        VERSION,
        build_id_pin,
        expected_archive_fingerprint,
        expected_revalidation_fingerprint,
        "computed_current_native_research_iv_spot_stress",
        ("REVIEWED_NATIVE_INPUTS_AND_FIXED_IV_STRESS_REPRODUCED",),
        study=first,
        evidence_fingerprint=fingerprint,
        source_option_event_ts=fresh.source_option_event_ts,
        source_spot_event_ts=fresh.source_spot_event_ts,
        **facts,
    )
