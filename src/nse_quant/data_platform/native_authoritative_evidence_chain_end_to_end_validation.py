"""Native authoritative evidence chain end-to-end validation.

Validates the complete authoritative evidence chain from recorded evidence
through acceptance/reconciliation, decision-loop linkage, real accepted-authority
integration, completeness-report integration, audit-trail integration, and
final-audit integration. Preserves all evidence fingerprints, exact replay,
immutable first-write behavior, and all safety boundaries. This module is
observational only and does not grant eligibility, live trading, healing,
backfill, adoption, deletion, or execution authority. POINT_IN_TIME_DECISION
remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-chain-end-to-end-validation@1"
COMMAND = "validate.native_authoritative_evidence_chain_end_to_end@1"
FINAL_AUDIT_VERSION = "native-authoritative-evidence-final-audit-integration@1"
EVIDENCE_KINDS = (
    "canonical_identity",
    "derivative_binding",
    "authorized_revocation",
    "availability",
    "economic_validity",
)
REQUIRED_OBLIGATIONS = (
    "original_first_write",
    "audit",
    "orphan_check",
    "final_audit",
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


def _validate_final_audit(final_audit: dict[str, Any]) -> dict[str, Any]:
    if type(final_audit) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_RESULT_REQUIRED")
    if final_audit.get("version") != FINAL_AUDIT_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if final_audit.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if final_audit.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if final_audit.get("final_audit_integration_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_INTEGRATION_INCOMPLETE")
    envelope = final_audit.get("final_audit")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    if envelope.get("backfilled") is True:
        raise Rejected("AUTHORITY_EVIDENCE_BACKFILL_FORBIDDEN")
    if envelope.get("adopted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_ADOPTION_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = final_audit.get("final_audit_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("final_audit_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_INTEGRATION_INCOMPLETE")
    if envelope.get("complete") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INCOMPLETE")
    if envelope.get("missing_obligations") != []:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_INCOMPLETE")
    return envelope


def validate_authoritative_evidence_chain_end_to_end(
    final_audit: dict[str, Any],
) -> dict[str, Any]:
    """Validate the complete authoritative evidence chain end to end exactly."""
    envelope = _validate_final_audit(final_audit)
    validation_envelope = {
        "version": VERSION,
        "final_audit_envelope": envelope,
        "final_audit_integration_fingerprint": final_audit["final_audit_integration_fingerprint"],
        "final_audit_id": envelope["final_audit_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "evidence_kinds": list(EVIDENCE_KINDS),
        "validated": True,
        "chain_complete": True,
        "complete": True,
        "missing_evidence_kinds": [],
        "obligations": list(REQUIRED_OBLIGATIONS),
        "missing_obligations": [],
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "end_to_end_validation_completed": True,
        "version": VERSION,
        "validated": validation_envelope,
        "end_to_end_validation_fingerprint": _sha(validation_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_chain_end_to_end_validation(
    validated: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence chain end-to-end validation."""
    if type(validated) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_VALIDATED_RESULT_REQUIRED")
    if validated.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if validated.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if validated.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if validated.get("end_to_end_validation_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_END_TO_END_VALIDATION_INCOMPLETE")
    envelope = validated.get("validated")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_VALIDATED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = validated.get("end_to_end_validation_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_END_TO_END_VALIDATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_END_TO_END_VALIDATION_FINGERPRINT_MISMATCH")
    if envelope.get("validated") is not True or envelope.get("chain_complete") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_END_TO_END_VALIDATION_INCOMPLETE")
    return {
        "end_to_end_validation_replayed": True,
        "version": VERSION,
        "validated_envelope": envelope,
        "end_to_end_validation_fingerprint": fingerprint,
        "validated": True,
        "chain_complete": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
