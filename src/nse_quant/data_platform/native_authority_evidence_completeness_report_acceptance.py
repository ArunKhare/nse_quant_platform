"""Native authority evidence completeness report acceptance and audit integration.

Accepts validated completeness reports across identity/time, availability, and
economic-validity evidence with exact audit, orphan-check, and final-audit
integration. This module is observational only and does not grant eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-acceptance@1"
COMMAND = "accept.native_authority_evidence_completeness_report_acceptance@1"
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


def accept_authority_evidence_completeness_report(
    validated: dict[str, Any],
) -> dict[str, Any]:
    """Accept a validated authority-evidence completeness report exactly."""
    if type(validated) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_VALIDATED_REQUIRED")
    if validated.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if validated.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if validated.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    report = validated.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    if report.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    fingerprint = validated.get("round_trip_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ROUND_TRIP_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(report)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ROUND_TRIP_FINGERPRINT_MISMATCH")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    accepted = {
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
        "accepted": accepted,
        "version": VERSION,
        "acceptance_fingerprint": hashlib.sha256(_canonical_bytes(accepted)).hexdigest(),
        "decision_eligibility_asserted": False,
    }
