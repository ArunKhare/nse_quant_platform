"""Actual current-record-bracketed hypothetical spot/vol surface, no publication or P&L."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_spot_vol_surface import (
    ResearchIvSpotVolSurface,
    canonical,
    compute_research_iv_spot_vol_surface,
    validate_vol_shifts,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_stress_archive_revalidation import (
        ResearchIvCurrentStressArchive,
    )

VERSION = "native-research-iv-hypothetical-spot-vol-surface@1"
MAX_CONTEXT_BYTES = 167772160


@dataclass(frozen=True)
class NativeResearchIvSpotVolSurface:
    version: str
    stress_record_id: str
    expected_recording_fingerprint: str
    vol_shifts_bps: tuple[int, ...]
    status: str
    reason_codes: tuple[str, ...]
    before: ResearchIvCurrentStressArchive | None = None
    after: ResearchIvCurrentStressArchive | None = None
    provisional_surface: ResearchIvSpotVolSurface | None = None
    repeated_surface: ResearchIvSpotVolSurface | None = None
    surface: ResearchIvSpotVolSurface | None = None
    current_source_checked: bool = False
    model_computation_rechecked: bool = False
    current_context_matched: bool = False
    surface_reproduced: bool = False
    evidence_fingerprint: str | None = None
    source_option_event_ts: str | None = None
    source_spot_event_ts: str | None = None
    hypothetical_volatility_shift_assumed: bool = True
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


def build_native_research_iv_spot_vol_surface(
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
    vol_shifts_bps: tuple[int, ...],
) -> NativeResearchIvSpotVolSurface:
    """Caller adds ONLY hypothetical vol offsets; source spot grid/base IV stay frozen."""
    from nse_quant.data_platform import research_iv_spot_vol_surface as surface_api
    from nse_quant.data_platform import research_iv_stress_archive_record as record
    from nse_quant.data_platform import research_iv_stress_archive_revalidation as current

    if (
        current.VERSION != "research-iv-spot-stress-archive-current-revalidation@1"
        or current.MAX_OBSERVATION_BYTES != 25165824
        or record.VERSION != "research-iv-spot-stress-archive-record@1"
        or surface_api.VERSION != "research-iv-hypothetical-spot-vol-surface@1"
        or surface_api.MAX_SURFACE_BYTES != 262144
        or surface_api.MAX_VOL_SHIFTS != 8
        or surface_api.MAX_CELLS != 128
    ):
        raise ValueError("UNSUPPORTED_NATIVE_SPOT_VOL_SURFACE_PROFILE")
    if not record.pin(stress_record_id_pin) or not record.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_REVIEWED_SPOT_VOL_SURFACE_RECORD_PINS_REQUIRED")
    validate_vol_shifts(vol_shifts_bps)
    inputs = (
        bronze,
        frame_silver,
        reference_silver,
        assessments,
        source_gold,
        archive,
        stress_archive,
    )

    def report(reasons: tuple[str, ...], **facts: Any) -> NativeResearchIvSpotVolSurface:
        return NativeResearchIvSpotVolSurface(
            VERSION,
            stress_record_id_pin,
            expected_recording_fingerprint,
            vol_shifts_bps,
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
            raise ValueError("SURFACE_TYPED_CURRENT_CONTEXT_REQUIRED")
        raw = canonical(asdict(value))
        if not 0 < len(raw) <= MAX_CONTEXT_BYTES:
            raise ValueError("SURFACE_CURRENT_CONTEXT_BYTE_LIMIT")
        return value, raw

    def complete(value: current.ResearchIvCurrentStressArchive) -> bool:
        return (
            value.version == current.VERSION
            and value.stress_record_id == stress_record_id_pin
            and value.expected_recording_fingerprint == expected_recording_fingerprint
            and value.status == "matched_current_research_iv_spot_stress_archive"
            and all(
                getattr(value, k) is True
                for k in (
                    "archived_recording_verified",
                    "current_source_checked",
                    "model_computation_rechecked",
                    "exact_recording_reproduced",
                    "archive_unchanged_observed",
                )
            )
            and all(getattr(value, k) is False for k in record.DENIALS)
            and all(getattr(value, k) is None for k in record.NULLS)
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
        return report(("SURFACE_REVIEWED_STRESS_CONTEXT_NOT_CURRENT_BEFORE",), **facts)
    if first.study is None:
        raise ValueError("SURFACE_COMPLETE_SOURCE_STUDY_MISSING_BEFORE")
    provisional = compute_research_iv_spot_vol_surface(first.study, vol_shifts_bps=vol_shifts_bps)
    second, second_raw = observe()
    facts.update(
        after=second,
        provisional_surface=provisional,
        model_computation_rechecked=(
            first.model_computation_rechecked and second.model_computation_rechecked
        ),
    )
    if not complete(second) or first_raw != second_raw:
        return report(("SURFACE_CURRENT_SOURCE_OR_AUDIT_CONTEXT_CHANGED",), **facts)
    if second.study is None:
        raise ValueError("SURFACE_COMPLETE_SOURCE_STUDY_MISSING_AFTER")
    repeated = compute_research_iv_spot_vol_surface(second.study, vol_shifts_bps=vol_shifts_bps)
    facts.update(repeated_surface=repeated, current_context_matched=True)
    if canonical(asdict(provisional)) != canonical(asdict(repeated)):
        return report(("SURFACE_REPRICING_RESULTS_CHANGED",), **facts)
    facts["surface_reproduced"] = True
    fingerprint = record.sha(
        canonical(
            [
                VERSION,
                stress_record_id_pin,
                expected_recording_fingerprint,
                vol_shifts_bps,
                record.sha(first_raw),
                record.sha(second_raw),
                asdict(provisional),
                asdict(repeated),
            ]
        )
    )
    return NativeResearchIvSpotVolSurface(
        VERSION,
        stress_record_id_pin,
        expected_recording_fingerprint,
        vol_shifts_bps,
        "computed_current_native_research_iv_spot_vol_surface",
        ("HYPOTHETICAL_SPOT_VOL_SURFACE_AND_CURRENT_CONTEXT_REPRODUCED",),
        surface=provisional,
        evidence_fingerprint=fingerprint,
        source_option_event_ts=first.source_option_event_ts,
        source_spot_event_ts=first.source_spot_event_ts,
        **facts,
    )
