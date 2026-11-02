"""Actual signed-policy checks with disposable keys; no authenticated governance root."""

import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.statement_scope_policy import (
    DOMAIN,
    MAX_BYTES,
    VERSION,
    ScopePolicyRejected,
    ScopeQuery,
    assess_signed_scope_policy,
    policy_signing_message,
)


def query():
    return ScopeQuery("TEST_NS", "ASSET1", "INDEX", "TEST_ISSUER", "ASSERTED", "a" * 64)


def grant(grant_id="g1", **changes):
    value = dict(grant_id=grant_id, **asdict(query()))
    value.update(changes)
    return value


def policy(**changes):
    value = dict(
        schema=VERSION, policy_id="SYNTHETIC", sequence=1, grants=[grant()], denied_keys=[]
    )
    value.update(changes)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def assess(raw=None, scope=None, signature_mode="profile", **changes):
    raw = policy() if raw is None else raw
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    message = policy_signing_message(raw) if signature_mode == "profile" else raw
    arguments: dict[str, Any] = dict(
        policy_signature=private.sign(message),
        governance_public_key=key,
        expected_policy_sha256=hashlib.sha256(raw).hexdigest(),
        expected_governance_key_sha256=hashlib.sha256(key).hexdigest(),
        query=query() if scope is None else scope,
    )
    arguments.update(changes)
    return assess_signed_scope_policy(raw, **arguments)


def test_real_signature_and_grant_never_authenticate_authority():
    value = assess()
    assert value.supplied_policy_permits_scope
    assert value.governance_signature_verified
    assert value.status == "permitted_under_supplied_policy"
    assert not value.policy_authority_authenticated
    assert not value.policy_currentness_verified
    assert not value.issuer_authenticated
    assert not value.namespace_authority_verified
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_underlying_id is None


def test_key_denial_beats_grant():
    value = assess(policy(denied_keys=["a" * 64]))
    assert value.status == "denied_under_supplied_policy"
    assert value.matched_grant_ids == ("g1",)
    assert not value.supplied_policy_permits_scope


def test_ambiguous_exact_grants_never_first_last_wins():
    value = assess(policy(grants=[grant("g2"), grant("g1")]))
    assert value.status == "review_required"
    assert value.matched_grant_ids == ("g1", "g2")


@pytest.mark.parametrize(
    "changes",
    [
        {"namespace": "test_ns"},
        {"external_id": "OTHER"},
        {"asset_kind": "EQUITY"},
        {"asserted_issuer": "OTHER"},
        {"assertion": "WITHDRAWN"},
        {"assertion": "DISPUTED"},
        {"signer_key_sha256": "b" * 64},
    ],
    ids=["namespace", "external-id", "asset", "issuer", "withdraw", "dispute", "key"],
)
def test_all_scope_dimensions_exact(changes):
    value = assess(scope=replace(query(), **changes))
    assert value.reason_codes == ("NO_EXACT_SCOPE_GRANT",)


def test_withdraw_permission_is_not_authorized_revocation():
    value = assess(
        policy(grants=[grant(assertion="WITHDRAWN")]), scope=replace(query(), assertion="WITHDRAWN")
    )
    assert value.supplied_policy_permits_scope
    assert not value.authorized_revocation_asserted


@pytest.mark.parametrize(
    "changes",
    [
        {"schema": "unknown"},
        {"sequence": True},
        {"sequence": 0},
        {"sequence": 2147483648},
        {"unknown": True},
        {"grants": [grant(), grant()]},
        {"grants": [grant(), grant("later", asset_kind="BAD")]},
        {"grants": [grant(namespace="*")]},
        {"denied_keys": ["a" * 64, "a" * 64]},
        {"denied_keys": [True]},
        {"grants": [grant(str(i)) for i in range(129)]},
        {"denied_keys": [f"{i:064x}" for i in range(129)]},
    ],
    ids=[
        "schema",
        "bool-sequence",
        "zero",
        "sequence-bound",
        "extra",
        "duplicate-grant",
        "invalid-later",
        "wildcard",
        "duplicate-deny",
        "bad-deny",
        "grant-bound",
        "deny-bound",
    ],
)
def test_whole_policy_rejected(changes):
    with pytest.raises(ScopePolicyRejected):
        assess(policy(**changes))


def test_denied_key_does_not_salvage_invalid_later_grant():
    with pytest.raises(ScopePolicyRejected):
        assess(policy(denied_keys=["a" * 64], grants=[grant(), grant("g2", assertion="BAD")]))


@pytest.mark.parametrize("mode", ["duplicate", "nonfinite", "newline", "later", "bom"])
def test_strict_original_document(mode):
    raw = policy()
    variants = {
        "duplicate": raw.replace(b'"sequence":1', b'"sequence":1,"sequence":1'),
        "nonfinite": raw.replace(b'"sequence":1', b'"sequence":NaN'),
        "newline": raw + b"\n",
        "later": raw + b"{}",
        "bom": b"\xef\xbb\xbf" + raw,
    }
    with pytest.raises(ScopePolicyRejected):
        assess(variants[mode])


def test_profile_domain_is_not_raw_statement_signature():
    with pytest.raises(ScopePolicyRejected, match="SIGNATURE_INVALID"):
        assess(signature_mode="raw")
    raw = policy()
    assert policy_signing_message(raw) == DOMAIN + len(raw).to_bytes(8, "big") + raw


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_policy_sha256": "0" * 64},
        {"expected_governance_key_sha256": "0" * 64},
        {"policy_signature": bytes(64)},
        {"governance_public_key": bytes(31)},
        {"expected_policy_sha256": "A" * 64},
    ],
    ids=["policy-pin", "governance-pin", "signature", "key-length", "uppercase"],
)
def test_no_pin_or_crypto_fallback(changes):
    with pytest.raises(ScopePolicyRejected):
        assess(**changes)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"x" * (MAX_BYTES + 1), id="oversized"),
        pytest.param(bytearray(b"x"), id="mutable"),
    ],
)
def test_byte_limits(raw):
    with pytest.raises(ScopePolicyRejected):
        policy_signing_message(raw)


def test_empty_policy_denies_and_sequence_is_not_currentness():
    value = assess(policy(grants=[], sequence=100))
    assert not value.supplied_policy_permits_scope
    assert not value.policy_currentness_verified
