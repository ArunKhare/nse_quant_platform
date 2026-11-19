"""Fresh native IV recomputation bracketed by full archived-head/audit observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_observation import (
    IvObservationComparison,
    compare_iv_observations,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.native_research_option import NativeResearchIvCandidate
    from nse_quant.data_platform.research_iv_store import ResearchIvArchive

VERSION = "research-iv-current-source-revalidation@1"


@dataclass(frozen=True)
class ResearchIvRevalidation:
    version: str
    build_id: str
    expected_archive_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    archive_before: ResearchIvArchive | None = None
    archive_after: ResearchIvArchive | None = None
    fresh_before: NativeResearchIvCandidate | None = None
    fresh_after: NativeResearchIvCandidate | None = None
    comparison: IvObservationComparison | None = None
    archived_recording_verified: bool = False
    current_source_checked: bool = False
    exact_recording_reproduced: bool = False
    archive_unchanged_observed: bool = False
    evidence_fingerprint: str | None = None
    publication_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    scenario_terms_authoritative: bool = False
    option_underlying_identity_binding_verified: bool = False
    canonical_contract_id: None = None
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def revalidate_research_iv_build(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    *,
    build_id_pin: str,
    expected_archive_fingerprint: str,
) -> ResearchIvRevalidation:
    """Read-only. No caller scenario/result DTO, latest lookup, write, repair or publication.

    Source role pins and exact terms are reconstructed from verified archive bytes.
    Runtime/numeric differences require explicit reassessment, never fuzzy matching.
    """
    from nse_quant.data_platform import native_research_option as native
    from nse_quant.data_platform import research_iv_store as store
    from nse_quant.data_platform.research_iv_record import (
        MAX_RESULT_BYTES,
        MAX_TERMS_BYTES,
        build_id,
        canonical,
        checked_json,
        pin,
        sha,
    )
    from nse_quant.data_platform.research_option_model import ScenarioTerms, scenario_terms_sha256

    if (
        store.VERSION != "audited-research-iv-builds@1"
        or native.VERSION != "native-gold-research-iv-candidate@1"
    ):
        raise ValueError("UNSUPPORTED_RESEARCH_IV_REVALIDATION_DEPENDENCY_VERSION")
    if not pin(build_id_pin) or not pin(expected_archive_fingerprint):
        raise ValueError("EXACT_RESEARCH_IV_BUILD_AND_ARCHIVE_FINGERPRINT_REQUIRED")
    paths = store._paths(archive)
    for source in (bronze, frame_silver, reference_silver, assessments, source_gold):
        if source is archive or any(
            a == b or a.samefile(b) for a in paths for b in store._paths(source)
        ):
            raise ValueError("SEPARATE_RESEARCH_IV_REVALIDATION_ARCHIVE_REQUIRED")

    def report(reasons: tuple[str, ...], **values: Any) -> ResearchIvRevalidation:
        return ResearchIvRevalidation(
            VERSION,
            build_id_pin,
            expected_archive_fingerprint,
            "review_required",
            reasons,
            **values,
        )

    def complete_archive(value: store.ResearchIvArchive) -> bool:
        return (
            type(value) is store.ResearchIvArchive
            and value.version == store.VERSION
            and value.build_id == build_id_pin
            and value.retained_head_build_id == build_id_pin
            and value.status == "verified_archived_head"
            and value.archived_recording_verified is True
            and value.archived_pin_is_head is True
            and value.current_source_checked is False
            and pin(value.input_id)
            and pin(value.evidence_fingerprint)
            and value.canonical_contract_id is None
            and all(
                flag is False
                for flag in (
                    value.publication_asserted,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                )
            )
        )

    try:
        before = store.read_research_iv_archive(archive, build_id_pin=build_id_pin)
    except store.IvArchiveReviewRequired:
        return report(("RESEARCH_IV_ARCHIVE_OR_AUDIT_NOT_COMPLETE_BEFORE",))
    if not complete_archive(before) or before.evidence_fingerprint != expected_archive_fingerprint:
        return report(("RESEARCH_IV_PIN_NOT_REVIEWED_EXACT_ARCHIVED_HEAD",), archive_before=before)
    recorded = checked_json(before.result_json, MAX_RESULT_BYTES)
    if before.recorded_result_status != "research_iv_candidate" or recorded["status"] != (
        "research_iv_candidate"
    ):
        return report(
            ("RECORDED_IV_REVIEW_RESULT_CANNOT_BE_PROMOTED",),
            archive_before=before,
            archived_recording_verified=True,
        )
    terms = ScenarioTerms(**checked_json(before.terms_json, MAX_TERMS_BYTES))
    terms_pin = scenario_terms_sha256(terms)
    option_pin, spot_pin = recorded["option_build_id"], recorded["spot_build_id"]
    if (
        not pin(option_pin)
        or not pin(spot_pin)
        or option_pin == spot_pin
        or recorded["scenario_terms_sha256"] != terms_pin
        or build_id(before.input_id, before.result_json) != build_id_pin
    ):
        return report(
            ("RECORDED_IV_EXACT_INPUT_OR_RESULT_PIN_MISMATCH",),
            archive_before=before,
            archived_recording_verified=True,
        )

    def observe() -> native.NativeResearchIvCandidate:
        return native.build_native_research_iv_candidate(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            source_gold,
            option_build_id=option_pin,
            spot_build_id=spot_pin,
            terms=terms,
            expected_scenario_terms_sha256=terms_pin,
        )

    def complete_native(value: native.NativeResearchIvCandidate) -> bool:
        return (
            type(value) is native.NativeResearchIvCandidate
            and value.version == native.VERSION
            and value.status == "research_iv_candidate"
            and value.native_price_inputs_rechecked is True
            and value.option_build_id == option_pin
            and value.spot_build_id == spot_pin
            and value.scenario_terms_sha256 == terms_pin
            and pin(value.evidence_fingerprint)
            and value.calculation is not None
            and value.calculation.status == "computed_research_scenario"
            and value.canonical_contract_id is None
            and all(
                flag is False
                for flag in (
                    value.scenario_terms_authoritative,
                    value.option_underlying_identity_binding_verified,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.publication_asserted,
                    value.decision_eligibility_asserted,
                    value.atomic_cross_database_snapshot_asserted,
                )
            )
        )

    first, second = observe(), observe()
    comparison = compare_iv_observations(
        before.result_json.encode(),
        canonical(asdict(first)).encode(),
        canonical(asdict(second)).encode(),
    )
    facts: dict[str, Any] = dict(
        archive_before=before,
        fresh_before=first,
        fresh_after=second,
        comparison=comparison,
        archived_recording_verified=True,
        current_source_checked=True,
    )
    try:
        after = store.read_research_iv_archive(archive, build_id_pin=build_id_pin)
    except store.IvArchiveReviewRequired:
        return report(("RESEARCH_IV_ARCHIVE_OR_AUDIT_NOT_COMPLETE_AFTER",), **facts)
    facts["archive_after"] = after
    archive_stable = complete_archive(after) and asdict(before) == asdict(after)
    reasons = list(comparison.reason_codes)
    if not complete_native(first) or not complete_native(second):
        reasons.append("RESEARCH_IV_FRESH_NATIVE_RESULT_NOT_COMPLETE")
    if not archive_stable:
        reasons.append("RESEARCH_IV_ARCHIVE_HEAD_OR_HISTORY_CHANGED")
    facts["archive_unchanged_observed"] = archive_stable
    if reasons:
        return report(tuple(reasons), **facts)
    fingerprint = sha(
        canonical(
            [
                VERSION,
                build_id_pin,
                expected_archive_fingerprint,
                asdict(before),
                asdict(after),
                asdict(first),
                asdict(second),
                asdict(comparison),
            ]
        ).encode()
    )
    return ResearchIvRevalidation(
        VERSION,
        build_id_pin,
        expected_archive_fingerprint,
        "matched_current_research_iv",
        ("EXACT_ARCHIVED_IV_AND_CURRENT_NATIVE_RECOMPUTATION_MATCH",),
        exact_recording_reproduced=True,
        evidence_fingerprint=fingerprint,
        **facts,
    )
