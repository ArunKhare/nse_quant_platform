"""Bounded two-pass current native assembly, NOT persistence or feature publication."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_bundle import (
    MAX_MEMBERS,
    IvBundleMember,
    ResearchIvBundle,
    canonical,
    make_research_iv_bundle,
    pin,
    sha,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_revalidation import ResearchIvRevalidation

VERSION = "native-research-iv-bundle-assembly@1"
MAX_PASS_BYTES = 8388608


@dataclass(frozen=True)
class IvBundleRequest:
    build_id: str
    expected_archive_fingerprint: str

    def __post_init__(self) -> None:
        if not pin(self.build_id) or not pin(self.expected_archive_fingerprint):
            raise ValueError("EXACT_IV_BUNDLE_BUILD_AND_ARCHIVE_PINS_REQUIRED")


@dataclass(frozen=True)
class NativeIvBundleAssembly:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    requests: tuple[IvBundleRequest, ...]
    first_pass: tuple[ResearchIvRevalidation, ...]
    second_pass: tuple[ResearchIvRevalidation, ...]
    bundle: ResearchIvBundle | None = None
    all_members_revalidated: bool = False
    evidence_fingerprint: str | None = None
    publication_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    option_underlying_identity_binding_verified: bool = False
    scenario_terms_authoritative: bool = False
    model_suitability_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    canonical_contract_id: None = None
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def assemble_native_research_iv_bundle(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    *,
    requests: tuple[IvBundleRequest, ...],
) -> NativeIvBundleAssembly:
    """Read only, no imports of caller evidence DTOs, no partial or old-good bundle.

    Full forward pass then reverse pass; retain every returned negative observation.
    Equality of repeated observations is NOT atomic multi-database/time coherence.
    """
    from nse_quant.data_platform import research_iv_revalidation as current
    from nse_quant.data_platform import research_iv_store as archive_store

    if (
        current.VERSION != "research-iv-current-source-revalidation@1"
        or archive_store.VERSION != "audited-research-iv-builds@1"
    ):
        raise ValueError("UNSUPPORTED_IV_BUNDLE_REVALIDATION_VERSION")
    if type(requests) is not tuple or not 1 <= len(requests) <= MAX_MEMBERS:
        raise ValueError("BOUNDED_IMMUTABLE_NATIVE_IV_BUNDLE_REQUESTS_REQUIRED")
    validated: list[IvBundleRequest] = []
    for item in requests:
        if type(item) is not IvBundleRequest:
            raise TypeError("TYPED_NATIVE_IV_BUNDLE_REQUEST_REQUIRED")
        validated.append(IvBundleRequest(item.build_id, item.expected_archive_fingerprint))
    ordered = tuple(sorted(validated, key=lambda item: item.build_id))
    if len({item.build_id for item in ordered}) != len(ordered):
        raise ValueError("IV_BUNDLE_DUPLICATE_OR_CONFLICTING_BUILD_REQUEST")

    def observe(reverse: bool = False) -> tuple[current.ResearchIvRevalidation, ...]:
        results: dict[str, current.ResearchIvRevalidation] = {}
        total = 0
        for item in reversed(ordered) if reverse else ordered:
            result = current.revalidate_research_iv_build(
                bronze,
                frame_silver,
                reference_silver,
                assessments,
                source_gold,
                archive,
                build_id_pin=item.build_id,
                expected_archive_fingerprint=item.expected_archive_fingerprint,
            )
            total += len(canonical(asdict(result)).encode())
            if total > MAX_PASS_BYTES:
                raise ValueError("NATIVE_IV_BUNDLE_OBSERVATION_PASS_BYTE_LIMIT")
            results[item.build_id] = result
        return tuple(results[item.build_id] for item in ordered)

    def complete(value: current.ResearchIvRevalidation, request: IvBundleRequest) -> bool:
        return (
            type(value) is current.ResearchIvRevalidation
            and value.version == current.VERSION
            and value.build_id == request.build_id
            and value.expected_archive_fingerprint == request.expected_archive_fingerprint
            and value.status == "matched_current_research_iv"
            and all(
                x is True
                for x in (
                    value.archived_recording_verified,
                    value.current_source_checked,
                    value.exact_recording_reproduced,
                    value.archive_unchanged_observed,
                )
            )
            and pin(value.evidence_fingerprint)
            and value.archive_before is not None
            and value.archive_after is not None
            and value.fresh_before is not None
            and value.fresh_after is not None
            and value.comparison is not None
            and value.comparison.all_observations_match is True
            and value.canonical_contract_id is None
            and all(
                x is False
                for x in (
                    value.publication_asserted,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.scenario_terms_authoritative,
                    value.option_underlying_identity_binding_verified,
                    value.decision_eligibility_asserted,
                    value.atomic_cross_database_snapshot_asserted,
                )
            )
        )

    first, second = observe(), observe(reverse=True)
    reasons: list[str] = []
    for request, before, after in zip(ordered, first, second, strict=True):
        if not complete(before, request) or not complete(after, request):
            reasons.append("IV_BUNDLE_MEMBER_NOT_COMPLETE_IN_BOTH_PASSES")
        if asdict(before) != asdict(after):
            reasons.append("IV_BUNDLE_WHOLE_SET_OBSERVATION_DRIFT")
    if reasons:
        return NativeIvBundleAssembly(
            VERSION, "review_required", tuple(dict.fromkeys(reasons)), ordered, first, second
        )
    members: list[IvBundleMember] = []
    definition_pin = sha(archive_store._definition().encode())
    for item in first:
        archived, fresh = item.archive_before, item.fresh_before
        if (
            archived is None
            or fresh is None
            or fresh.calculation is None
            or not isinstance(item.evidence_fingerprint, str)
        ):
            raise ValueError("IV_BUNDLE_COMPLETE_MEMBER_PROJECTION_MISSING")
        members.append(
            IvBundleMember(
                item.build_id,
                archived.input_id,
                definition_pin,
                item.expected_archive_fingerprint,
                item.evidence_fingerprint,
                fresh.option_build_id,
                fresh.spot_build_id,
                fresh.scenario_terms_sha256,
                canonical(asdict(fresh.calculation)),
                archived.terms_json,
                fresh.source_option_event_ts,
                fresh.source_spot_event_ts,
            )
        )
    scopes = [
        (item.option_build_id, item.spot_build_id, item.scenario_terms_sha256) for item in members
    ]
    if len(set(scopes)) != len(scopes):
        return NativeIvBundleAssembly(
            VERSION,
            "review_required",
            ("IV_BUNDLE_DUPLICATE_EXACT_SCENARIO_ROLE_SCOPE",),
            ordered,
            first,
            second,
        )
    bundle = make_research_iv_bundle(tuple(members))
    fingerprint = sha(
        canonical(
            [
                VERSION,
                [asdict(item) for item in ordered],
                [asdict(item) for item in first],
                [asdict(item) for item in second],
                bundle.bundle_id,
            ]
        ).encode()
    )
    return NativeIvBundleAssembly(
        VERSION,
        "assembled_current_research_iv_bundle",
        ("ALL_EXACT_MEMBERS_MATCHED_IN_TWO_FULL_PASSES",),
        ordered,
        first,
        second,
        bundle,
        True,
        fingerprint,
    )
