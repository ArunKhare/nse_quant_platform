"""Native authoritative evidence operational cutover authorization.

Records an observational operational cutover authorization for the complete
authoritative evidence chain. Requires explicit release readiness and cutover
readiness, and does not grant eligibility, live trading, healing, backfill,
adoption, deletion, production cutover, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-authoritative-evidence-operational-cutover-authorization@1"
COMMAND = "authorize.native_authoritative_evidence_operational_cutover@1"
CUTOVER_VERSION = "native-authoritative-evidence-production-cutover-readiness@1"
AUTHORIZATION_GATES = (
    "cutover_ready",
    "explicit_cutover_request",
    "package_qa_passed",
    "integration_tests_passed",
    "operational_checks_passed",
    "evidence_chain_complete",
    "native_gates_open",
    "observational_only",
    "explicit_operational_authorization",
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


def _validate_cutover_ready(cutover_ready: dict[str, Any]) -> dict[str, Any]:
    if type(cutover_ready) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_CUTOVER_READY_RESULT_REQUIRED")
    if cutover_ready.get("version") != CUTOVER_VERSION:
        raise Rejected("AUTHORITY_EVIDENCE_VERSION_MISMATCH")
    if cutover_ready.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if cutover_ready.get("decision_eligibility_asserted") is not False:
        raise Rejected("AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    if cutover_ready.get("production_cutover_readiness_completed") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_INCOMPLETE")
    envelope = cutover_ready.get("cutover_ready")
    if type(envelope) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_CUTOVER_READY_ENVELOPE_REQUIRED")
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
    fingerprint = cutover_ready.get("production_cutover_readiness_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_FINGERPRINT_MISMATCH")
    if envelope.get("cutover_ready") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_PRODUCTION_CUTOVER_READINESS_INCOMPLETE")
    if envelope.get("explicit_cutover_request") is not True:
        raise Rejected("EXPLICIT_CUTOVER_REQUEST_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_NATIVE_GATES_NOT_OPEN")
    return envelope


def authorize_authoritative_evidence_operational_cutover(
    cutover_ready: dict[str, Any],
    *,
    explicit_operational_authorization: bool,
) -> dict[str, Any]:
    """Record observational operational cutover authorization exactly."""
    envelope = _validate_cutover_ready(cutover_ready)
    if type(explicit_operational_authorization) is not bool or not explicit_operational_authorization:
        raise Rejected("EXPLICIT_OPERATIONAL_AUTHORIZATION_REQUIRED")
    authorization_envelope = {
        "version": VERSION,
        "cutover_ready_envelope": envelope,
        "production_cutover_readiness_fingerprint": cutover_ready["production_cutover_readiness_fingerprint"],
        "final_audit_id": envelope["final_audit_id"],
        "authority_id": envelope["authority_id"],
        "namespace": envelope["namespace"],
        "authorization_gates": list(AUTHORIZATION_GATES),
        "operationally_authorized": True,
        "explicit_operational_authorization": True,
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
        "operational_cutover_authorization_completed": True,
        "version": VERSION,
        "operationally_authorized": authorization_envelope,
        "operational_cutover_authorization_fingerprint": _sha(authorization_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_authoritative_evidence_operational_cutover_authorization(
    operationally_authorized: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay authoritative evidence operational cutover authorization."""
    if type(operationally_authorized) is not dict:
        raise Rejected("AUTHORITY_EVIDENCE_AUTHORIZED_RESULT_REQUIRED")
    if operationally_authorized.get("version") != VERSION:
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
    fingerprint = operationally_authorized.get("operational_cutover_authorization_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("AUTHORITY_EVIDENCE_OPERATIONAL_CUTOVER_AUTHORIZATION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("AUTHORITY_EVIDENCE_OPERATIONAL_CUTOVER_AUTHORIZATION_FINGERPRINT_MISMATCH")
    if envelope.get("operationally_authorized") is not True or envelope.get("observational_only") is not True:
        raise Rejected("AUTHORITY_EVIDENCE_OPERATIONAL_CUTOVER_AUTHORIZATION_INCOMPLETE")
    return {
        "operational_cutover_authorization_replayed": True,
        "version": VERSION,
        "authorized_envelope": envelope,
        "operational_cutover_authorization_fingerprint": fingerprint,
        "operationally_authorized": True,
        "observational_only": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
