"""Integration with the actual document parser; synthetic keys and statements only."""

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.identity_statement_document import (
    VERSION,
    StatementDocumentRejected,
    canonical,
)
from nse_quant.data_platform.signed_statement_document import inspect_signed_statement_document
from nse_quant.data_platform.statement_signature import signing_message


def record(record_id="r1", assertion="ASSERTED"):
    return canonical(
        dict(
            statement_schema=VERSION,
            record_id=record_id,
            namespace="SYNTHETIC",
            external_id="TEST",
            asset_kind="INDEX",
            asserted_issuer="UNTRUSTED",
            assertion=assertion,
        )
    ).encode()


def inspect(payload):
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    return inspect_signed_statement_document(
        payload,
        signature=private.sign(signing_message(payload)),
        public_key=key,
        expected_public_key_sha256=hashlib.sha256(key).hexdigest(),
    )


def test_real_parser_and_signature_keep_conflicting_claims_unresolved():
    payload = record() + b"\r\n" + record("r2", "WITHDRAWN") + b"\r\n"
    value = inspect(payload)
    assert value.signature.cryptographic_signature_verified
    assert len(value.document.records) == 2
    assert value.document.records[1].byte_start == len(record()) + 2
    assert not value.issuer_authenticated
    assert not value.namespace_authority_verified
    assert not value.identity_verified
    assert not value.authorized_revocation_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_underlying_id is None


def test_valid_signature_cannot_salvage_malformed_later_record():
    with pytest.raises(StatementDocumentRejected):
        inspect(record() + b"\n{}\n")
