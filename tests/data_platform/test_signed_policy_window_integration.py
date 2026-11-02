"""Actual existing signed-policy verifier integration, not a replacement harness."""

import hashlib
import json
from dataclasses import asdict, replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.policy_window import PolicyPosition
from nse_quant.data_platform.signed_policy_window import (
    SignedPolicyInput,
    inspect_signed_policy_window,
)
from nse_quant.data_platform.statement_scope_policy import (
    VERSION,
    ScopePolicyRejected,
    ScopeQuery,
    policy_signing_message,
)


def signed_window(rows):
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    query = ScopeQuery("TEST_NS", "ASSET1", "INDEX", "TEST_ISSUER", "ASSERTED", "a" * 64)
    snapshots = []
    for seq, denied, grant_id in rows:
        raw = json.dumps(
            dict(
                schema=VERSION,
                policy_id="SYNTHETIC",
                sequence=seq,
                grants=[dict(grant_id=grant_id, **asdict(query))],
                denied_keys=list(denied),
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        snapshots.append(
            SignedPolicyInput(
                raw, private.sign(policy_signing_message(raw)), hashlib.sha256(raw).hexdigest()
            )
        )
    return dict(
        snapshots=tuple(snapshots),
        governance_public_key=key,
        expected_governance_key_sha256=hashlib.sha256(key).hexdigest(),
        query=query,
        anchor=PolicyPosition(rows[0][0], snapshots[0].expected_policy_sha256),
        tip=PolicyPosition(rows[-1][0], snapshots[-1].expected_policy_sha256),
    )


def test_real_signed_window():
    value = inspect_signed_policy_window(**signed_window([(1, (), "g1"), (2, (), "g2")]))
    assert value.signed_window_constraints_satisfied
    assert len(value.observations) == 2
    assert not value.policy_currentness_verified
    assert not value.policy_authority_authenticated
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted


@pytest.mark.parametrize(
    "rows,reason",
    [
        ([(1, (), "g1"), (1, (), "g2")], "SAME_SEQUENCE_FORK"),
        ([(1, (), "g1"), (3, (), "g3")], "SEQUENCE_GAP"),
        ([(2, (), "g2"), (1, (), "g1"), (2, (), "g2")], "OBSERVED_ROLLBACK"),
        ([(1, ("b" * 64,), "g1"), (2, (), "g2")], "DENIAL_REMOVAL"),
    ],
    ids=["fork", "gap", "rollback", "denial-removal"],
)
def test_real_signed_policy_constraints(rows, reason):
    value = inspect_signed_policy_window(**signed_window(rows))
    assert not value.signed_window_constraints_satisfied
    assert any(reason in code for code in value.reason_codes)


def test_invalid_intermediate_signature_cannot_be_filtered():
    args = signed_window([(1, (), "g1"), (2, (), "g2"), (3, (), "g3")])
    args["snapshots"] = (
        args["snapshots"][0],
        replace(args["snapshots"][1], policy_signature=bytes(64)),
        args["snapshots"][2],
    )
    with pytest.raises(ScopePolicyRejected, match="SIGNATURE_INVALID"):
        inspect_signed_policy_window(**args)


def test_signed_tip_deny_never_selects_old_good():
    value = inspect_signed_policy_window(**signed_window([(1, (), "g1"), (2, ("a" * 64,), "g2")]))
    assert value.window.window_constraints_satisfied
    assert not value.signed_window_constraints_satisfied
    assert "POLICY_WINDOW_TIP_DOES_NOT_PERMIT_EXACT_SCOPE" in value.reason_codes
