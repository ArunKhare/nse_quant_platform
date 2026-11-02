"""Bind non-authoritative internal review evidence to checkpoint-native observations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.delegation_review import (
    DelegationInput,
    DelegationReviewSet,
    DelegationTarget,
    assess_delegation_review_set,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
    from nse_quant.data_platform.checkpoint_native_revalidation import CheckpointNativeRevalidation
    from nse_quant.data_platform.signed_policy_window import SignedPolicyInput
    from nse_quant.data_platform.statement_scope_policy import ScopeQuery
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

VERSION = "delegation-review-native-binding@1"


@dataclass(frozen=True)
class DelegationNativeBinding:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    review: DelegationReviewSet
    native: CheckpointNativeRevalidation | None = None
    internal_review_evidence_bound: bool = False
    evidence_fingerprint: str | None = None
    internal_authorization_asserted: bool = False
    supporting_bronze_refs_checked: bool = False
    reviewer_identities_authenticated: bool = False
    policy_authority_authenticated: bool = False
    external_issuer_authority_verified: bool = False
    namespace_authority_verified: bool = False
    issuer_authenticated: bool = False
    identity_verified: bool = False
    authorized_revocation_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def inspect_delegation_native_binding(
    checkpoint: Any,
    registry: Any,
    bronze: Any,
    proof_bronze: Any,
    *,
    declarations: tuple[DelegationInput, ...],
    expected_model: str,
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
) -> DelegationNativeBinding:
    """Both models explicit; external claims cannot fall back to internal review.

    No root registration, approval persistence, evidence-ref lookup, identity or
    research authorization. Actual native result re-read, never accepted from caller.
    """
    from nse_quant.data_platform import checkpoint_native_revalidation as native
    from nse_quant.data_platform import underlying_assertion as kernel

    if native.VERSION != "checkpoint-pinned-native-policy-revalidation@1":
        raise ValueError("UNSUPPORTED_DELEGATION_NATIVE_DEPENDENCY_VERSION")
    if type(request) is not kernel.UnderlyingAssertionRequest:
        raise TypeError("EXACT_TYPED_DELEGATION_ASSERTION_REQUEST_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
    target = DelegationTarget(
        checked.namespace,
        checked.asset_kind,
        policy_id,
        expected_governance_key_sha256,
        expected_checkpoint_id,
        expected_history_fingerprint,
    )
    review = assess_delegation_review_set(
        declarations, expected_model=expected_model, expected_target=target
    )
    if not review.internal_review_constraints_satisfied:
        return DelegationNativeBinding(VERSION, "review_required", review.reason_codes, review)
    result = native.revalidate_checkpoint_native_policy(
        checkpoint,
        registry,
        bronze,
        proof_bronze,
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
    complete = (
        type(result) is native.CheckpointNativeRevalidation
        and result.version == native.VERSION
        and result.status == "retained_checkpoint_and_current_native_scope_bound"
        and result.exact_checkpoint_record_reproduced is True
        and result.retained_head_and_native_scope_bound is True
        and result.expected_checkpoint_id == expected_checkpoint_id
        and result.expected_history_fingerprint == expected_history_fingerprint
        and isinstance(result.evidence_fingerprint, str)
        and re.fullmatch(r"[a-f0-9]{64}", result.evidence_fingerprint) is not None
        and result.canonical_underlying_id is None
        and all(
            flag is False
            for flag in (
                result.policy_currentness_verified,
                result.policy_authority_authenticated,
                result.issuer_authenticated,
                result.namespace_authority_verified,
                result.identity_verified,
                result.authorized_revocation_asserted,
                result.availability_evidence_verified,
                result.historical_validity_asserted,
                result.decision_eligibility_asserted,
                result.atomic_cross_database_snapshot_asserted,
            )
        )
    )
    if not complete:
        return DelegationNativeBinding(
            VERSION,
            "review_required",
            ("DELEGATION_NATIVE_CHECKPOINT_NOT_COMPLETE",),
            review,
            result,
        )
    digest = hashlib.sha256(
        json.dumps(
            [
                VERSION,
                asdict(target),
                review.evidence_fingerprint,
                result.evidence_fingerprint,
            ],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return DelegationNativeBinding(
        VERSION,
        "internal_review_evidence_bound_to_native_checkpoint",
        ("INTERNAL_REVIEW_AND_EXACT_NATIVE_CHECKPOINT_MATCH",),
        review,
        result,
        True,
        digest,
    )
