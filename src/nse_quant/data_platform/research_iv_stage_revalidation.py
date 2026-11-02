"""Read-only current-source consumption of an exact reviewed first-stage binding."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_stage_observation import (
    MAX_ARTIFACT_BYTES,
    MAX_NATIVE_BYTES,
    IvStageObservationComparison,
    compare_iv_stage_observations,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_bundle_revalidation import ResearchIvBundleRevalidation
    from nse_quant.data_platform.research_iv_first_stage import ResearchIvFirstStage

VERSION = "research-iv-first-stage-current-source-revalidation@1"


@dataclass(frozen=True)
class ResearchIvCurrentStage:
    version: str
    stage_build_id: str
    expected_stage_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    stage_before: ResearchIvFirstStage | None = None
    stage_after: ResearchIvFirstStage | None = None
    fresh_before: ResearchIvBundleRevalidation | None = None
    fresh_after: ResearchIvBundleRevalidation | None = None
    comparison: IvStageObservationComparison | None = None
    archived_stage_recording_verified: bool = False
    current_source_checked: bool = False
    recorded_native_digests_matched: bool = False
    artifact_bytes_matched: bool = False
    stage_unchanged_observed: bool = False
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
    event_ts: None = None
    published_at: None = None


def revalidate_research_iv_first_stage(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    bundle_archive: Any,
    staging: Any,
    *,
    stage_build_id_pin: str,
    expected_stage_fingerprint: str,
    artifact_root: Path,
) -> ResearchIvCurrentStage:
    """No writes, caller DTOs, pin refresh, adoption or admission. Errors fail closed.

    Original binding holds complete-observation digests, NOT retained full replay
    bytes. Compare actual current native bytes with each other and their frozen
    digests; compare actual fresh canonical bundle bytes with both artifact reads.
    """
    from nse_quant.data_platform import research_iv_artifact_files as files_api
    from nse_quant.data_platform import research_iv_bundle as codec
    from nse_quant.data_platform import research_iv_bundle_revalidation as current
    from nse_quant.data_platform import research_iv_first_stage as store
    from nse_quant.data_platform import research_iv_stage_record as record

    if (
        store.VERSION != "audited-research-iv-first-stage@1"
        or record.VERSION != "research-iv-first-stage-record@1"
        or current.VERSION != "research-iv-bundle-current-source-revalidation@1"
        or codec.VERSION != "research-iv-feature-bundle@1"
        or files_api.VERSION != "research-iv-artifact-files@1"
        or codec.MAX_BUNDLE_BYTES != MAX_ARTIFACT_BYTES
        or files_api.MAX_BYTES != MAX_ARTIFACT_BYTES
        or record.MAX_RECORD_BYTES != 8192
    ):
        raise ValueError("UNSUPPORTED_CURRENT_IV_STAGE_DEPENDENCY_PROFILE")
    if not record.pin(stage_build_id_pin) or not record.pin(expected_stage_fingerprint):
        raise ValueError("EXACT_REVIEWED_IV_STAGE_ID_AND_FINGERPRINT_REQUIRED")
    files = files_api.ResearchIvArtifactFiles(artifact_root)
    files._parents()
    inputs = (
        bronze,
        frame_silver,
        reference_silver,
        assessments,
        source_gold,
        archive,
        bundle_archive,
    )
    stage_paths = store._paths(staging)
    for conn in inputs:
        if conn is staging or any(
            a == b or a.samefile(b) for a in stage_paths for b in store._paths(conn)
        ):
            raise ValueError("SEPARATE_CURRENT_IV_STAGE_DATABASE_REQUIRED")
    paths = [path for conn in (*inputs, staging) for path in store._paths(conn)]
    resolved_root = artifact_root.resolve()
    for path in paths:
        path = path.resolve()
        if resolved_root == path or resolved_root in path.parents or path in resolved_root.parents:
            raise ValueError("CURRENT_IV_STAGE_ARTIFACT_DATABASE_OVERLAP")
    files._root()
    if any(child.samefile(path) for child in artifact_root.iterdir() for path in paths):
        raise ValueError("CURRENT_IV_STAGE_ARTIFACT_DATABASE_HARDLINK")

    def report(reasons: tuple[str, ...], **facts: Any) -> ResearchIvCurrentStage:
        return ResearchIvCurrentStage(
            VERSION,
            stage_build_id_pin,
            expected_stage_fingerprint,
            "review_required",
            reasons,
            **facts,
        )

    def read_stage() -> store.ResearchIvFirstStage:
        return store.read_research_iv_first_stage(
            staging,
            build_id_pin=stage_build_id_pin,
            artifact_root=artifact_root,
        )

    def complete_stage(value: store.ResearchIvFirstStage) -> bool:
        return (
            type(value) is store.ResearchIvFirstStage
            and value.version == store.VERSION
            and value.build_id == stage_build_id_pin
            and value.status == "verified_research_stage_recording"
            and value.archived_stage_recording_verified is True
            and value.artifact_bytes_checked is True
            and value.current_source_checked is False
            and value.publication_asserted is False
            and value.decision_eligibility_asserted is False
            and value.canonical_contract_id is None
            and record.pin(value.evidence_fingerprint)
        )

    try:
        before = read_stage()
    except store.IvFirstStageReviewRequired:
        return report(("IV_STAGE_ORIGINAL_RECORDING_NOT_COMPLETE_BEFORE",))
    if not complete_stage(before) or before.evidence_fingerprint != expected_stage_fingerprint:
        return report(("IV_STAGE_NOT_EXACT_REVIEWED_RECORDING",), stage_before=before)
    binding = record.decode(before.record_json)
    if record.build_id(before.record_json) != stage_build_id_pin or binding["artifact_root"] != str(
        artifact_root
    ):
        raise ValueError("CURRENT_IV_STAGE_BINDING_ID_OR_ROOT_MISMATCH")
    pins = binding["pins"]
    first_artifact = files.read_exact(pins[2])

    def observe() -> tuple[current.ResearchIvBundleRevalidation, bytes]:
        value = current.revalidate_research_iv_bundle(
            *inputs,
            build_id_pin=pins[0],
            expected_archive_fingerprint=pins[1],
        )
        if type(value) is not current.ResearchIvBundleRevalidation:
            raise ValueError("CURRENT_IV_STAGE_TYPED_NATIVE_OBSERVATION_REQUIRED")
        raw = record.canonical(asdict(value)).encode()
        if not 0 < len(raw) <= MAX_NATIVE_BYTES:
            raise ValueError("CURRENT_IV_STAGE_NATIVE_OBSERVATION_BYTE_LIMIT")
        return value, raw

    def complete_native(value: current.ResearchIvBundleRevalidation) -> bool:
        return (
            value.version == current.VERSION
            and value.status == "matched_current_research_iv_bundle"
            and (
                value.build_id,
                value.expected_archive_fingerprint,
                value.bundle_id,
                value.evidence_fingerprint,
            )
            == tuple(pins)
            and all(
                getattr(value, key) is True
                for key in (
                    "archived_recording_verified",
                    "current_source_checked",
                    "exact_recording_reproduced",
                    "archive_unchanged_observed",
                    "all_members_revalidated",
                )
            )
            and all(getattr(value, key) is False for key in record.FLAGS)
            and value.canonical_contract_id is None
            and value.archive_before is not None
            and value.archive_after is not None
            and value.fresh_before is not None
            and value.fresh_after is not None
            and value.comparison is not None
            and value.comparison.all_observations_match is True
        )

    first, first_raw = observe()
    second, second_raw = observe()
    last_artifact = files.read_exact(pins[2])
    comparison = compare_iv_stage_observations(
        first_raw,
        second_raw,
        first_artifact,
        last_artifact,
        recorded_before_sha256=binding["before_sha256"],
        recorded_after_sha256=binding["after_sha256"],
        expected_bundle_id=pins[2],
    )
    native_complete = complete_native(first) and complete_native(second)
    artifact_matches = len(first_artifact) == len(last_artifact) == binding["artifact_bytes"]
    for observed in (first, second):
        for assembled in (observed.fresh_before, observed.fresh_after):
            if (
                assembled is None
                or assembled.bundle is None
                or codec.encode_research_iv_bundle(assembled.bundle) != first_artifact
            ):
                artifact_matches = False
    artifact_matches = artifact_matches and first_artifact == last_artifact
    reasons = list(comparison.reason_codes)
    if not native_complete:
        reasons.append("CURRENT_IV_STAGE_NATIVE_OBSERVATION_NOT_COMPLETE")
    if not artifact_matches:
        reasons.append("CURRENT_IV_STAGE_NATIVE_BUNDLE_BYTES_DIFFER_FROM_ARTIFACT")
    native_digests_match = (
        native_complete
        and comparison.first_matches_recorded_digest
        and comparison.second_matches_recorded_digest
        and comparison.native_observations_match
    )
    artifact_bytes_match = (
        artifact_matches
        and comparison.first_artifact_matches_pin
        and comparison.second_artifact_matches_pin
    )
    facts: dict[str, Any] = dict(
        stage_before=before,
        fresh_before=first,
        fresh_after=second,
        comparison=comparison,
        archived_stage_recording_verified=True,
        current_source_checked=True,
        recorded_native_digests_matched=native_digests_match,
        artifact_bytes_matched=artifact_bytes_match,
    )
    try:
        after = read_stage()
    except store.IvFirstStageReviewRequired:
        reasons.append("IV_STAGE_ORIGINAL_RECORDING_NOT_COMPLETE_AFTER")
        return report(tuple(reasons), **facts)
    stable = complete_stage(after) and asdict(before) == asdict(after)
    facts["stage_after"] = after
    facts["stage_unchanged_observed"] = stable
    if not stable:
        reasons.append("IV_STAGE_RECORDING_AUDIT_OR_ARTIFACT_CHANGED")
    if reasons:
        return report(tuple(reasons), **facts)
    fingerprint = record.sha(
        record.canonical(
            [
                VERSION,
                stage_build_id_pin,
                expected_stage_fingerprint,
                record.sha(record.canonical(asdict(before)).encode()),
                record.sha(record.canonical(asdict(after)).encode()),
                asdict(comparison),
                pins[2],
            ]
        ).encode()
    )
    return ResearchIvCurrentStage(
        VERSION,
        stage_build_id_pin,
        expected_stage_fingerprint,
        "matched_current_research_iv_stage",
        ("REVIEWED_STAGE_ARTIFACT_AND_FROZEN_NATIVE_DIGESTS_REPRODUCED",),
        bundle_id=pins[2],
        evidence_fingerprint=fingerprint,
        **facts,
    )
