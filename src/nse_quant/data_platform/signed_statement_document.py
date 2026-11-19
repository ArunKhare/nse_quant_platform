"""Whole-document syntax plus pinned-key cryptography, without issuer trust."""

from __future__ import annotations

from dataclasses import dataclass

from nse_quant.data_platform.identity_statement_document import (
    VERSION as DOCUMENT_VERSION,
)
from nse_quant.data_platform.identity_statement_document import (
    StatementDocument,
    parse_statement_document,
)
from nse_quant.data_platform.statement_signature import (
    SignatureEvidence,
    verify_pinned_statement_signature,
)

VERSION = "signed-untrusted-statement-document@1"


@dataclass(frozen=True)
class SignedStatementDocument:
    version: str
    document: StatementDocument
    signature: SignatureEvidence
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    authorized_revocation_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def inspect_signed_statement_document(
    payload: bytes,
    *,
    signature: bytes,
    public_key: bytes,
    expected_public_key_sha256: str,
) -> SignedStatementDocument:
    """No I/O or persistence. All records validate; no selected-prefix salvage.

    Signature validity is separate from statement meaning. In particular multiple
    same-subject records are retained, not resolved by a signature or row order.
    No existing recorded-content gate or canonical binding is promoted.
    """
    if DOCUMENT_VERSION != "underlying-statement-document@1":
        raise ValueError("UNSUPPORTED_SIGNATURE_DOCUMENT_VERSION")
    document = parse_statement_document(payload)
    evidence = verify_pinned_statement_signature(
        payload,
        signature=signature,
        public_key=public_key,
        expected_public_key_sha256=expected_public_key_sha256,
    )
    return SignedStatementDocument(VERSION, document, evidence)
