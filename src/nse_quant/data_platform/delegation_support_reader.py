"""Read-only current native storage support for every signed delegation reference."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.delegation_reference_coverage import (
    ReferenceCoverage,
    plan_reference_coverage,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_jsonl_support_reader import JsonlSupportEvidence
    from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
    from nse_quant.data_platform.delegation_native_reader import DelegationNativeBinding
    from nse_quant.data_platform.delegation_review import DelegationInput, DelegationReviewSet
    from nse_quant.data_platform.signed_policy_window import SignedPolicyInput
    from nse_quant.data_platform.statement_scope_policy import ScopeQuery
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

VERSION = "delegation-signed-reference-storage@1"


@dataclass(frozen=True)
class DelegationReferenceSource:
    bronze: Any
    support: BronzeSupportPin
    original_plan: bytes
    expected_plan_sha256: str


@dataclass(frozen=True)
class DelegationSupportEvidence:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    review: DelegationReviewSet
    coverage: ReferenceCoverage | None = None
    support_before: tuple[JsonlSupportEvidence, ...] = ()
    support_after: tuple[JsonlSupportEvidence, ...] = ()
    native_before: DelegationNativeBinding | None = None
    native_after: DelegationNativeBinding | None = None
    all_signed_reference_storage_verified: bool = False
    evidence_fingerprint: str | None = None
    reference_content_semantics_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    reviewer_identities_authenticated: bool = False
    internal_authorization_asserted: bool = False
    policy_authority_authenticated: bool = False
    external_issuer_authority_verified: bool = False
    namespace_authority_verified: bool = False
    issuer_authenticated: bool = False
    identity_verified: bool = False
    authorized_revocation_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None
    atomic_cross_database_snapshot_asserted: bool = False


def inspect_delegation_reference_support(
    checkpoint: Any,
    registry: Any,
    bronze: Any,
    proof_bronze: Any,
    *,
    declarations: tuple[DelegationInput, ...],
    expected_model: str,
    reference_sources: tuple[DelegationReferenceSource, ...],
    policy_id: str,
    expected_checkpoint_id: str,
    expected_history_fingerprint: str,
    recording_query: ScopeQuery,
    assertion_id: str,
    request: UnderlyingAssertionRequest,
    record_id: str,
    original_plan: bytes,
    expected_plan_sha256: str,
    payload: bytes,
    proof_support: BronzeSupportPin,
    proof_plan: bytes,
    expected_proof_plan_sha256: str,
    expected_public_key_sha256: str,
    snapshots: tuple[SignedPolicyInput, ...],
    governance_public_key: bytes,
    expected_governance_key_sha256: str,
) -> DelegationSupportEvidence:
    """Every signed slot requires exactly one reviewed native source/plan binding.

    No caller DTOs, cached-success reuse, source discovery or format/authority
    inference. Internal model only can match; external and disputes remain blocked.
    """
    from nse_quant.data_platform import bronze_jsonl_support_reader as jsonl
    from nse_quant.data_platform import bronze_support_reader as source
    from nse_quant.data_platform import delegation_native_reader as native
    from nse_quant.data_platform import delegation_review as review_codec
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform.checkpoint_observation import hash_pin, observation_digest

    if (
        review_codec.VERSION != "delegation-review-evidence@1"
        or native.VERSION != "delegation-review-native-binding@1"
        or jsonl.VERSION != "bronze-jsonl-support-consumer@1"
        or source.VERSION != "pinned-bronze-support-storage@1"
    ):
        raise ValueError("UNSUPPORTED_DELEGATION_REFERENCE_DEPENDENCY_VERSION")
    if type(request) is not kernel.UnderlyingAssertionRequest:
        raise TypeError("TYPED_DELEGATION_REFERENCE_REQUEST_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
    target = review_codec.DelegationTarget(
        checked.namespace,
        checked.asset_kind,
        policy_id,
        expected_governance_key_sha256,
        expected_checkpoint_id,
        expected_history_fingerprint,
    )
    review = review_codec.assess_delegation_review_set(
        declarations,
        expected_model=expected_model,
        expected_target=target,
    )
    if not review.internal_review_constraints_satisfied:
        return DelegationSupportEvidence(VERSION, "review_required", review.reason_codes, review)

    def key(pin: source.BronzeSupportPin) -> str:
        return hashlib.sha256(
            json.dumps(asdict(pin), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    expected: list[str] = []
    # Projection only after ALL actual signed packets have passed native schema/crypto checks.
    for declaration in declarations:
        for value in json.loads(declaration.document)["evidence_refs"]:
            expected.append(key(source.BronzeSupportPin(**value)))
    if type(reference_sources) is not tuple or len(reference_sources) > 64:
        raise ValueError("BOUNDED_IMMUTABLE_REFERENCE_SOURCE_INPUTS_REQUIRED")
    validated: list[DelegationReferenceSource] = []
    total = 0
    for item in reference_sources:
        if (
            type(item) is not DelegationReferenceSource
            or type(item.support) is not source.BronzeSupportPin
            or type(item.original_plan) is not bytes
            or not 0 < len(item.original_plan) <= 65536
            or not hash_pin(item.expected_plan_sha256)
        ):
            raise ValueError("TYPED_BOUNDED_REFERENCE_SOURCE_AND_PLAN_REQUIRED")
        support = source.BronzeSupportPin(**asdict(item.support))
        validated.append(
            DelegationReferenceSource(
                item.bronze, support, item.original_plan, item.expected_plan_sha256
            )
        )
        total += len(item.original_plan)
    if total > 4194304:
        raise ValueError("DELEGATION_REFERENCE_PLAN_AGGREGATE_LIMIT")
    coverage = plan_reference_coverage(tuple(expected), tuple(key(x.support) for x in validated))
    if not coverage.exact_coverage:
        return DelegationSupportEvidence(
            VERSION, "review_required", coverage.reason_codes, review, coverage
        )

    def observe_sources() -> tuple[jsonl.JsonlSupportEvidence, ...]:
        return tuple(
            jsonl.inspect_jsonl_bronze_support(
                item.bronze,
                support=item.support,
                plan_bytes=item.original_plan,
                expected_plan_sha256=item.expected_plan_sha256,
            )
            for item in validated
        )

    def complete(value: jsonl.JsonlSupportEvidence) -> bool:
        return (
            type(value) is jsonl.JsonlSupportEvidence
            and value.version == jsonl.VERSION
            and value.status == "verified_jsonl_recomputation"
            and value.artifact_to_event_semantics_verified is True
            and value.original_plan_binding_verified is True
            and hash_pin(value.evidence_fingerprint)
            and all(
                flag is False
                for flag in (
                    value.identity_semantics_verified,
                    value.source_acquisition_authenticity_asserted,
                    value.issuer_authenticated,
                    value.identity_verified,
                    value.retry_link_coverage_verified,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                    value.atomic_cross_database_snapshot_asserted,
                )
            )
        )

    before = observe_sources()
    if not all(complete(item) for item in before):
        return DelegationSupportEvidence(
            VERSION,
            "review_required",
            ("SIGNED_REFERENCE_SUPPORT_NOT_COMPLETE_BEFORE",),
            review,
            coverage,
            before,
        )

    def observe_native() -> native.DelegationNativeBinding:
        return native.inspect_delegation_native_binding(
            checkpoint,
            registry,
            bronze,
            proof_bronze,
            declarations=declarations,
            expected_model=expected_model,
            policy_id=policy_id,
            expected_checkpoint_id=expected_checkpoint_id,
            expected_history_fingerprint=expected_history_fingerprint,
            recording_query=recording_query,
            assertion_id=assertion_id,
            request=checked,
            record_id=record_id,
            original_plan=original_plan,
            expected_plan_sha256=expected_plan_sha256,
            payload=payload,
            proof_support=proof_support,
            proof_plan=proof_plan,
            expected_proof_plan_sha256=expected_proof_plan_sha256,
            expected_public_key_sha256=expected_public_key_sha256,
            snapshots=snapshots,
            governance_public_key=governance_public_key,
            expected_governance_key_sha256=expected_governance_key_sha256,
        )

    def complete_native(value: native.DelegationNativeBinding) -> bool:
        return (
            type(value) is native.DelegationNativeBinding
            and value.version == native.VERSION
            and value.status == "internal_review_evidence_bound_to_native_checkpoint"
            and value.internal_review_evidence_bound is True
            and hash_pin(value.evidence_fingerprint)
            and value.review == review
            and value.canonical_underlying_id is None
            and all(
                flag is False
                for flag in (
                    value.internal_authorization_asserted,
                    value.supporting_bronze_refs_checked,
                    value.reviewer_identities_authenticated,
                    value.policy_authority_authenticated,
                    value.external_issuer_authority_verified,
                    value.namespace_authority_verified,
                    value.issuer_authenticated,
                    value.identity_verified,
                    value.authorized_revocation_asserted,
                    value.decision_eligibility_asserted,
                )
            )
        )

    first, second = observe_native(), observe_native()
    after = observe_sources()
    reasons: list[str] = []
    if not all(complete(item) for item in after) or asdict_sequence(before) != asdict_sequence(
        after
    ):
        reasons.append("SIGNED_REFERENCE_SUPPORT_CHANGED_OR_INCOMPLETE_AFTER")
    if not complete_native(first) or not complete_native(second):
        reasons.append("SUPPORTED_DELEGATION_NATIVE_BINDING_NOT_COMPLETE")
    if observation_digest(asdict(first)) != observation_digest(asdict(second)):
        reasons.append("SUPPORTED_DELEGATION_NATIVE_OBSERVATION_DRIFT")
    if reasons:
        return DelegationSupportEvidence(
            VERSION,
            "review_required",
            tuple(reasons),
            review,
            coverage,
            before,
            after,
            first,
            second,
        )
    fingerprint = observation_digest(
        [
            VERSION,
            asdict(review),
            asdict(coverage),
            [[asdict(x.support), x.expected_plan_sha256] for x in validated],
            asdict_sequence(before),
            asdict_sequence(after),
            asdict(first),
            asdict(second),
        ]
    )
    return DelegationSupportEvidence(
        VERSION,
        "signed_delegation_references_storage_linked",
        ("ALL_SIGNED_REFERENCES_AND_NATIVE_DELEGATION_OBSERVATIONS_MATCH",),
        review,
        coverage,
        before,
        after,
        first,
        second,
        True,
        fingerprint,
    )


def asdict_sequence(values: tuple[JsonlSupportEvidence, ...]) -> list[dict[str, Any]]:
    return [asdict(item) for item in values]
