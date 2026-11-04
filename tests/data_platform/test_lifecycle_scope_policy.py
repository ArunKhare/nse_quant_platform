"""Actual existing scope verifier integrated with new signed lifecycle mechanics."""

from dataclasses import asdict, replace

import pytest
from key_lifecycle_fixture import arguments, event, key, public

from nse_quant.data_platform import statement_scope_policy as policy
from nse_quant.data_platform.lifecycle_scope_policy import assess_lifecycle_scope_policy
from nse_quant.data_platform.observed_key_lifecycle import canonical, sha


def policy_arguments(private, **changes):
    query = policy.ScopeQuery("TEST_NS", "ASSET1", "INDEX", "TEST_ISSUER", "ASSERTED", "a" * 64)
    value = dict(
        schema=policy.VERSION,
        policy_id="TEST_POLICY",
        sequence=1,
        grants=[dict(grant_id="g1", **asdict(query))],
        denied_keys=[],
    )
    value.update(changes)
    raw = canonical(value)
    return dict(
        policy_bytes=raw,
        policy_signature=private.sign(policy.policy_signing_message(raw)),
        expected_policy_sha256=sha(raw),
        query=query,
    )


def test_rotated_policy_key_is_derived_not_caller_selected():
    root, second = key(), key()
    raw = event(root, second, root=root)
    args = arguments((raw,), root)
    result = assess_lifecycle_scope_policy(**args, **policy_arguments(second))
    assert result.status == "matched_supplied_constraints"
    assert result.policy is not None and result.policy.governance_signature_verified
    assert result.policy.governance_key_sha256 == sha(public(second))
    assert result.supplied_lifecycle_and_policy_constraints_satisfied
    assert not result.root_authority_authenticated
    assert not result.policy_authority_authenticated
    assert not result.authorized_revocation_asserted
    assert not result.decision_eligibility_asserted
    assert result.canonical_underlying_id is None
    with pytest.raises(policy.ScopePolicyRejected, match="SIGNATURE_INVALID"):
        assess_lifecycle_scope_policy(**args, **policy_arguments(root))


def test_terminal_chain_revocation_precedes_scope_grant():
    root = key()
    raw = event(root, None, root=root)
    result = assess_lifecycle_scope_policy(**arguments((raw,), root), **policy_arguments(root))
    assert result.reason_codes == ("SUPPLIED_CHAIN_GOVERNANCE_KEY_REVOKED",)
    assert result.policy is None
    assert not result.supplied_lifecycle_and_policy_constraints_satisfied
    assert not result.authorized_revocation_asserted


def test_existing_denial_and_ambiguity_semantics_preserved():
    root, second = key(), key()
    raw = event(root, second, root=root)
    base = policy_arguments(second)
    query = base["query"]
    for changes, reason in (
        (dict(denied_keys=[query.signer_key_sha256]), "SIGNER_KEY_EXPLICITLY_DENIED"),
        (
            dict(
                grants=[dict(grant_id="g1", **asdict(query)), dict(grant_id="g2", **asdict(query))]
            ),
            "MULTIPLE_EXACT_GRANTS_REQUIRE_RESOLUTION",
        ),
        (dict(policy_id="OTHER"), "LIFECYCLE_EXACT_POLICY_SERIES_MISMATCH"),
    ):
        result = assess_lifecycle_scope_policy(
            **arguments((raw,), root),
            **policy_arguments(second, **changes),
        )
        assert result.reason_codes == (reason,)
        assert not result.supplied_lifecycle_and_policy_constraints_satisfied
    base["query"] = replace(query, namespace="OTHER")
    result = assess_lifecycle_scope_policy(**arguments((raw,), root), **base)
    assert result.reason_codes == ("LIFECYCLE_EXACT_NAMESPACE_OR_ASSET_MISMATCH",)


def test_terminal_refusal_fingerprint_still_binds_complete_requested_policy():
    root = key()
    args = arguments((event(root, None, root=root),), root)
    first = assess_lifecycle_scope_policy(**args, **policy_arguments(root, sequence=1))
    second = assess_lifecycle_scope_policy(**args, **policy_arguments(root, sequence=2))
    assert first.reason_codes == second.reason_codes
    assert first.evidence_fingerprint != second.evidence_fingerprint
    assert not first.decision_eligibility_asserted
