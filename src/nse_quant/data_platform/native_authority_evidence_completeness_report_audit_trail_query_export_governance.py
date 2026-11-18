"""Native authority evidence completeness report audit-trail query and export governance.

Provides governed, non-destructive query and export for archived or closed
audit trails for reconciled completeness reports across identity/time,
availability, and economic-validity evidence. This module is observational only
and does not grant eligibility, live trading, healing, backfill, adoption,
deletion, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-query-export-governance@1"
COMMAND = "query_export.native_authority_evidence_completeness_report_audit_trail_query_export_governance@1"
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
    "archived",
    "closed",
    "queried",
    "exported",
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


def _validate_archival(archival: dict[str, Any]) -> dict[str, Any]:
    if type(archival) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_RESULT_REQUIRED")
    if archival.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if archival.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if archival.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if archival.get("archival_governance_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_INCOMPLETE")
    envelope = archival.get("archival_governed")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    archival_fingerprint = archival.get("archival_governance_fingerprint")
    if not _pin(archival_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != archival_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_MISMATCH")
    governed_envelope = envelope.get("governed_envelope")
    if type(governed_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_GOVERNED_ENVELOPE_REQUIRED")
    retention_fingerprint = envelope.get("retention_governance_fingerprint")
    if not _pin(retention_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(governed_envelope)).hexdigest() != retention_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_MISMATCH")
    persisted_envelope = governed_envelope.get("persisted_envelope")
    if type(persisted_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTED_ENVELOPE_REQUIRED")
    persistence_fingerprint = envelope.get("persistence_fingerprint")
    if not _pin(persistence_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(persisted_envelope)).hexdigest() != persistence_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_MISMATCH")
    enforcement_fingerprint = envelope.get("enforcement_fingerprint")
    if not _pin(enforcement_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_INVALID")
    enforced_envelope = persisted_envelope.get("enforced_envelope")
    if type(enforced_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCED_ENVELOPE_REQUIRED")
    if hashlib.sha256(_canonical_bytes(enforced_envelope)).hexdigest() != enforcement_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_MISMATCH")
    return envelope


def query_export_authority_evidence_completeness_report_audit_trail(
    archival: dict[str, Any],
) -> dict[str, Any]:
    """Perform governed, non-destructive query and export of an archived audit trail."""
    envelope = _validate_archival(archival)
    queried_envelope = {
        "version": VERSION,
        "archival_governed_envelope": envelope,
        "archival_governance_fingerprint": archival["archival_governance_fingerprint"],
        "retention_governance_fingerprint": envelope["retention_governance_fingerprint"],
        "persistence_fingerprint": envelope["persistence_fingerprint"],
        "enforcement_fingerprint": envelope["enforcement_fingerprint"],
        "archived": envelope.get("archived") is True,
        "closed": envelope.get("closed") is True,
        "closure_status": envelope.get("closure_status"),
        "complete": envelope.get("complete") is True,
        "missing_obligations": list(envelope.get("missing_obligations", [])),
        "audit_integrated": envelope.get("audit_integrated") is True,
        "orphan_check_integrated": envelope.get("orphan_check_integrated") is True,
        "final_audit_integrated": envelope.get("final_audit_integrated") is True,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "queried": True,
        "exported": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    export_envelope = {
        "version": VERSION,
        "queried_envelope": queried_envelope,
        "query_export_fingerprint": hashlib.sha256(_canonical_bytes(queried_envelope)).hexdigest(),
        "export_format": "native_authority_evidence_audit_trail_query_export@1",
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "query_export_completed": True,
        "version": VERSION,
        "queried": queried_envelope,
        "export": export_envelope,
        "query_export_governance_fingerprint": hashlib.sha256(_canonical_bytes(export_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def replay_query_export_authority_evidence_completeness_report_audit_trail(
    query_export: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay a governed query and export result without mutation."""
    if type(query_export) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_RESULT_REQUIRED")
    if query_export.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if query_export.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if query_export.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if query_export.get("query_export_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_INCOMPLETE")
    export_envelope = query_export.get("export")
    if type(export_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXPORT_ENVELOPE_REQUIRED")
    if export_envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if export_envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = query_export.get("query_export_governance_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(export_envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_MISMATCH")
    queried_envelope = export_envelope.get("queried_envelope")
    if type(queried_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_QUERIED_ENVELOPE_REQUIRED")
    queried_fingerprint = export_envelope.get("query_export_fingerprint")
    if not _pin(queried_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(queried_envelope)).hexdigest() != queried_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_FINGERPRINT_MISMATCH")
    return {
        "query_export_replayed": True,
        "version": VERSION,
        "queried_envelope": queried_envelope,
        "export_envelope": export_envelope,
        "query_export_governance_fingerprint": fingerprint,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
