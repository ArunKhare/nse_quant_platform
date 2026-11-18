"""Native authority evidence completeness report audit-trail persistence and replay integration.

Persists and exactly replays enforced audit trails for reconciled completeness
reports across identity/time, availability, and economic-validity evidence.
This module is observational only and does not grant eligibility, live trading,
healing, backfill, adoption, or execution authority. POINT_IN_TIME_DECISION
remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-persistence-replay@1"
COMMAND = "persist.native_authority_evidence_completeness_report_audit_trail_persistence_replay@1"
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


def _validate_enforced(enforced: dict[str, Any]) -> dict[str, Any]:
    if type(enforced) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCED_RESULT_REQUIRED")
    if enforced.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if enforced.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if enforced.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if enforced.get("enforcement_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_INCOMPLETE")
    envelope = enforced.get("enforced")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = enforced.get("enforcement_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_MISMATCH")
    if envelope.get("lifecycle_stages") != list(LIFECYCLE_STAGES):
        raise Rejected("AUTHORITY_EVIDENCE_LIFECYCLE_MISMATCH")
    return envelope


def persist_authority_evidence_completeness_report_audit_trail(
    enforced: dict[str, Any],
) -> dict[str, Any]:
    """Persist an enforced authority-evidence completeness report audit trail exactly."""
    envelope = _validate_enforced(enforced)
    audit_trail = envelope.get("audit_trail")
    if type(audit_trail) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_REQUIRED")
    report = audit_trail.get("report")
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_REQUIRED")
    obligations = report.get("obligations")
    if type(obligations) is not list:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_REQUIRED")
    missing = [obligation for obligation in REQUIRED_OBLIGATIONS if obligation not in obligations]
    persisted_envelope = {
        "version": VERSION,
        "enforced_envelope": envelope,
        "enforcement_fingerprint": enforced["enforcement_fingerprint"],
        "complete": len(missing) == 0,
        "missing_obligations": missing,
        "audit_integrated": "audit" in obligations,
        "orphan_check_integrated": "orphan_check" in obligations,
        "final_audit_integrated": "final_audit" in obligations,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "persistence_completed": True,
        "version": VERSION,
        "persisted": persisted_envelope,
        "persistence_fingerprint": hashlib.sha256(_canonical_bytes(persisted_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def replay_authority_evidence_completeness_report_audit_trail(
    persisted: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay a persisted authority-evidence completeness report audit trail."""
    if type(persisted) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTED_RESULT_REQUIRED")
    if persisted.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if persisted.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if persisted.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if persisted.get("persistence_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTENCE_INCOMPLETE")
    envelope = persisted.get("persisted")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = persisted.get("persistence_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_MISMATCH")
    if envelope.get("lifecycle_stages") != list(LIFECYCLE_STAGES):
        raise Rejected("AUTHORITY_EVIDENCE_LIFECYCLE_MISMATCH")
    enforced_envelope = envelope.get("enforced_envelope")
    if type(enforced_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCED_ENVELOPE_REQUIRED")
    enforcement_fingerprint = envelope.get("enforcement_fingerprint")
    if not _pin(enforcement_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(enforced_envelope)).hexdigest() != enforcement_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_MISMATCH")
    return {
        "replayed": True,
        "version": VERSION,
        "enforced_envelope": enforced_envelope,
        "enforcement_fingerprint": enforcement_fingerprint,
        "persistence_fingerprint": fingerprint,
        "complete": envelope.get("complete") is True,
        "missing_obligations": list(envelope.get("missing_obligations", [])),
        "audit_integrated": envelope.get("audit_integrated") is True,
        "orphan_check_integrated": envelope.get("orphan_check_integrated") is True,
        "final_audit_integrated": envelope.get("final_audit_integrated") is True,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "healed": False,
        "decision_eligibility_asserted": False,
    }
