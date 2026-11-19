"""Native P1 evidence-chain operational hardening.

Hardens the completed authoritative evidence chain for operational readiness by
adding immutable health, incident, recovery, and rollback observations without
granting eligibility, live trading, healing, backfill, adoption, deletion,
production cutover, or execution authority. POINT_IN_TIME_DECISION remains
rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-p1-evidence-chain-operational-hardening@1"
COMMAND = "harden.native_p1_evidence_chain_operational@1"
COMPLETION_VERSION = "native-authoritative-evidence-production-cutover-execution-completion@1"
HEALTH_STATES = ("healthy", "degraded", "unavailable")
INCIDENT_SEVERITIES = ("informational", "warning", "critical")
RECOVERY_OUTCOMES = ("observed", "retry_pending")
ROLLBACK_OUTCOMES = ("not_required", "requested", "completed")


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


def _nonempty(value: object, maximum: int = 256) -> bool:
    return type(value) is str and 0 < len(value) <= maximum


def _validate_completed(completed: dict[str, Any]) -> dict[str, Any]:
    if type(completed) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETED_RESULT_REQUIRED")
    if completed.get("version") != COMPLETION_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if completed.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if completed.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if completed.get("production_cutover_execution_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_INCOMPLETE")
    envelope = completed.get("completed")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETED_ENVELOPE_REQUIRED")
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
    fingerprint = completed.get("production_cutover_execution_completion_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_FINGERPRINT_MISMATCH")
    if envelope.get("completed") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_INCOMPLETE")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_NATIVE_GATES_NOT_OPEN")
    return envelope


def harden_p1_evidence_chain_operations(
    completed: dict[str, Any],
    *,
    health_state: str,
    incident_severity: str,
    recovery_outcome: str,
    rollback_outcome: str,
    observation_id: str,
) -> dict[str, Any]:
    """Record immutable P1 operational hardening observations exactly."""
    envelope = _validate_completed(completed)
    if health_state not in HEALTH_STATES:
        raise Rejected("P1_HEALTH_STATE_INVALID")
    if incident_severity not in INCIDENT_SEVERITIES:
        raise Rejected("P1_INCIDENT_SEVERITY_INVALID")
    if recovery_outcome not in RECOVERY_OUTCOMES:
        raise Rejected("P1_RECOVERY_OUTCOME_INVALID")
    if rollback_outcome not in ROLLBACK_OUTCOMES:
        raise Rejected("P1_ROLLBACK_OUTCOME_INVALID")
    if not _nonempty(observation_id):
        raise Rejected("P1_OBSERVATION_ID_REQUIRED")
    hardening_envelope = {
        "version": VERSION,
        "completed_envelope": envelope,
        "production_cutover_execution_completion_fingerprint": completed[
            "production_cutover_execution_completion_fingerprint"
        ],
        "observation_id": observation_id,
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "health_state": health_state,
        "incident_severity": incident_severity,
        "recovery_outcome": recovery_outcome,
        "rollback_outcome": rollback_outcome,
        "hardened": True,
        "health_observed": True,
        "incident_observed": True,
        "recovery_observed": True,
        "rollback_observed": True,
        "healed": False,
        "deleted": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "p1_operational_hardening_completed": True,
        "version": VERSION,
        "hardened": hardening_envelope,
        "p1_operational_hardening_fingerprint": _sha(hardening_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_p1_evidence_chain_operational_hardening(
    hardened: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay P1 evidence-chain operational hardening without mutation."""
    if type(hardened) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_HARDENED_RESULT_REQUIRED")
    if hardened.get("version") != VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if hardened.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if hardened.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if hardened.get("p1_operational_hardening_completed") is not True:
        raise Rejected("P1_OPERATIONAL_HARDENING_INCOMPLETE")
    envelope = hardened.get("hardened")
    if type(envelope) is not dict:
        raise Rejected("P1_OPERATIONAL_HARDENING_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("AUTHORITY_EVIDENCE_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("AUTHORITY_EVIDENCE_DELETION_FORBIDDEN")
    fingerprint = hardened.get("p1_operational_hardening_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("P1_OPERATIONAL_HARDENING_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("P1_OPERATIONAL_HARDENING_FINGERPRINT_MISMATCH")
    if envelope.get("hardened") is not True or envelope.get("health_observed") is not True:
        raise Rejected("P1_OPERATIONAL_HARDENING_INCOMPLETE")
    return {
        "p1_operational_hardening_replayed": True,
        "version": VERSION,
        "hardened_envelope": envelope,
        "p1_operational_hardening_fingerprint": fingerprint,
        "hardened": True,
        "health_observed": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
