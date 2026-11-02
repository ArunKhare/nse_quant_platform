"""Verify each supplied signed policy before observed-window constraints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from nse_quant.data_platform.policy_window import (
    PolicyPosition,
    PolicyWindowCheck,
    PolicyWindowEntry,
    check_policy_window,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.statement_scope_policy import ScopeAssessment, ScopeQuery

VERSION = "signed-scope-policy-window@1"


@dataclass(frozen=True)
class SignedPolicyInput:
    policy_bytes: bytes
    policy_signature: bytes
    expected_policy_sha256: str


@dataclass(frozen=True)
class SignedPolicyWindow:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    observations: tuple[ScopeAssessment, ...]
    window: PolicyWindowCheck
    signed_window_constraints_satisfied: bool = False
    evidence_fingerprint: str | None = None
    policy_currentness_verified: bool = False
    policy_authority_authenticated: bool = False
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    authorized_key_reactivation_asserted: bool = False
    authorized_revocation_asserted: bool = False
    identity_verified: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def inspect_signed_policy_window(
    snapshots: tuple[SignedPolicyInput, ...],
    *,
    governance_public_key: bytes,
    expected_governance_key_sha256: str,
    query: ScopeQuery,
    anchor: PolicyPosition,
    tip: PolicyPosition,
) -> SignedPolicyWindow:
    """No persistence, key rotation, acquisition or trusted/latest checkpoint inference.

    Every snapshot verifies under ONE explicitly pinned governance key. All grants
    validate via the existing actual policy verifier, including denying snapshots.
    Intermediate scope denials need not imply tip denial; global denied_keys may
    only accumulate in this profile. This is not an authenticated revocation claim.
    """
    from nse_quant.data_platform import statement_scope_policy as policy

    if policy.VERSION != "statement-key-scope-policy@1":
        raise ValueError("UNSUPPORTED_POLICY_WINDOW_DEPENDENCY_VERSION")
    if type(snapshots) is not tuple or not 1 <= len(snapshots) <= 64:
        raise ValueError("BOUNDED_IMMUTABLE_SIGNED_POLICY_WINDOW_REQUIRED")
    total = 0
    for item in snapshots:
        if (
            type(item) is not SignedPolicyInput
            or type(item.policy_bytes) is not bytes
            or not 0 < len(item.policy_bytes) <= 65536
        ):
            raise ValueError("BOUNDED_SIGNED_POLICY_INPUT_REQUIRED")
        total += len(item.policy_bytes)
    if total > 4194304:
        raise ValueError("SIGNED_POLICY_WINDOW_AGGREGATE_LIMIT")
    observations: list[policy.ScopeAssessment] = []
    entries: list[PolicyWindowEntry] = []
    signature_pins: list[str] = []
    for item in snapshots:
        result = policy.assess_signed_scope_policy(
            item.policy_bytes,
            policy_signature=item.policy_signature,
            governance_public_key=governance_public_key,
            expected_policy_sha256=item.expected_policy_sha256,
            expected_governance_key_sha256=expected_governance_key_sha256,
            query=query,
        )
        observations.append(result)
        # Only project AFTER the actual whole canonical signed document validated.
        value = json.loads(item.policy_bytes)
        entries.append(
            PolicyWindowEntry(
                result.policy_id,
                PolicyPosition(result.sequence, result.policy_sha256),
                tuple(value["denied_keys"]),
            )
        )
        signature_pins.append(hashlib.sha256(item.policy_signature).hexdigest())
    checked = check_policy_window(tuple(entries), anchor=anchor, tip=tip)
    reasons = list(checked.reason_codes) if not checked.window_constraints_satisfied else []
    if not observations[-1].supplied_policy_permits_scope:
        reasons.append("POLICY_WINDOW_TIP_DOES_NOT_PERMIT_EXACT_SCOPE")
    complete = not reasons
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                VERSION,
                asdict(anchor),
                asdict(tip),
                [asdict(item) for item in observations],
                asdict(checked),
                signature_pins,
            ],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return SignedPolicyWindow(
        VERSION,
        "signed_observed_window_constraints_satisfied" if complete else "review_required",
        tuple(reasons) if reasons else ("SIGNED_OBSERVED_WINDOW_AND_TIP_SCOPE_MATCH",),
        tuple(observations),
        checked,
        complete,
        fingerprint,
    )
