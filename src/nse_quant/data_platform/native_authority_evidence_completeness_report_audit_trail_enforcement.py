"""Native authority evidence completeness report audit-trail enforcement and replay integration.

Enforces the governed lifecycle of retained audit trails for reconciled
completeness reports across identity/time, availability, and economic-validity
evidence. This module is observational only and does not grant eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-enforcement@1"
COMMAND = "enforce.native_authority_evidence_completeness_report_audit_trail_enforcement@1"
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
LIFECYCLE_STAGES = (
    "retained",
    "validated",
    "reconciled",
    "audited",
    "orphan_checked",
    "final_audited",
    "persisted",
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


def enforce_authority_evidence_completeness_report_audit_trail(
    retained: dict[str, Any],
) -> dict[str, Any]:
    """Enforce the governed lifecycle of a retained audit trail exactly."""
    if type(retained) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_RETAINED_REQUIRED")
    if retained.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if retained.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if retained.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    envelope = retained.get("retained")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_RETAINED_ENVELOPE_REQUIRED")
    audit_trail = envelope.get("audit_trail")
    if type(audit_trail) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_REQUIRED")
    if audit_trail.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    fingerprint = retained.get("governance_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_GOVERNANCE_FINGERPRINT_MISMATCH")
    report = audit_trail.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    enforced = len(missing) == 0
    enforced_envelope = {
        "version": VERSION,
        "audit_trail": audit_trail,
        "complete": enforced,
        "missing_obligations": missing,
        "audit_integrated": "audit" in obligations,
        "orphan_check_integrated": "orphan_check" in obligations,
        "final_audit_integrated": "final_audit" in obligations,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "enforcement_completed": True,
        "version": VERSION,
        "enforced": enforced_envelope,
        "enforcement_fingerprint": hashlib.sha256(_canonical_bytes(enforced_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }
