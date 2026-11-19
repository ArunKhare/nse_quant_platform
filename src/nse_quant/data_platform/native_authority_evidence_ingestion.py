"""Native authority evidence ingestion.

Records independently sourced identity/time, availability, and economic-validity
evidence with original first-write, audit, orphan, and final-audit obligations.
This module is observational only and does not grant eligibility, live trading,
healing, backfill, adoption, or execution authority. POINT_IN_TIME_DECISION
remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-ingestion@1"
COMMAND = "ingest.native_authority_evidence_ingestion@1"
EVIDENCE_KINDS = (
    "identity_time",
    "availability",
    "economic_validity",
)


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_evidence(document: dict[str, Any]) -> dict[str, Any]:
    evidence = document.get("evidence")
    if type(evidence) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REQUIRED")
    if evidence.get("kind") not in EVIDENCE_KINDS:
        raise Rejected("AUTHORITY_EVIDENCE_KIND_INVALID")
    if not _pin(evidence.get("revision_id")) or not _pin(evidence.get("recording_fingerprint")):
        raise Rejected("AUTHORITY_EVIDENCE_PINS_INVALID")
    if evidence.get("source_authority") != "accepted_authority":
        raise Rejected("AUTHORITY_EVIDENCE_SOURCE_INVALID")
    return evidence


def ingest_authority_evidence(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Record an original authority-evidence first-write obligation."""
    if type(document) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_DOCUMENT_REQUIRED")
    if document.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if document.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    evidence = _require_evidence(document)
    if document.get("obligation") != "original_first_write":
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATION_INVALID")
    if document.get("duplicate") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DUPLICATE")
    return {
        "recorded": True,
        "version": VERSION,
        "evidence_kind": evidence["kind"],
        "obligation": "original_first_write",
        "audit_required": True,
        "orphan_check_required": True,
        "final_audit_required": True,
        "decision_eligibility_asserted": False,
    }


def audit_authority_evidence(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Audit a recorded authority-evidence obligation without healing it."""
    if type(document) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_DOCUMENT_REQUIRED")
    if document.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if document.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    evidence = _require_evidence(document)
    if document.get("obligation") not in (
        "original_first_write",
        "audit",
        "orphan_check",
        "final_audit",
    ):
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATION_INVALID")
    if document.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    return {
        "audited": True,
        "version": VERSION,
        "evidence_kind": evidence["kind"],
        "obligation": document["obligation"],
        "healed": False,
        "decision_eligibility_asserted": False,
    }
