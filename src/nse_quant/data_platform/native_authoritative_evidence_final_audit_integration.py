"""Native authoritative evidence final-audit integration.

Integrates completeness-report audit-trail evidence with final-audit evidence.
Preserves all evidence fingerprints, exact replay, immutable first-write
behavior, and all safety boundaries. This module is observational only and does
not grant eligibility, live trading, healing, backfill, adoption, deletion, or
execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-final-audit-integration@1"
COMMAND = "integrate.native_authoritative_evidence_final_audit@1"
AUDIT_TRAIL_VERSION = "native-authoritative-evidence-completeness-report-audit-trail-integration@1"
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


def _validate_audit_trail(audit_trail: dict[str, Any]) -> dict[str, Any]:
    if type(audit_trail) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_RESULT_REQUIRED")
    if audit_trail.get("version") != AUDIT_TRAIL_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if audit_trail.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if audit_trail.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if audit_trail.get("audit_trail_integration_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_INCOMPLETE")
    envelope = audit_trail.get("audit_trail")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_ENVELOPE_REQUIRED")
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
    fingerprint = audit_trail.get("audit_trail_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("audit_trail_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_INCOMPLETE")
    if envelope.get("complete") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INCOMPLETE")
    if envelope.get("missing_obligations") != []:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_INCOMPLETE")
    return envelope


def integrate_authoritative_evidence_with_final_audit(
    audit_trail: dict[str, Any],
    *,
    final_audit_id: str,
) -> dict[str, Any]:
    """Integrate completeness-report audit-trail evidence with final-audit evidence."""
    envelope = _validate_audit_trail(audit_trail)
    if type(final_audit_id) is not str or not final_audit_id:
        raise Rejected("EXACT_FINAL_AUDIT_ID_REQUIRED")
    final_audit_envelope = {
        "version": VERSION,
        "audit_trail_envelope": envelope,
        "audit_trail_integration_fingerprint": audit_trail["audit_trail_integration_fingerprint"],
        "final_audit_id": final_audit_id,
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "evidence_kinds": list(EVIDENCE_KINDS),
        "integrated": True,
        "final_audit_integrated": True,
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
        "final_audit_integration_completed": True,
        "version": VERSION,
        "final_audit": final_audit_envelope,
        "final_audit_integration_fingerprint": _sha(final_audit_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_final_audit_integration(
    final_audit: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence final-audit integration."""
    if type(final_audit) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_RESULT_REQUIRED")
    if final_audit.get("version") != VERSION:
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
    fingerprint = final_audit.get("final_audit_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("final_audit_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_INTEGRATION_INCOMPLETE")
    return {
        "final_audit_integration_replayed": True,
        "version": VERSION,
        "final_audit_envelope": envelope,
        "final_audit_integration_fingerprint": fingerprint,
        "integrated": True,
        "final_audit_integrated": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
