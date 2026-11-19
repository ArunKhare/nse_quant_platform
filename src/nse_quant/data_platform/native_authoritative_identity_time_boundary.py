"""Authoritative identity and time boundary for native iron-condor decisions.

Validates independently evidenced canonical underlying identity, derivative
binding, and authorized revocation before native decision inputs may be
considered reconciled. This is observational validation only: no eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-identity-time-boundary@1"
COMMAND = "validate.native_authoritative_identity_time_boundary@1"
MAX_DOCUMENT_BYTES = 262_144
AUTHORITATIVE_REQUIREMENT = "authoritative_identity_and_time"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _required(document: dict[str, Any], key: str) -> object:
    if key not in document:
        raise Rejected(f"AUTHORITATIVE_{key.upper()}_REQUIRED")
    return document[key]


def _identity(document: dict[str, Any]) -> None:
    identity = _required(document, "identity")
    if type(identity) is not dict:
        raise Rejected("AUTHORITATIVE_IDENTITY_DOCUMENT_REQUIRED")
    canonical_underlying = _required(identity, "canonical_underlying")
    if canonical_underlying not in ("NIFTY", "BANKNIFTY"):
        raise Rejected("AUTHORITATIVE_CANONICAL_UNDERLYING_INVALID")
    source = _required(identity, "source")
    if source != "exchange_master":
        raise Rejected("AUTHORITATIVE_IDENTITY_SOURCE_INVALID")
    revision = _required(identity, "revision_id")
    fingerprint = _required(identity, "recording_fingerprint")
    if not _pin(revision) or not _pin(fingerprint):
        raise Rejected("AUTHORITATIVE_IDENTITY_EVIDENCE_INVALID")


def _derivative(document: dict[str, Any]) -> None:
    derivative = _required(document, "derivative")
    if type(derivative) is not dict:
        raise Rejected("AUTHORITATIVE_DERIVATIVE_DOCUMENT_REQUIRED")
    if derivative.get("binding") != "canonical_underlying_to_derivative":
        raise Rejected("AUTHORITATIVE_DERIVATIVE_BINDING_INVALID")
    if not _pin(_required(derivative, "revision_id")):
        raise Rejected("AUTHORITATIVE_DERIVATIVE_REVISION_INVALID")
    if not _pin(_required(derivative, "recording_fingerprint")):
        raise Rejected("AUTHORITATIVE_DERIVATIVE_FINGERPRINT_INVALID")


def _revocation(document: dict[str, Any]) -> None:
    revocation = _required(document, "authorized_revocation")
    if type(revocation) is not dict:
        raise Rejected("AUTHORITATIVE_REVOCATION_DOCUMENT_REQUIRED")
    if revocation.get("authorized") is not True:
        raise Rejected("AUTHORITATIVE_REVOCATION_NOT_AUTHORIZED")
    if not _pin(_required(revocation, "revision_id")):
        raise Rejected("AUTHORITATIVE_REVOCATION_REVISION_INVALID")
    if not _pin(_required(revocation, "recording_fingerprint")):
        raise Rejected("AUTHORITATIVE_REVOCATION_FINGERPRINT_INVALID")


def validate_authoritative_identity_time_boundary(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Validate the authoritative identity and time boundary document."""
    if type(document) is not dict:
        raise Rejected("AUTHORITATIVE_BOUNDARY_DOCUMENT_REQUIRED")
    if document.get("version") != VERSION:
        raise Rejected("AUTHORITATIVE_BOUNDARY_VERSION_MISMATCH")
    if document.get("requirement") != AUTHORITATIVE_REQUIREMENT:
        raise Rejected("AUTHORITATIVE_BOUNDARY_REQUIREMENT_MISMATCH")
    if document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if document.get("auto_coverable") is not False:
        raise Rejected("AUTHORITATIVE_BOUNDARY_NOT_AUTO_COVERABLE")
    if document.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITATIVE_ELIGIBILITY_FORBIDDEN")

    _identity(document)
    _derivative(document)
    _revocation(document)

    return {
        "valid": True,
        "version": VERSION,
        "requirement": AUTHORITATIVE_REQUIREMENT,
        "decision_eligibility_asserted": False,
        "document_sha256": _sha(_canonical(document)),
    }


def authoritative_boundary_context(document: dict[str, Any]) -> str:
    """Return the exact context hash for a validated boundary document."""
    result = validate_authoritative_identity_time_boundary(document)
    return result["document_sha256"]
