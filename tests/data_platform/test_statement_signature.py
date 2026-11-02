"""Real cryptography on disposable generated keys, not issuer-authentication E2E."""

import hashlib
from dataclasses import asdict
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.statement_signature import (
    DOMAIN,
    MAX_PAYLOAD_BYTES,
    signing_message,
    verify_pinned_statement_signature,
)


@pytest.fixture
def proof():
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    payload = b"synthetic untrusted bytes\r\n"
    return private, key, payload, hashlib.sha256(key).hexdigest()


def verify(proof, **changes):
    private, key, payload, pin = proof
    arguments: dict[str, Any] = dict(
        signature=private.sign(signing_message(payload)),
        public_key=key,
        expected_public_key_sha256=pin,
    )
    arguments.update(changes)
    return verify_pinned_statement_signature(payload, **arguments)


def test_valid_signature_never_confers_authority(proof):
    value = verify(proof)
    assert value.cryptographic_signature_verified
    assert value.status == "valid_signature_under_pinned_key"
    for name, flag in asdict(value).items():
        if name.endswith(("authenticated", "asserted", "verified")):
            assert flag is (name == "cryptographic_signature_verified")
    assert value.canonical_underlying_id is None


def test_exact_profile_framing(proof):
    payload = proof[2]
    assert signing_message(payload) == DOMAIN + len(payload).to_bytes(8, "big") + payload


def test_pin_mismatch_does_not_fall_back(proof):
    value = verify(proof, expected_public_key_sha256="0" * 64)
    assert value.reason_codes == ("PUBLIC_KEY_PIN_MISMATCH",)
    assert not value.cryptographic_signature_verified


def test_foreign_signer_rejected(proof):
    other = Ed25519PrivateKey.generate()
    signature = other.sign(signing_message(proof[2]))
    assert not verify(proof, signature=signature).cryptographic_signature_verified


@pytest.mark.parametrize("mode", ["raw", "wrong-domain", "wrong-length", "lf", "modified"])
def test_no_profile_or_original_byte_substitution(proof, mode):
    private, _, payload, _ = proof
    messages = {
        "raw": payload,
        "wrong-domain": b"other" + signing_message(payload),
        "wrong-length": DOMAIN + (len(payload) + 1).to_bytes(8, "big") + payload,
        "lf": signing_message(payload.replace(b"\r\n", b"\n")),
        "modified": signing_message(payload + b"x"),
    }
    value = verify(proof, signature=private.sign(messages[mode]))
    assert value.reason_codes == ("DETACHED_SIGNATURE_INVALID",)


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("signature", b"x" * 63, id="short-signature"),
        pytest.param("signature", b"x" * 65, id="long-signature"),
        pytest.param("public_key", b"x" * 31, id="short-key"),
        pytest.param("public_key", bytearray(32), id="mutable-key"),
        pytest.param("expected_public_key_sha256", "A" * 64, id="uppercase-pin"),
        pytest.param("expected_public_key_sha256", None, id="missing-pin"),
    ],
)
def test_exact_input_shapes_required(proof, field, value):
    with pytest.raises(ValueError):
        verify(proof, **{field: value})


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"", id="empty"),
        pytest.param(bytearray(b"x"), id="mutable"),
        pytest.param(b"x" * (MAX_PAYLOAD_BYTES + 1), id="oversized"),
    ],
)
def test_payload_bounds(payload):
    with pytest.raises(ValueError):
        signing_message(payload)


def test_maximum_payload_allowed():
    payload = b"x" * MAX_PAYLOAD_BYTES
    assert signing_message(payload).endswith(payload)
