"""Real Ed25519 role/quorum tests; no authenticated organization/issuer root."""

import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.delegation_review import (
    EXTERNAL,
    INTERNAL,
    MAX_BYTES,
    ROLES,
    SCHEMAS,
    DelegationInput,
    DelegationReviewRejected,
    DelegationTarget,
    ReviewerProof,
    assess_delegation_review,
    assess_delegation_review_set,
    review_signing_message,
)


def target():
    return DelegationTarget("TEST_NS", "INDEX", "TEST_POLICY", "a" * 64, "b" * 64, "c" * 64)


def packet(model=INTERNAL, **changes):
    value = dict(
        schema=SCHEMAS[model],
        delegation_id="SYNTHETIC",
        target=asdict(target()),
        capability="SIGN_RESEARCH_SCOPE_POLICY",
        statement_kind="APPROVE",
        evidence_refs=[
            dict(
                capture_event_id="d" * 64,
                envelope_hash="e" * 64,
                payload_hash="f" * 64,
                byte_start=0,
                byte_end=1,
                fragment_sha256="0" * 64,
            )
        ],
    )
    if model == INTERNAL:
        value["organization_ref"] = "UNVERIFIED_ORG"
    else:
        value.update(
            claimed_issuer_ref="UNVERIFIED_ISSUER",
            verification_method="INDEPENDENT_EXTERNAL_REVIEW_REQUIRED",
        )
    value.update(changes)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def proofs(raw, model=INTERNAL):
    result = []
    for role in ROLES[model]:
        private = Ed25519PrivateKey.generate()
        key = private.public_key().public_bytes_raw()
        result.append(
            ReviewerProof(
                role,
                key,
                private.sign(review_signing_message(raw, role)),
                hashlib.sha256(key).hexdigest(),
            )
        )
    return tuple(result)


def assess(raw=None, model=INTERNAL, **changes):
    raw = packet(model) if raw is None else raw
    arguments: dict[str, Any] = dict(
        expected_document_sha256=hashlib.sha256(raw).hexdigest(),
        expected_model=model,
        expected_target=target(),
        proofs=proofs(raw, model),
    )
    arguments.update(changes)
    return assess_delegation_review(raw, **arguments)


def test_internal_is_review_evidence_not_authority():
    value = assess()
    assert value.internal_review_constraints_satisfied
    assert value.approval_quorum_signatures_verified
    assert not value.supporting_bronze_refs_checked
    assert not value.reviewer_identities_authenticated
    assert not value.independent_humans_verified
    assert not value.internal_authorization_asserted
    assert not value.external_issuer_authority_verified
    assert not value.policy_authority_authenticated
    assert not value.namespace_authority_verified
    assert not value.issuer_authenticated
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_underlying_id is None


def test_external_remains_blocked_despite_two_good_signatures():
    value = assess(model=EXTERNAL)
    assert value.approval_quorum_signatures_verified
    assert value.reason_codes == ("INDEPENDENT_EXTERNAL_AUTHORITY_VERIFIER_REQUIRED",)
    assert not value.internal_review_constraints_satisfied
    assert not value.external_issuer_authority_verified


@pytest.mark.parametrize("model", [INTERNAL, EXTERNAL])
def test_model_downgrade_or_upgrade_is_not_allowed(model):
    raw = packet(model)
    other = EXTERNAL if model == INTERNAL else INTERNAL
    with pytest.raises(DelegationReviewRejected):
        assess(raw, model=other)


@pytest.mark.parametrize(
    "changes",
    [
        {"namespace": "OTHER"},
        {"asset_kind": "EQUITY"},
        {"policy_id": "OTHER"},
        {"governance_key_sha256": "0" * 64},
        {"checkpoint_id": "0" * 64},
        {"checkpoint_history_fingerprint": "0" * 64},
    ],
    ids=["namespace", "asset", "policy", "key", "checkpoint", "history"],
)
def test_exact_target_all_dimensions(changes):
    value = assess(expected_target=replace(target(), **changes))
    assert not value.internal_review_constraints_satisfied
    assert value.reason_codes == ("DELEGATION_EXACT_TARGET_MISMATCH",)


@pytest.mark.parametrize("kind", ["DISPUTE", "WITHDRAW"])
def test_negative_statements_never_authorized_revocation(kind):
    value = assess(packet(statement_kind=kind))
    assert not value.internal_review_constraints_satisfied
    assert not value.authorized_revocation_asserted


def test_same_key_cannot_fill_two_roles():
    raw = packet()
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    repeated = tuple(
        ReviewerProof(
            role,
            key,
            private.sign(review_signing_message(raw, role)),
            hashlib.sha256(key).hexdigest(),
        )
        for role in ROLES[INTERNAL]
    )
    with pytest.raises(DelegationReviewRejected, match="SELF_OR_DUPLICATE"):
        assess(raw, proofs=repeated)


def test_delegate_key_cannot_approve_its_own_delegation():
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    key_pin = hashlib.sha256(key).hexdigest()
    changed = replace(target(), governance_key_sha256=key_pin)
    raw = packet(target=asdict(changed))
    role = ROLES[INTERNAL][0]
    first = ReviewerProof(role, key, private.sign(review_signing_message(raw, role)), key_pin)
    with pytest.raises(DelegationReviewRejected, match="SELF_OR_DUPLICATE"):
        assess(raw, expected_target=changed, proofs=(first, proofs(raw)[1]))


