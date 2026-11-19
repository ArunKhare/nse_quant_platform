"""Apply explicit signed scope constraints to freshly read native receipt evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.statement_scope_policy import (
    ScopeAssessment,
    ScopeQuery,
    assess_signed_scope_policy,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
    from nse_quant.data_platform.signature_receipt_reader import SignatureReceiptEvidence
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

VERSION = "native-statement-scope-assessment@1"


@dataclass(frozen=True)
class NativeScopeAssessment:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    policy: ScopeAssessment
    receipt: SignatureReceiptEvidence
    supplied_policy_constraints_satisfied: bool = False
    evidence_fingerprint: str | None = None
    policy_authority_authenticated: bool = False
    policy_currentness_verified: bool = False
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    canonical_underlying_id: None = None
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def inspect_statement_scope_policy(
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
    policy_bytes: bytes,
    policy_signature: bytes,
    governance_public_key: bytes,
    expected_policy_sha256: str,
    expected_governance_key_sha256: str,
) -> NativeScopeAssessment:
    """No caller receipt DTO or caller query. No trust/root/key registration or I/O opens."""
    from nse_quant.data_platform import signature_receipt_reader as native
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform.identity_statement_document import canonical, pin, sha

    if native.VERSION != "recorded-signature-receipt-linkage@1":
        raise ValueError("UNSUPPORTED_SCOPE_RECEIPT_DEPENDENCY_VERSION")
    if type(request) is not kernel.UnderlyingAssertionRequest:
        raise TypeError("TYPED_SCOPE_ASSERTION_REQUEST_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
    query = ScopeQuery(
        checked.namespace,
        checked.external_id,
        checked.asset_kind,
        checked.asserted_issuer,
        checked.assertion,
        expected_public_key_sha256,
    )
    policy = assess_signed_scope_policy(
        policy_bytes,
        policy_signature=policy_signature,
        governance_public_key=governance_public_key,
        expected_policy_sha256=expected_policy_sha256,
        expected_governance_key_sha256=expected_governance_key_sha256,
        query=query,
    )
    receipt = native.inspect_signature_receipt(
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
    )
    complete = (
        type(receipt) is native.SignatureReceiptEvidence
        and receipt.version == native.VERSION
        and receipt.assertion_id == assertion_id
        and receipt.status == "recorded_signature_proof_storage_linked"
        and receipt.proof_receipt_storage_linkage_verified is True
        and pin(receipt.evidence_fingerprint)
        and receipt.artifact is not None
        and sha(receipt.artifact.public_key) == query.signer_key_sha256
        and receipt.canonical_underlying_id is None
        and all(
            flag is False
            for flag in (
                receipt.signature_acquisition_provenance_verified,
                receipt.source_acquisition_authenticity_asserted,
                receipt.issuer_authenticated,
                receipt.namespace_authority_verified,
                receipt.identity_verified,
                receipt.authorized_revocation_asserted,
                receipt.availability_evidence_verified,
                receipt.historical_validity_asserted,
                receipt.decision_eligibility_asserted,
                receipt.atomic_cross_database_snapshot_asserted,
            )
        )
    )
    if not complete:
        return NativeScopeAssessment(
            VERSION, "review_required", ("NATIVE_SCOPE_RECEIPT_NOT_COMPLETE",), policy, receipt
        )
    if not policy.supplied_policy_permits_scope:
        return NativeScopeAssessment(VERSION, policy.status, policy.reason_codes, policy, receipt)
    fingerprint = sha(
        canonical(
            [
                VERSION,
                assertion_id,
                asdict(query),
                asdict(policy),
                sha(policy_signature),
                receipt.evidence_fingerprint,
            ]
        ).encode()
    )
    return NativeScopeAssessment(
        VERSION,
        "native_receipt_satisfies_supplied_policy",
        ("EXACT_NATIVE_SCOPE_CONSTRAINTS_SATISFIED",),
        policy,
        receipt,
        True,
        fingerprint,
    )
