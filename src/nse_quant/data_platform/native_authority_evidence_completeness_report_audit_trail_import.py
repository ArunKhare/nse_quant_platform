"""Native authority evidence completeness report audit-trail import and replay integration.

Imports exported audit trails for reconciled completeness reports across
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

VERSION = "native-authority-evidence-completeness-report-audit-trail-import@1"
COMMAND = "import.native_authority_evidence_completeness_report_audit_trail_import@1"
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


def import_authority_evidence_completeness_report_audit_trail(
    exported: dict[str, Any],
) -> dict[str, Any]:
    """Import an exported authority-evidence completeness report audit trail exactly."""
    if type(exported) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXPORT_REQUIRED")
    if exported.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if exported.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if exported.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    export = exported.get("export")
    if type(export) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXPORT_ENVELOPE_REQUIRED")
    audit_trail = export.get("audit_trail")
    if type(audit_trail) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_REQUIRED")
    if audit_trail.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    fingerprint = exported.get("export_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_EXPORT_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(export)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_EXPORT_FINGERPRINT_MISMATCH")
    report = audit_trail.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    return {
        "imported": True,
        "version": VERSION,
        "audit_trail": audit_trail,
        "export_fingerprint": fingerprint,
        "complete": len(missing) == 0,
        "missing_obligations": missing,
        "audit_integrated": "audit" in obligations,
        "orphan_check_integrated": "orphan_check" in obligations,
        "final_audit_integrated": "final_audit" in obligations,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