def test_role_relabeling_invalidates_signature():
    raw = packet()
    one, two = proofs(raw)
    with pytest.raises(DelegationReviewRejected, match="ROLE_SIGNATURE"):
        assess(raw, proofs=(replace(one, role=two.role), replace(two, role=one.role)))


@pytest.mark.parametrize("mode", ["missing", "invalid", "wrong-pin", "duplicate-role", "mixed"])
def test_no_quorum_signature_or_pin_fallback(mode):
    raw = packet()
    one, two = proofs(raw)
    cases = {
        "missing": (one,),
        "invalid": (one, replace(two, signature=bytes(64))),
        "wrong-pin": (one, replace(two, expected_public_key_sha256="0" * 64)),
        "duplicate-role": (one, replace(two, role=one.role)),
        "mixed": (one, proofs(packet(delegation_id="OTHER"))[1]),
    }
    with pytest.raises(DelegationReviewRejected):
        assess(raw, proofs=cases[mode])


@pytest.mark.parametrize(
    "changes",
    [
        {"capability": "ROTATE_KEY"},
        {"capability": "REVOKE_IDENTITY"},
        {"extra": True},
        {"statement_kind": "ACCEPTED"},
        {"organization_ref": ""},
        {"evidence_refs": []},
        {"evidence_refs": [{}]},
    ],
    ids=["rotation", "revocation", "extra", "kind", "org", "empty-refs", "bad-ref"],
)
def test_schema_and_capability_do_not_escalate(changes):
    with pytest.raises(DelegationReviewRejected):
        assess(packet(**changes))


@pytest.mark.parametrize("mode", ["duplicate", "nonfinite", "newline", "later", "bom"])
def test_strict_whole_document(mode):
    raw = packet()
    cases = {
        "duplicate": raw.replace(b'"delegation_id":', b'"delegation_id":"x","delegation_id":'),
        "nonfinite": raw.replace(b'"byte_end":1', b'"byte_end":NaN'),
        "newline": raw + b"\n",
        "later": raw + b"{}",
        "bom": b"\xef\xbb\xbf" + raw,
    }
    with pytest.raises(DelegationReviewRejected):
        assess(cases[mode])


def test_distinct_declarations_not_first_last_or_issuer_wins():
    first, second = packet(), packet(delegation_id="OTHER")
    declarations = tuple(
        DelegationInput(raw, hashlib.sha256(raw).hexdigest(), proofs(raw))
        for raw in (first, second)
    )
    result = assess_delegation_review_set(
        declarations, expected_model=INTERNAL, expected_target=target()
    )
    assert not result.internal_review_constraints_satisfied
    assert len(result.observations) == 2
    assert not result.supplied_set_completeness_asserted


def test_exact_retries_retained_and_malformed_later_never_filtered():
    raw = packet()
    item = DelegationInput(raw, hashlib.sha256(raw).hexdigest(), proofs(raw))
    value = assess_delegation_review_set(
        (item, item), expected_model=INTERNAL, expected_target=target()
    )
    assert value.internal_review_constraints_satisfied
    assert len(value.observations) == 2
    bad = b"{}"
    later = DelegationInput(bad, hashlib.sha256(bad).hexdigest(), proofs(bad))
    with pytest.raises(DelegationReviewRejected):
        assess_delegation_review_set(
            (item, later), expected_model=INTERNAL, expected_target=target()
        )


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"x" * (MAX_BYTES + 1), id="oversized"),
        pytest.param(bytearray(b"x"), id="mutable"),
    ],
)
def test_byte_limits(raw):
    with pytest.raises(DelegationReviewRejected):
        review_signing_message(raw, ROLES[INTERNAL][0])


def test_duplicate_refs_and_boolean_spans_rejected():
    reference = json.loads(packet())["evidence_refs"][0]
    for refs in (
        [reference, reference],
        [dict(reference, byte_start=False)],
        [dict(reference, byte_end=1048577)],
        [reference] * 9,
    ):
        with pytest.raises(DelegationReviewRejected):
            assess(packet(evidence_refs=refs))


def test_review_domain_is_not_raw_packet_signature():
    raw = packet()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    role = ROLES[INTERNAL][0]
    wrong = ReviewerProof(role, public, private.sign(raw), hashlib.sha256(public).hexdigest())
    with pytest.raises(DelegationReviewRejected, match="ROLE_SIGNATURE"):
        assess(raw, proofs=(wrong, proofs(raw)[1]))


def test_exact_document_pin_required():
    with pytest.raises(DelegationReviewRejected, match="DOCUMENT_PIN_MISMATCH"):
        assess(expected_document_sha256="0" * 64)


def test_external_arbitrary_verification_label_never_authenticates():
    raw = packet(EXTERNAL, verification_method="OFFICIALLY_VERIFIED")
    with pytest.raises(DelegationReviewRejected, match="EXTERNAL_METHOD"):
        assess(raw, model=EXTERNAL)


def test_set_bounds_and_full_conflicting_negatives():
    raw = packet()
    item = DelegationInput(raw, hashlib.sha256(raw).hexdigest(), proofs(raw))
    for values in ((), [item], (item,) * 9):
        with pytest.raises(DelegationReviewRejected):
            assess_delegation_review_set(values, expected_model=INTERNAL, expected_target=target())
    withdraw = packet(statement_kind="WITHDRAW")
    other = DelegationInput(withdraw, hashlib.sha256(withdraw).hexdigest(), proofs(withdraw))
    value = assess_delegation_review_set(
        (item, other), expected_model=INTERNAL, expected_target=target()
    )
    assert not value.internal_review_constraints_satisfied
    assert not value.authorized_revocation_asserted
    assert len(value.observations) == 2
