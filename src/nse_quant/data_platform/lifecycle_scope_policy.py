"""Existing exact-scope policy evaluation under a causally observed governance key."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from nse_quant.data_platform import statement_scope_policy as policy
from nse_quant.data_platform.observed_key_lifecycle import (
    LifecycleScope,
    ObservedKeyLifecycle,
    canonical,
    inspect_key_lifecycle,
    pin,
    sha,
)

VERSION = "observed-key-lifecycle-scope-policy@1"


@dataclass(frozen=True)
class LifecycleScopeAssessment:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    lifecycle: ObservedKeyLifecycle
    policy: policy.ScopeAssessment | None
    evidence_fingerprint: str
    supplied_lifecycle_and_policy_constraints_satisfied: bool = False
    root_authority_authenticated: bool = False
    policy_authority_authenticated: bool = False
    namespace_authority_verified: bool = False
    issuer_authenticated: bool = False
    identity_verified: bool = False
    key_currentness_verified: bool = False
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def assess_lifecycle_scope_policy(
    records: tuple[bytes, ...],
    *,
    expected_record_sha256s: tuple[str, ...],
    root_public_key: bytes,
    expected_root_key_sha256: str,
    scope: LifecycleScope,
    policy_bytes: bytes,
    policy_signature: bytes,
    expected_policy_sha256: str,
    query: policy.ScopeQuery,
) -> LifecycleScopeAssessment:
    """Reverify original signed records. No caller-created lifecycle result is accepted.

    A terminal supplied-chain revocation prevents policy evaluation. This mechanical
    denial is not an independently authenticated or globally current revocation.
    Lifecycle sequence and policy sequence are distinct; no market-time inference.
    """
    if policy.VERSION != "statement-key-scope-policy@1":
        raise ValueError("UNSUPPORTED_LIFECYCLE_SCOPE_POLICY_DEPENDENCY")
    if type(query) is not policy.ScopeQuery:
        raise TypeError("TYPED_LIFECYCLE_SCOPE_QUERY_REQUIRED")
    query = policy.ScopeQuery(**asdict(query))
    if (
        type(policy_bytes) is not bytes
        or not 0 < len(policy_bytes) <= policy.MAX_BYTES
        or type(policy_signature) is not bytes
        or len(policy_signature) != 64
        or not pin(expected_policy_sha256)
        or sha(policy_bytes) != expected_policy_sha256
    ):
        raise policy.ScopePolicyRejected("LIFECYCLE_POLICY_INPUT_PIN_OR_SHAPE")
    observed = inspect_key_lifecycle(
        records,
        expected_record_sha256s=expected_record_sha256s,
        root_public_key=root_public_key,
        expected_root_key_sha256=expected_root_key_sha256,
        scope=scope,
    )
    result: policy.ScopeAssessment | None = None
    if observed.active_public_key_hex is None:
        reasons = ("SUPPLIED_CHAIN_GOVERNANCE_KEY_REVOKED",)
    elif (query.namespace, query.asset_kind) != (scope.namespace, scope.asset_kind):
        reasons = ("LIFECYCLE_EXACT_NAMESPACE_OR_ASSET_MISMATCH",)
    else:
        active = bytes.fromhex(observed.active_public_key_hex)
        result = policy.assess_signed_scope_policy(
            policy_bytes,
            policy_signature=policy_signature,
            governance_public_key=active,
            expected_policy_sha256=expected_policy_sha256,
            expected_governance_key_sha256=sha(active),
            query=query,
        )
        if result.policy_id != scope.policy_id:
            reasons = ("LIFECYCLE_EXACT_POLICY_SERIES_MISMATCH",)
        elif not result.supplied_policy_permits_scope:
            reasons = result.reason_codes
        else:
            reasons = ("EXACT_SIGNED_CHAIN_AND_SUPPLIED_SCOPE_MATCH_NOT_AUTHORITY",)
    complete = reasons == ("EXACT_SIGNED_CHAIN_AND_SUPPLIED_SCOPE_MATCH_NOT_AUTHORITY",)
    fingerprint = sha(
        canonical(
            [
                VERSION,
                asdict(observed),
                asdict(query),
                sha(policy_bytes),
                sha(policy_signature),
                expected_policy_sha256,
                None if result is None else asdict(result),
                reasons,
            ]
        )
    )
    return LifecycleScopeAssessment(
        VERSION,
        "matched_supplied_constraints" if complete else "review_required",
        reasons,
        observed,
        result,
        fingerprint,
        complete,
    )
