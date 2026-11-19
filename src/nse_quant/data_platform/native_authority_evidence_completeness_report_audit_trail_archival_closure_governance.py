"""Native authority evidence completeness report audit-trail archival and closure governance.

Governs non-destructive archival and closure status for retained audit trails
for reconciled completeness reports across identity/time, availability, and
economic-validity evidence. This module is observational only and does not grant
eligibility, live trading, healing, backfill, adoption, deletion, or execution
authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-archival-closure-governance@1"
COMMAND = "govern_archival.native_authority_evidence_completeness_report_audit_trail_archival_closure_governance@1"
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


def _iso(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _validate_governed(governed: dict[str, Any]) -> dict[str, Any]:
    if type(governed) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_GOVERNED_RESULT_REQUIRED")
    if governed.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if governed.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if governed.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if governed.get("retention_governance_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_INCOMPLETE")
    envelope = governed.get("governed")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_GOVERNED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    if envelope.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    fingerprint = governed.get("retention_governance_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_MISMATCH")
    persisted_envelope = envelope.get("persisted_envelope")
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


def govern_archival_authority_evidence_completeness_report_audit_trail(
    governed: dict[str, Any],
    *,
    as_of: str,
) -> dict[str, Any]:
    """Govern non-destructive archival and closure status for a retained audit trail."""
    envelope = _validate_governed(governed)
    if not _iso(as_of):
        raise Rejected("EXACT_AS_OF_REQUIRED")
    retention_as_of = envelope.get("as_of")
    if not _iso(retention_as_of):
        raise Rejected("RETENTION_AS_OF_REQUIRED")
    if retention_as_of is None:
        raise Rejected("RETENTION_AS_OF_REQUIRED")
    if datetime.fromisoformat(as_of.replace("Z", "+00:00")) < datetime.fromisoformat(
        retention_as_of.replace("Z", "+00:00")
    ):
        raise Rejected("ARCHIVAL_AS_OF_BEFORE_RETENTION_AS_OF")
    archived = True
    closed = envelope.get("expired") is True
    archival_envelope = {
        "version": VERSION,
        "governed_envelope": envelope,
        "retention_governance_fingerprint": governed["retention_governance_fingerprint"],
        "persistence_fingerprint": envelope["persistence_fingerprint"],
        "enforcement_fingerprint": envelope["enforcement_fingerprint"],
        "as_of": as_of,
        "retention_as_of": retention_as_of,
        "archived": archived,
        "closed": closed,
        "closure_status": "CLOSED" if closed else "ARCHIVED",
        "deleted": False,
        "complete": envelope.get("complete") is True,
        "missing_obligations": list(envelope.get("missing_obligations", [])),
        "audit_integrated": envelope.get("audit_integrated") is True,
        "orphan_check_integrated": envelope.get("orphan_check_integrated") is True,
        "final_audit_integrated": envelope.get("final_audit_integrated") is True,
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "archival_governance_completed": True,
        "version": VERSION,
        "archival_governed": archival_envelope,
        "archival_governance_fingerprint": hashlib.sha256(_canonical_bytes(archival_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def replay_archival_authority_evidence_completeness_report_audit_trail(
    archival_governed: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay governed archival and closure status without mutation."""
    if type(archival_governed) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNED_RESULT_REQUIRED")
    if archival_governed.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if archival_governed.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if archival_governed.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if archival_governed.get("archival_governance_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_INCOMPLETE")
    envelope = archival_governed.get("archival_governed")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNED_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = archival_governed.get("archival_governance_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ARCHIVAL_GOVERNANCE_FINGERPRINT_MISMATCH")
    return {
        "archival_replayed": True,
        "version": VERSION,
        "archival_governed_envelope": envelope,
        "archival_governance_fingerprint": fingerprint,
        "archived": envelope.get("archived") is True,
        "closed": envelope.get("closed") is True,
        "closure_status": envelope.get("closure_status"),
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
