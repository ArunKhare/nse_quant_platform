"""Native authority evidence completeness report audit-trail retention and expiry governance.

Governs non-destructive retention and expiry status for persisted audit trails
for reconciled completeness reports across identity/time, availability, and
economic-validity evidence. This module is observational only and does not grant
eligibility, live trading, healing, backfill, adoption, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authority-evidence-completeness-report-audit-trail-retention-expiry-governance@1"
COMMAND = "govern_retention.native_authority_evidence_completeness_report_audit_trail_retention_expiry_governance@1"
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


def _iso(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _validate_persisted(persisted: dict[str, Any]) -> dict[str, Any]:
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
    persistence_fingerprint = persisted.get("persistence_fingerprint")
    if not _pin(persistence_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != persistence_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PERSISTENCE_FINGERPRINT_MISMATCH")
    if envelope.get("lifecycle_stages") != list(LIFECYCLE_STAGES):
        raise Rejected("AUTHORITY_EVIDENCE_LIFECYCLE_MISMATCH")
    enforcement_fingerprint = envelope.get("enforcement_fingerprint")
    if not _pin(enforcement_fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_INVALID")
    enforced_envelope = envelope.get("enforced_envelope")
    if type(enforced_envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCED_ENVELOPE_REQUIRED")
    if hashlib.sha256(_canonical_bytes(enforced_envelope)).hexdigest() != enforcement_fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_ENFORCEMENT_FINGERPRINT_MISMATCH")
    return envelope


def govern_retention_authority_evidence_completeness_report_audit_trail(
    persisted: dict[str, Any],
    *,
    as_of: str,
    retention_days: int,
) -> dict[str, Any]:
    """Govern non-destructive retention and expiry status for a persisted audit trail."""
    envelope = _validate_persisted(persisted)
    if not _iso(as_of):
        raise Rejected("EXACT_AS_OF_REQUIRED")
    if type(retention_days) is not int or retention_days < 1:
        raise Rejected("EXACT_RETENTION_DAYS_REQUIRED")
    persisted_at = envelope.get("persisted_at")
    if not _iso(persisted_at):
        raise Rejected("PERSISTED_AT_REQUIRED")
    as_of_time = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if persisted_at is None:
        raise Rejected("PERSISTED_AT_REQUIRED")
    persisted_time = datetime.fromisoformat(persisted_at.replace("Z", "+00:00"))
    if as_of_time < persisted_time:
        raise Rejected("RETENTION_AS_OF_BEFORE_PERSISTED_AT")
    expiry_due = persisted_time.timestamp() + retention_days * 86400
    expired = as_of_time.timestamp() >= expiry_due
    governed_envelope = {
        "version": VERSION,
        "persisted_envelope": envelope,
        "persistence_fingerprint": persisted["persistence_fingerprint"],
        "enforcement_fingerprint": envelope["enforcement_fingerprint"],
        "as_of": as_of,
        "persisted_at": persisted_at,
        "retention_days": retention_days,
        "expiry_due": datetime.fromtimestamp(expiry_due, as_of_time.tzinfo).isoformat(),
        "expired": expired,
        "retention_action": "EXPIRY_OBSERVED" if expired else "RETAIN",
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
        "retention_governance_completed": True,
        "version": VERSION,
        "governed": governed_envelope,
        "retention_governance_fingerprint": hashlib.sha256(_canonical_bytes(governed_envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def replay_retention_authority_evidence_completeness_report_audit_trail(
    governed: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay governed retention and expiry status without mutation."""
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
    fingerprint = governed.get("retention_governance_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_INVALID")
    if hashlib.sha256(_canonical_bytes(envelope)).hexdigest() != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_RETENTION_GOVERNANCE_FINGERPRINT_MISMATCH")
    return {
        "retention_replayed": True,
        "version": VERSION,
        "governed_envelope": envelope,
        "retention_governance_fingerprint": fingerprint,
        "expired": envelope.get("expired") is True,
        "retention_action": envelope.get("retention_action"),
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
