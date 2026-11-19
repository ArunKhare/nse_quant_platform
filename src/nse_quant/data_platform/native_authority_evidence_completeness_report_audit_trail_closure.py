"""Native authority evidence completeness report audit-trail closure and replay integration.

Closes final-audited audit trails for reconciled completeness reports across
identity/time, availability, and economic-validity evidence and replays them
exactly across audit, orphan-check, and final-audit obligations. This module is
observational only and does not grant eligibility, live trading, healing,
backfill, adoption, or execution authority. POINT_IN_TIME_DECISION remains
rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-closure@1"
COMMAND = "close.native_authority_evidence_completeness_report_audit_trail_closure@1"
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


def close_authority_evidence_completeness_report_audit_trail(
    final_audited: dict[str, Any],
) -> dict[str, Any]:
    """Close a final-audited authority-evidence completeness report audit trail exactly."""
    if type(final_audited) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDITED_REQUIRED")
    if final_audited.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if final_audited.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if final_audited.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    envelope = final_audited.get("final_audited")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDITED_ENVELOPE_REQUIRED")
    audit_trail = envelope.get("audit_trail")
    if type(audit_trail) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_REQUIRED")
    if audit_trail.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    fingerprint = final_audited.get("final_audit_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_FINAL_AUDIT_FINGERPRINT_MISMATCH")
    report = audit_trail.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    closed = {
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
        "closure_completed": True,
        "version": VERSION,
        "closed": closed,
        "closure_fingerprint": hashlib.sha256(_canonical_bytes(closed)).hexdigest(),
        "decision_eligibility_asserted": False,
    }
