"""Actual prior native fixtures/consumer plus generated two-role delegation proofs."""

import hashlib
from dataclasses import asdict

from test_checkpoint_native_revalidation import checkpoint_case as checkpoint_case
from test_delegation_review import packet, proofs
from test_identity_statement_reader_native import source_claim as source_claim
from test_signature_receipt_reader_native import proof_store as proof_store

from nse_quant.data_platform import checkpoint_native_revalidation as native
from nse_quant.data_platform import delegation_native_reader as reader
from nse_quant.data_platform.delegation_review import (
    EXTERNAL,
    INTERNAL,
    DelegationInput,
    DelegationTarget,
)


def declarations(args, model=INTERNAL, **changes):
    target = DelegationTarget(
        args["request"].namespace,
        args["request"].asset_kind,
        args["policy_id"],
        args["expected_governance_key_sha256"],
        args["expected_checkpoint_id"],
        args["expected_history_fingerprint"],
    )
    values = dict(target=asdict(target))
    values.update(changes)
    raw = packet(model, **values)
    return (DelegationInput(raw, hashlib.sha256(raw).hexdigest(), proofs(raw, model)),)


def test_internal_review_binds_without_promoting_authority(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    value = reader.inspect_delegation_native_binding(
        **args,
        declarations=declarations(args),
        expected_model=INTERNAL,
    )
    assert value.internal_review_evidence_bound
    assert value.native.retained_head_and_native_scope_bound
    assert not value.internal_authorization_asserted
    assert not value.supporting_bronze_refs_checked
    assert not value.reviewer_identities_authenticated
    assert not value.policy_authority_authenticated
    assert not value.external_issuer_authority_verified
    assert not value.namespace_authority_verified
    assert not value.issuer_authenticated
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_underlying_id is None


def test_external_claim_does_not_fall_back_to_internal(checkpoint_case, monkeypatch):
    args, _, _, _, _ = checkpoint_case()

    def forbidden(*positional, **keywords):
        raise AssertionError("External authority claim reached native promotion")

    monkeypatch.setattr(native, "revalidate_checkpoint_native_policy", forbidden)
    value = reader.inspect_delegation_native_binding(
        **args,
        declarations=declarations(args, EXTERNAL),
        expected_model=EXTERNAL,
    )
    assert value.status == "review_required"
    assert value.native is None
    assert not value.internal_review_evidence_bound


def test_new_checkpoint_retry_invalidates_signed_history_pin(checkpoint_case):
    args, _, retry, _, _ = checkpoint_case()
    original = declarations(args)
    retry()
    value = reader.inspect_delegation_native_binding(
        **args,
        declarations=original,
        expected_model=INTERNAL,
    )
    assert value.review.internal_review_constraints_satisfied
    assert not value.internal_review_evidence_bound
    assert value.status == "review_required"


def test_disputed_review_set_never_picks_approved_entry(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    supplied = declarations(args) + declarations(args, statement_kind="DISPUTE")
    value = reader.inspect_delegation_native_binding(
        **args,
        declarations=supplied,
        expected_model=INTERNAL,
    )
    assert not value.internal_review_evidence_bound
    assert value.native is None
    assert len(value.review.observations) == 2


def test_wrong_scope_packet_cannot_bind(checkpoint_case):
    args, _, _, _, _ = checkpoint_case()
    target = asdict(
        DelegationTarget(
            "OTHER",
            "INDEX",
            args["policy_id"],
            args["expected_governance_key_sha256"],
            args["expected_checkpoint_id"],
            args["expected_history_fingerprint"],
        )
    )
    value = reader.inspect_delegation_native_binding(
        **args,
        declarations=declarations(args, target=target),
        expected_model=INTERNAL,
    )
    assert not value.internal_review_evidence_bound
    assert value.native is None
