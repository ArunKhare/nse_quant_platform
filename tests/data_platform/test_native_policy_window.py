"""Actual native receipt fixtures plus actual signed-window policy verification."""

from dataclasses import replace

from test_identity_statement_reader_native import source_claim as source_claim
from test_recorded_statement_signature_native import inputs
from test_signature_receipt_reader_native import proof_store as proof_store
from test_signed_policy_window_integration import signed_window

from nse_quant.data_platform import native_policy_window as reader
from nse_quant.data_platform.policy_window import PolicyPosition


def arguments(receipt_args):
    # Construct real signed policies for this native fixture's generated signer key.
    import hashlib
    import json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from nse_quant.data_platform.signed_policy_window import SignedPolicyInput
    from nse_quant.data_platform.statement_scope_policy import policy_signing_message

    sample = signed_window([(1, (), "g1"), (2, (), "g2")])
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    snapshots = []
    for old in sample["snapshots"]:
        value = json.loads(old.policy_bytes)
        value["grants"][0]["signer_key_sha256"] = receipt_args["expected_public_key_sha256"]
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        snapshots.append(
            SignedPolicyInput(
                raw, private.sign(policy_signing_message(raw)), hashlib.sha256(raw).hexdigest()
            )
        )
    return dict(
        snapshots=tuple(snapshots),
        governance_public_key=key,
        expected_governance_key_sha256=hashlib.sha256(key).hexdigest(),
        anchor=PolicyPosition(1, snapshots[0].expected_policy_sha256),
        tip=PolicyPosition(2, snapshots[-1].expected_policy_sha256),
    )


def test_actual_native_scope_and_window(source_claim, proof_store):
    args, _ = proof_store(inputs(source_claim()))
    value = reader.inspect_native_policy_window(**args, **arguments(args))
    assert value.observed_window_and_native_scope_satisfied
    assert value.native_scope.supplied_policy_constraints_satisfied
    assert not value.policy_currentness_verified
    assert not value.policy_authority_authenticated
    assert not value.issuer_authenticated
    assert not value.namespace_authority_verified
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_underlying_id is None


def test_actual_obsolete_recording_not_rescued_by_history(source_claim, proof_store):
    claim = source_claim()
    args, _ = proof_store(inputs(claim))
    claim[5](replace(claim[2], assertion="WITHDRAWN"))
    value = reader.inspect_native_policy_window(**args, **arguments(args))
    assert value.history.signed_window_constraints_satisfied
    assert not value.observed_window_and_native_scope_satisfied
    assert value.status == "review_required"
