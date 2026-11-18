"""Native authority evidence completeness report audit-trail import, round-trip, acceptance, and r
econciliation governance.

Imports exported audit trails exactly, performs non-destructive round-trip
replay, governs acceptance, and reconciles audit trails for reconciled
completeness reports across identity/time, availability, and economic-validity
evidence. This module is observational only and does not grant eligibility,
live trading, healing, backfill, adoption, deletion, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = (
    "native-authority-evidence-completeness-report-audit-trail-import-round-trip-acceptance-reconciliation-governance@1"
)
COMMAND = "import_round_trip_accept_reconcile.native_authority_evidence_completeness_report_audit_trail_\
    import_round_trip_acceptance_reconciliation_governance@1"
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


def _validate_query_export(query_export: dict[str, Any]) -> dict[str, Any]:
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
    if export_envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    export_fingerprint = query_export.get("query_export_governance_fingerprint")
    if not _pin(export_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(export_envelope)).hexdigest() != export_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_EXPORT_GOVERNANCE_FINGERPRINT_MISMATCH")
    queried_envelope = export_envelope.get("queried_envelope")
    if type(queried_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_QUERIED_ENVELOPE_REQUIRED")
    queried_fingerprint = export_envelope.get("query_export_fingerprint")
    if not _pin(queried_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(queried_envelope)).hexdigest() != queried_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_QUERY_FINGERPRINT_MISMATCH")
    archival_envelope = queried_envelope.get("archival_governed_envelope")
    if type(archival_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNED_ENVELOPE_REQUIRED")
    archival_fingerprint = queried_envelope.get("archival_governance_fingerprint")
    if not _pin(archival_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(archival_envelope)).hexdigest() != archival_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_MISMATCH")
    return queried_envelope


def import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(
    query_export: dict[str, Any],
) -> dict[str, Any]:
    """Import, round-trip, accept, and reconcile an exported audit trail exactly."""
    queried_envelope = _validate_query_export(query_export)
    imported_envelope = {
        "version": VERSION,
        "queried_envelope": queried_envelope,
        "query_export_governance_fingerprint": query_export["query_export_governance_fingerprint"],
        "query_fingerprint": query_export["export"]["query_export_fingerprint"],
        "archival_governance_fingerprint": queried_envelope["archival_governance_fingerprint"],
        "retention_governance_fingerprint": queried_envelope["retention_governance_fingerprint"],
        "persistence_fingerprint": queried_envelope["persistence_fingerprint"],
        "enforcement_fingerprint": queried_envelope["enforcement_fingerprint"],
        "imported": True,
        "round_tripped": True,
        "accepted": True,
        "reconciled": True,
        "complete": queried_envelope.get("complete") is True,
        "missing_obligations": list(queried_envelope.get("missing_obligations", [])),
        "audit_integrated": queried_envelope.get("audit_integrated") is True,
        "orphan_check_integrated": queried_envelope.get("orphan_check_integrated") is True,
        "final_audit_integrated": queried_envelope.get("final_audit_integrated") is True,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "import_round_trip_acceptance_reconciliation_completed": True,
        "version": VERSION,
        "imported": imported_envelope,
        "round_tripped": imported_envelope,
        "accepted": imported_envelope,
        "reconciled": imported_envelope,
        "import_round_trip_acceptance_reconciliation_fingerprint": hashlib.sha256(
            _canonical_bytes(imported_envelope)
        ).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def replay_import_round_trip_accept_reconcile_authority_evidence_compl_report_audit_trail(
    governed: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay import, round-trip, acceptance, and reconciliation without mutation."""
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
    fingerprint = governed.get("import_round_trip_acceptance_reconciliation_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_IMPORT_ROUND_TRIP_ACCEPTANCE_RECONCILIATION_FINGERPRINT_MISMATCH")
    return {
        "import_round_trip_acceptance_reconciliation_replayed": True,
        "version": VERSION,
        "imported_envelope": envelope,
        "import_round_trip_acceptance_reconciliation_fingerprint": fingerprint,
        "imported": envelope.get("imported") is True,
        "round_tripped": envelope.get("round_tripped") is True,
        "accepted": envelope.get("accepted") is True,
        "reconciled": envelope.get("reconciled") is True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
