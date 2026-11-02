"""Read-only exact archived research-IV bundle/current native source revalidation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_bundle_observation import (
    MAX_OBSERVATION_BYTES,
    IvBundleObservationComparison,
    compare_iv_bundle_observations,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.native_research_iv_bundle import NativeIvBundleAssembly
    from nse_quant.data_platform.research_iv_bundle_store import ResearchIvBundleArchive

VERSION = "research-iv-bundle-current-source-revalidation@1"


@dataclass(frozen=True)
class ResearchIvBundleRevalidation:
    version: str
    build_id: str
    expected_archive_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    archive_before: ResearchIvBundleArchive | None = None
    archive_after: ResearchIvBundleArchive | None = None
    fresh_before: NativeIvBundleAssembly | None = None
    fresh_after: NativeIvBundleAssembly | None = None
    comparison: IvBundleObservationComparison | None = None
    archived_recording_verified: bool = False
    current_source_checked: bool = False
    exact_recording_reproduced: bool = False
    archive_unchanged_observed: bool = False
    all_members_revalidated: bool = False
    bundle_id: str | None = None
    evidence_fingerprint: str | None = None
    publication_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    option_underlying_identity_binding_verified: bool = False
    scenario_terms_authoritative: bool = False
    model_suitability_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None


def revalidate_research_iv_bundle(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    bundle_archive: Any,
    *,
    build_id_pin: str,
    expected_archive_fingerprint: str,
) -> ResearchIvBundleRevalidation:
    """Reconstruct reviewed member requests from the exact verified archive record.

    Two actual native whole-set assemblies, each already forward/reverse pass,
    bracketed by archive observations. No caller bundle DTO, writes or repairs.
    Any unexpected exception propagates: no partial accepted return or fallback.
    """
    from nse_quant.data_platform import native_research_iv_bundle as native
    from nse_quant.data_platform import research_iv_bundle as codec
    from nse_quant.data_platform import research_iv_bundle_archive_record as record
    from nse_quant.data_platform import research_iv_bundle_store as store

    if (
        store.VERSION != "audited-research-iv-bundles@1"
        or record.VERSION != "research-iv-bundle-archive-record@1"
        or native.VERSION != "native-research-iv-bundle-assembly@1"
        or codec.VERSION != "research-iv-feature-bundle@1"
        or record.MAX_RESULT_BYTES != MAX_OBSERVATION_BYTES
    ):
        raise ValueError("UNSUPPORTED_IV_BUNDLE_REVALIDATION_DEPENDENCY_VERSION")
    if not record.pin(build_id_pin) or not record.pin(expected_archive_fingerprint):
        raise ValueError("EXACT_IV_BUNDLE_RECORD_AND_ARCHIVE_FINGERPRINT_REQUIRED")
    paths = store._paths(bundle_archive)
    for source in (bronze, frame_silver, reference_silver, assessments, source_gold, archive):
        if source is bundle_archive or any(
            a == b or a.samefile(b) for a in paths for b in store._paths(source)
        ):
            raise ValueError("SEPARATE_IV_BUNDLE_REVALIDATION_ARCHIVE_REQUIRED")

    def report(reasons: tuple[str, ...], **facts: Any) -> ResearchIvBundleRevalidation:
        return ResearchIvBundleRevalidation(
            VERSION,
            build_id_pin,
            expected_archive_fingerprint,
            "review_required",
            reasons,
            **facts,
        )

    def complete_archive(value: store.ResearchIvBundleArchive) -> bool:
        return (
            type(value) is store.ResearchIvBundleArchive
            and value.version == store.VERSION
            and value.build_id == value.retained_head_build_id == build_id_pin
            and value.status == "verified_archived_head"
            and value.archived_recording_verified is True
            and value.current_source_checked is False
            and value.publication_asserted is False
            and value.decision_eligibility_asserted is False
            and value.canonical_contract_id is None
            and record.pin(value.input_id)
            and record.pin(value.evidence_fingerprint)
        )

    try:
        before = store.read_research_iv_bundle_archive(bundle_archive, build_id_pin=build_id_pin)
    except store.IvBundleArchiveReviewRequired:
        return report(("IV_BUNDLE_ARCHIVE_OR_AUDIT_NOT_COMPLETE_BEFORE",))
    if not complete_archive(before) or before.evidence_fingerprint != expected_archive_fingerprint:
        return report(("IV_BUNDLE_PIN_NOT_REVIEWED_EXACT_ARCHIVED_HEAD",), archive_before=before)
    definition_hash = record.sha(store._definition().encode())
    if (
        record.scope_id(before.requests_json, definition_hash) != before.input_id
        or record.record_id(before.input_id, before.result_json, before.requests_json)
        != build_id_pin
    ):
        raise ValueError("IV_BUNDLE_ARCHIVED_INPUT_OR_RESULT_PIN_MISMATCH")
    recorded = record.result_value(before.result_json, before.requests_json)
    if (
        before.recorded_result_status != "assembled_current_research_iv_bundle"
        or recorded["status"] != "assembled_current_research_iv_bundle"
    ):
        return report(
            ("RECORDED_IV_BUNDLE_REVIEW_CANNOT_BE_PROMOTED",),
            archive_before=before,
            archived_recording_verified=True,
        )
    requests = tuple(
        native.IvBundleRequest(item["build_id"], item["expected_archive_fingerprint"])
        for item in record.requests_value(before.requests_json)
    )

    def observe() -> tuple[native.NativeIvBundleAssembly, str, bool]:
        value = native.assemble_native_research_iv_bundle(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            source_gold,
            archive,
            requests=requests,
        )
        if type(value) is not native.NativeIvBundleAssembly:
            raise ValueError("IV_BUNDLE_FRESH_NATIVE_RESULT_TYPE_REQUIRED")
        raw = record.canonical(asdict(value))
        # Validates negatives as well: no negative observation is discarded.
        checked = record.result_value(raw, before.requests_json)
        complete = (
            checked["status"] == "assembled_current_research_iv_bundle"
            and value.all_members_revalidated is True
            and value.bundle is not None
        )
        return value, raw, complete

    first, first_raw, first_complete = observe()
    second, second_raw, second_complete = observe()
    comparison = compare_iv_bundle_observations(
        before.result_json.encode(),
        first_raw.encode(),
        second_raw.encode(),
    )
    reasons = list(comparison.reason_codes)
    if not first_complete or not second_complete:
        reasons.append("IV_BUNDLE_FRESH_NATIVE_ASSEMBLY_NOT_COMPLETE")
    facts: dict[str, Any] = dict(
        archive_before=before,
        fresh_before=first,
        fresh_after=second,
        comparison=comparison,
        archived_recording_verified=True,
        current_source_checked=True,
    )
    try:
        after = store.read_research_iv_bundle_archive(bundle_archive, build_id_pin=build_id_pin)
    except store.IvBundleArchiveReviewRequired:
        reasons.append("IV_BUNDLE_ARCHIVE_OR_AUDIT_NOT_COMPLETE_AFTER")
        return report(tuple(reasons), **facts)
    facts["archive_after"] = after
    # Compare entire DTO, not merely bundle ID, status, or IV values.
    stable = complete_archive(after) and asdict(before) == asdict(after)
    facts["archive_unchanged_observed"] = stable
    if not stable:
        reasons.append("IV_BUNDLE_ARCHIVE_HEAD_OR_HISTORY_CHANGED")
    if reasons:
        return report(tuple(reasons), **facts)
    if first.bundle is None:
        raise ValueError("IV_BUNDLE_COMPLETE_ASSEMBLY_BUNDLE_MISSING")
    # Hash canonical observation bytes separately to avoid another huge combined copy.
    # Full DTOs remain in the returned observation, including every source clock.
    fingerprint = record.sha(
        record.canonical(
            [
                VERSION,
                build_id_pin,
                expected_archive_fingerprint,
                record.sha(record.canonical(asdict(before)).encode()),
                record.sha(record.canonical(asdict(after)).encode()),
                asdict(comparison),
                first.bundle.bundle_id,
            ]
        ).encode()
    )
    return ResearchIvBundleRevalidation(
        VERSION,
        build_id_pin,
        expected_archive_fingerprint,
        "matched_current_research_iv_bundle",
        ("EXACT_ARCHIVED_BUNDLE_AND_TWO_CURRENT_NATIVE_ASSEMBLIES_MATCH",),
        exact_recording_reproduced=True,
        all_members_revalidated=True,
        bundle_id=first.bundle.bundle_id,
        evidence_fingerprint=fingerprint,
        **facts,
    )
