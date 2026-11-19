"""Native authority evidence completeness report audit trail and reconciliation integration.

Builds an audit trail for reconciled completeness reports across identity/time,
availability, and economic-validity evidence with exact audit, orphan-check, and
final-audit integration. This module is observational only and does not grant
eligibility, live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail@1"
COMMAND = "audit.native_authority_evidence_completeness_report_audit_trail@1"
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


def build_authority_evidence_completeness_report_audit_trail(
    reconciled: dict[str, Any],
) -> dict[str, Any]:
    """Build an audit trail for a reconciled authority-evidence completeness report."""
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
    report = envelope.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    if report.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    fingerprint = reconciled.get("reconciliation_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_RECONCILIATION_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RECONCILIATION_FINGERPRINT_MISMATCH")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    audit_trail = {
        "version": VERSION,
        "report": report,
        "complete": len(missing) == 0,
        "missing_obligations": missing,
        "audit_integrated": "audit" in obligations,
        "orphan_check_integrated": "orphan_check" in obligations,
        "final_audit_integrated": "final_audit" in obligations,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "audit_trail_built": True,
        "version": VERSION,
        "audit_trail": audit_trail,
        "audit_trail_fingerprint": hashlib.sha256(_canonical_bytes(audit_trail)).hexdigest(),
        "decision_eligibility_asserted": False,
    }
