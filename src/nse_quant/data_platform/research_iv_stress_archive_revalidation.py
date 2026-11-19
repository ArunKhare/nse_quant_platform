"""Actual current native revalidation of a reviewed complete stress archive recording."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_stress_archive_observation import (
    MAX_OBSERVATION_BYTES,
    IvStressArchiveComparison,
    compare_iv_stress_archive_observations,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.native_research_iv_spot_stress import NativeResearchIvSpotStress
    from nse_quant.data_platform.research_iv_spot_stress import ResearchIvSpotStress
    from nse_quant.data_platform.research_iv_stress_archive import ResearchIvStressRecording

VERSION = "research-iv-spot-stress-archive-current-revalidation@1"


@dataclass(frozen=True)
class ResearchIvCurrentStressArchive:
    version: str
    stress_record_id: str
    expected_recording_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    archive_before: ResearchIvStressRecording | None = None
    archive_after: ResearchIvStressRecording | None = None
    fresh_before: NativeResearchIvSpotStress | None = None
    fresh_after: NativeResearchIvSpotStress | None = None
    comparison: IvStressArchiveComparison | None = None
    archived_recording_verified: bool = False
    current_source_checked: bool = False
    model_computation_rechecked: bool = False
    exact_recording_reproduced: bool = False
    archive_unchanged_observed: bool = False
    study: ResearchIvSpotStress | None = None
    native_stress_fingerprint: str | None = None
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


def revalidate_research_iv_spot_stress_archive(
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
) -> ResearchIvCurrentStressArchive:
    """No caller study/pins/grid DTO, writes, rounding, latest lookup or accepted partial result."""
    from nse_quant.data_platform import native_research_iv_spot_stress as native
    from nse_quant.data_platform import research_iv_spot_stress as numerical
    from nse_quant.data_platform import research_iv_stress_archive as store
    from nse_quant.data_platform import research_iv_stress_archive_record as record

    if (
        store.VERSION != "audited-research-iv-spot-stress-recording@1"
        or record.VERSION != "research-iv-spot-stress-archive-record@1"
        or record.STORE_VERSION != store.VERSION
        or record.NATIVE_VERSION != native.VERSION
        or native.VERSION != "native-research-iv-fixed-vol-spot-stress@1"
        or native.MAX_NATIVE_BYTES != record.MAX_NATIVE_BYTES
        or record.MAX_NATIVE_BYTES != 8388608
        or record.MAX_RECORD_BYTES != MAX_OBSERVATION_BYTES
        or record.MAX_STUDY_BYTES != numerical.MAX_RESULT_BYTES
        or numerical.MAX_RESULT_BYTES != 65536
        or numerical.MAX_SHOCKS != 16
        or numerical.VERSION != "research-iv-fixed-vol-spot-stress@1"
    ):
        raise ValueError("UNSUPPORTED_CURRENT_STRESS_ARCHIVE_DEPENDENCY_PROFILE")
    if not record.pin(stress_record_id_pin) or not record.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_REVIEWED_STRESS_RECORD_ID_AND_FINGERPRINT_REQUIRED")

    def report(reasons: tuple[str, ...], **facts: Any) -> ResearchIvCurrentStressArchive:
        return ResearchIvCurrentStressArchive(
            VERSION,
            stress_record_id_pin,
            expected_recording_fingerprint,
            "review_required",
            reasons,
            **facts,
        )

    def read_original() -> store.ResearchIvStressRecording:
        return store.read_research_iv_spot_stress_archive(
            stress_archive,
            build_id_pin=stress_record_id_pin,
        )

    def complete_recording(value: store.ResearchIvStressRecording) -> bool:
        return (
            type(value) is store.ResearchIvStressRecording
            and value.version == store.VERSION
            and value.build_id == stress_record_id_pin
            and value.status == "recorded_research_iv_spot_stress_not_published"
            and value.original_recording_checked is True
            and value.current_source_checked is False
            and value.model_computation_rechecked is False
            and value.portfolio_pnl_asserted is False
            and value.publication_asserted is False
            and value.decision_eligibility_asserted is False
            and all(getattr(value, k) is None for k in record.NULLS)
            and record.pin(value.evidence_fingerprint)
        )

    try:
        before = read_original()
    except store.IvStressArchiveReviewRequired:
        return report(("STRESS_ORIGINAL_RECORDING_INCOMPLETE_BEFORE",))
    if (
        not complete_recording(before)
        or before.evidence_fingerprint != expected_recording_fingerprint
    ):
        return report(("STRESS_NOT_EXACT_REVIEWED_RECORDING",), archive_before=before)
    body = record.decode(before.record_json)
    if record.sha(before.record_json.encode()) != stress_record_id_pin:
        raise ValueError("CURRENT_STRESS_RECORD_BINDING_ID_MISMATCH")
    facts: dict[str, Any] = dict(archive_before=before, archived_recording_verified=True)
    if (
        before.recorded_native_status != "computed_current_native_research_iv_spot_stress"
        or body["result"]["status"] != "computed_current_native_research_iv_spot_stress"
    ):
        return report(("RECORDED_STRESS_REVIEW_CANNOT_BE_PROMOTED",), **facts)
    inputs = (bronze, frame_silver, reference_silver, assessments, source_gold, archive)
    paths = store._paths(stress_archive)
    for conn in inputs:
        if conn is stress_archive or any(
            a == b or a.samefile(b) for a in paths for b in store._paths(conn)
        ):
            raise ValueError("SEPARATE_CURRENT_STRESS_ARCHIVE_REQUIRED")
    requested = body["request"]
    pins = tuple(requested["pins"])
    shocks = tuple(requested["shocks_bps"])
    # Reconstruct exclusively from actual verified retained bytes; no refresh.
    record.request(pins, shocks)

    def observe() -> tuple[native.NativeResearchIvSpotStress, bytes, bool]:
        value = native.build_native_research_iv_spot_stress(
            *inputs,
            build_id_pin=pins[0],
            expected_archive_fingerprint=pins[1],
            expected_revalidation_fingerprint=pins[2],
            shocks_bps=shocks,
        )
        if type(value) is not native.NativeResearchIvSpotStress:
            raise ValueError("CURRENT_STRESS_TYPED_NATIVE_OBSERVATION_REQUIRED")
        raw = record.encode(requested, asdict(value)).encode()
        if not 0 < len(raw) <= MAX_OBSERVATION_BYTES:
            raise ValueError("CURRENT_STRESS_OBSERVATION_BYTE_LIMIT")
        # Existing codec validates negative outcomes too. Do not discard either pass.
        positive = (
            value.status == "computed_current_native_research_iv_spot_stress"
            and all(getattr(value, k) is True for k in record.FACTS)
            and value.study is not None
            and record.pin(value.evidence_fingerprint)
        )
        return value, raw, positive

    first, first_raw, first_positive = observe()
    second, second_raw, second_positive = observe()
    comparison = compare_iv_stress_archive_observations(
        before.record_json.encode(),
        first_raw,
        second_raw,
    )
    reasons = list(comparison.reason_codes)
    recomputed = first_positive and second_positive
    if not recomputed:
        reasons.append("CURRENT_NATIVE_STRESS_NOT_COMPLETE_IN_BOTH_PASSES")
    facts.update(
        fresh_before=first,
        fresh_after=second,
        comparison=comparison,
        current_source_checked=True,
        model_computation_rechecked=recomputed,
        exact_recording_reproduced=recomputed and comparison.all_observations_match,
    )
    try:
        after = read_original()
    except store.IvStressArchiveReviewRequired:
        reasons.append("STRESS_ORIGINAL_RECORDING_INCOMPLETE_AFTER")
        return report(tuple(reasons), **facts)
    stable = complete_recording(after) and asdict(before) == asdict(after)
    facts.update(archive_after=after, archive_unchanged_observed=stable)
    if not stable:
        reasons.append("STRESS_ARCHIVE_RECORDING_OR_AUDIT_CHANGED")
    if reasons:
        return report(tuple(reasons), **facts)
    fingerprint = record.sha(
        record.canonical(
            [
                VERSION,
                stress_record_id_pin,
                expected_recording_fingerprint,
                record.sha(record.canonical(asdict(before)).encode()),
                record.sha(record.canonical(asdict(after)).encode()),
                asdict(comparison),
                first.evidence_fingerprint,
            ]
        ).encode()
    )
    return ResearchIvCurrentStressArchive(
        VERSION,
        stress_record_id_pin,
        expected_recording_fingerprint,
        "matched_current_research_iv_spot_stress_archive",
        ("COMPLETE_RETAINED_STRESS_AND_TWO_CURRENT_NATIVE_OBSERVATIONS_MATCH",),
        study=first.study,
        native_stress_fingerprint=first.evidence_fingerprint,
        evidence_fingerprint=fingerprint,
        source_option_event_ts=first.source_option_event_ts,
        source_spot_event_ts=first.source_spot_event_ts,
        **facts,
    )
