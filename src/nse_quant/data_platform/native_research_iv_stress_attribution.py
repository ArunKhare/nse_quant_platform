"""Research Taylor attribution bracketed by actual current archived-stress revalidation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_stress_attribution import (
    ResearchIvStressAttribution,
    attribute_research_iv_spot_stress,
    canonical,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_stress_archive_revalidation import (
        ResearchIvCurrentStressArchive,
    )

VERSION = "native-research-iv-stress-delta-gamma-attribution@1"
MAX_CONTEXT_BYTES = 167772160


@dataclass(frozen=True)
class NativeResearchIvStressAttribution:
    version: str
    stress_record_id: str
    expected_recording_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    before: ResearchIvCurrentStressArchive | None = None
    after: ResearchIvCurrentStressArchive | None = None
    provisional_attribution: ResearchIvStressAttribution | None = None
    repeated_attribution: ResearchIvStressAttribution | None = None
    attribution: ResearchIvStressAttribution | None = None
    current_source_checked: bool = False
    model_computation_rechecked: bool = False
    current_context_matched: bool = False
    attribution_reproduced: bool = False
    evidence_fingerprint: str | None = None
    source_option_event_ts: str | None = None
    source_spot_event_ts: str | None = None
    approximation_accuracy_certified: bool = False
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


def build_native_research_iv_stress_attribution(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    stress_archive: Any,
    *,
    stress_record_id_pin: str,
    expected_recording_fingerprint: str,
) -> NativeResearchIvStressAttribution:
    """No caller study, coefficients, grid, native pins or accepted-result DTO. No writes."""
    from nse_quant.data_platform import research_iv_stress_archive_record as record
    from nse_quant.data_platform import research_iv_stress_archive_revalidation as current
    from nse_quant.data_platform import research_iv_stress_attribution as attribution_api

    if (
        current.VERSION != "research-iv-spot-stress-archive-current-revalidation@1"
        or current.MAX_OBSERVATION_BYTES != 25165824
        or record.VERSION != "research-iv-spot-stress-archive-record@1"
        or attribution_api.VERSION != "research-iv-spot-stress-delta-gamma-attribution@1"
        or attribution_api.MAX_ATTRIBUTION_BYTES != 65536
    ):
        raise ValueError("UNSUPPORTED_NATIVE_STRESS_ATTRIBUTION_PROFILE")
    if not record.pin(stress_record_id_pin) or not record.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_REVIEWED_ATTRIBUTION_RECORD_PINS_REQUIRED")
    inputs = (
        bronze,
        frame_silver,
        reference_silver,
        assessments,
        source_gold,
        archive,
        stress_archive,
    )

    def report(reasons: tuple[str, ...], **facts: Any) -> NativeResearchIvStressAttribution:
        return NativeResearchIvStressAttribution(
            VERSION,
            stress_record_id_pin,
            expected_recording_fingerprint,
            "review_required",
            reasons,
            **facts,
        )

    def observe() -> tuple[current.ResearchIvCurrentStressArchive, bytes]:
        value = current.revalidate_research_iv_spot_stress_archive(
            *inputs,
            stress_record_id_pin=stress_record_id_pin,
            expected_recording_fingerprint=expected_recording_fingerprint,
        )
        if type(value) is not current.ResearchIvCurrentStressArchive:
            raise ValueError("ATTRIBUTION_TYPED_CURRENT_CONTEXT_REQUIRED")
        raw = canonical(asdict(value))
        if not 0 < len(raw) <= MAX_CONTEXT_BYTES:
            raise ValueError("ATTRIBUTION_CURRENT_CONTEXT_BYTE_LIMIT")
        return value, raw

    def complete(value: current.ResearchIvCurrentStressArchive) -> bool:
        return (
            value.version == current.VERSION
            and value.stress_record_id == stress_record_id_pin
            and value.expected_recording_fingerprint == expected_recording_fingerprint
            and value.status == "matched_current_research_iv_spot_stress_archive"
            and all(
                getattr(value, key) is True
                for key in (
                    "archived_recording_verified",
                    "current_source_checked",
                    "model_computation_rechecked",
                    "exact_recording_reproduced",
                    "archive_unchanged_observed",
                )
            )
            and all(getattr(value, key) is False for key in record.DENIALS)
            and all(getattr(value, key) is None for key in record.NULLS)
            and record.pin(value.native_stress_fingerprint)
            and record.pin(value.evidence_fingerprint)
            and value.study is not None
            and value.fresh_before is not None
            and value.fresh_after is not None
            and value.archive_before is not None
            and value.archive_after is not None
            and value.comparison is not None
            and value.comparison.all_observations_match is True
        )

    first, first_raw = observe()
    facts: dict[str, Any] = dict(
        before=first,
        current_source_checked=first.current_source_checked,
        model_computation_rechecked=first.model_computation_rechecked,
    )
    if not complete(first):
        return report(("ATTRIBUTION_REVIEWED_STRESS_CONTEXT_NOT_CURRENT_BEFORE",), **facts)
    if first.study is None:
        raise ValueError("ATTRIBUTION_COMPLETE_STUDY_MISSING_BEFORE")
    provisional = attribute_research_iv_spot_stress(first.study)
    second, second_raw = observe()
    facts.update(
        after=second,
        provisional_attribution=provisional,
        model_computation_rechecked=(
            first.model_computation_rechecked and second.model_computation_rechecked
        ),
    )
    if not complete(second) or first_raw != second_raw:
        return report(("ATTRIBUTION_CURRENT_STRESS_OR_AUDIT_CONTEXT_CHANGED",), **facts)
    if second.study is None:
        raise ValueError("ATTRIBUTION_COMPLETE_STUDY_MISSING_AFTER")
    repeated = attribute_research_iv_spot_stress(second.study)
    facts.update(repeated_attribution=repeated, current_context_matched=True)
    if canonical(asdict(provisional)) != canonical(asdict(repeated)):
        return report(("ATTRIBUTION_ARITHMETIC_RESULT_CHANGED",), **facts)
    facts["attribution_reproduced"] = True
    fingerprint = record.sha(
        canonical(
            [
                VERSION,
                stress_record_id_pin,
                expected_recording_fingerprint,
                record.sha(first_raw),
                record.sha(second_raw),
                asdict(provisional),
                asdict(repeated),
            ]
        )
    )
    return NativeResearchIvStressAttribution(
        VERSION,
        stress_record_id_pin,
        expected_recording_fingerprint,
        "computed_current_native_research_iv_stress_attribution",
        ("BASELINE_DELTA_GAMMA_DIAGNOSTICS_REPRODUCED_NOT_ACCURACY_CERTIFICATION",),
        attribution=provisional,
        evidence_fingerprint=fingerprint,
        source_option_event_ts=first.source_option_event_ts,
        source_spot_event_ts=first.source_spot_event_ts,
        **facts,
    )
