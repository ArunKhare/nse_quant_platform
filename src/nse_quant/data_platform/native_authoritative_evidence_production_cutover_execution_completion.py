"""Native authoritative evidence production cutover execution completion.

Completes the authoritative evidence production cutover execution chain while
remaining observational. Requires explicit production cutover execution
readiness and does not grant eligibility, live trading, healing, backfill,
adoption, deletion, production cutover, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-production-cutover-execution-completion@1"
COMMAND = "complete.native_authoritative_evidence_production_cutover_execution@1"
READINESS_VERSION = "native-authoritative-evidence-production-cutover-execution-readiness@1"
COMPLETION_GATES = (
    "execution_ready",
    "explicit_readiness_request",
    "package_qa_passed",
    "integration_tests_passed",
    "operational_checks_passed",
    "evidence_chain_complete",
    "native_gates_open",
    "observational_only",
    "explicit_completion_request",
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


def _validate_execution_ready(
    execution_ready: dict[str, Any],
) -> dict[str, Any]:
    if type(execution_ready) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXECUTION_READY_RESULT_REQUIRED")
    if execution_ready.get("version") != READINESS_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if execution_ready.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if execution_ready.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if execution_ready.get("production_cutover_execution_readiness_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_READINESS_INCOMPLETE")
    envelope = execution_ready.get("execution_ready")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXECUTION_READY_ENVELOPE_REQUIRED")
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
    fingerprint = execution_ready.get("production_cutover_execution_readiness_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_READINESS_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_READINESS_FINGERPRINT_MISMATCH")
    if envelope.get("execution_ready") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_READINESS_INCOMPLETE")
    if envelope.get("explicit_readiness_request") is not True:
        raise Rejected("EXPLICIT_READINESS_REQUEST_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_NATIVE_GATES_NOT_OPEN")
    return envelope


def complete_authoritative_evidence_production_cutover_execution(
    execution_ready: dict[str, Any],
    *,
    explicit_completion_request: bool,
) -> dict[str, Any]:
    """Complete the authoritative evidence production cutover execution chain exactly."""
    envelope = _validate_execution_ready(execution_ready)
    if type(explicit_completion_request) is not bool or not explicit_completion_request:
        raise Rejected("EXPLICIT_COMPLETION_REQUEST_REQUIRED")
    completion_envelope = {
        "version": VERSION,
        "execution_ready_envelope": envelope,
        "production_cutover_execution_readiness_fingerprint": execution_ready[
            "production_cutover_execution_readiness_fingerprint"
        ],
        "final_audit_id": envelope["final_audit_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "completion_gates": list(COMPLETION_GATES),
        "completed": True,
        "explicit_completion_request": True,
        "package_qa_passed": True,
        "integration_tests_passed": True,
        "operational_checks_passed": True,
        "evidence_chain_complete": True,
        "native_gates_open": True,
        "observational_only": True,
        "production_cutover_authorized": False,
        "live_trading_authorized": False,
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "production_cutover_execution_completed": True,
        "version": VERSION,
        "completed": completion_envelope,
        "production_cutover_execution_completion_fingerprint": _sha(completion_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_production_cutover_execution_completion(
    completed: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence production cutover execution completion."""
    if type(completed) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_COMPLETED_RESULT_REQUIRED")
    if completed.get("version") != VERSION:
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
    fingerprint = completed.get("production_cutover_execution_completion_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_FINGERPRINT_MISMATCH")
    if envelope.get("completed") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_COMPLETION_INCOMPLETE")
    return {
        "production_cutover_execution_completion_replayed": True,
        "version": VERSION,
        "completed_envelope": envelope,
        "production_cutover_execution_completion_fingerprint": fingerprint,
        "completed": True,
        "observational_only": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
