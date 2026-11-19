"""Read actual native scope assessment only after signed observed-window checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.policy_window import PolicyPosition
from nse_quant.data_platform.signed_policy_window import (
    SignedPolicyInput,
    SignedPolicyWindow,
    inspect_signed_policy_window,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
    from nse_quant.data_platform.native_statement_scope import NativeScopeAssessment
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

VERSION = "native-policy-window-assessment@1"


@dataclass(frozen=True)
class NativePolicyWindow:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    history: SignedPolicyWindow
    native_scope: NativeScopeAssessment | None = None
    observed_window_and_native_scope_satisfied: bool = False
    evidence_fingerprint: str | None = None
    policy_currentness_verified: bool = False
    policy_authority_authenticated: bool = False
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    authorized_revocation_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def inspect_native_policy_window(
    registry: Any,
    bronze: Any,
    proof_bronze: Any,
    *,
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
    anchor: PolicyPosition,
    tip: PolicyPosition,
) -> NativePolicyWindow:
    from nse_quant.data_platform import native_statement_scope as native
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform.identity_statement_document import canonical, sha
    from nse_quant.data_platform.statement_scope_policy import ScopeQuery

    if native.VERSION != "native-statement-scope-assessment@1":
        raise ValueError("UNSUPPORTED_NATIVE_POLICY_WINDOW_DEPENDENCY_VERSION")
    if type(request) is not kernel.UnderlyingAssertionRequest:
        raise TypeError("EXACT_TYPED_POLICY_WINDOW_REQUEST_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
    query = ScopeQuery(
        checked.namespace,
        checked.external_id,
        checked.asset_kind,
        checked.asserted_issuer,
        checked.assertion,
        expected_public_key_sha256,
    )
    history = inspect_signed_policy_window(
        snapshots,
        governance_public_key=governance_public_key,
        expected_governance_key_sha256=expected_governance_key_sha256,
        query=query,
        anchor=anchor,
        tip=tip,
    )
    if not history.signed_window_constraints_satisfied:
        return NativePolicyWindow(VERSION, "review_required", history.reason_codes, history)
    last = snapshots[-1]
    result = native.inspect_statement_scope_policy(
        registry,
        bronze,
        proof_bronze,
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
        policy_bytes=last.policy_bytes,
        policy_signature=last.policy_signature,
        governance_public_key=governance_public_key,
        expected_policy_sha256=last.expected_policy_sha256,
        expected_governance_key_sha256=expected_governance_key_sha256,
    )
    if (
        not result.supplied_policy_constraints_satisfied
        or result.policy != history.observations[-1]
    ):
        return NativePolicyWindow(
            VERSION, "review_required", ("POLICY_WINDOW_NATIVE_SCOPE_NOT_MATCHED",), history, result
        )
    fingerprint = sha(
        canonical([VERSION, history.evidence_fingerprint, result.evidence_fingerprint]).encode()
    )
    return NativePolicyWindow(
        VERSION,
        "observed_policy_window_and_native_scope_satisfied",
        ("EXACT_WINDOW_AND_NATIVE_SCOPE_SATISFIED",),
        history,
        result,
        True,
        fingerprint,
    )
