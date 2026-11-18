"""Native authoritative identity, derivative binding, and authorized revocation evidence.

Records independently sourced canonical identity, derivative binding, and
authorized revocation evidence from accepted authorities. Records are immutable
first-write evidence and replay exactly. This module is observational only and
does not grant eligibility, live trading, healing, backfill, adoption, deletion,
or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-identity-derivative-binding-revocation-evidence@1"
COMMAND = "record.native_authoritative_identity_derivative_binding_revocation_evidence@1"
EVIDENCE_KINDS = (
    "canonical_identity",
    "derivative_binding",
    "authorized_revocation",
)


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _iso(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _nonempty(value: object, maximum: int = 256) -> bool:
    return type(value) is str and 0 < len(value) <= maximum


def _validate_evidence(evidence: dict[str, Any]) -> None:
    if type(evidence) is not dict:
        raise Rejected("AUTHORITATIVE_EVIDENCE_DOCUMENT_REQUIRED")
    if evidence.get("version") != VERSION:
        raise Rejected("AUTHORITATIVE_EVIDENCE_VERSION_MISMATCH")
    if evidence.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if evidence.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITATIVE_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if evidence.get("healed") is True:
        raise Rejected("AUTHORITATIVE_EVIDENCE_HEALING_FORBIDDEN")
    authority = evidence.get("authority")
    if type(authority) is not dict:
        raise Rejected("ACCEPTED_AUTHORITY_REQUIRED")
    if not _nonempty(authority.get("authority_id")):
        raise Rejected("AUTHORITY_ID_REQUIRED")
    if authority.get("accepted") is not True:
        raise Rejected("AUTHORITY_NOT_ACCEPTED")
    if not _pin(authority.get("authority_fingerprint")):
        raise Rejected("AUTHORITY_FINGERPRINT_INVALID")
    if not _iso(evidence.get("recorded_at")):
        raise Rejected("RECORDED_AT_REQUIRED")
    if not _iso(evidence.get("knowledge_cutoff")):
        raise Rejected("KNOWLEDGE_CUTOFF_REQUIRED")
    canonical_identity = evidence.get("canonical_identity")
    if type(canonical_identity) is not dict:
        raise Rejected("CANONICAL_IDENTITY_REQUIRED")
    if not _nonempty(canonical_identity.get("canonical_symbol")):
        raise Rejected("CANONICAL_SYMBOL_REQUIRED")
    if canonical_identity.get("identity_source") != "accepted_authority":
        raise Rejected("CANONICAL_IDENTITY_SOURCE_INVALID")
    if not _pin(canonical_identity.get("identity_fingerprint")):
        raise Rejected("CANONICAL_IDENTITY_FINGERPRINT_INVALID")
    derivative_binding = evidence.get("derivative_binding")
    if type(derivative_binding) is not dict:
        raise Rejected("DERIVATIVE_BINDING_REQUIRED")
    if not _nonempty(derivative_binding.get("underlying_symbol")):
        raise Rejected("UNDERLYING_SYMBOL_REQUIRED")
    if not _nonempty(derivative_binding.get("derivative_symbol")):
        raise Rejected("DERIVATIVE_SYMBOL_REQUIRED")
    if derivative_binding.get("binding_source") != "accepted_authority":
        raise Rejected("DERIVATIVE_BINDING_SOURCE_INVALID")
    if not _pin(derivative_binding.get("binding_fingerprint")):
        raise Rejected("DERIVATIVE_BINDING_FINGERPRINT_INVALID")
    revocation = evidence.get("authorized_revocation")
    if type(revocation) is not dict:
        raise Rejected("AUTHORIZED_REVOCATION_REQUIRED")
    if revocation.get("revoked") not in (True, False):
        raise Rejected("REVOCATION_STATUS_REQUIRED")
    if revocation.get("revocation_source") != "accepted_authority":
        raise Rejected("REVOCATION_SOURCE_INVALID")
    if not _pin(revocation.get("revocation_fingerprint")):
        raise Rejected("REVOCATION_FINGERPRINT_INVALID")
    if not _iso(revocation.get("revocation_effective_at")):
        raise Rejected("REVOCATION_EFFECTIVE_AT_REQUIRED")


def evidence_context(evidence: dict[str, Any]) -> str:
    """Return the exact canonical SHA-256 context for authoritative evidence."""
    _validate_evidence(evidence)
    return _sha(evidence)


def record_authoritative_identity_derivative_binding_revocation_evidence(
    evidence: dict[str, Any],
    *,
    expected_context_sha256: str,
) -> dict[str, Any]:
    """Record one immutable authoritative evidence bundle with exact context."""
    _validate_evidence(evidence)
    if not _pin(expected_context_sha256):
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")
    context = _sha(evidence)
    if context != expected_context_sha256:
        raise Rejected("REVIEWED_AUTHORITATIVE_CONTEXT_CHANGED")
    revision_id = _sha([VERSION, COMMAND, context])
    return {
        "recorded": True,
        "version": VERSION,
        "revision_id": revision_id,
        "recording_fingerprint": context,
        "evidence": evidence,
        "evidence_kinds": list(EVIDENCE_KINDS),
        "immutable": True,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "deleted": False,
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_identity_derivative_binding_revocation_evidence(
    recorded: dict[str, Any],
    *,
    expected_revision_id: str,
    expected_recording_fingerprint: str,
) -> dict[str, Any]:
    """Exactly replay recorded authoritative evidence without mutation."""
    if type(recorded) is not dict:
        raise Rejected("AUTHORITATIVE_EVIDENCE_RECORDED_RESULT_REQUIRED")
    if recorded.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if recorded.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if recorded.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if recorded.get("recorded") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_RECORDING_INCOMPLETE")
    evidence = recorded.get("evidence")
    if type(evidence) is not dict:
        raise Rejected("AUTHORITATIVE_EVIDENCE_DOCUMENT_REQUIRED")
    if evidence.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if not _pin(expected_revision_id) or not _pin(expected_recording_fingerprint):
        raise Rejected("EXACT_EVIDENCE_PINS_REQUIRED")
    if recorded.get("revision_id") != expected_revision_id:
        raise Rejected("AUTHORITY_EVIDENCE_REVISION_MISMATCH")
    context = _sha(evidence)
    if context != expected_recording_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RECORDING_FINGERPRINT_MISMATCH")
    expected_revision = _sha([VERSION, COMMAND, context])
    if expected_revision != expected_revision_id:
        raise Rejected("AUTHORITY_EVIDENCE_REVISION_MISMATCH")
    _validate_evidence(evidence)
    return {
        "replayed": True,
        "version": VERSION,
        "revision_id": expected_revision_id,
        "recording_fingerprint": expected_recording_fingerprint,
        "evidence": evidence,
        "evidence_kinds": list(EVIDENCE_KINDS),
        "immutable": True,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "deleted": False,
        "decision_eligibility_asserted": False,
    }
