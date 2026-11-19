"""Native authority evidence replay and audit integration.

Replays recorded authority evidence across identity/time, availability, and
economic-validity obligations with exact audit, orphan-check, and final-audit
integration. This module is observational only and does not grant eligibility,
live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-replay-audit@1"
COMMAND = "replay.native_authority_evidence_replay_audit@1"
EVIDENCE_KINDS = (
    "identity_time",
    "availability",
    "economic_validity",
)
OBLIGATIONS = (
    "original_first_write",
    "audit",
    "orphan_check",
    "final_audit",
)


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_document(document: dict[str, Any]) -> dict[str, Any]:
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
    if evidence.get("kind") not in EVIDENCE_KINDS:
        raise Rejected("AUTHORITY_EVIDENCE_KIND_INVALID")
    if evidence.get("source_authority") != "accepted_authority":
        raise Rejected("AUTHORITY_EVIDENCE_SOURCE_INVALID")
    if not _pin(evidence.get("revision_id")) or not _pin(evidence.get("recording_fingerprint")):
        raise Rejected("AUTHORITY_EVIDENCE_PINS_INVALID")
    if document.get("obligation") not in OBLIGATIONS:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATION_INVALID")
    if document.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    return evidence


def replay_authority_evidence(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Replay a recorded authority-evidence obligation exactly."""
    evidence = _validate_document(document)
    return {
        "replayed": True,
        "version": VERSION,
        "evidence_kind": evidence["kind"],
        "obligation": document["obligation"],
        "audit_integrated": document["obligation"] in ("audit", "final_audit"),
        "orphan_check_integrated": document["obligation"] == "orphan_check",
        "final_audit_integrated": document["obligation"] == "final_audit",
        "healed": False,
        "decision_eligibility_asserted": False,
    }
