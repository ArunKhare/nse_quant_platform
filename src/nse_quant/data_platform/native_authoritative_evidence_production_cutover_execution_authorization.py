"""Native authoritative evidence production cutover execution authorization.

Records an observational production cutover execution authorization for the
complete authoritative evidence chain. Requires explicit operational cutover
authorization and does not grant eligibility, live trading, healing, backfill,
adoption, deletion, production cutover, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-production-cutover-execution-authorization@1"
COMMAND = "authorize.native_authoritative_evidence_production_cutover_execution@1"
OPERATIONAL_VERSION = "native-authoritative-evidence-operational-cutover-authorization@1"
EXECUTION_GATES = (
    "operationally_authorized",
    "explicit_operational_authorization",
    "package_qa_passed",
    "integration_tests_passed",
    "operational_checks_passed",
    "evidence_chain_complete",
    "native_gates_open",
    "observational_only",
    "explicit_execution_authorization",
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


def _validate_operationally_authorized(
    operationally_authorized: dict[str, Any],
) -> dict[str, Any]:
    if type(operationally_authorized) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUTHORIZED_RESULT_REQUIRED")
    if operationally_authorized.get("version") != OPERATIONAL_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if operationally_authorized.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if operationally_authorized.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if operationally_authorized.get("operational_cutover_authorization_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_OPERATIONAL_CUTOVER_AUTHORIZATION_INCOMPLETE")
    envelope = operationally_authorized.get("operationally_authorized")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUTHORIZED_ENVELOPE_REQUIRED")
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
    fingerprint = operationally_authorized.get("operational_cutover_authorization_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_OPERATIONAL_CUTOVER_AUTHORIZATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_OPERATIONAL_CUTOVER_AUTHORIZATION_FINGERPRINT_MISMATCH")
    if envelope.get("operationally_authorized") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_OPERATIONAL_CUTOVER_AUTHORIZATION_INCOMPLETE")
    if envelope.get("explicit_operational_authorization") is not True:
        raise Rejected("EXPLICIT_OPERATIONAL_AUTHORIZATION_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_NATIVE_GATES_NOT_OPEN")
    return envelope


def authorize_authoritative_evidence_production_cutover_execution(
    operationally_authorized: dict[str, Any],
    *,
    explicit_execution_authorization: bool,
) -> dict[str, Any]:
    """Record observational production cutover execution authorization exactly."""
    envelope = _validate_operationally_authorized(operationally_authorized)
    if type(explicit_execution_authorization) is not bool or not explicit_execution_authorization:
        raise Rejected("EXPLICIT_EXECUTION_AUTHORIZATION_REQUIRED")
    execution_envelope = {
        "version": VERSION,
        "authorized_envelope": envelope,
        "operational_cutover_authorization_fingerprint": operationally_authorized[
            "operational_cutover_authorization_fingerprint"
        ],
        "final_audit_id": envelope["final_audit_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "execution_gates": list(EXECUTION_GATES),
        "execution_authorized": True,
        "explicit_execution_authorization": True,
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
        "production_cutover_execution_authorization_completed": True,
        "version": VERSION,
        "execution_authorized": execution_envelope,
        "production_cutover_execution_authorization_fingerprint": _sha(execution_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_production_cutover_execution_authorization(
    execution_authorized: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence production cutover execution authorization."""
    if type(execution_authorized) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_EXECUTION_AUTHORIZED_RESULT_REQUIRED")
    if execution_authorized.get("version") != VERSION:
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
    fingerprint = execution_authorized.get("production_cutover_execution_authorization_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_AUTHORIZATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_AUTHORIZATION_FINGERPRINT_MISMATCH")
    if envelope.get("execution_authorized") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_EXECUTION_AUTHORIZATION_INCOMPLETE")
    return {
        "production_cutover_execution_authorization_replayed": True,
        "version": VERSION,
        "execution_authorized_envelope": envelope,
        "production_cutover_execution_authorization_fingerprint": fingerprint,
        "execution_authorized": True,
        "observational_only": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
