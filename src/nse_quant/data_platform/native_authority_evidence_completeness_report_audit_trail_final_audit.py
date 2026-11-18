"""Native authority evidence completeness report audit-trail final audit and replay integration.

Performs a final audit on reconciled audit trails for reconciled completeness
reports across identity/time, availability, and economic-validity evidence and
replays them exactly across audit, orphan-check, and final-audit obligations.
This module is observational only and does not grant eligibility, live trading,
healing, backfill, adoption, or execution authority. POINT_IN_TIME_DECISION
remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-final-audit@1"
COMMAND = "final_audit.native_authority_evidence_completeness_report_audit_trail_final_audit@1"
EVIDENCE_KINDS = (
    "identity_time",
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
        ensure_ascii=False,
    ).encode("utf-8")


def final_audit_authority_evidence_completeness_report_audit_trail(
    reconciled: dict[str, Any],
) -> dict[str, Any]:
    """Final-audit a reconciled authority-evidence completeness report audit trail exactly."""
    if type(reconciled) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_RECONCILED_REQUIRED")
    if reconciled.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if reconciled.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if reconciled.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    envelope = reconciled.get("reconciled")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_RECONCILED_ENVELOPE_REQUIRED")
    audit_trail = envelope.get("audit_trail")
    if type(audit_trail) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_REQUIRED")
    if audit_trail.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    fingerprint = reconciled.get("reconciliation_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_RECONCILIATION_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RECONCILIATION_FINGERPRINT_MISMATCH")
    report = audit_trail.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    final_audited = {
        "version": VERSION,
        "audit_trail": audit_trail,
        "complete": len(missing) == 0,
        "missing_obligations": missing,
        "audit_integrated": "audit" in obligations,
        "orphan_check_integrated": "orphan_check" in obligations,
        "final_audit_integrated": "final_audit" in obligations,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "final_audit_completed": True,
        "version": VERSION,
        "final_audited": final_audited,
        "final_audit_fingerprint": hashlib.sha256(_canonical_bytes(final_audited)).hexdigest(),
        "decision_eligibility_asserted": False,
    }
