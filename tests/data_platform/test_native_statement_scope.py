"""Actual receipt/crypto/policy composition using disposable native fixtures."""

import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_identity_statement_reader_native import source_claim as source_claim
from test_recorded_statement_signature_native import inputs
from test_signature_receipt_reader_native import proof_store as proof_store

from nse_quant.data_platform import native_statement_scope as reader
from nse_quant.data_platform import signature_receipt_reader as receipts
from nse_quant.data_platform import statement_scope_policy as policy


def governance(args, *, grants=None, denied=None):
    request = args["request"]
    grant = dict(
        grant_id="g1",
        namespace=request.namespace,
        external_id=request.external_id,
        asset_kind=request.asset_kind,
        asserted_issuer=request.asserted_issuer,
        assertion=request.assertion,
        signer_key_sha256=args["expected_public_key_sha256"],
    )
    value = dict(
        schema=policy.VERSION,
        policy_id="SYNTHETIC",
        sequence=1,
        grants=[grant] if grants is None else grants,
        denied_keys=[] if denied is None else denied,
    )
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    return dict(
        policy_bytes=raw,
        policy_signature=private.sign(policy.policy_signing_message(raw)),
        governance_public_key=key,
        expected_policy_sha256=hashlib.sha256(raw).hexdigest(),
        expected_governance_key_sha256=hashlib.sha256(key).hexdigest(),
    )


def test_real_receipt_and_scope_policy_are_conditional(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()))
    signed = governance(args)
    value = reader.inspect_statement_scope_policy(**args, **signed)
    assert value.supplied_policy_constraints_satisfied
    assert value.receipt.proof_receipt_storage_linkage_verified
    assert value.policy.governance_signature_verified
    assert value.evidence_fingerprint == (
        reader.inspect_statement_scope_policy(**args, **signed).evidence_fingerprint
    )
    assert not value.policy_authority_authenticated
    assert not value.policy_currentness_verified
    assert not value.issuer_authenticated
    assert not value.namespace_authority_verified
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_underlying_id is None


def test_real_receipt_cannot_override_explicit_denial(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()))
    value = reader.inspect_statement_scope_policy(
        **args, **governance(args, denied=[args["expected_public_key_sha256"]])
    )
    assert value.receipt.proof_receipt_storage_linkage_verified
    assert value.status == "denied_under_supplied_policy"
    assert not value.supplied_policy_constraints_satisfied


def test_no_grant_means_deny_not_auto_registration(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()))
    value = reader.inspect_statement_scope_policy(**args, **governance(args, grants=[]))
    assert value.reason_codes == ("NO_EXACT_SCOPE_GRANT",)
    assert not value.supplied_policy_constraints_satisfied


def test_withdraw_grant_still_not_authorized_revocation(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim(claim_kind="WITHDRAWN"), "WITHDRAWN"))
    value = reader.inspect_statement_scope_policy(**args, **governance(args))
    assert value.supplied_policy_constraints_satisfied
    assert not value.authorized_revocation_asserted
    assert not value.receipt.authorized_revocation_asserted


def test_invalid_policy_stops_without_claiming_native_checks(
    source_claim,
    proof_store,
    monkeypatch,
):
    args, _ = proof_store(inputs(source_claim()))
    signed = governance(args)
    signed["policy_signature"] = bytes(64)

    def forbidden(*positional, **keywords):
        raise AssertionError("Malformed policy reached native receipt execution")

    monkeypatch.setattr(receipts, "inspect_signature_receipt", forbidden)
    with pytest.raises(policy.ScopePolicyRejected, match="SIGNATURE_INVALID"):
        reader.inspect_statement_scope_policy(**args, **signed)


def test_stale_recording_blocks_matching_policy(source_claim, proof_store):
    from dataclasses import replace

    claim = source_claim()
    args, _ = proof_store(inputs(claim))
    claim[5](replace(claim[2], assertion="WITHDRAWN"))
    value = reader.inspect_statement_scope_policy(**args, **governance(args))
    assert value.policy.supplied_policy_permits_scope
    assert value.status == "review_required"
    assert not value.supplied_policy_constraints_satisfied
