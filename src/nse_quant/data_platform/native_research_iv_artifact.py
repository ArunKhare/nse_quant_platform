"""Fresh-native research-IV artifact materialization, explicitly NOT audited staging."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_artifact_files import (
    MAX_BYTES,
    ResearchIvArtifactFiles,
    valid_pin,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_bundle_revalidation import ResearchIvBundleRevalidation

VERSION = "native-research-iv-artifact-materialization@1"


@dataclass(frozen=True)
class ResearchIvArtifactMaterialization:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    archive_record_id: str
    expected_archive_fingerprint: str
    expected_bundle_id: str
    expected_revalidation_fingerprint: str
    before: ResearchIvBundleRevalidation
    after: ResearchIvBundleRevalidation | None = None
    artifact_written: bool = False
    artifact_bytes_rechecked: bool = False
    artifact_name: str | None = None
    audited_stage_recorded: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    option_underlying_identity_binding_verified: bool = False
    scenario_terms_authoritative: bool = False
    model_suitability_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    canonical_contract_id: None = None
    event_ts: None = None
    published_at: None = None


def materialize_research_iv_artifact(
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
    expected_bundle_id: str,
    expected_revalidation_fingerprint: str,
    artifact_root: Path,
    initialize: bool = False,
) -> ResearchIvArtifactMaterialization:
    """Caller supplies reviewed pins only, never a verified/result DTO.

    File visibility is NOT staging acceptance. Two real whole-service observations
    bracket the write. Any negative/changed after-observation leaves a review-only
    unbound artifact; exceptions can likewise leave an orphan. Never adopt/retry it.
    """
    from nse_quant.data_platform import research_iv_bundle as codec
    from nse_quant.data_platform import research_iv_bundle_revalidation as current
    from nse_quant.data_platform import research_iv_bundle_store as store

    if (
        current.VERSION != "research-iv-bundle-current-source-revalidation@1"
        or codec.VERSION != "research-iv-feature-bundle@1"
        or store.VERSION != "audited-research-iv-bundles@1"
        or codec.MAX_BUNDLE_BYTES != MAX_BYTES
    ):
        raise ValueError("UNSUPPORTED_IV_ARTIFACT_DEPENDENCY_VERSION")
    if type(initialize) is not bool or not all(
        valid_pin(value)
        for value in (
            build_id_pin,
            expected_archive_fingerprint,
            expected_bundle_id,
            expected_revalidation_fingerprint,
        )
    ):
        raise ValueError("EXACT_REVIEWED_IV_ARTIFACT_PINS_REQUIRED")
    files = ResearchIvArtifactFiles(artifact_root)
    files._parents()
    output = files.root.resolve()
    database_paths: list[Path] = []
    for conn in (
        bronze,
        frame_silver,
        reference_silver,
        assessments,
        source_gold,
        archive,
        bundle_archive,
    ):
        for path in store._paths(conn):
            selected = path.resolve()
            database_paths.append(selected)
            if output == selected or output in selected.parents or selected in output.parents:
                raise ValueError("IV_ARTIFACT_ROOT_MUST_BE_SEPARATE_FROM_DATABASES")

    if files.root.exists():
        files._root()
        for child in files.root.iterdir():
            if any(child.samefile(path) for path in database_paths):
                raise ValueError("IV_ARTIFACT_FILE_ALIASES_DATABASE")

    def observe() -> current.ResearchIvBundleRevalidation:
        return current.revalidate_research_iv_bundle(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            source_gold,
            archive,
            bundle_archive,
            build_id_pin=build_id_pin,
            expected_archive_fingerprint=expected_archive_fingerprint,
        )

    def complete(value: current.ResearchIvBundleRevalidation) -> bool:
        return (
            type(value) is current.ResearchIvBundleRevalidation
            and value.version == current.VERSION
            and value.status == "matched_current_research_iv_bundle"
            and value.build_id == build_id_pin
            and value.expected_archive_fingerprint == expected_archive_fingerprint
            and value.bundle_id == expected_bundle_id
            and value.evidence_fingerprint == expected_revalidation_fingerprint
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
            and value.canonical_contract_id is None
            and all(
                getattr(value, key) is False
                for key in (
                    "publication_asserted",
                    "availability_evidence_verified",
                    "historical_validity_asserted",
                    "option_underlying_identity_binding_verified",
                    "scenario_terms_authoritative",
                    "model_suitability_verified",
                    "source_acquisition_authenticity_asserted",
                    "atomic_cross_database_snapshot_asserted",
                    "decision_eligibility_asserted",
                )
            )
            and value.archive_before is not None
            and value.archive_after is not None
            and value.fresh_before is not None
            and value.fresh_after is not None
            and value.comparison is not None
            and value.comparison.all_observations_match is True
        )

    before = observe()
    if type(before) is not current.ResearchIvBundleRevalidation:
        raise ValueError("TYPED_IV_ARTIFACT_NATIVE_OBSERVATION_REQUIRED")
    common: dict[str, Any] = dict(
        version=VERSION,
        archive_record_id=build_id_pin,
        expected_archive_fingerprint=expected_archive_fingerprint,
        expected_bundle_id=expected_bundle_id,
        expected_revalidation_fingerprint=expected_revalidation_fingerprint,
        before=before,
    )
    if not complete(before):
        return ResearchIvArtifactMaterialization(
            status="review_required",
            reason_codes=("IV_ARTIFACT_REVIEWED_NATIVE_PIN_NOT_MATCHED",),
            **common,
        )
    if before.fresh_before is None or before.fresh_before.bundle is None:
        raise ValueError("IV_ARTIFACT_NATIVE_BUNDLE_MISSING")
    raw = codec.encode_research_iv_bundle(before.fresh_before.bundle)
    codec.decode_research_iv_bundle(raw, expected_bundle_id=expected_bundle_id)
    if initialize:
        files.initialize()
    files.write_new(raw, bundle_id=expected_bundle_id)
    after = observe()
    if type(after) is not current.ResearchIvBundleRevalidation:
        raise ValueError("TYPED_IV_ARTIFACT_NATIVE_OBSERVATION_REQUIRED")
    unchanged = complete(after) and asdict(before) == asdict(after)
    exact = files.read_exact(expected_bundle_id) == raw
    return ResearchIvArtifactMaterialization(
        status="materialized_research_iv_artifact_not_staged"
        if unchanged and exact
        else "review_required",
        reason_codes=("IMMUTABLE_RESEARCH_ARTIFACT_NOT_AUDITED_STAGE",)
        if unchanged and exact
        else ("IV_ARTIFACT_AFTER_OBSERVATION_OR_BYTES_CHANGED",),
        after=after,
        artifact_written=True,
        artifact_bytes_rechecked=exact,
        artifact_name=files.path(expected_bundle_id).name,
        **common,
    )
