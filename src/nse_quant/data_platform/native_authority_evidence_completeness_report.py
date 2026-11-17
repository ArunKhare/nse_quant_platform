"""Native authority evidence completeness report and audit integration.

Produces a consolidated completeness report across identity/time, availability,
and economic-validity evidence with exact audit, orphan-check, and final-audit
integration. This module is observational only and does not grant eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report@1"
COMMAND = "report.native_authority_evidence_completeness_report@1"
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


def _validate_evidence(evidence: dict[str, Any]) -> None:
    if evidence.get("kind") not in EVIDENCE_KINDS:
        raise Rejected("AUTHORITY_EVIDENCE_KIND_INVALID")
    if evidence.get("source_authority") != "accepted_authority":
        raise Rejected("AUTHORITY_EVIDENCE_SOURCE_INVALID")
    if not _pin(evidence.get("revision_id")) or not _pin(evidence.get("recording_fingerprint")):
        raise Rejected("AUTHORITY_EVIDENCE_PINS_INVALID")


def build_authority_evidence_completeness_report(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Build a consolidated completeness report for authority evidence."""
    if type(document) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_DOCUMENT_REQUIRED")
    if document.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if document.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    evidence = document.get("evidence")
    if type(evidence) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REQUIRED")
    _validate_evidence(evidence)
    obligations = document.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    if len(obligations) != len(set(obligations)):
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_DUPLICATE")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    if document.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    return {
        "complete": len(missing) == 0,
        "version": VERSION,
        "evidence_kind": evidence["kind"],
        "obligations": list(obligations),
        "missing_obligations": missing,
        "audit_integrated": "audit" in obligations,
        "orphan_check_integrated": "orphan_check" in obligations,
        "final_audit_integrated": "final_audit" in obligations,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
