"""Native authoritative evidence completeness-report audit-trail integration.

Integrates completeness-report evidence with the audit-trail lifecycle.
Preserves all evidence fingerprints, exact replay, immutable first-write
behavior, and all safety boundaries. This module is observational only and does
not grant eligibility, live trading, healing, backfill, adoption, deletion, or
execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-completeness-report-audit-trail-integration@1"
COMMAND = "integrate.native_authoritative_evidence_completeness_report_audit_trail@1"
REPORT_VERSION = "native-authoritative-evidence-completeness-report-integration@1"
EVIDENCE_KINDS = (
    "canonical_identity",
    "derivative_binding",
    "authorized_revocation",
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
    "archived",
    "closed",
    "final_audited",
    "reconciled",
    "accepted",
    "validated",
    "round_tripped",
    "imported",
    "exported",
    "queried",
    "persisted",
)


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_report(report: dict[str, Any]) -> dict[str, Any]:
    if type(report) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_RESULT_REQUIRED")
    if report.get("version") != REPORT_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if report.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if report.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if report.get("completeness_report_integration_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_INCOMPLETE")
    envelope = report.get("report")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_REPORT_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    if envelope.get("backfilled") is True:
        raise Rejected("AUTHORITY_EVIDENCE_BACKFILL_FORBIDDEN")
    if envelope.get("adopted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_ADOPTION_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = report.get("completeness_report_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("completeness_report_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INTEGRATION_INCOMPLETE")
    if envelope.get("complete") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETENESS_REPORT_INCOMPLETE")
    if envelope.get("missing_obligations") != []:
        raise Rejected("AUTHORITY_EVIDENCE_OBLIGATIONS_INCOMPLETE")
    return envelope


def integrate_authoritative_evidence_with_completeness_report_audit_trail(
    report: dict[str, Any],
) -> dict[str, Any]:
    """Integrate completeness-report evidence with the audit-trail lifecycle exactly."""
    envelope = _validate_report(report)
    audit_trail = {
        "version": VERSION,
        "report_envelope": envelope,
        "completeness_report_integration_fingerprint": report["completeness_report_integration_fingerprint"],
        "report_id": envelope["report_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "evidence_kinds": list(EVIDENCE_KINDS),
        "integrated": True,
        "audit_trail_integrated": True,
        "complete": True,
        "missing_obligations": [],
        "obligations": list(REQUIRED_OBLIGATIONS),
        "audit_integrated": True,
        "orphan_check_integrated": True,
        "final_audit_integrated": True,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "audit_trail_integration_completed": True,
        "version": VERSION,
        "audit_trail": audit_trail,
        "audit_trail_integration_fingerprint": _sha(audit_trail),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_completeness_report_audit_trail_integration(
    audit_trail: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence completeness-report audit-trail integration."""
    if type(audit_trail) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_RESULT_REQUIRED")
    if audit_trail.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if audit_trail.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if audit_trail.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if audit_trail.get("audit_trail_integration_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_INCOMPLETE")
    envelope = audit_trail.get("audit_trail")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = audit_trail.get("audit_trail_integration_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_FINGERPRINT_MISMATCH")
    if envelope.get("integrated") is not True or envelope.get("audit_trail_integrated") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_AUDIT_TRAIL_INTEGRATION_INCOMPLETE")
    return {
        "audit_trail_integration_replayed": True,
        "version": VERSION,
        "audit_trail_envelope": envelope,
        "audit_trail_integration_fingerprint": fingerprint,
        "integrated": True,
        "audit_trail_integrated": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
