"""Native authority evidence completeness report audit-trail end-to-end lifecycle acceptance.

Performs governed, non-destructive end-to-end lifecycle acceptance for audit
trails across identity/time, availability, and economic-validity evidence. This
module is observational only and does not grant eligibility, live trading,
healing, backfill, adoption, deletion, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-end-to-end-lifecycle-acceptance@1"
COMMAND = "accept.native_authority_evidence_completeness_report_audit_trail_end_to_end_lifecycle_acceptance@1"
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
    "imported",
    "round_tripped",
    "accepted",
    "end_to_end_accepted",
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


def _validate_governed(governed: dict[str, Any]) -> dict[str, Any]:
    if type(governed) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_GOVERNED_RESULT_REQUIRED")
    if governed.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if governed.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if governed.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if governed.get("import_round_trip_acceptance_reconciliation_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_INCOMPLETE")
    envelope = governed.get("imported")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_IMPORTED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = governed.get("import_round_trip_acceptance_reconciliation_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_FINGERPRINT_MISMATCH")
    queried_envelope = envelope.get("queried_envelope")
    if type(queried_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_QUERIED_ENVELOPE_REQUIRED")
    query_export_fingerprint = envelope.get("query_export_governance_fingerprint")
    if not _pin(query_export_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_INVALID")
    export_envelope = {
        "version": "native-authority-evidence-completeness-report-audit-trail-query-export-governance@1",
        "queried_envelope": queried_envelope,
        "query_export_fingerprint": envelope.get("query_fingerprint"),
        "export_format": "native_authority_evidence_audit_trail_query_export@1",
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    if hashlib.sha256(_canonical_bytes(export_envelope)).hexdigest() != query_export_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_MISMATCH")
    archival_envelope = queried_envelope.get("archival_governed_envelope")
    if type(archival_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNED_ENVELOPE_REQUIRED")
    archival_fingerprint = queried_envelope.get("archival_governance_fingerprint")
    if not _pin(archival_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(archival_envelope)).hexdigest() != archival_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_MISMATCH")
    return envelope


def accept_end_to_end_authority_evidence_completeness_report_audit_trail(
    governed: dict[str, Any],
) -> dict[str, Any]:
    """Perform governed, non-destructive end-to-end lifecycle acceptance exactly."""
    envelope = _validate_governed(governed)
    accepted_envelope = {
        "version": VERSION,
        "imported_envelope": envelope,
        "import_round_trip_acceptance_reconciliation_fingerprint": governed[
            "import_round_trip_acceptance_reconciliation_fingerprint"
        ],
        "query_export_governance_fingerprint": envelope["query_export_governance_fingerprint"],
        "query_fingerprint": envelope["query_fingerprint"],
        "archival_governance_fingerprint": envelope["archival_governance_fingerprint"],
        "retention_governance_fingerprint": envelope["retention_governance_fingerprint"],
        "persistence_fingerprint": envelope["persistence_fingerprint"],
        "enforcement_fingerprint": envelope["enforcement_fingerprint"],
        "end_to_end_accepted": True,
        "complete": envelope.get("complete") is True,
        "missing_obligations": list(envelope.get("missing_obligations", [])),
        "audit_integrated": envelope.get("audit_integrated") is True,
        "orphan_check_integrated": envelope.get("orphan_check_integrated") is True,
        "final_audit_integrated": envelope.get("final_audit_integrated") is True,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "end_to_end_lifecycle_acceptance_completed": True,
        "version": VERSION,
        "end_to_end_accepted": accepted_envelope,
        "end_to_end_lifecycle_acceptance_fingerprint": hashlib.sha256(_canonical_bytes(accepted_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def replay_end_to_end_authority_evidence_completeness_report_audit_trail(
    accepted: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay end-to-end lifecycle acceptance without mutation."""
    if type(accepted) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTED_RESULT_REQUIRED")
    if accepted.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if accepted.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if accepted.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if accepted.get("end_to_end_lifecycle_acceptance_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_END_TO_END_LIFECYCLE_ACCEPTANCE_INCOMPLETE")
    envelope = accepted.get("end_to_end_accepted")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ACCEPTED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = accepted.get("end_to_end_lifecycle_acceptance_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_END_TO_END_LIFECYCLE_ACCEPTANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_END_TO_END_LIFECYCLE_ACCEPTANCE_FINGERPRINT_MISMATCH")
    return {
        "end_to_end_lifecycle_acceptance_replayed": True,
        "version": VERSION,
        "end_to_end_accepted_envelope": envelope,
        "end_to_end_lifecycle_acceptance_fingerprint": fingerprint,
        "end_to_end_accepted": envelope.get("end_to_end_accepted") is True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
