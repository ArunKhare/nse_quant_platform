"""Native authority evidence completeness report validation and audit integration.

Validates round-tripped completeness reports across identity/time, availability,
and economic-validity evidence with exact audit, orphan-check, and final-audit
integration. This module is observational only and does not grant eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-validation@1"
COMMAND = "validate.native_authority_evidence_completeness_report_validation@1"
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


def validate_authority_evidence_completeness_report(
    round_tripped: dict[str, Any],
) -> dict[str, Any]:
    """Validate a round-tripped authority-evidence completeness report exactly."""
    if type(round_tripped) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ROUND_TRIP_REQUIRED")
    if round_tripped.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if round_tripped.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if round_tripped.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    report = round_tripped.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    if report.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    fingerprint = round_tripped.get("round_trip_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ROUND_TRIP_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(report)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ROUND_TRIP_FINGERPRINT_MISMATCH")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    return {
        "validated": True,
        "version": VERSION,
        "report": report,
        "round_trip_fingerprint": fingerprint,
        "complete": len(missing) == 0,
        "missing_obligations": missing,
        "audit_integrated": "audit" in obligations,
        "orphan_check_integrated": "orphan_check" in obligations,
        "final_audit_integrated": "final_audit" in obligations,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
