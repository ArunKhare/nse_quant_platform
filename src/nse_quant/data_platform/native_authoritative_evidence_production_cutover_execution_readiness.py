"""Native authoritative evidence production cutover execution readiness.

Verifies that the complete authoritative evidence chain is production cutover
execution ready while remaining observational. Requires explicit production
cutover execution authorization and does not grant eligibility, live trading,
healing, backfill, adoption, deletion, production cutover, or execution
authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-production-cutover-execution-readiness@1"
COMMAND = "verify.native_authoritative_evidence_production_cutover_execution_readiness@1"
EXECUTION_VERSION = "native-authoritative-evidence-production-cutover-execution-authorization@1"
READINESS_GATES = (
    "execution_authorized",
    "explicit_execution_authorization",
    "package_qa_passed",
    "integration_tests_passed",
    "operational_checks_passed",
    "evidence_chain_complete",
    "native_gates_open",
    "observational_only",
    "explicit_readiness_request",
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


def _validate_execution_authorized(
    execution_authorized: dict[str, Any],
) -> dict[str, Any]:
    if type(execution_authorized) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXECUTION_AUTHORIZED_RESULT_REQUIRED")
    if execution_authorized.get("version") != EXECUTION_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if execution_authorized.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if execution_authorized.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if execution_authorized.get("production_cutover_execution_authorization_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_AUTHORIZATION_INCOMPLETE")
    envelope = execution_authorized.get("execution_authorized")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXECUTION_AUTHORIZED_ENVELOPE_REQUIRED")
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
    fingerprint = execution_authorized.get("production_cutover_execution_authorization_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_AUTHORIZATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_AUTHORIZATION_FINGERPRINT_MISMATCH")
    if envelope.get("execution_authorized") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_AUTHORIZATION_INCOMPLETE")
    if envelope.get("explicit_execution_authorization") is not True:
        raise Rejected("EXPLICIT_EXECUTION_AUTHORIZATION_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_NATIVE_GATES_NOT_OPEN")
    return envelope


def verify_authoritative_evidence_production_cutover_execution_readiness(
    execution_authorized: dict[str, Any],
    *,
    explicit_readiness_request: bool,
) -> dict[str, Any]:
    """Verify production cutover execution readiness for the evidence chain exactly."""
    envelope = _validate_execution_authorized(execution_authorized)
    if type(explicit_readiness_request) is not bool or not explicit_readiness_request:
        raise Rejected("EXPLICIT_READINESS_REQUEST_REQUIRED")
    readiness_envelope = {
        "version": VERSION,
        "execution_authorized_envelope": envelope,
        "production_cutover_execution_authorization_fingerprint": execution_authorized[
            "production_cutover_execution_authorization_fingerprint"
        ],
        "final_audit_id": envelope["final_audit_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "readiness_gates": list(READINESS_GATES),
        "execution_ready": True,
        "explicit_readiness_request": True,
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
        "production_cutover_execution_readiness_completed": True,
        "version": VERSION,
        "execution_ready": readiness_envelope,
        "production_cutover_execution_readiness_fingerprint": _sha(readiness_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_production_cutover_execution_readiness(
    execution_ready: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence production cutover execution readiness."""
    if type(execution_ready) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXECUTION_READY_RESULT_REQUIRED")
    if execution_ready.get("version") != VERSION:
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
    fingerprint = execution_ready.get("production_cutover_execution_readiness_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_READINESS_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_READINESS_FINGERPRINT_MISMATCH")
    if envelope.get("execution_ready") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_READINESS_INCOMPLETE")
    return {
        "production_cutover_execution_readiness_replayed": True,
        "version": VERSION,
        "execution_ready_envelope": envelope,
        "production_cutover_execution_readiness_fingerprint": fingerprint,
        "execution_ready": True,
        "observational_only": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
